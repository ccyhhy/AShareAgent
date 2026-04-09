import ast
import json

from langchain_core.messages import HumanMessage

from src.agents.state import AgentState, show_agent_reasoning, show_workflow_status
from src.utils.api_utils import agent_endpoint


@agent_endpoint(
    "researcher_bear",
    "Bear-side researcher, builds risk thesis from first-layer agent signals.",
)
def researcher_bear_agent(state: AgentState):
    """Analyze first-layer signals from a bearish perspective."""
    show_workflow_status("Bearish Researcher")
    show_reasoning = state["metadata"]["show_reasoning"]

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

    bearish_points = []
    weighted_scores = []
    risk_factors = []
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
    if tech_signal == "bearish":
        bearish_points.append(
            f"Relative valuation shows overvaluation risk (PB percentile), confidence {tech_conf:.1%}."
        )
        weighted_scores.append(tech_conf * weights["technical"])
        risk_factors.append("valuation_position_risk")
        if tech_conf > 0.8:
            risk_factors.append("limit_down_risk")
    elif tech_signal == "bullish":
        bearish_points.append("Strong valuation rebound may trigger pullback risk after sentiment overheating.")
        weighted_scores.append(0.60 * weights["technical"])
        risk_factors.append("pullback_risk")
    else:
        bearish_points.append("Relative valuation is mixed; downside tail risk still needs monitoring.")
        weighted_scores.append(0.40 * weights["technical"])

    # Fundamentals
    fund_conf = _parse_confidence(fundamental_signals.get("confidence", 0))
    fund_signal = fundamental_signals.get("signal", "neutral")
    if fund_signal == "bearish":
        bearish_points.append(f"Fundamentals deteriorate with confidence {fund_conf:.1%}.")
        weighted_scores.append(fund_conf * weights["fundamental"])
        risk_factors.append("fundamental_risk")
        if "policy" in str(fundamental_signals).lower():
            risk_factors.append("policy_risk")
    elif fund_signal == "bullish":
        bearish_points.append("Strong fundamentals are priced in; earnings-disappointment risk remains.")
        weighted_scores.append(0.45 * weights["fundamental"])
        risk_factors.append("expectation_risk")
    else:
        bearish_points.append("Fundamentals are neutral; growth durability still uncertain.")
        weighted_scores.append(0.35 * weights["fundamental"])

    # Valuation
    val_conf = _parse_confidence(valuation_signals.get("confidence", 0))
    val_signal = valuation_signals.get("signal", "neutral")
    if val_signal == "bearish":
        bearish_points.append(f"DCF valuation indicates downside pressure, confidence {val_conf:.1%}.")
        weighted_scores.append(val_conf * weights["valuation"])
        risk_factors.append("valuation_risk")
    elif val_signal == "bullish":
        bearish_points.append("Valuation upside depends on perfect execution; repricing risk should be considered.")
        weighted_scores.append(0.40 * weights["valuation"])
    else:
        bearish_points.append("Valuation is fair, leaving limited buffer if macro shocks occur.")
        weighted_scores.append(0.35 * weights["valuation"])

    # Market sentiment
    sent_conf = _parse_confidence(sentiment_signals.get("confidence", 0))
    sent_signal = sentiment_signals.get("signal", "neutral")
    if sent_signal == "bearish":
        bearish_points.append(f"Market sentiment is weak, confidence {sent_conf:.1%}.")
        weighted_scores.append(sent_conf * weights["sentiment"])
        risk_factors.append("sentiment_risk")
    elif sent_signal == "bullish":
        bearish_points.append("Sentiment overheating can become euphoria risk.")
        weighted_scores.append(0.70 * weights["sentiment"])
        risk_factors.append("euphoria_risk")
    else:
        bearish_points.append("Neutral sentiment offers limited downside protection in volatility spikes.")
        weighted_scores.append(0.30 * weights["sentiment"])

    weighted_confidence = sum(weighted_scores)
    risk_concentration = min(1.0, len(set(risk_factors)) / 4.0)
    avg_confidence = min(max(weighted_confidence * (1 + risk_concentration * 0.2), 0.0), 0.95)

    logic_parts = []
    if "limit_down_risk" in risk_factors:
        logic_parts.append("technical drawdown risk may accelerate")
    if "policy_risk" in risk_factors:
        logic_parts.append("policy uncertainty may pressure valuation")
    if "euphoria_risk" in risk_factors:
        logic_parts.append("sentiment overheating increases reversal probability")
    if len(set(risk_factors)) >= 3:
        logic_parts.append("multiple risks are stacking")
    risk_logic = "; ".join(logic_parts) if logic_parts else "downside risks are still non-trivial"

    message_content = {
        "perspective": "bearish",
        "confidence": avg_confidence,
        "thesis_points": bearish_points,
        "technical_signal_semantics": technical_semantics,
        "sentiment_signal_semantics": sentiment_semantics,
        "reasoning": f"Bearish thesis under A-share context: {risk_logic}.",
        "risk_weights": weights,
        "risk_factors": sorted(set(risk_factors)),
        "risk_concentration": risk_concentration,
        "ashare_risks": {
            "limit_down_risk": "limit_down_risk" in risk_factors,
            "policy_sensitivity": "policy_risk" in risk_factors,
            "liquidity_crunch": technical_signals.get("volume_analysis", {}).get("liquidity_stress", False),
            "margin_pressure": sentiment_signals.get("margin_sentiment", 0.5) > 0.7,
        },
    }

    message = HumanMessage(
        content=json.dumps(message_content, ensure_ascii=False),
        name="researcher_bear",
    )

    if show_reasoning:
        show_agent_reasoning(message_content, "Bearish Researcher")

    state["metadata"]["researcher_bear_reasoning"] = message_content
    show_workflow_status("Bearish Researcher", "completed")

    result_metadata = state["metadata"].copy()
    result_metadata["researcher_bear_reasoning"] = message_content

    return {
        "messages": state["messages"] + [message],
        "data": state["data"],
        "metadata": result_metadata,
    }
