import ast
import json

from langchain_core.messages import HumanMessage

from src.agents.state import (
    AgentState,
    _ensure_agent_outputs,
    maybe_return_ablation_stub,
    show_agent_reasoning,
    show_workflow_status,
)
from src.utils.api_utils import agent_endpoint




@agent_endpoint(
    "researcher_bear",
    "Bear-side researcher, builds risk thesis from first-layer agent signals.",
)
def researcher_bear_agent(state: AgentState):
    """Analyze first-layer signals from a bearish perspective."""
    show_workflow_status("Bearish Researcher")
    show_reasoning = state["metadata"]["show_reasoning"]

    ablation_result = maybe_return_ablation_stub(
        state,
        agent_key="researcher_bear",
        agent_type="llm",
        message_name="researcher_bear",
        output_key="researcher_bear",
        payload_overrides={
            "perspective": "bearish",
            "confidence": 0.5,
            "thesis_points": ["Ablation disabled bearish researcher; neutral risk stance applied."],
            "technical_signal_semantics": "relative_valuation_pb_percentile",
            "sentiment_signal_semantics": "market_news_sentiment",
            "risk_weights": {
                "fundamental": 0.35,
                "technical": 0.25,
                "valuation": 0.25,
                "sentiment": 0.15,
            },
            "risk_factors": [],
            "risk_concentration": 0.0,
            "ashare_risks": {
                "limit_down_risk": False,
                "policy_sensitivity": False,
                "liquidity_crunch": False,
                "margin_pressure": False,
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
        {"signal": "neutral", "confidence": 0.5, "reasoning": "暂无可用数据"}
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
            f"相对估值（PB分位）显示高估风险，置信度 {tech_conf:.1%}。"
        )
        weighted_scores.append(tech_conf * weights["technical"])
        risk_factors.append("valuation_position_risk")
        if tech_conf > 0.8:
            risk_factors.append("limit_down_risk")
    elif tech_signal == "bullish":
        bearish_points.append("估值修复过快后，若情绪过热可能触发回撤风险。")
        weighted_scores.append(0.60 * weights["technical"])
        risk_factors.append("pullback_risk")
    else:
        bearish_points.append("相对估值信号分化，下行尾部风险仍需跟踪。")
        weighted_scores.append(0.40 * weights["technical"])

    # Fundamentals
    fund_conf = _parse_confidence(fundamental_signals.get("confidence", 0))
    fund_signal = fundamental_signals.get("signal", "neutral")
    if fund_signal == "bearish":
        bearish_points.append(f"基本面走弱，置信度 {fund_conf:.1%}。")
        weighted_scores.append(fund_conf * weights["fundamental"])
        risk_factors.append("fundamental_risk")
        if "policy" in str(fundamental_signals).lower():
            risk_factors.append("policy_risk")
    elif fund_signal == "bullish":
        bearish_points.append("较强基本面可能已被定价，仍需警惕业绩不及预期风险。")
        weighted_scores.append(0.45 * weights["fundamental"])
        risk_factors.append("expectation_risk")
    else:
        bearish_points.append("基本面中性，增长持续性仍有不确定性。")
        weighted_scores.append(0.35 * weights["fundamental"])

    # Valuation
    val_conf = _parse_confidence(valuation_signals.get("confidence", 0))
    val_signal = valuation_signals.get("signal", "neutral")
    if val_signal == "bearish":
        bearish_points.append(f"DCF估值显示下行压力，置信度 {val_conf:.1%}。")
        weighted_scores.append(val_conf * weights["valuation"])
        risk_factors.append("valuation_risk")
    elif val_signal == "bullish":
        bearish_points.append("估值上行依赖较强执行兑现，需考虑再定价风险。")
        weighted_scores.append(0.40 * weights["valuation"])
    else:
        bearish_points.append("估值大体合理，面对宏观冲击时缓冲有限。")
        weighted_scores.append(0.35 * weights["valuation"])

    # Market sentiment
    sent_conf = _parse_confidence(sentiment_signals.get("confidence", 0))
    sent_signal = sentiment_signals.get("signal", "neutral")
    if sent_signal == "bearish":
        bearish_points.append(f"市场情绪偏弱，置信度 {sent_conf:.1%}。")
        weighted_scores.append(sent_conf * weights["sentiment"])
        risk_factors.append("sentiment_risk")
    elif sent_signal == "bullish":
        bearish_points.append("情绪过热可能演化为乐观透支风险。")
        weighted_scores.append(0.70 * weights["sentiment"])
        risk_factors.append("euphoria_risk")
    else:
        bearish_points.append("中性情绪在波动放大阶段的下行保护有限。")
        weighted_scores.append(0.30 * weights["sentiment"])

    weighted_confidence = sum(weighted_scores)
    risk_concentration = min(1.0, len(set(risk_factors)) / 4.0)
    avg_confidence = min(max(weighted_confidence * (1 + risk_concentration * 0.2), 0.0), 0.95)

    logic_parts = []
    if "limit_down_risk" in risk_factors:
        logic_parts.append("技术面回撤风险可能加速")
    if "policy_risk" in risk_factors:
        logic_parts.append("政策不确定性可能压制估值")
    if "euphoria_risk" in risk_factors:
        logic_parts.append("情绪过热提升反转概率")
    if len(set(risk_factors)) >= 3:
        logic_parts.append("多重风险正在叠加")
    risk_logic = "；".join(logic_parts) if logic_parts else "下行风险仍不可忽视"

    message_content = {
        "agent_type": "llm",
        "perspective": "bearish",
        "confidence": avg_confidence,
        "thesis_points": bearish_points,
        "technical_signal_semantics": technical_semantics,
        "sentiment_signal_semantics": sentiment_semantics,
        "reasoning": f"A股语境下的空头观点：{risk_logic}。",
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
    updated_data = dict(state["data"])
    agent_outputs = _ensure_agent_outputs(updated_data)
    agent_outputs["researcher_bear"] = message_content

    return {
        "messages": [message],
        "data": updated_data,
        "metadata": result_metadata,
    }

