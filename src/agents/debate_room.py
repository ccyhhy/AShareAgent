from __future__ import annotations

import ast
import json
import logging
import os
from typing import Any

from langchain_core.messages import HumanMessage

from src.agents.state import AgentState, show_agent_reasoning, show_workflow_status
from src.tools.openrouter_config import get_chat_completion
from src.utils.api_utils import agent_endpoint, log_llm_interaction

logger = logging.getLogger("debate_room")


def _is_backtest_mode() -> bool:
    value = os.getenv("ASHAREAGENT_BACKTEST_MODE")
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_payload(content: Any) -> dict[str, Any]:
    if not isinstance(content, str):
        return {}
    try:
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        try:
            parsed = ast.literal_eval(content)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}


def _to_confidence(value: Any) -> float:
    try:
        score = float(value)
    except Exception:
        return 0.5
    return max(0.0, min(score, 1.0))


@agent_endpoint("debate_room", "Debate room that balances bull and bear researcher views")
def debate_room_agent(state: AgentState):
    """Facilitate structured bull-vs-bear debate and output a balanced signal."""
    show_workflow_status("Debate Room")
    show_reasoning = state["metadata"]["show_reasoning"]

    researcher_aliases = {
        "researcher_bull_agent": "researcher_bull",
        "researcher_bear_agent": "researcher_bear",
    }

    researcher_messages: dict[str, HumanMessage] = {}
    for msg in state.get("messages", []):
        if msg is None or not hasattr(msg, "name"):
            continue
        msg_name = getattr(msg, "name", None)
        if not isinstance(msg_name, str) or not msg_name.startswith("researcher_"):
            continue
        canonical_name = researcher_aliases.get(msg_name, msg_name)
        researcher_messages[canonical_name] = msg

    if "researcher_bull" not in researcher_messages or "researcher_bear" not in researcher_messages:
        raise ValueError("Missing required researcher_bull or researcher_bear messages")

    bull_thesis = _parse_payload(researcher_messages["researcher_bull"].content)
    bear_thesis = _parse_payload(researcher_messages["researcher_bear"].content)

    if not bull_thesis or not bear_thesis:
        raise ValueError("Could not parse required researcher_bull or researcher_bear messages")

    bull_confidence = _to_confidence(bull_thesis.get("confidence", 0.5))
    bear_confidence = _to_confidence(bear_thesis.get("confidence", 0.5))

    bull_points = [str(p) for p in bull_thesis.get("thesis_points", []) if str(p).strip()]
    bear_points = [str(p) for p in bear_thesis.get("thesis_points", []) if str(p).strip()]

    debate_summary = ["Bullish Arguments:"]
    debate_summary.extend([f"+ {point}" for point in bull_points])
    debate_summary.append("\nBearish Arguments:")
    debate_summary.extend([f"- {point}" for point in bear_points])

    llm_analysis: dict[str, Any] | None = None
    llm_score = 0.0

    if _is_backtest_mode():
        llm_analysis = {
            "analysis": "Backtest mode active. Third-party LLM debate scoring skipped.",
            "score": 0.0,
            "reasoning": "Deterministic fallback for reproducibility.",
        }
    else:
        prompt_parts = [
            "Analyze the following bull and bear theses and return JSON with fields analysis, score, reasoning.",
            f"BULL confidence={bull_confidence}: {bull_points}",
            f"BEAR confidence={bear_confidence}: {bear_points}",
        ]
        messages = [
            {
                "role": "system",
                "content": "You are a professional financial analyst. Reply in valid JSON only.",
            },
            {"role": "user", "content": "\n".join(prompt_parts)},
        ]

        try:
            llm_response = log_llm_interaction(state)(lambda: get_chat_completion(messages))()
            if llm_response:
                start = llm_response.find("{")
                end = llm_response.rfind("}") + 1
                if start >= 0 and end > start:
                    parsed = json.loads(llm_response[start:end])
                    if isinstance(parsed, dict):
                        llm_analysis = parsed
                        llm_score = max(-1.0, min(1.0, float(parsed.get("score", 0.0))))
        except Exception as exc:
            logger.error("LLM call failed in debate_room_agent: %s", exc)
            llm_analysis = {
                "analysis": "LLM API call failed",
                "score": 0.0,
                "reasoning": "API error",
            }

    if llm_analysis is None:
        llm_analysis = {
            "analysis": "No valid LLM analysis returned",
            "score": 0.0,
            "reasoning": "Fallback",
        }

    confidence_diff = bull_confidence - bear_confidence

    bull_reasoning = str(bull_thesis.get("reasoning", ""))
    bear_reasoning = str(bear_thesis.get("reasoning", ""))

    ashare_adjustments = {
        "policy_factor": 0.0,
        "liquidity_factor": 0.0,
        "volatility_factor": 0.0,
        "sentiment_extreme": 0.0,
    }

    if "policy" in bull_reasoning.lower() or "policy" in bear_reasoning.lower():
        ashare_adjustments["policy_factor"] = 0.1 if bull_confidence > bear_confidence else -0.1

    if "liquidity" in bear_reasoning.lower():
        ashare_adjustments["liquidity_factor"] = -0.05

    if abs(confidence_diff) > 0.7:
        ashare_adjustments["sentiment_extreme"] = -0.1 * abs(confidence_diff)

    total_adjustment = sum(ashare_adjustments.values())
    adjusted_confidence_diff = confidence_diff + total_adjustment

    llm_weight = 0.4
    mixed_confidence_diff = (1 - llm_weight) * adjusted_confidence_diff + llm_weight * llm_score

    market_volatility = abs(confidence_diff)
    adaptive_threshold = 0.1 + min(market_volatility * 0.1, 0.05)

    special_conditions = {
        "policy_sensitive": ashare_adjustments["policy_factor"] != 0,
        "high_volatility": market_volatility > 0.6,
        "extreme_sentiment": abs(adjusted_confidence_diff) > 0.8,
        "liquidity_concern": ashare_adjustments["liquidity_factor"] < 0,
    }

    if abs(mixed_confidence_diff) < adaptive_threshold:
        final_signal = "neutral"
        confidence = max(bull_confidence, bear_confidence)
        reasoning = f"Balanced debate; both sides have merit. threshold={adaptive_threshold:.3f}"
    elif mixed_confidence_diff > 0:
        final_signal = "bullish"
        confidence = bull_confidence
        reasoning = f"Bullish tilt after debate. score={mixed_confidence_diff:.3f}"
    else:
        final_signal = "bearish"
        confidence = bear_confidence
        reasoning = f"Bearish tilt after debate. score={mixed_confidence_diff:.3f}"

    if special_conditions["policy_sensitive"]:
        reasoning += " | policy-sensitive"
    if special_conditions["liquidity_concern"]:
        reasoning += " | liquidity concern"
    if special_conditions["high_volatility"]:
        reasoning += " | high volatility"

    max_conf = max(bull_confidence, bear_confidence)
    min_conf = min(bull_confidence, bear_confidence)

    llm_alignment = 1 - abs(llm_score - (adjusted_confidence_diff / 2))
    llm_alignment = max(0.0, min(1.0, llm_alignment))

    message_content = {
        "signal": final_signal,
        "confidence": confidence,
        "bull_confidence": bull_confidence,
        "bear_confidence": bear_confidence,
        "confidence_diff": confidence_diff,
        "adjusted_confidence_diff": adjusted_confidence_diff,
        "llm_score": llm_score,
        "llm_analysis": llm_analysis.get("analysis"),
        "llm_reasoning": llm_analysis.get("reasoning"),
        "mixed_confidence_diff": mixed_confidence_diff,
        "debate_summary": debate_summary,
        "reasoning": reasoning,
        "ashare_factors": {
            "policy_sensitivity": special_conditions["policy_sensitive"],
            "liquidity_concerns": special_conditions["liquidity_concern"],
            "volatility_level": market_volatility,
            "adaptive_threshold": adaptive_threshold,
            "adjustments_applied": ashare_adjustments,
        },
        "decision_quality": {
            "consensus_strength": max(0.0, min(1.0, 1 - market_volatility)),
            "argument_balance": (min_conf / max_conf) if max_conf > 0 else 0,
            "llm_agreement": llm_alignment,
        },
    }

    message = HumanMessage(
        content=json.dumps(message_content, ensure_ascii=False),
        name="debate_room_agent",
    )

    if show_reasoning:
        show_agent_reasoning(message_content, "Debate Room")

    state["metadata"]["agent_reasoning"] = message_content
    show_workflow_status("Debate Room", "completed")

    return {
        "messages": [message],
        "data": {
            **state["data"],
            "debate_analysis": message_content,
            "ashare_debate_metrics": {
                "volatility_level": market_volatility,
                "policy_sensitivity": special_conditions["policy_sensitive"],
                "decision_confidence": confidence,
                "consensus_quality": message_content["decision_quality"]["consensus_strength"],
            },
        },
        "metadata": {
            **state["metadata"],
            "debate_enhanced": True,
            "adaptive_threshold": adaptive_threshold,
            "special_conditions": special_conditions,
        },
    }
