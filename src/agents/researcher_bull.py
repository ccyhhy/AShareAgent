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
        message_name="researcher_bull",
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

    bullish_points = []
    weighted_scores = []
    signal_strengths = []
    technical_semantics = "relative_valuation_pb_percentile"
    sentiment_semantics = "market_news_sentiment"
    data_section = state.get("data", {})
    raw_critical_data_complete = data_section.get("critical_data_complete")
    critical_data_complete = True if raw_critical_data_complete is None else bool(raw_critical_data_complete)
    missing_critical_data = list(data_section.get("missing_critical_data", []))

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
            f"相对估值（PB分位）处于偏低区间，具备吸引力，置信度 {tech_conf:.1%}。"
        )
        weighted_scores.append(tech_conf * weights["technical"])
        signal_strengths.append(tech_conf)
    elif tech_signal == "neutral":
        bullish_points.append("相对估值接近合理区间，可择机分批布局。")
        weighted_scores.append(0.60 * weights["technical"])
        signal_strengths.append(0.60)
    else:
        if tech_conf < 0.6:
            bullish_points.append("估值压力中等，仍存在均值回归后的配置机会。")
            weighted_scores.append(0.45 * weights["technical"])
            signal_strengths.append(0.45)
        else:
            bullish_points.append("估值偏高，但长期优质标的仍可持续跟踪并等待配置机会。")
            weighted_scores.append(0.30 * weights["technical"])
            signal_strengths.append(0.30)

    # Fundamentals
    fund_conf = _parse_confidence(fundamental_signals.get("confidence", 0))
    fund_signal = fundamental_signals.get("signal", "neutral")
    if fund_signal == "bullish":
        bullish_points.append(f"基本面整体稳健，置信度 {fund_conf:.1%}。")
        weighted_scores.append(fund_conf * weights["fundamental"])
        signal_strengths.append(fund_conf)
    elif fund_signal == "neutral":
        bullish_points.append("基本面保持稳定，上行空间取决于下一阶段业绩催化。")
        weighted_scores.append(0.55 * weights["fundamental"])
        signal_strengths.append(0.55)
    else:
        bullish_points.append("基本面偏弱，但仍需关注后续改善弹性与修复机会。")
        weighted_scores.append((0.35 if fund_conf < 0.5 else 0.20) * weights["fundamental"])
        signal_strengths.append(0.35 if fund_conf < 0.5 else 0.20)

    # Valuation
    val_conf = _parse_confidence(valuation_signals.get("confidence", 0))
    val_signal = valuation_signals.get("signal", "neutral")
    if val_signal == "bullish":
        bullish_points.append(f"DCF估值显示存在安全边际，置信度 {val_conf:.1%}。")
        weighted_scores.append(val_conf * weights["valuation"])
        signal_strengths.append(val_conf)
    elif val_signal == "neutral":
        bullish_points.append("估值整体合理，支持持有或小幅加仓。")
        weighted_scores.append(0.50 * weights["valuation"])
        signal_strengths.append(0.50)
    else:
        bullish_points.append("估值偏高，仓位管理应保持谨慎。")
        weighted_scores.append(0.35 * weights["valuation"])
        signal_strengths.append(0.35)

    # Market sentiment
    sent_conf = _parse_confidence(sentiment_signals.get("confidence", 0))
    sent_signal = sentiment_signals.get("signal", "neutral")
    if sent_signal == "bullish":
        bullish_points.append(f"市场情绪偏正面，置信度 {sent_conf:.1%}。")
        weighted_scores.append(sent_conf * weights["sentiment"])
        signal_strengths.append(sent_conf)
    elif sent_signal == "neutral":
        bullish_points.append("市场情绪中性，不构成做多阻碍。")
        weighted_scores.append(0.55 * weights["sentiment"])
        signal_strengths.append(0.55)
    else:
        bullish_points.append("市场情绪偏谨慎，可能带来逆向布局窗口。")
        weighted_scores.append(0.50 * weights["sentiment"])
        signal_strengths.append(0.50)

    weighted_confidence = sum(weighted_scores)
    spread = max(signal_strengths) - min(signal_strengths) if signal_strengths else 0.0
    signal_consistency = max(0.6, 1 - spread * 0.3)
    avg_confidence = min(max(weighted_confidence * signal_consistency, 0.0), 0.95)

    if not critical_data_complete:
        bullish_points = [
            f"关键数据缺失（{', '.join(missing_critical_data) if missing_critical_data else 'financial_metrics'}），当前不形成可靠多头论证。"
        ]
        signal_consistency = min(signal_consistency, 0.5)
        avg_confidence = min(avg_confidence, 0.25)
        investment_logic = "关键数据缺失，关键财务/市场数据不足，多头结论主动降级"
    else:
        logic_parts = []
        if max(signal_strengths) > 0.7:
            logic_parts.append("关键维度存在高置信支持信号")
        if "policy" in str(fundamental_signals).lower():
            logic_parts.append("政策方向可能对投资逻辑形成支撑")
        if min(signal_strengths) > 0.4:
            logic_parts.append("在A股波动特征下，信号组合相对均衡")
        investment_logic = "；".join(logic_parts) if logic_parts else "综合信号仍显示一定上行潜力"

    message_content = {
        "agent_type": "llm",
        "perspective": "bullish",
        "confidence": avg_confidence,
        "thesis_points": bullish_points,
        "technical_signal_semantics": technical_semantics,
        "sentiment_signal_semantics": sentiment_semantics,
        "reasoning": f"A股语境下的多头观点：{investment_logic}。",
        "data_sufficiency": {
            "critical_data_complete": critical_data_complete,
            "missing_critical_data": missing_critical_data,
        },
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
        name="researcher_bull",
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

