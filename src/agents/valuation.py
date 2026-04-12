from __future__ import annotations

import json
import math
from typing import Any

from langchain_core.messages import HumanMessage

from src.agents.state import (
    AgentState,
    _ensure_agent_outputs,
    maybe_return_ablation_stub,
    show_agent_reasoning,
    show_workflow_status,
)
from src.utils.api_utils import agent_endpoint
from src.utils.logging_config import setup_logger

logger = setup_logger("valuation_agent")


def _safe_number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except (TypeError, ValueError):
        return default


def _estimate_stage1_growth_rate(
    current_fcf: float,
    previous_fcf: float,
    fallback_growth_candidates: list[float],
) -> float:
    if current_fcf > 0 and previous_fcf > 0:
        # CAGR = (Ending / Beginning)^(1/n) - 1, here n=1 year proxy.
        cagr = (current_fcf / previous_fcf) - 1
    else:
        cagr = 0.05
        for candidate in fallback_growth_candidates:
            if candidate is not None:
                cagr = candidate
                break

    # Guide requirement: stage-1 growth has a 20% upper bound.
    return min(max(cagr, -0.20), 0.20)


def _two_stage_dcf(
    base_free_cash_flow: float,
    stage1_growth_rate: float,
    discount_rate: float = 0.10,
    terminal_growth_rate: float = 0.03,
    years: int = 5,
) -> tuple[float, list[dict[str, float]], float]:
    if base_free_cash_flow <= 0:
        return 0.0, [], 0.0

    discounted_yearly_cashflows: list[dict[str, float]] = []
    year_n_cashflow = base_free_cash_flow

    for year in range(1, years + 1):
        # Stage 1: forecast FCF_t = FCF_0 * (1+g)^t.
        year_n_cashflow = base_free_cash_flow * ((1 + stage1_growth_rate) ** year)
        # Discount PV_t = FCF_t / (1+r)^t.
        present_value = year_n_cashflow / ((1 + discount_rate) ** year)
        discounted_yearly_cashflows.append(
            {
                "year": float(year),
                "projected_fcf": float(year_n_cashflow),
                "discounted_fcf": float(present_value),
            }
        )

    if discount_rate <= terminal_growth_rate:
        terminal_value = year_n_cashflow * 12.0
    else:
        # Gordon growth: TV = FCF_(n+1) / (r-g).
        terminal_value = (year_n_cashflow * (1 + terminal_growth_rate)) / (
            discount_rate - terminal_growth_rate
        )
    terminal_present_value = terminal_value / ((1 + discount_rate) ** years)
    intrinsic_value = sum(item["discounted_fcf"] for item in discounted_yearly_cashflows) + terminal_present_value

    return intrinsic_value, discounted_yearly_cashflows, terminal_present_value


def _margin_assessment(margin_of_safety: float) -> str:
    if margin_of_safety >= 0.35:
        return "高"
    if margin_of_safety >= 0.15:
        return "中"
    if margin_of_safety >= 0.0:
        return "低"
    return "负"


def _signal_from_margin(margin_of_safety: float) -> str:
    if margin_of_safety > 0.15:
        return "bullish"
    if margin_of_safety < -0.15:
        return "bearish"
    return "neutral"


def _confidence_from_margin(margin_of_safety: float) -> str:
    confidence = max(0.35, min(abs(margin_of_safety), 0.95))
    return f"{round(confidence * 100)}%"




@agent_endpoint("valuation", "DCF估值分析师（定量模型）")
def valuation_agent(state: AgentState):
    show_workflow_status("Valuation Agent")
    show_reasoning = state["metadata"]["show_reasoning"]
    data = state["data"]

    ablation_result = maybe_return_ablation_stub(
        state,
        agent_key="valuation",
        agent_type="quantitative_model",
        message_name="valuation_agent",
        output_key="valuation",
        data_key="valuation_analysis",
    )
    if ablation_result is not None:
        return ablation_result

    financial_metrics = data.get("financial_metrics", [{}])
    line_items = data.get("financial_line_items", [{}, {}])
    market_cap = _safe_number(data.get("market_cap"), 0.0)

    latest = line_items[0] if len(line_items) > 0 else {}
    previous = line_items[1] if len(line_items) > 1 else {}
    metrics = financial_metrics[0] if financial_metrics else {}

    latest_fcf = _safe_number(latest.get("free_cash_flow"), 0.0)
    previous_fcf = _safe_number(previous.get("free_cash_flow"), 0.0)

    if latest_fcf <= 0:
        # Conservative fallback when free cash flow is unavailable.
        latest_net_income = _safe_number(latest.get("net_income"), 0.0)
        latest_fcf = max(latest_net_income * 0.7, 0.0)

    fallback_growth_candidates = [
        _safe_number(metrics.get("earnings_growth"), None),
        _safe_number(metrics.get("revenue_growth"), None),
        0.05,
    ]
    stage1_growth_rate = _estimate_stage1_growth_rate(
        latest_fcf,
        previous_fcf,
        fallback_growth_candidates,
    )

    intrinsic_value, discounted_cashflows, discounted_terminal_value = _two_stage_dcf(
        latest_fcf,
        stage1_growth_rate,
        discount_rate=0.10,
        terminal_growth_rate=0.03,
        years=5,
    )

    has_core_inputs = latest_fcf > 0 and market_cap > 0 and intrinsic_value > 0
    if has_core_inputs:
        margin_of_safety = (intrinsic_value - market_cap) / market_cap
        margin_assessment = _margin_assessment(margin_of_safety)
        signal = _signal_from_margin(margin_of_safety)
        confidence = _confidence_from_margin(margin_of_safety)
        reasoning = (
            f"两阶段DCF测算内在价值={intrinsic_value:,.2f}，当前市值={market_cap:,.2f}，"
            f"安全边际={margin_of_safety:.2%}（{margin_assessment}）。"
        )
        data_quality = "正常"
    else:
        margin_of_safety = None
        margin_assessment = "数据不足"
        signal = "neutral"
        confidence = "30%"
        reasoning = (
            "估值所需关键数据不足（自由现金流或市值缺失/无效），"
            "因此DCF结论降级为中性。"
        )
        data_quality = "数据不足"

    message_content = {
        "agent_type": "quantitative_model",
        "signal": signal,
        "confidence": confidence,
        "intrinsic_value": round(intrinsic_value, 2),
        "market_cap": round(market_cap, 2),
        "margin_of_safety": round(margin_of_safety, 4) if margin_of_safety is not None else None,
        "margin_of_safety_assessment": margin_assessment,
        "data_quality": data_quality,
        "assumptions": {
            "stage1_years": 5,
            "stage1_growth_rate": round(stage1_growth_rate, 4),
            "terminal_growth_rate": 0.03,
            "discount_rate": 0.10,
            "base_free_cash_flow": round(latest_fcf, 2),
        },
        "discounted_cashflows": discounted_cashflows,
        "discounted_terminal_value": round(discounted_terminal_value, 2),
        "reasoning": reasoning,
    }

    message = HumanMessage(
        content=json.dumps(message_content, ensure_ascii=False),
        name="valuation_agent",
    )

    updated_data = dict(data)
    agent_outputs = _ensure_agent_outputs(updated_data)
    agent_outputs["valuation"] = message_content
    updated_data["valuation_analysis"] = message_content

    if show_reasoning:
        show_agent_reasoning(message_content, "Valuation Analysis Agent")
    state["metadata"]["agent_reasoning"] = message_content

    show_workflow_status("Valuation Agent", "completed")
    return {
        "messages": [message],
        "data": updated_data,
        "metadata": state["metadata"],
    }

