import ast
import json

from langchain_core.messages import HumanMessage

from src.agents.state import (
    AgentState,
    maybe_return_ablation_stub,
    show_agent_reasoning,
    show_workflow_status,
)
from src.utils.api_utils import agent_endpoint


def _ensure_agent_outputs(data: dict) -> dict:
    agent_outputs = data.get("agent_outputs")
    if not isinstance(agent_outputs, dict):
        agent_outputs = {}
    data["agent_outputs"] = agent_outputs
    return agent_outputs


@agent_endpoint(
    "researcher_bull",
    "Bull-side researcher, builds optimistic thesis from first-layer agent signals.",
)
def researcher_bull_agent(state: AgentState):
    """Analyze first-layer signals from a bullish perspective."""
    show_workflow_status("Bullish Researcher")
    show_reasoning = state["metadata"]["show_reasoning"]

    ablation_result = maybe_return_ablation_stub(
        state,
        agent_key="researcher_bull",
        agent_type="llm",
        message_name="researcher_bull_agent",
        output_key="researcher_bull",
        payload_overrides={
            "perspective": "bullish",
            "confidence": 0.5,
            "thesis_points": ["Ablation disabled bullish researcher; neutral stance applied."],
            "technical_signal_semantics": "relative_valuation_pb_percentile",
            "sentiment_signal_semantics": "market_news_sentiment",
            "signal_weights": {
                "fundamental": 0.35,
                "technical": 0.25,
                "valuation": 0.25,
                "sentiment": 0.15,
            },
            "signal_consistency": 1.0,
            "ashare_factors": {
                "policy_sensitivity": False,
                "liquidity_risk": 0.5,
                "institutional_flow": 0.5,
            },
        },
    )
    if ablation_result is not None:
        return ablation_result

    technical_message = next(
        (msg for msg in state["messages"] if msg.name == "technical_analyst_agent"), None
    )
    fundamentals_message = next(
        (msg for msg in state["messages"] if msg.name == "fundamentals_agent"), None
    )
    sentiment_message = next(
        (msg for msg in state["messages"] if msg.name == "sentiment_agent"), None
    )
    valuation_message = next(
        (msg for msg in state["messages"] if msg.name == "valuation_agent"), None
    )

    default_signal = json.dumps(
        {"signal": "neutral", "confidence": 0.5, "reasoning": "No data available"}
    )
    if not technical_message:
        technical_message = HumanMessage(content=default_signal, name="technical_analyst_agent")
    if not fundamentals_message:
        fundamentals_message = HumanMessage(content=default_signal, name="fundamentals_agent")
    if not sentiment_message:
        sentiment_message = HumanMessage(content=default_signal, name="sentiment_agent")
    if not valuation_message:
        valuation_message = HumanMessage(content=default_signal, name="valuation_agent")

    try:
        fundamental_signals = json.loads(fundamentals_message.content)
        technical_signals = json.loads(technical_message.content)
        sentiment_signals = json.loads(sentiment_message.content)
        valuation_signals = json.loads(valuation_message.content)
    except Exception:
        fundamental_signals = ast.literal_eval(fundamentals_message.content)
        technical_signals = ast.literal_eval(technical_message.content)
        sentiment_signals = ast.literal_eval(sentiment_message.content)
        valuation_signals = ast.literal_eval(valuation_message.content)

    bullish_points = []
    weighted_scores = []
    signal_strengths = []
    technical_semantics = "relative_valuation_pb_percentile"
    sentiment_semantics = "market_news_sentiment"

    weights = {
        "fundamental": 0.35,
        "technical": 0.25,
        "valuation": 0.25,
        "sentiment": 0.15,
    }

    def _parse_confidence(confidence_value):
        if isinstance(confidence_value, str):
            try:
                return float(confidence_value.replace("%", "")) / 100
            except ValueError:
                return 0.0
        try:
            return float(confidence_value) if confidence_value is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    # Relative valuation (PB percentile)
    tech_conf = _parse_confidence(technical_signals.get("confidence", 0))
    tech_signal = technical_signals.get("signal", "neutral")
    if tech_signal == "bullish":
        bullish_points.append(
            f"Relative valuation looks attractive (PB percentile), confidence {tech_conf:.1%}."
        )
        weighted_scores.append(tech_conf * weights["technical"])
        signal_strengths.append(tech_conf)
    elif tech_signal == "neutral":
        bullish_points.append("Relative valuation is near fair value; room for selective accumulation.")
        weighted_scores.append(0.60 * weights["technical"])
        signal_strengths.append(0.60)
    else:
        if tech_conf < 0.6:
            bullish_points.append("Valuation pressure is moderate; potential mean-reversion opportunity remains.")
            weighted_scores.append(0.45 * weights["technical"])
            signal_strengths.append(0.45)
        else:
            bullish_points.append("Valuation is expensive, but long-term quality names can still be tracked.")
            weighted_scores.append(0.30 * weights["technical"])
            signal_strengths.append(0.30)

    # Fundamentals
    fund_conf = _parse_confidence(fundamental_signals.get("confidence", 0))
    fund_signal = fundamental_signals.get("signal", "neutral")
    if fund_signal == "bullish":
        bullish_points.append(f"Fundamentals remain solid, confidence {fund_conf:.1%}.")
        weighted_scores.append(fund_conf * weights["fundamental"])
        signal_strengths.append(fund_conf)
    elif fund_signal == "neutral":
        bullish_points.append("Fundamentals are stable; upside depends on next earnings catalyst.")
        weighted_scores.append(0.55 * weights["fundamental"])
        signal_strengths.append(0.55)
    else:
        bullish_points.append("Fundamentals are weak, but improvement potential should be monitored.")
        weighted_scores.append((0.35 if fund_conf < 0.5 else 0.20) * weights["fundamental"])
        signal_strengths.append(0.35 if fund_conf < 0.5 else 0.20)

    # Valuation
    val_conf = _parse_confidence(valuation_signals.get("confidence", 0))
    val_signal = valuation_signals.get("signal", "neutral")
    if val_signal == "bullish":
        bullish_points.append(f"DCF valuation indicates margin of safety, confidence {val_conf:.1%}.")
        weighted_scores.append(val_conf * weights["valuation"])
        signal_strengths.append(val_conf)
    elif val_signal == "neutral":
        bullish_points.append("Valuation is broadly fair and supports hold/add decisions.")
        weighted_scores.append(0.50 * weights["valuation"])
        signal_strengths.append(0.50)
    else:
        bullish_points.append("Valuation is stretched; position sizing should stay conservative.")
        weighted_scores.append(0.35 * weights["valuation"])
        signal_strengths.append(0.35)

    # Market sentiment
    sent_conf = _parse_confidence(sentiment_signals.get("confidence", 0))
    sent_signal = sentiment_signals.get("signal", "neutral")
    if sent_signal == "bullish":
        bullish_points.append(f"Market sentiment is supportive, confidence {sent_conf:.1%}.")
        weighted_scores.append(sent_conf * weights["sentiment"])
        signal_strengths.append(sent_conf)
    elif sent_signal == "neutral":
        bullish_points.append("Market sentiment is balanced and does not block long allocation.")
        weighted_scores.append(0.55 * weights["sentiment"])
        signal_strengths.append(0.55)
    else:
        bullish_points.append("Sentiment is cautious; contrarian entry opportunities may appear.")
        weighted_scores.append(0.50 * weights["sentiment"])
        signal_strengths.append(0.50)

    weighted_confidence = sum(weighted_scores)
    spread = max(signal_strengths) - min(signal_strengths) if signal_strengths else 0.0
    signal_consistency = max(0.6, 1 - spread * 0.3)
    avg_confidence = min(max(weighted_confidence * signal_consistency, 0.0), 0.95)

    logic_parts = []
    if max(signal_strengths) > 0.7:
        logic_parts.append("High-conviction signals exist across key dimensions")
    if "policy" in str(fundamental_signals).lower():
        logic_parts.append("policy direction may support the investment thesis")
    if min(signal_strengths) > 0.4:
        logic_parts.append("signal mix is relatively balanced for A-share volatility")
    investment_logic = "; ".join(logic_parts) if logic_parts else "composite signals still indicate potential upside"

    message_content = {
        "agent_type": "llm",
        "perspective": "bullish",
        "confidence": avg_confidence,
        "thesis_points": bullish_points,
        "technical_signal_semantics": technical_semantics,
        "sentiment_signal_semantics": sentiment_semantics,
        "reasoning": f"Bullish thesis under A-share context: {investment_logic}.",
        "signal_weights": weights,
        "signal_consistency": signal_consistency,
        "ashare_factors": {
            "policy_sensitivity": "policy" in str(fundamental_signals).lower(),
            "liquidity_risk": technical_signals.get("volume_analysis", {}).get("liquidity_score", 0.5),
            "institutional_flow": sentiment_signals.get("institutional_sentiment", 0.5),
        },
    }

    message = HumanMessage(
        content=json.dumps(message_content, ensure_ascii=False),
        name="researcher_bull_agent",
    )

    if show_reasoning:
        show_agent_reasoning(message_content, "Bullish Researcher")

    state["metadata"]["researcher_bull_reasoning"] = message_content
    show_workflow_status("Bullish Researcher", "completed")

    result_metadata = state["metadata"].copy()
    result_metadata["researcher_bull_reasoning"] = message_content
    updated_data = dict(state["data"])
    agent_outputs = _ensure_agent_outputs(updated_data)
    agent_outputs["researcher_bull"] = message_content

    return {
        "messages": [message],
        "data": updated_data,
        "metadata": result_metadata,
    }
