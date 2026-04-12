import json
import math
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as ConcurrentTimeoutError
from typing import Any

from langchain_core.messages import HumanMessage

from src.agents.state import (
    AgentState,
    get_ablation_disable_reason,
    show_agent_reasoning,
    show_workflow_status,
)
from src.tools.openrouter_config import get_chat_completion
from src.utils.api_utils import agent_endpoint, log_llm_interaction
from src.utils.logging_config import setup_logger

logger = setup_logger("portfolio_management_agent")


def _is_backtest_mode() -> bool:
    value = os.getenv("ASHAREAGENT_BACKTEST_MODE")
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_latest_message_by_name(messages: list, name: str):
    for msg in reversed(messages):
        if msg.name == name:
            return msg
    logger.debug("Message from agent '%s' not found in portfolio_management_agent.", name)
    return HumanMessage(
        content=json.dumps({"signal": "error", "details": f"缺少 {name} 的输出"}),
        name=name,
    )


def _safe_json_loads(content: str, default: Any) -> Any:
    try:
        return json.loads(content)
    except Exception:
        return default


def _extract_agent_output_payload(
    data: dict[str, Any],
    *,
    primary_key: str,
    compatibility_keys: list[str] | None = None,
) -> dict[str, Any] | None:
    compatibility_keys = compatibility_keys or []
    agent_outputs = data.get("agent_outputs")
    if isinstance(agent_outputs, dict):
        for key in [primary_key, *compatibility_keys]:
            candidate = agent_outputs.get(key)
            if isinstance(candidate, dict):
                return candidate
    for key in compatibility_keys:
        candidate = data.get(key)
        if isinstance(candidate, dict):
            return candidate
    return None


def _as_prompt_payload(payload: dict[str, Any] | None, fallback_content: str, fallback_error: str) -> str:
    if isinstance(payload, dict):
        return json.dumps(payload, ensure_ascii=False)
    if fallback_content:
        return fallback_content
    return json.dumps({"signal": "error", "details": fallback_error}, ensure_ascii=False)


def _default_decision() -> dict[str, Any]:
    return {
        "agent_type": "llm",
        "signal": "neutral",
        "action": "hold",
        "quantity": 0,
        "confidence": 0.7,
        "agent_signals": [
            {"agent_name": "technical_analysis", "signal": "neutral", "confidence": 0.0},
            {"agent_name": "relative_valuation_analysis", "signal": "neutral", "confidence": 0.0},
            {"agent_name": "fundamental_analysis", "signal": "neutral", "confidence": 0.0},
            {"agent_name": "sentiment_analysis", "signal": "neutral", "confidence": 0.0},
            {"agent_name": "valuation_analysis", "signal": "neutral", "confidence": 0.0},
            {"agent_name": "risk_management", "signal": "hold", "confidence": 1.0},
            {"agent_name": "selected_stock_macro_analysis", "signal": "neutral", "confidence": 0.0},
            {"agent_name": "market_wide_news_summary", "signal": "unavailable_or_llm_error", "confidence": 0.0},
            {"agent_name": "ashare_policy_impact", "signal": "neutral", "confidence": 0.0},
            {"agent_name": "liquidity_assessment", "signal": "neutral", "confidence": 0.0},
            {"agent_name": "bull_researcher", "signal": "neutral", "confidence": 0.0},
            {"agent_name": "bear_researcher", "signal": "neutral", "confidence": 0.0},
        ],
        "reasoning": "LLM接口异常，按风控优先原则回退为保守持有。",
    }
def _coerce_non_negative_int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number) or math.isinf(number):
        return default
    return number


def _apply_missing_data_guard(decision_json: dict[str, Any], *, critical_data_complete: bool, missing_critical_data: list[str]) -> dict[str, Any]:
    if critical_data_complete:
        return decision_json
    action_text = str(decision_json.get("action", "")).strip().lower()
    if action_text != "buy":
        return decision_json
    updated = dict(decision_json)
    updated["action"] = "hold"
    updated["quantity"] = 0
    updated["signal"] = "neutral"
    original_reasoning = str(updated.get("reasoning", "")).strip()
    guard_reason = (
        "关键数据缺失，最终决策禁止买入。"
        f"缺失项：{', '.join(missing_critical_data) if missing_critical_data else 'unknown'}。"
    )
    updated["reasoning"] = f"{original_reasoning} {guard_reason}".strip()
    return updated


def _apply_buy_quantity_caps(
    decision_json: dict[str, Any],
    *,
    risk_payload: dict[str, Any] | None,
    portfolio: dict[str, Any],
) -> dict[str, Any]:
    updated = dict(decision_json)
    action_text = str(updated.get("action", "")).strip().lower()
    requested_quantity = _coerce_non_negative_int(updated.get("quantity", 0))
    updated["quantity"] = requested_quantity

    if action_text != "buy":
        return updated

    risk_data = risk_payload if isinstance(risk_payload, dict) else {}
    lot_size = _coerce_non_negative_int(risk_data.get("quantity_lot_size", 100))
    if lot_size <= 0:
        lot_size = 100

    current_price = _safe_float(risk_data.get("current_price"), 0.0)
    cash_available = _safe_float(portfolio.get("cash", 0.0), 0.0)

    risk_cap_quantity = requested_quantity
    if "max_buy_quantity" in risk_data:
        risk_cap_quantity = _coerce_non_negative_int(risk_data.get("max_buy_quantity", 0))

    cash_cap_quantity = requested_quantity
    if current_price > 0:
        cash_cap_quantity = int(cash_available // current_price)

    capped_quantity = min(requested_quantity, risk_cap_quantity, cash_cap_quantity)
    if lot_size > 1:
        capped_quantity = (capped_quantity // lot_size) * lot_size

    updated["quantity_constraints"] = {
        "requested_quantity": requested_quantity,
        "risk_cap_quantity": risk_cap_quantity,
        "cash_cap_quantity": cash_cap_quantity,
        "lot_size": lot_size,
        "current_price": current_price if current_price > 0 else None,
    }

    if capped_quantity < requested_quantity:
        original_reasoning = str(updated.get("reasoning", "")).strip()
        cap_reason = (
            f"数量约束生效：请求{requested_quantity}股，"
            f"风控上限{risk_cap_quantity}股，现金上限{cash_cap_quantity}股，"
            f"整手后执行{capped_quantity}股。"
        )
        updated["reasoning"] = f"{original_reasoning} {cap_reason}".strip()

    updated["quantity"] = capped_quantity
    if capped_quantity <= 0:
        updated["action"] = "hold"
        updated["signal"] = "neutral"
        original_reasoning = str(updated.get("reasoning", "")).strip()
        hold_reason = "按风控/资金与整手约束，当前无法形成有效买入股数，已回退为持有。"
        updated["reasoning"] = f"{original_reasoning} {hold_reason}".strip()

    return updated


@agent_endpoint(
    "portfolio_management",
    "Portfolio manager, produces final trading decision from all agent outputs.",
)
def portfolio_management_agent(state: AgentState):
    """Aggregate all agent views and produce final action/quantity decision."""
    agent_name = "portfolio_management_agent"
    show_workflow_status(f"{agent_name}: executing")
    show_reasoning_flag = state["metadata"]["show_reasoning"]
    portfolio = state["data"].get("portfolio", {"cash": 0.0, "stock": 0})
    critical_data_complete = bool(state["data"].get("critical_data_complete", False))
    missing_critical_data = list(state["data"].get("missing_critical_data", []))

    ablation_reason = get_ablation_disable_reason(
        state,
        agent_key="portfolio_management",
        agent_type="llm",
    )
    if ablation_reason is not None:
        decision_json = _default_decision()
        decision_json["reasoning"] = (
            f"{ablation_reason} 已强制回退为确定性持有决策。"
        )
        final_decision_message = HumanMessage(
            content=json.dumps(decision_json, ensure_ascii=False),
            name=agent_name,
        )
        return {
            "messages": [final_decision_message],
            "data": state["data"],
            "metadata": {
                **state["metadata"],
                f"{agent_name}_decision_details": {
                    "action": decision_json.get("action"),
                    "quantity": decision_json.get("quantity"),
                    "confidence": decision_json.get("confidence"),
                    "reasoning_snippet": str(decision_json.get("reasoning", ""))[:150] + "...",
                },
                "agent_reasoning": decision_json["reasoning"],
            },
        }

    unique_incoming_messages = {}
    for msg in state["messages"]:
        unique_incoming_messages[msg.name] = msg
    cleaned_messages_for_processing = list(unique_incoming_messages.values())

    technical_message = get_latest_message_by_name(cleaned_messages_for_processing, "technical_analyst_agent")
    fundamentals_message = get_latest_message_by_name(cleaned_messages_for_processing, "fundamentals_agent")
    sentiment_message = get_latest_message_by_name(cleaned_messages_for_processing, "sentiment_agent")
    valuation_message = get_latest_message_by_name(cleaned_messages_for_processing, "valuation_agent")
    risk_message = get_latest_message_by_name(cleaned_messages_for_processing, "risk_management_agent")
    macro_message = get_latest_message_by_name(cleaned_messages_for_processing, "macro_analyst_agent")
    bull_researcher_message = get_latest_message_by_name(cleaned_messages_for_processing, "researcher_bull")
    bear_researcher_message = get_latest_message_by_name(cleaned_messages_for_processing, "researcher_bear")

    data_section = state.get("data", {})
    technical_payload = _extract_agent_output_payload(
        data_section,
        primary_key="technicals",
        compatibility_keys=["relative_valuation", "relative_valuation_analysis", "technical_analysis"],
    )
    fundamentals_payload = _extract_agent_output_payload(
        data_section,
        primary_key="fundamentals",
        compatibility_keys=["fundamental_analysis"],
    )
    sentiment_payload = _extract_agent_output_payload(
        data_section,
        primary_key="sentiment",
        compatibility_keys=["sentiment_analysis"],
    )
    valuation_payload = _extract_agent_output_payload(
        data_section,
        primary_key="valuation",
        compatibility_keys=["valuation_analysis"],
    )
    risk_payload = _extract_agent_output_payload(
        data_section,
        primary_key="risk_manager",
        compatibility_keys=["risk_management", "risk_analysis"],
    )
    macro_payload = _extract_agent_output_payload(
        data_section,
        primary_key="macro_analyst",
        compatibility_keys=["macro_analysis"],
    )

    technical_content = _as_prompt_payload(
        technical_payload,
        technical_message.content if technical_message else "",
        "缺少相对估值信号",
    )
    fundamentals_content = _as_prompt_payload(
        fundamentals_payload,
        fundamentals_message.content if fundamentals_message else "",
        "缺少基本面信号",
    )
    sentiment_content = _as_prompt_payload(
        sentiment_payload,
        sentiment_message.content if sentiment_message else "",
        "缺少市场情绪信号",
    )
    valuation_content = _as_prompt_payload(
        valuation_payload,
        valuation_message.content if valuation_message else "",
        "缺少估值信号",
    )
    risk_content = _as_prompt_payload(
        risk_payload,
        risk_message.content if risk_message else "",
        "缺少风险管理信号",
    )
    macro_content = _as_prompt_payload(
        macro_payload,
        macro_message.content if macro_message else "",
        "缺少宏观信号",
    )
    bull_researcher_content = bull_researcher_message.content if bull_researcher_message else json.dumps(
        {"signal": "error", "details": "缺少多头研究员输出"}
    )
    bear_researcher_content = bear_researcher_message.content if bear_researcher_message else json.dumps(
        {"signal": "error", "details": "缺少空头研究员输出"}
    )

    market_wide_news_summary_content = state["data"].get(
        "macro_news_analysis_result",
        "暂无可用的全市场宏观新闻摘要。",
    )

    system_message_content = """你是A股组合经理，负责生成最终交易决策。请综合全部信号并仅返回JSON。

语义约定：
- `relative_valuation_analysis` 是PB分位估值信号的首选名称。
- `technical_analysis` 仅作为兼容别名。
- `sentiment_analysis` 指基于近期新闻的市场情绪。
- `quantity` 表示最终交易股数，必须按100股整手。
- 若关键数据缺失，不得输出 buy。
- buy 数量不得超过风险管理给出的 `max_buy_quantity` 与现金可买上限。

必填JSON字段：
- action: buy | sell | hold
- quantity: 正整数
- confidence: 0到1之间的小数
- agent_signals: 列表，元素包含 agent_name、signal、confidence
- reasoning: 中文简明决策理由
- ashare_considerations: A股特有约束或注意事项（可选）
"""

    user_message_content = f"""请基于以下团队分析给出最终交易决策（仅JSON）：

相对估值信号（PB分位，优先使用 structured agent_outputs）：{technical_content}
基本面信号（优先使用 structured agent_outputs）：{fundamentals_content}
市场情绪信号（新闻口径，优先使用 structured agent_outputs）：{sentiment_content}
估值信号（优先使用 structured agent_outputs）：{valuation_content}
风险管理信号（优先使用 structured agent_outputs）：{risk_content}
个股宏观信号（风险后阶段）：{macro_content}
全市场宏观新闻摘要（并行阶段）：{market_wide_news_summary_content}
多头研究员观点：{bull_researcher_content}
空头研究员观点：{bear_researcher_content}

组合状态：
- 现金：{portfolio.get('cash', 0.0):.2f}
- 持仓股数：{portfolio.get('stock', 0)}

关键数据完整性：
- critical_data_complete: {critical_data_complete}
- missing_critical_data: {missing_critical_data}
"""

    llm_interaction_messages = [
        {"role": "system", "content": system_message_content},
        {"role": "user", "content": user_message_content},
    ]

    if _is_backtest_mode():
        show_agent_reasoning(
            "当前为回测模式，跳过远程LLM调用并使用确定性保守决策。",
            agent_name,
        )
        llm_response_content = None
        decision_json = _default_decision()
        decision_json["reasoning"] = (
            "当前为回测模式，已跳过远程LLM调用并采用确定性保守持有决策。"
        )
    else:
        show_agent_reasoning(
            "正在汇总相对估值、基本面、情绪、估值、风控、宏观与多空研究观点，准备调用LLM。",
            agent_name,
        )

        def call_llm():
            return get_chat_completion(llm_interaction_messages)

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(call_llm)
                llm_response_content = future.result(timeout=90)
        except ConcurrentTimeoutError:
            logger.error("%s: LLM call timeout after 90 seconds", agent_name)
            llm_response_content = None
        except Exception as exc:
            logger.error("%s: LLM call failed: %s", agent_name, exc)
            llm_response_content = None

        state["metadata"]["current_agent_name"] = agent_name
        log_llm_interaction(state)(lambda: llm_response_content)()

        if llm_response_content is None:
            show_agent_reasoning("LLM调用失败，回退为默认保守决策。", agent_name)
            decision_json = _default_decision()
        else:
            decision_json = _safe_json_loads(llm_response_content, _default_decision())

    bull_researcher_data = _safe_json_loads(bull_researcher_content, {})
    bear_researcher_data = _safe_json_loads(bear_researcher_content, {})

    if isinstance(decision_json.get("agent_signals"), list):
        for signal in decision_json["agent_signals"]:
            if signal.get("agent_name") == "bull_researcher" and bull_researcher_data:
                signal.update(
                    {
                        "reasoning": bull_researcher_data.get("reasoning", ""),
                        "thesis_points": bull_researcher_data.get("thesis_points", []),
                        "perspective": bull_researcher_data.get("perspective", "bullish"),
                        "signal_weights": bull_researcher_data.get("signal_weights", {}),
                        "ashare_factors": bull_researcher_data.get("ashare_factors", {}),
                    }
                )
            elif signal.get("agent_name") == "bear_researcher" and bear_researcher_data:
                signal.update(
                    {
                        "reasoning": bear_researcher_data.get("reasoning", ""),
                        "thesis_points": bear_researcher_data.get("thesis_points", []),
                        "perspective": bear_researcher_data.get("perspective", "bearish"),
                        "risk_factors": bear_researcher_data.get("risk_factors", []),
                        "ashare_risks": bear_researcher_data.get("ashare_risks", {}),
                    }
                )

    decision_json.setdefault("agent_type", "llm")
    decision_json["quantity"] = _coerce_non_negative_int(decision_json.get("quantity", 0))
    decision_json = _apply_missing_data_guard(
        decision_json,
        critical_data_complete=critical_data_complete,
        missing_critical_data=missing_critical_data,
    )
    decision_json = _apply_buy_quantity_caps(
        decision_json,
        risk_payload=risk_payload,
        portfolio=portfolio,
    )
    if not decision_json.get("signal"):
        action_text = str(decision_json.get("action", "")).strip().lower()
        if action_text == "buy":
            decision_json["signal"] = "bullish"
        elif action_text == "sell":
            decision_json["signal"] = "bearish"
        else:
            decision_json["signal"] = "neutral"
    decision_json["data_sufficiency"] = {
        "critical_data_complete": critical_data_complete,
        "missing_critical_data": missing_critical_data,
    }

    llm_response_content = json.dumps(decision_json, ensure_ascii=False)

    final_decision_message = HumanMessage(
        content=llm_response_content,
        name=agent_name,
    )

    if show_reasoning_flag:
        show_agent_reasoning(f"Final LLM decision JSON: {llm_response_content}", agent_name)

    agent_decision_details_value = {
        "action": decision_json.get("action"),
        "quantity": decision_json.get("quantity"),
        "confidence": decision_json.get("confidence"),
        "reasoning_snippet": str(decision_json.get("reasoning", ""))[:150] + "...",
    }

    show_workflow_status(f"{agent_name}: completed", "completed")

    return {
        "messages": [final_decision_message],
        "data": state["data"],
        "metadata": {
            **state["metadata"],
            f"{agent_name}_decision_details": agent_decision_details_value,
            "agent_reasoning": llm_response_content,
        },
    }


def format_decision(
    action: str,
    quantity: int,
    confidence: float,
    agent_signals: list,
    reasoning: str,
    market_wide_news_summary: str = "N/A",
) -> dict:
    """Format trading decision into a stable structure for downstream display."""

    def _find_signal(*agent_names: str):
        return next(
            (s for s in agent_signals if s.get("agent_name") in set(agent_names)),
            None,
        )

    fundamental_signal = _find_signal("fundamental_analysis")
    valuation_signal = _find_signal("valuation_analysis")
    technical_signal = _find_signal("relative_valuation_analysis", "technical_analysis")
    sentiment_signal = _find_signal("sentiment_analysis")
    risk_signal = _find_signal("risk_management")

    def _signal_to_text(signal_data: dict | None) -> str:
        if not signal_data:
            return "no_data"
        signal = signal_data.get("signal")
        if signal == "bullish":
            return "bullish"
        if signal == "bearish":
            return "bearish"
        return "neutral"

    detailed_analysis = (
        "Portfolio decision summary\n"
        f"- fundamental: {_signal_to_text(fundamental_signal)}\n"
        f"- valuation: {_signal_to_text(valuation_signal)}\n"
        f"- relative_valuation(pb): {_signal_to_text(technical_signal)}\n"
        f"- market_sentiment: {_signal_to_text(sentiment_signal)}\n"
        f"- risk: {_signal_to_text(risk_signal)}\n"
        f"- market_wide_news: {market_wide_news_summary}\n"
        f"- reasoning: {reasoning}"
    )

    return {
        "action": action,
        "quantity": quantity,
        "confidence": confidence,
        "agent_signals": agent_signals,
        "analysis_report": detailed_analysis,
    }
