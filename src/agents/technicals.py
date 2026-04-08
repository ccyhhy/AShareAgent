# 规则引擎型异构Agent
from __future__ import annotations

import json
from typing import Any

import pandas as pd
from langchain_core.messages import HumanMessage

from src.agents.state import AgentState, show_agent_reasoning, show_workflow_status
from src.tools.local_csv_provider import LocalCSVProvider
from src.utils.api_utils import agent_endpoint
from src.utils.logging_config import setup_logger

logger = setup_logger("technical_analyst_agent")


def _score_pb_percentile(percentile: float) -> int:
    if percentile < 20:
        return 90
    if percentile < 40:
        return 70
    if percentile < 60:
        return 50
    if percentile > 80:
        return 10
    return 30


def _signal_from_score(score: int) -> str:
    if score >= 70:
        return "bullish"
    if score <= 30:
        return "bearish"
    return "neutral"


def _confidence_from_score(score: int) -> str:
    confidence = max(0.35, min(abs(score - 50) / 50, 0.95))
    return f"{round(confidence * 100)}%"


def _ensure_agent_outputs(data: dict[str, Any]) -> dict[str, Any]:
    agent_outputs = data.get("agent_outputs")
    if not isinstance(agent_outputs, dict):
        agent_outputs = {}
    data["agent_outputs"] = agent_outputs
    return agent_outputs


@agent_endpoint("technical_analyst", "估值分析师（规则引擎），基于PB历史百分位输出估值信号")
def technical_analyst_agent(state: AgentState):
    show_workflow_status("Technical Analyst")
    show_reasoning = state["metadata"]["show_reasoning"]
    data = state["data"]
    ticker = data.get("ticker") or data.get("stock_symbol")

    message_content: dict[str, Any]
    if not ticker:
        message_content = {
            "agent_type": "rule_engine",
            "signal": "neutral",
            "confidence": "35%",
            "reasoning": "Missing ticker in state data.",
            "pb_percentile_5y": None,
            "pb_current": None,
            "valuation_score": 50,
        }
    else:
        provider = LocalCSVProvider()
        pb_history = provider.get_pb_history(str(ticker))
        pb_history = pb_history.copy()

        if pb_history.empty or "pb" not in pb_history.columns or "date" not in pb_history.columns:
            message_content = {
                "agent_type": "rule_engine",
                "signal": "neutral",
                "confidence": "35%",
                "reasoning": f"No PB history found in local CSV for {ticker}.",
                "pb_percentile_5y": None,
                "pb_current": None,
                "valuation_score": 50,
            }
        else:
            pb_history["pb"] = pd.to_numeric(pb_history["pb"], errors="coerce")
            pb_history = pb_history.dropna(subset=["date", "pb"]).sort_values("date")

            if (pb_history["pb"] > 0).any():
                pb_history = pb_history.loc[pb_history["pb"] > 0]

            end_date = pd.to_datetime(data.get("end_date"), errors="coerce")
            if pd.isna(end_date):
                end_date = pb_history["date"].max()
            start_date = end_date - pd.DateOffset(years=5)
            lookback = pb_history.loc[pb_history["date"] >= start_date]

            if lookback.empty:
                lookback = pb_history

            current_pb = float(lookback["pb"].iloc[-1])
            pb_percentile_5y = float((lookback["pb"] <= current_pb).mean() * 100)
            valuation_score = _score_pb_percentile(pb_percentile_5y)
            signal = _signal_from_score(valuation_score)
            confidence = _confidence_from_score(valuation_score)

            message_content = {
                "agent_type": "rule_engine",
                "signal": signal,
                "confidence": confidence,
                "reasoning": (
                    f"PB 5Y percentile={pb_percentile_5y:.2f}%, "
                    f"current PB={current_pb:.4f}, valuation_score={valuation_score}."
                ),
                "pb_percentile_5y": round(pb_percentile_5y, 2),
                "pb_current": round(current_pb, 4),
                "valuation_score": valuation_score,
                "sample_size": int(len(lookback)),
            }

    message = HumanMessage(
        content=json.dumps(message_content, ensure_ascii=False),
        name="technical_analyst_agent",
    )

    updated_data = dict(data)
    agent_outputs = _ensure_agent_outputs(updated_data)
    agent_outputs["technicals"] = message_content
    updated_data["technical_analysis"] = message_content

    if show_reasoning:
        show_agent_reasoning(message_content, "Technical Analysis")
    state["metadata"]["agent_reasoning"] = message_content

    show_workflow_status("Technical Analyst", "completed")
    return {
        "messages": [message],
        "data": updated_data,
        "metadata": state["metadata"],
    }
