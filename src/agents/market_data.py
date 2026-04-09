from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

import pandas as pd
from langchain_core.messages import HumanMessage

from src.agents.state import (
    AgentState,
    maybe_return_ablation_stub,
    show_agent_reasoning,
    show_workflow_status,
)
from src.tools.api import (
    calculate_comprehensive_financial_metrics,
    get_financial_metrics,
    get_financial_statements,
    get_market_data,
    get_price_history,
)
from src.utils.api_utils import agent_endpoint
from src.utils.logging_config import setup_logger

logger = setup_logger("market_data_agent")


def _is_truthy_env_var(env_var: str) -> bool:
    value = os.getenv(env_var)
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _ensure_agent_outputs(data: dict[str, object]) -> dict[str, object]:
    agent_outputs = data.get("agent_outputs")
    if not isinstance(agent_outputs, dict):
        agent_outputs = {}
    data["agent_outputs"] = agent_outputs
    return agent_outputs


@agent_endpoint("market_data", "Market data collection and preprocessing")
def market_data_agent(state: AgentState):
    """Gather and normalize market/financial inputs for downstream agents."""
    show_workflow_status("Market Data Agent")
    show_reasoning = state["metadata"]["show_reasoning"]
    data = state["data"]

    ablation_result = maybe_return_ablation_stub(
        state,
        agent_key="market_data",
        agent_type="data_layer",
        message_name="market_data_agent",
        output_key="market_data",
        payload_overrides={
            "ticker": data.get("ticker") or data.get("stock_symbol"),
            "start_date": data.get("start_date"),
            "end_date": data.get("end_date"),
            "data_collected": {
                "price_history": False,
                "financial_metrics": False,
                "financial_statements": False,
                "market_data": False,
            },
            "summary": "Ablation disabled market_data agent. Using empty deterministic payload.",
        },
    )
    if ablation_result is not None:
        payload = json.loads(ablation_result["messages"][0].content)
        ablation_result["data"].update(
            {
                "prices": [],
                "financial_metrics": [{}],
                "financial_line_items": [{}],
                "market_cap": 0,
                "market_data": {"market_cap": 0},
                "start_date": data.get("start_date"),
                "end_date": data.get("end_date"),
            }
        )
        ablation_result["data"]["agent_outputs"]["market_data"] = payload
        return ablation_result

    current_date = datetime.now()
    yesterday = current_date - timedelta(days=1)
    end_date = data.get("end_date") or yesterday.strftime("%Y-%m-%d")

    end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
    if end_date_obj > yesterday:
        end_date_obj = yesterday
        end_date = yesterday.strftime("%Y-%m-%d")

    if not data.get("start_date"):
        start_date = (end_date_obj - timedelta(days=365)).strftime("%Y-%m-%d")
    else:
        start_date = data["start_date"]

    ticker = data.get("ticker") or data.get("stock_symbol")
    backtest_mode = _is_truthy_env_var("ASHAREAGENT_BACKTEST_MODE")

    prices_df = get_price_history(
        ticker,
        start_date,
        end_date,
        provider_preference="local_csv",
        local_only=backtest_mode,
    )
    if prices_df is None or prices_df.empty:
        logger.warning(
            f"Warning: no price data for {ticker}, proceeding with empty fallback dataset"
        )
        prices_df = pd.DataFrame(columns=["close", "open", "high", "low", "volume"])

    if backtest_mode:
        logger.info("Backtest mode enabled: skip remote financial metrics fetch")
        financial_metrics = [{}]
        logger.info("Backtest mode enabled: skip remote financial statements fetch")
        financial_line_items = [{}]
        logger.info("Backtest mode enabled: skip remote market data fetch")
        market_data = {"market_cap": 0}
    else:
        try:
            financial_metrics = get_financial_metrics(ticker)
        except Exception as exc:
            logger.error(f"Failed to fetch financial metrics: {exc}")
            financial_metrics = [{}]

        try:
            financial_line_items = get_financial_statements(ticker)
        except Exception as exc:
            logger.error(f"Failed to fetch financial statements: {exc}")
            financial_line_items = [{}]

        try:
            market_data = get_market_data(ticker)
        except Exception as exc:
            logger.error(f"Failed to fetch market data: {exc}")
            market_data = {"market_cap": 0}

    try:
        logger.info("Computing comprehensive financial metrics from all available data sources...")
        enhanced_metrics = calculate_comprehensive_financial_metrics(
            symbol=ticker,
            financial_statements=financial_line_items,
            financial_indicators=financial_metrics,
            market_data=market_data,
        )

        if enhanced_metrics:
            if financial_metrics and len(financial_metrics) > 0:
                financial_metrics[0].update(enhanced_metrics)
            else:
                financial_metrics = [enhanced_metrics]
            logger.info("Financial metrics enhanced with calculated ratios")
    except Exception as exc:
        logger.error(f"Enhanced financial metrics calculation failed: {exc}")

    if not isinstance(prices_df, pd.DataFrame):
        prices_df = pd.DataFrame(columns=["close", "open", "high", "low", "volume"])

    prices_dict = prices_df.to_dict("records")

    market_data_summary = {
        "ticker": ticker,
        "start_date": start_date,
        "end_date": end_date,
        "data_collected": {
            "price_history": len(prices_dict) > 0,
            "financial_metrics": len(financial_metrics) > 0,
            "financial_statements": len(financial_line_items) > 0,
            "market_data": len(market_data) > 0,
        },
        "summary": (
            f"Collected market data for {ticker} from {start_date} to {end_date}, "
            "including price history, financial metrics, and market profile."
        ),
    }

    if show_reasoning:
        show_agent_reasoning(market_data_summary, "Market Data Agent")
        state["metadata"]["agent_reasoning"] = market_data_summary

    message = HumanMessage(
        content=json.dumps(market_data_summary, ensure_ascii=False),
        name="market_data_agent",
    )

    updated_data = {
        **data,
        "prices": prices_dict,
        "start_date": start_date,
        "end_date": end_date,
        "financial_metrics": financial_metrics,
        "financial_line_items": financial_line_items,
        "market_cap": market_data.get("market_cap", 0),
        "market_data": market_data,
    }
    agent_outputs = _ensure_agent_outputs(updated_data)
    agent_outputs["market_data"] = market_data_summary

    return {
        "messages": [message],
        "data": updated_data,
        "metadata": state["metadata"],
    }
