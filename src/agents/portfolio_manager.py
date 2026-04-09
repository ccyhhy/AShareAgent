import json
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
        content=json.dumps({"signal": "error", "details": f"Message from {name} not found"}),
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
        "reasoning": "LLM API error. Defaulting to conservative hold based on risk management.",
    }


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

    ablation_reason = get_ablation_disable_reason(
        state,
        agent_key="portfolio_management",
        agent_type="llm",
    )
    if ablation_reason is not None:
        decision_json = _default_decision()
        decision_json["reasoning"] = (
            f"{ablation_reason} Final decision forced to deterministic hold."
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
        "Relative valuation message missing",
    )
    fundamentals_content = _as_prompt_payload(
        fundamentals_payload,
        fundamentals_message.content if fundamentals_message else "",
        "Fundamentals message missing",
    )
    sentiment_content = _as_prompt_payload(
        sentiment_payload,
        sentiment_message.content if sentiment_message else "",
        "Market sentiment message missing",
    )
    valuation_content = _as_prompt_payload(
        valuation_payload,
        valuation_message.content if valuation_message else "",
        "Valuation message missing",
    )
    risk_content = _as_prompt_payload(
        risk_payload,
        risk_message.content if risk_message else "",
        "Risk message missing",
    )
    macro_content = _as_prompt_payload(
        macro_payload,
        macro_message.content if macro_message else "",
        "Macro message missing",
    )
    bull_researcher_content = bull_researcher_message.content if bull_researcher_message else json.dumps(
        {"signal": "error", "details": "Bull researcher message missing"}
    )
    bear_researcher_content = bear_researcher_message.content if bear_researcher_message else json.dumps(
        {"signal": "error", "details": "Bear researcher message missing"}
    )

    market_wide_news_summary_content = state["data"].get(
        "macro_news_analysis_result",
        "Market-wide macro news summary is unavailable.",
    )

    system_message_content = """You are a portfolio manager making final trading decisions.
Use all signals and produce JSON only.

Preferred semantics and keys:
- Use `relative_valuation_analysis` as the preferred name for PB-percentile valuation-position signal.
- `technical_analysis` is accepted as a compatibility alias.
- `sentiment_analysis` means market sentiment from recent news.

Required JSON fields:
- action: buy | sell | hold
- quantity: positive integer
- confidence: float between 0 and 1
- agent_signals: list of objects with agent_name, signal, confidence
- reasoning: concise decision explanation
- ashare_considerations: A-share specific considerations (optional)
"""

    user_message_content = f"""Based on the team's analysis below, make the final trading decision.

Relative Valuation Signal (PB Percentile, prefer structured agent_outputs): {technical_content}
Fundamental Analysis Signal (prefer structured agent_outputs): {fundamentals_content}
Market Sentiment Signal (News-based, prefer structured agent_outputs): {sentiment_content}
Valuation Analysis Signal (prefer structured agent_outputs): {valuation_content}
Risk Management Signal (prefer structured agent_outputs): {risk_content}
Macro Stock-Level Analysis Signal (post-risk stage): {macro_content}
Macro Market-Wide News Summary Signal (parallel stage): {market_wide_news_summary_content}
Bull Researcher Analysis: {bull_researcher_content}
Bear Researcher Analysis: {bear_researcher_content}

Portfolio state:
- cash: {portfolio.get('cash', 0.0):.2f}
- stock position: {portfolio.get('stock', 0)}
"""

    llm_interaction_messages = [
        {"role": "system", "content": system_message_content},
        {"role": "user", "content": user_message_content},
    ]

    if _is_backtest_mode():
        show_agent_reasoning(
            agent_name,
            "Backtest mode active. Skip remote LLM call and use deterministic conservative decision.",
        )
        llm_response_content = None
        decision_json = _default_decision()
        decision_json["reasoning"] = (
            "Backtest mode active. Remote LLM call skipped; using deterministic conservative hold decision."
        )
    else:
        show_agent_reasoning(
            agent_name,
            "Preparing LLM with RV(PB), fundamentals, market sentiment, valuation, risk, macro, and researcher views.",
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
            show_agent_reasoning(agent_name, "LLM call failed. Using default conservative decision.")
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

    llm_response_content = json.dumps(decision_json, ensure_ascii=False)

    final_decision_message = HumanMessage(
        content=llm_response_content,
        name=agent_name,
    )

    if show_reasoning_flag:
        show_agent_reasoning(agent_name, f"Final LLM decision JSON: {llm_response_content}")

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
