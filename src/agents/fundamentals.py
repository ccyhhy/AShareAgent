from langchain_core.messages import HumanMessage
from src.utils.logging_config import setup_logger

from src.agents.state import (
    AgentState,
    maybe_return_ablation_stub,
    show_agent_reasoning,
    show_workflow_status,
)
from src.utils.api_utils import agent_endpoint, log_llm_interaction

import json
from typing import Any

from src.rag.knowledge_base import KnowledgeBase

# 初始化 logger
logger = setup_logger('fundamentals_agent')


def _ensure_agent_outputs(data: dict) -> dict:
    agent_outputs = data.get("agent_outputs")
    if not isinstance(agent_outputs, dict):
        agent_outputs = {}
    data["agent_outputs"] = agent_outputs
    return agent_outputs


FUNDAMENTALS_MEMORY_LIMIT = 3


def _get_knowledge_base() -> KnowledgeBase:
    return KnowledgeBase()


def _build_memory_scope(stock_code: str | None) -> dict[str, Any]:
    normalized = str(stock_code or "").split(".")[0]
    return {
        "mode": "sqlite_first",
        "channel": "fundamentals_memory",
        "stock_code": normalized,
        "hard_filter": "stock_code_exact",
        "limit": FUNDAMENTALS_MEMORY_LIMIT,
        "retrieved_count": 0,
        "status": "not_attempted",
    }


def _normalize_signal(value: Any) -> str:
    signal = str(value or "").strip().lower()
    if signal in {"bullish", "bearish", "neutral"}:
        return signal
    return "unknown"


def _parse_confidence_percent(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        score = float(value)
        if 0 <= score <= 1:
            score *= 100.0
        return max(0.0, min(score, 100.0))
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        score = float(text)
    except ValueError:
        return None
    if 0 <= score <= 1:
        score *= 100.0
    return max(0.0, min(score, 100.0))


def _build_memory_delta(
    *,
    current_signal: str,
    current_confidence: str,
    retrieved_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    if not retrieved_refs:
        return {
            "status": "no_history",
            "changed": False,
            "summary": "No prior fundamentals memory available for longitudinal comparison.",
        }

    latest_ref = retrieved_refs[0]
    previous_signal = _normalize_signal(latest_ref.get("signal"))
    previous_confidence = _parse_confidence_percent(latest_ref.get("confidence"))
    current_conf = _parse_confidence_percent(current_confidence)

    signal_changed = previous_signal != "unknown" and previous_signal != current_signal
    confidence_delta = None
    confidence_regime_changed = False
    if previous_confidence is not None and current_conf is not None:
        confidence_delta = round(current_conf - previous_confidence, 2)
        confidence_regime_changed = abs(confidence_delta) >= 20.0

    if signal_changed:
        summary = (
            f"Signal changed from {previous_signal} ({latest_ref.get('analysis_date', 'n/a')}) "
            f"to {current_signal}."
        )
    elif confidence_regime_changed and confidence_delta is not None:
        direction = "increased" if confidence_delta > 0 else "decreased"
        summary = (
            f"Signal stayed {current_signal}, confidence {direction} by {abs(confidence_delta):.2f} points "
            f"vs {latest_ref.get('analysis_date', 'n/a')}."
        )
    else:
        summary = (
            f"Signal remained {current_signal} versus latest memory "
            f"({latest_ref.get('analysis_date', 'n/a')})."
        )

    return {
        "status": "ok",
        "changed": signal_changed or confidence_regime_changed,
        "change_type": (
            "signal_reversal"
            if signal_changed
            else "confidence_shift"
            if confidence_regime_changed
            else "stable"
        ),
        "previous_signal": previous_signal,
        "current_signal": current_signal,
        "previous_confidence": latest_ref.get("confidence"),
        "current_confidence": current_confidence,
        "confidence_delta_points": confidence_delta,
        "latest_ref_date": latest_ref.get("analysis_date"),
        "summary": summary,
    }


def _sanitize_memory_refs(refs: Any, limit: int = FUNDAMENTALS_MEMORY_LIMIT) -> list[dict[str, Any]]:
    if not isinstance(refs, list):
        return []
    sanitized: list[dict[str, Any]] = []
    for ref in refs[:limit]:
        if not isinstance(ref, dict):
            continue
        sanitized.append(
            {
                "id": ref.get("id"),
                "stock_code": ref.get("stock_code"),
                "analysis_date": ref.get("analysis_date"),
                "signal": ref.get("signal"),
                "confidence": ref.get("confidence"),
                "summary": ref.get("summary"),
                "run_id": ref.get("run_id"),
                "created_at": ref.get("created_at"),
            }
        )
    return sanitized


##### Fundamental Agent #####


@agent_endpoint("fundamentals", "基本面分析师，分析公司财务指标、盈利能力和增长潜力")
def fundamentals_agent(state: AgentState):
    """Responsible for fundamental analysis"""
    show_workflow_status("Fundamentals Analyst")
    show_reasoning = state["metadata"]["show_reasoning"]
    data = state["data"]

    ablation_result = maybe_return_ablation_stub(
        state,
        agent_key="fundamentals",
        agent_type="rule_engine",
        message_name="fundamentals_agent",
        output_key="fundamentals",
        data_key="fundamental_analysis",
        payload_overrides={
            "analysis_mode": "memory_enhanced_rule_engine",
            "retrieved_refs": [],
            "memory_scope": {
                "mode": "sqlite_first",
                "channel": "fundamentals_memory",
                "status": "ablation_disabled",
            },
            "memory_delta": {
                "status": "ablation_disabled",
                "changed": False,
                "summary": "Ablation disabled fundamentals agent.",
            },
        },
    )
    if ablation_result is not None:
        return ablation_result

    stock_code = data.get("ticker") or data.get("stock_symbol")
    metrics = data["financial_metrics"][0]

    retrieved_refs: list[dict[str, Any]] = []
    memory_scope = _build_memory_scope(stock_code)
    knowledge_base: KnowledgeBase | None = None
    if stock_code:
        try:
            knowledge_base = _get_knowledge_base()
            retrieved_refs = knowledge_base.retrieve_fundamentals_refs(
                stock_code=str(stock_code),
                limit=FUNDAMENTALS_MEMORY_LIMIT,
                as_of_date=data.get("end_date"),
                include_payload=False,
            )
            retrieved_refs = _sanitize_memory_refs(retrieved_refs)
            memory_scope["retrieved_count"] = len(retrieved_refs)
            memory_scope["status"] = "ok"
        except Exception as exc:
            logger.warning("Fundamentals memory retrieval unavailable: %s", exc)
            memory_scope["status"] = "unavailable"
            memory_scope["error"] = str(exc)
    else:
        memory_scope["status"] = "no_stock_code"

    # Initialize signals list for different fundamental aspects
    signals = []
    reasoning = {}

    # 1. Profitability Analysis
    return_on_equity = metrics.get("return_on_equity", None)
    net_margin = metrics.get("net_margin", None)
    operating_margin = metrics.get("operating_margin", None)

    thresholds = [
        (return_on_equity, 0.15),  # Strong ROE above 15%
        (net_margin, 0.20),  # Healthy profit margins
        (operating_margin, 0.15)  # Strong operating efficiency
    ]
    profitability_score = sum(
        metric is not None and metric > threshold
        for metric, threshold in thresholds
    )

    signals.append('bullish' if profitability_score >=
                   2 else 'bearish' if profitability_score == 0 else 'neutral')
    # 修复百分比显示问题：确保数值在合理范围内
    def format_percentage(value, name):
        if value is None:
            return f"{name}: N/A"
        # 检查是否为极端异常值
        if abs(value) > 10.0:  # 大于1000%的值视为异常
            return f"{name}: N/A (异常值)"
        # 检查是否为极端负增长（可能是数据质量问题）
        if value < -1.0:  # 过小的值可能有问题，特别是对于收入和利润增长
            return f"{name}: N/A (数据异常)"
        # 如果值已经是小数形式(如0.1563)，直接格式化为百分比
        return f"{name}: {value:.2%}"
    
    reasoning["profitability_signal"] = {
        "signal": signals[0],
        "details": format_percentage(metrics.get('return_on_equity'), "ROE") + 
                  ", " + format_percentage(metrics.get('net_margin'), "Net Margin") +
                  ", " + format_percentage(metrics.get('operating_margin'), "Op Margin")
    }

    # 2. Growth Analysis
    revenue_growth = metrics.get("revenue_growth", None)
    earnings_growth = metrics.get("earnings_growth", None)
    book_value_growth = metrics.get("book_value_growth", None)

    thresholds = [
        (revenue_growth, 0.10),  # 10% revenue growth
        (earnings_growth, 0.10),  # 10% earnings growth
        (book_value_growth, 0.10)  # 10% book value growth
    ]
    growth_score = sum(
        metric is not None and metric > threshold
        for metric, threshold in thresholds
    )

    signals.append('bullish' if growth_score >=
                   2 else 'bearish' if growth_score == 0 else 'neutral')
    reasoning["growth_signal"] = {
        "signal": signals[1],
        "details": format_percentage(metrics.get('revenue_growth'), "Revenue Growth") +
                  ", " + format_percentage(metrics.get('earnings_growth'), "Earnings Growth")
    }

    # 3. Financial Health
    current_ratio = metrics.get("current_ratio", None)
    debt_to_equity = metrics.get("debt_to_equity", None)
    free_cash_flow_per_share = metrics.get("free_cash_flow_per_share", None)
    earnings_per_share = metrics.get("earnings_per_share", None)

    health_score = 0
    if current_ratio and current_ratio > 1.5:  # Strong liquidity
        health_score += 1
    if debt_to_equity and debt_to_equity < 0.5:  # Conservative debt levels
        health_score += 1
    if (free_cash_flow_per_share and earnings_per_share and
            free_cash_flow_per_share > earnings_per_share * 0.8):  # Strong FCF conversion
        health_score += 1

    signals.append('bullish' if health_score >=
                   2 else 'bearish' if health_score == 0 else 'neutral')
    def format_ratio(value, name):
        if value is None or value == 0:
            return f"{name}: N/A"
        return f"{name}: {value:.2f}"
    
    reasoning["financial_health_signal"] = {
        "signal": signals[2],
        "details": format_ratio(metrics.get('current_ratio'), "Current Ratio") +
                  ", " + format_ratio(metrics.get('debt_to_equity'), "D/E")
    }

    # 4. Price to X ratios
    pe_ratio = metrics.get("pe_ratio", None)
    price_to_book = metrics.get("price_to_book", None)
    price_to_sales = metrics.get("price_to_sales", None)

    thresholds = [
        (pe_ratio, 25),  # Reasonable P/E ratio
        (price_to_book, 3),  # Reasonable P/B ratio
        (price_to_sales, 5)  # Reasonable P/S ratio
    ]
    price_ratio_score = sum(
        metric is not None and metric < threshold
        for metric, threshold in thresholds
    )

    signals.append('bullish' if price_ratio_score >=
                   2 else 'bearish' if price_ratio_score == 0 else 'neutral')
    reasoning["price_ratios_signal"] = {
        "signal": signals[3],
        "details": format_ratio(pe_ratio, "P/E") +
                  ", " + format_ratio(price_to_book, "P/B") +
                  ", " + format_ratio(price_to_sales, "P/S")
    }

    # Determine overall signal
    bullish_signals = signals.count('bullish')
    bearish_signals = signals.count('bearish')

    if bullish_signals > bearish_signals:
        overall_signal = 'bullish'
    elif bearish_signals > bullish_signals:
        overall_signal = 'bearish'
    else:
        overall_signal = 'neutral'

    # Calculate confidence level
    total_signals = len(signals)
    confidence = max(bullish_signals, bearish_signals) / total_signals
    confidence_text = f"{round(confidence * 100)}%"
    memory_delta = _build_memory_delta(
        current_signal=overall_signal,
        current_confidence=confidence_text,
        retrieved_refs=retrieved_refs,
    )
    reasoning["memory_comparison"] = memory_delta["summary"]

    message_content = {
        "agent_type": "rule_engine",
        "analysis_mode": "memory_enhanced_rule_engine",
        "signal": overall_signal,
        "confidence": confidence_text,
        "reasoning": reasoning,
        "retrieved_refs": retrieved_refs,
        "memory_scope": memory_scope,
        "memory_delta": memory_delta,
    }

    # Create the fundamental analysis message
    message = HumanMessage(
        content=json.dumps(message_content),
        name="fundamentals_agent",
    )

    # Print the reasoning if the flag is set
    if show_reasoning:
        show_agent_reasoning(message_content, "Fundamental Analysis Agent")
    
    # 始终保存推理信息到metadata供API使用
    updated_data = dict(data)
    agent_outputs = _ensure_agent_outputs(updated_data)
    agent_outputs["fundamentals"] = message_content
    updated_data["fundamental_analysis"] = message_content
    state["metadata"]["agent_reasoning"] = message_content

    if stock_code:
        try:
            if knowledge_base is None:
                knowledge_base = _get_knowledge_base()
            memory_payload = dict(message_content)
            memory_payload["retrieved_refs"] = _sanitize_memory_refs(retrieved_refs)
            knowledge_base.save_fundamentals_memory(
                stock_code=str(stock_code),
                analysis_payload=memory_payload,
                run_id=data.get("run_id"),
                analysis_date=data.get("end_date"),
            )
        except Exception as exc:
            logger.warning("Fundamentals memory save skipped: %s", exc)

    show_workflow_status("Fundamentals Analyst", "completed")
    # logger.info(f"--- DEBUG: fundamentals_agent RETURN messages: {[msg.name for msg in [message]]} ---")
    return {
        "messages": [message],
        "data": updated_data,
        "metadata": state["metadata"],
    }
