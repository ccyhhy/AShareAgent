import os

from langchain_core.messages import HumanMessage
from src.agents.state import (
    AgentState,
    _ensure_agent_outputs,
    maybe_return_ablation_stub,
    show_agent_reasoning,
    show_workflow_status,
)
from src.tools.news_crawler import get_stock_news
from src.utils.logging_config import setup_logger
from src.utils.api_utils import agent_endpoint, log_llm_interaction
import json
from datetime import datetime, timedelta
from src.tools.openrouter_config import get_chat_completion
from src.database.data_service import get_data_service

# 设置日志记录
logger = setup_logger('macro_analyst_agent')




def _resolve_reference_datetime(end_date) -> datetime:
    text = str(end_date or "").strip()
    if text:
        candidate = text[:19]
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(candidate, fmt)
                if fmt == "%Y-%m-%d":
                    return parsed.replace(hour=23, minute=59, second=59)
                return parsed
            except ValueError:
                continue
    return datetime.now()


_VALID_MACRO_LABELS = {"positive", "neutral", "negative"}
_VALID_SIGNALS = {"bullish", "neutral", "bearish"}


def _normalize_macro_label(value: str | None, default: str = "neutral") -> str:
    text = str(value or "").strip().lower()
    return text if text in _VALID_MACRO_LABELS else default


def _normalize_confidence(value, fallback: str = "60%") -> str:
    if isinstance(value, (int, float)):
        score = float(value)
        if 0 <= score <= 1:
            score *= 100
        score = max(0.0, min(score, 100.0))
        return f"{round(score)}%"

    if isinstance(value, str):
        text = value.strip()
        if text.endswith("%"):
            try:
                score = float(text[:-1].strip())
            except ValueError:
                return fallback
            score = max(0.0, min(score, 100.0))
            return f"{round(score)}%"
        try:
            score = float(text)
        except ValueError:
            return fallback
        if 0 <= score <= 1:
            score *= 100
        score = max(0.0, min(score, 100.0))
        return f"{round(score)}%"

    return fallback


def _default_confidence_for_macro(impact_on_stock: str, key_factors: list[str]) -> str:
    score = 55
    if impact_on_stock in {"positive", "negative"}:
        score += 10
    if len(key_factors) >= 3:
        score += 10
    return f"{min(score, 90)}%"


def _normalize_macro_message(payload) -> dict:
    source = payload if isinstance(payload, dict) else {}
    macro_environment = _normalize_macro_label(source.get("macro_environment"))
    impact_on_stock = _normalize_macro_label(source.get("impact_on_stock"))

    raw_factors = source.get("key_factors")
    if isinstance(raw_factors, list):
        key_factors = [str(item).strip() for item in raw_factors if str(item).strip()]
    else:
        key_factors = []

    reasoning = source.get("reasoning")
    if not isinstance(reasoning, str) or not reasoning.strip():
        reasoning = "模型输出缺失或无效，已使用宏观分析回退结果。"

    derived_signal = {
        "positive": "bullish",
        "negative": "bearish",
        "neutral": "neutral",
    }[impact_on_stock]
    signal = str(source.get("signal", "")).strip().lower()
    if signal not in _VALID_SIGNALS:
        signal = derived_signal

    default_confidence = _default_confidence_for_macro(impact_on_stock, key_factors)
    confidence = _normalize_confidence(source.get("confidence"), default_confidence)

    normalized = dict(source)
    normalized.update(
        {
            "agent_type": str(source.get("agent_type") or "llm"),
            "macro_environment": macro_environment,
            "impact_on_stock": impact_on_stock,
            "key_factors": key_factors,
            "reasoning": reasoning,
            "signal": signal,
            "confidence": confidence,
            "analysis_domain": str(source.get("analysis_domain") or "macro_cycle_policy"),
        }
    )
    return normalized


@agent_endpoint("macro_analyst", "Macro analyst for stock-level macroeconomic impact")
def macro_analyst_agent(state: AgentState):
    """Responsible for macro analysis"""
    show_workflow_status("Macro Analyst")
    show_reasoning = state["metadata"]["show_reasoning"]
    data = state["data"]

    ablation_result = maybe_return_ablation_stub(
        state,
        agent_key="macro_analyst",
        agent_type="llm",
        message_name="macro_analyst_agent",
        output_key="macro_analyst",
        data_key="macro_analysis",
        payload_overrides={
            "analysis_domain": "macro_cycle_policy",
            "macro_environment": "neutral",
            "impact_on_stock": "neutral",
            "key_factors": [],
        },
    )
    if ablation_result is not None:
        return ablation_result

    symbol = data["ticker"]
    logger.info(f"正在进行宏观分析: {symbol}")

    # --- Backtest-safe guard: skip all remote calls in backtest mode ---
    _backtest_mode = os.getenv("ASHAREAGENT_BACKTEST_MODE", "").strip().lower() in {
        "1", "true", "yes", "on",
    }
    if _backtest_mode:
        logger.info("Backtest mode enabled: returning deterministic macro fallback")
        message_content = _normalize_macro_message({
            "macro_environment": "neutral",
            "impact_on_stock": "neutral",
            "key_factors": ["回测模式：跳过远程新闻抓取与LLM调用"],
            "reasoning": "当前为回测模式，已跳过远程新闻抓取与LLM调用以保证可复现性。",
            "signal": "neutral",
            "confidence": "50%",
        })
        message = HumanMessage(
            content=json.dumps(message_content, ensure_ascii=False),
            name="macro_analyst_agent",
        )
        if show_reasoning:
            show_agent_reasoning(message_content, "Macro Analysis Agent")
        updated_data = dict(data)
        agent_outputs = _ensure_agent_outputs(updated_data)
        agent_outputs["macro_analyst"] = message_content
        state["metadata"]["agent_reasoning"] = message_content
        show_workflow_status("Macro Analyst", "completed")
        return {
            "messages": [message],
            "data": {**updated_data, "macro_analysis": message_content},
            "metadata": state["metadata"],
        }

    # 获取 end_date 并传递给 get_stock_news
    end_date = data.get("end_date")  # 浠?run_hedge_fund 浼犻€掓潵鐨?end_date

    # 获取大量新闻数据（最大100条），传递正确的日期参数
    news_list = get_stock_news(symbol, max_news=100, date=end_date)

    # 过滤七天前的新闻和失败的搜索结果
    reference_datetime = _resolve_reference_datetime(end_date)
    cutoff_date = reference_datetime - timedelta(days=7)
    recent_news = []
    for news in news_list:
        # 过滤掉搜索失败的新闻
        if news.get('title') == '搜索失败' or '搜索失败' in news.get('title', ''):
            logger.warning(f"过滤掉搜索失败的新闻: {news.get('title', '')}")
            continue
            
        # Filter out obviously invalid news items.
        if news.get('content') and '无法完成搜索，错误信息' in news.get('content', ''):
            logger.warning(f"Filtered invalid news item: {news.get('title', '')}")
            continue
            
        if 'publish_time' in news:
            try:
                news_date = datetime.strptime(
                    news['publish_time'], '%Y-%m-%d %H:%M:%S')
                if news_date > cutoff_date:
                    recent_news.append(news)
            except ValueError:
                # 如果时间格式无法解析，默认包含这条新闻
                recent_news.append(news)
        else:
            # 如果没有publish_time字段，默认包含这条新闻
            recent_news.append(news)

    logger.info("Retrieved %s news items within the seven-day window", len(recent_news))

    # 如果没有获取到新闻，尝试强制刷新获取新的新闻数据
    if not recent_news:
        logger.warning(f"未获取到 {symbol} 的最近有效新闻，尝试强制刷新...")
        
        # 尝试直接使用akshare获取新闻，跳过缓存
        try:
            import akshare as ak
            fresh_news_df = ak.stock_news_em(symbol=symbol)
            if fresh_news_df is not None:
                if not fresh_news_df.empty:
                    fresh_news_list = []
                    for _, row in fresh_news_df.head(10).iterrows():
                        try:
                            content = row.get("新闻内容", "") or row.get("新闻标题", "")
                            if len(content.strip()) > 10:
                                fresh_news_item = {
                                    "title": row.get("新闻标题", "").strip(),
                                    "content": content.strip(),
                                    "publish_time": str(row.get("发布时间", "")),
                                    "source": row.get("文章来源", "").strip(),
                                    "url": row.get("新闻链接", "").strip(),
                                    "keyword": symbol
                                }
                                fresh_news_list.append(fresh_news_item)
                        except Exception:
                            continue
                    
                    if fresh_news_list:
                        logger.info(
                            "Refreshed %s news items directly via akshare",
                            len(fresh_news_list),
                        )
                        recent_news = fresh_news_list
        except Exception as e:
            logger.error(f"强制刷新新闻失败: {e}")
    
    # 如果仍然没有获取到新闻，返回默认结果
    if not recent_news:
        logger.warning(f"最终未获取到 {symbol} 的最近新闻，无法进行宏观分析")
        message_content = {
            "macro_environment": "neutral",
            "impact_on_stock": "neutral",
            "key_factors": [
                "未检索到有效新闻数据",
                "新闻检索链路可能出现异常",
                "请检查新闻数据源与缓存状态",
            ],
            "reasoning": (
                "近期未获取到有效新闻，可能由新闻检索失败或上游数据源异常导致。"
            ),
        }
    else:
        # 获取宏观分析结果
        macro_analysis = get_macro_news_analysis(recent_news)
        message_content = macro_analysis

    message_content = _normalize_macro_message(message_content)

    # 如果需要显示推理过程
    if show_reasoning:
        show_agent_reasoning(message_content, "Macro Analysis Agent")
    
    # 始终保存推理信息到metadata供API使用
    updated_data = dict(data)
    agent_outputs = _ensure_agent_outputs(updated_data)
    agent_outputs["macro_analyst"] = message_content
    state["metadata"]["agent_reasoning"] = message_content

    # 创建消息
    message = HumanMessage(
        content=json.dumps(message_content, ensure_ascii=False),
        name="macro_analyst_agent",
    )

    show_workflow_status("Macro Analyst", "completed")
    # logger.info(f"--- DEBUG: macro_analyst_agent COMPLETED ---")
    # logger.info(
    # f"--- DEBUG: macro_analyst_agent RETURN messages: {[msg.name for msg in (state['messages'] + [message])]} ---")
    return {
        "messages": [message],
        "data": {
            **updated_data,
            "macro_analysis": message_content
        },
        "metadata": state["metadata"],
    }


def get_macro_news_analysis(news_list: list) -> dict:
    """分析宏观经济新闻对股票的影响

    Args:
        news_list (list): 新闻列表

    Returns:
        dict: 宏观分析结果，包含环境评估、对股票的影响、关键因素和详细推理
    """
    if not news_list:
        return {
            "macro_environment": "neutral",
            "impact_on_stock": "neutral",
            "key_factors": [],
            "reasoning": "可用新闻样本不足，无法完成可靠的宏观分析。",
        }

    # 获取数据服务
    data_service = get_data_service()
    
    # 生成新闻内容的唯一标识
    news_key = "|".join([
        f"{news['title']}|{news.get('publish_time', '')}"
        for news in news_list[:20]  # 使用前20条新闻作为标识
    ])

    # 检查数据库缓存
    cached_analysis = data_service.get_macro_analysis_from_cache(news_key)
    if cached_analysis:
        logger.info("Using cached macro analysis from the database")
        return cached_analysis

    system_message = {
        "role": "system",
        "content": """你是专注A股上市公司的宏观分析师。
请基于给定新闻评估当前宏观环境及其对目标股票的潜在影响。

分析需覆盖：
1. 宏观环境判断：positive / neutral / negative
2. 对目标股票影响：positive / neutral / negative
3. 关键因素：列出3-5个最重要宏观因素
4. reasoning：用中文说明这些因素为何重要

要求内容客观、具体、可执行。""",
    }

    news_content = "\n\n".join(
        [
            f"Title: {news['title']}\n"
            f"Source: {news['source']}\n"
            f"Time: {news['publish_time']}\n"
            f"Content: {news['content']}"
            for news in news_list[:50]
        ]
    )

    user_message = {
        "role": "user",
        "content": (
            "请分析以下新闻，并返回JSON字段："
            "`macro_environment`、`impact_on_stock`、`key_factors`、`reasoning`。\n\n"
            f"{news_content}"
        ),
    }

    try:
        logger.info("Calling LLM for macro analysis")
        result = get_chat_completion([system_message, user_message])
        if result is None:
            logger.error("LLM analysis failed; no macro result returned")
            return {
                "macro_environment": "neutral",
                "impact_on_stock": "neutral",
                "key_factors": [],
                "reasoning": "LLM分析失败，未返回宏观分析结果。",
            }

        try:
            analysis_result = json.loads(result.strip())
            logger.info("Parsed macro analysis JSON directly")
        except json.JSONDecodeError:
            import re

            json_match = re.search(r"```json\s*(.*?)\s*```", result, re.DOTALL)
            if json_match:
                try:
                    analysis_result = json.loads(json_match.group(1).strip())
                    logger.info("Parsed macro analysis JSON from fenced code block")
                except Exception:
                    logger.error("Failed to parse JSON content from fenced code block")
                    return {
                        "macro_environment": "neutral",
                        "impact_on_stock": "neutral",
                        "key_factors": [],
                        "reasoning": "LLM返回内容解析失败，无法提取有效JSON。",
                    }
            else:
                logger.error("LLM did not return valid JSON content")
                return {
                    "macro_environment": "neutral",
                    "impact_on_stock": "neutral",
                    "key_factors": [],
                    "reasoning": "LLM未返回合法JSON内容。",
                }

        try:
            current_date = datetime.now().strftime("%Y-%m-%d")
            data_service.save_macro_analysis_to_cache(
                analysis_key=news_key,
                date=current_date,
                analysis_type="news",
                macro_environment=analysis_result.get("macro_environment"),
                impact_on_stock=analysis_result.get("impact_on_stock"),
                key_factors=analysis_result.get("key_factors", []),
                reasoning=analysis_result.get("reasoning"),
                content=json.dumps(analysis_result, ensure_ascii=False),
                news_count=len(news_list),
            )
            logger.info("Cached macro analysis result to the database")
        except Exception as cache_error:
            logger.warning("Failed to cache macro analysis result: %s", cache_error)

        return analysis_result

    except Exception as exc:
        logger.error("Macro analysis failed: %s", exc)
        return {
            "macro_environment": "neutral",
            "impact_on_stock": "neutral",
            "key_factors": [],
            "reasoning": f"宏观分析失败：{exc}",
        }


