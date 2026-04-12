from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd
from langchain_core.messages import HumanMessage

from src.agents.state import (
    AgentState,
    _ensure_agent_outputs,
    maybe_return_ablation_stub,
    show_agent_reasoning,
    show_workflow_status,
)
from src.tools.api import prices_to_df
from src.utils.api_utils import agent_endpoint
from src.utils.logging_config import setup_logger

logger = setup_logger("risk_management_agent")
LOT_SIZE = 100


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number) or math.isinf(number):
        return default
    return number


def _max_buy_quantity_from_value(max_buy_value: float, current_price: float, lot_size: int = LOT_SIZE) -> int:
    if current_price <= 0 or max_buy_value <= 0:
        return 0
    raw_quantity = int(max_buy_value // current_price)
    if lot_size > 1:
        return (raw_quantity // lot_size) * lot_size
    return max(raw_quantity, 0)


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




@agent_endpoint("risk_management", "Risk management analyst (statistical model)")
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
            "max_total_position_value": 0.0,
            "remaining_position_value_capacity": 0.0,
            "current_price": None,
            "max_buy_quantity": 0,
            "quantity_lot_size": LOT_SIZE,
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
        cash_available = _safe_float(portfolio.get("cash", 0.0), 0.0)
        latest_price = (
            _safe_float(prices_df["close"].iloc[-1], 0.0)
            if not prices_df.empty and "close" in prices_df.columns
            else 0.0
        )
        current_stock_value = _safe_float(portfolio.get("stock", 0.0), 0.0) * latest_price
        total_portfolio_value = cash_available + current_stock_value
        max_position = 0.35
        max_total_position_value = total_portfolio_value * max_position
        remaining_position_value_capacity = max(max_total_position_value - current_stock_value, 0.0)
        max_buy_value = min(cash_available, remaining_position_value_capacity)
        max_buy_quantity = _max_buy_quantity_from_value(max_buy_value, latest_price, LOT_SIZE)

        message_content = {
            "agent_type": "statistical_model",
            "signal": "neutral",
            "confidence": "40%",
            "risk_score": 50.0,
            "margin_of_safety_score": 50.0,
            "max_position": max_position,
            "max_position_size": round(max_total_position_value, 2),
            "max_total_position_value": round(max_total_position_value, 2),
            "remaining_position_value_capacity": round(remaining_position_value_capacity, 2),
            "current_price": round(latest_price, 4) if latest_price > 0 else None,
            "max_buy_quantity": max_buy_quantity,
            "quantity_lot_size": LOT_SIZE,
            "trading_action": "hold",
            "risk_metrics": {
                "annualized_volatility": None,
                "max_drawdown": None,
                "value_at_risk_95": None,
                "sharpe_ratio": None,
            },
            "reasoning": "价格历史样本不足，无法稳定估计统计风险。",
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
        cash_available = _safe_float(portfolio.get("cash", 0.0), 0.0)
        total_portfolio_value = float(cash_available + current_stock_value)

        max_position = _position_cap_from_risk_score(risk_score)
        max_total_position_value = total_portfolio_value * max_position
        remaining_position_value_capacity = max(max_total_position_value - current_stock_value, 0.0)
        max_buy_value = min(cash_available, remaining_position_value_capacity)
        max_buy_quantity = _max_buy_quantity_from_value(max_buy_value, latest_price, LOT_SIZE)

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
            "max_position_size": round(max_total_position_value, 2),
            "max_total_position_value": round(max_total_position_value, 2),
            "remaining_position_value_capacity": round(remaining_position_value_capacity, 2),
            "current_price": round(latest_price, 4),
            "max_buy_quantity": int(max_buy_quantity),
            "quantity_lot_size": LOT_SIZE,
            "trading_action": trading_action,
            "risk_metrics": {
                "annualized_volatility": round(annualized_volatility, 4),
                "max_drawdown": round(max_drawdown, 4),
                "value_at_risk_95": round(value_at_risk_95, 4),
                "sharpe_ratio": round(float(sharpe_ratio), 4),
            },
            "reasoning": (
                f"风险评分={risk_score:.2f}，年化波动率={annualized_volatility:.2%}，"
                f"最大回撤={max_drawdown:.2%}，VaR95={value_at_risk_95:.2%}，夏普比率={sharpe_ratio:.2f}；"
                f"可买上限={max_buy_quantity}股。"
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

