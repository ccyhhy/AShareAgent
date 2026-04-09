from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd
from langchain_core.messages import HumanMessage

from src.agents.state import (
    AgentState,
    maybe_return_ablation_stub,
    show_agent_reasoning,
    show_workflow_status,
)
from src.tools.api import prices_to_df
from src.utils.api_utils import agent_endpoint
from src.utils.logging_config import setup_logger

logger = setup_logger("risk_management_agent")


def _to_confidence(sample_size: int) -> str:
    confidence = max(0.40, min(sample_size / 252, 0.95))
    return f"{round(confidence * 100)}%"


def _position_cap_from_risk_score(risk_score: float) -> float:
    if risk_score >= 80:
        return 0.15
    if risk_score >= 65:
        return 0.25
    if risk_score >= 50:
        return 0.35
    if risk_score >= 35:
        return 0.50
    return 0.65


def _signal_from_risk(risk_score: float) -> str:
    if risk_score >= 60:
        return "bearish"
    if risk_score <= 35:
        return "bullish"
    return "neutral"


def _ensure_agent_outputs(data: dict[str, Any]) -> dict[str, Any]:
    agent_outputs = data.get("agent_outputs")
    if not isinstance(agent_outputs, dict):
        agent_outputs = {}
    data["agent_outputs"] = agent_outputs
    return agent_outputs


@agent_endpoint("risk_management", "安全边际/风险评估分析师（统计模型）")
def risk_management_agent(state: AgentState):
    show_workflow_status("Risk Manager")
    show_reasoning = state["metadata"]["show_reasoning"]
    data = state["data"]
    portfolio = data.get("portfolio", {"cash": 0.0, "stock": 0.0})

    ablation_result = maybe_return_ablation_stub(
        state,
        agent_key="risk_management",
        agent_type="statistical_model",
        message_name="risk_management_agent",
        output_key="risk_manager",
        data_key="risk_analysis",
        payload_overrides={
            "risk_score": 50.0,
            "margin_of_safety_score": 50.0,
            "max_position": 0.35,
            "max_position_size": 0.0,
            "trading_action": "hold",
            "risk_metrics": {
                "annualized_volatility": None,
                "max_drawdown": None,
                "value_at_risk_95": None,
                "sharpe_ratio": None,
            },
        },
    )
    if ablation_result is not None:
        return ablation_result

    prices_df = prices_to_df(data.get("prices", []))
    if "close" not in prices_df.columns:
        prices_df["close"] = np.nan
    prices_df["close"] = pd.to_numeric(prices_df["close"], errors="coerce")
    prices_df = prices_df.dropna(subset=["close"]).reset_index(drop=True)

    if prices_df.empty or len(prices_df) < 20:
        message_content = {
            "agent_type": "statistical_model",
            "signal": "neutral",
            "confidence": "40%",
            "risk_score": 50.0,
            "margin_of_safety_score": 50.0,
            "max_position": 0.35,
            "max_position_size": 0.0,
            "trading_action": "hold",
            "risk_metrics": {
                "annualized_volatility": None,
                "max_drawdown": None,
                "value_at_risk_95": None,
                "sharpe_ratio": None,
            },
            "reasoning": "Insufficient price history for statistical risk estimation.",
        }
    else:
        close = prices_df["close"].astype(float)
        returns = close.pct_change().dropna()

        annualized_volatility = float(returns.std() * np.sqrt(252))
        rolling_peak = close.cummax()
        drawdown_series = close / rolling_peak - 1.0
        max_drawdown = float(drawdown_series.min())
        value_at_risk_95 = float(returns.quantile(0.05))

        annualized_return = float(returns.mean() * 252)
        volatility_denom = float(returns.std() * np.sqrt(252))
        if volatility_denom > 0:
            sharpe_ratio = (annualized_return - 0.02) / volatility_denom
        else:
            sharpe_ratio = 0.0

        volatility_component = np.clip((annualized_volatility - 0.15) / 0.45, 0, 1)
        drawdown_component = np.clip(abs(max_drawdown) / 0.50, 0, 1)
        var_component = np.clip(abs(value_at_risk_95) / 0.08, 0, 1)
        sharpe_component = np.clip((1.5 - sharpe_ratio) / 2.5, 0, 1)

        risk_score = float(
            (0.35 * volatility_component + 0.30 * drawdown_component + 0.20 * var_component + 0.15 * sharpe_component)
            * 100
        )
        margin_of_safety_score = float(np.clip(100 - risk_score, 0, 100))

        latest_price = float(close.iloc[-1])
        current_stock_value = float(portfolio.get("stock", 0) * latest_price)
        total_portfolio_value = float(portfolio.get("cash", 0) + current_stock_value)

        max_position = _position_cap_from_risk_score(risk_score)
        max_position_size = total_portfolio_value * max_position

        if risk_score >= 80:
            trading_action = "reduce_aggressively"
        elif risk_score >= 65:
            trading_action = "reduce"
        elif risk_score >= 50:
            trading_action = "hold_or_reduce"
        else:
            trading_action = "normal_positioning"

        message_content = {
            "agent_type": "statistical_model",
            "signal": _signal_from_risk(risk_score),
            "confidence": _to_confidence(len(returns)),
            "risk_score": round(risk_score, 2),
            "margin_of_safety_score": round(margin_of_safety_score, 2),
            "max_position": round(max_position, 2),
            "max_position_size": round(max_position_size, 2),
            "trading_action": trading_action,
            "risk_metrics": {
                "annualized_volatility": round(annualized_volatility, 4),
                "max_drawdown": round(max_drawdown, 4),
                "value_at_risk_95": round(value_at_risk_95, 4),
                "sharpe_ratio": round(float(sharpe_ratio), 4),
            },
            "reasoning": (
                f"risk_score={risk_score:.2f}, volatility={annualized_volatility:.2%}, "
                f"max_drawdown={max_drawdown:.2%}, VaR95={value_at_risk_95:.2%}, Sharpe={sharpe_ratio:.2f}."
            ),
        }

    message = HumanMessage(
        content=json.dumps(message_content, ensure_ascii=False),
        name="risk_management_agent",
    )

    updated_data = dict(data)
    agent_outputs = _ensure_agent_outputs(updated_data)
    agent_outputs["risk_manager"] = message_content
    updated_data["risk_analysis"] = message_content

    if show_reasoning:
        show_agent_reasoning(message_content, "Risk Management Agent")
    state["metadata"]["agent_reasoning"] = message_content

    show_workflow_status("Risk Manager", "completed")
    return {
        "messages": [message],
        "data": updated_data,
        "metadata": state["metadata"],
    }
