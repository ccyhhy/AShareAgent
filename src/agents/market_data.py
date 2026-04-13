from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

import pandas as pd
from langchain_core.messages import HumanMessage

from src.agents.state import (
    AgentState,
    _ensure_agent_outputs,
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


def _has_meaningful_financial_metrics(financial_metrics: list[dict]) -> bool:
    if not financial_metrics:
        return False
    first = financial_metrics[0] if isinstance(financial_metrics[0], dict) else {}
    if not isinstance(first, dict):
        return False
    for value in first.values():
        if isinstance(value, (int, float)) and value not in (0, 0.0):
            return True
    return False


def _has_meaningful_financial_statements(financial_line_items: list[dict]) -> bool:
    if not financial_line_items:
        return False
    for row in financial_line_items[:2]:
        if not isinstance(row, dict):
            continue
        for key in ("revenue", "net_income", "free_cash_flow"):
            value = row.get(key)
            if isinstance(value, (int, float)) and value not in (0, 0.0):
                return True
    return False


def _has_meaningful_market_data(market_data: dict) -> bool:
    if not isinstance(market_data, dict) or not market_data:
        return False
    for key in ("current_price", "market_cap", "volume"):
        value = market_data.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return True
    return False


def _extract_latest_close(prices_df: pd.DataFrame) -> tuple[float | None, str | None]:
    if not isinstance(prices_df, pd.DataFrame) or prices_df.empty or "close" not in prices_df.columns:
        return None, None

    valid_rows = prices_df.dropna(subset=["close"])
    if valid_rows.empty:
        return None, None

    last_row = valid_rows.iloc[-1]
    close_value = last_row.get("close")
    if not isinstance(close_value, (int, float)):
        try:
            close_value = float(close_value)
        except (TypeError, ValueError):
            return None, None

    date_value = last_row.get("date")
    if isinstance(date_value, pd.Timestamp):
        price_as_of = date_value.strftime("%Y-%m-%d")
    elif isinstance(date_value, datetime):
        price_as_of = date_value.strftime("%Y-%m-%d")
    elif date_value is None:
        price_as_of = None
    else:
        price_as_of = str(date_value)[:10]

    return float(close_value), price_as_of


def _extract_market_cap(financial_metrics: list[dict]) -> float | None:
    if not financial_metrics:
        return None
    first = financial_metrics[0] if isinstance(financial_metrics[0], dict) else {}
    if not isinstance(first, dict):
        return None
    value = first.get("market_cap")
    return value if isinstance(value, (int, float)) and value > 0 else None




@agent_endpoint("market_data", "市场数据收集与预处理")
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
            "critical_data_complete": False,
            "missing_critical_data": [
                "financial_metrics",
                "financial_statements",
                "market_data",
            ],
            "summary": "Ablation 已禁用 market_data 节点，使用确定性空载荷。",
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

    if not isinstance(market_data, dict):
        market_data = {}

    latest_available_price, price_as_of = _extract_latest_close(prices_df)
    if latest_available_price is not None:
        market_data["current_price"] = latest_available_price
        market_data["price_source"] = "latest_close"
        market_data["price_is_realtime"] = False
        if price_as_of:
            market_data["price_as_of"] = price_as_of

    market_cap_value = market_data.get("market_cap")
    if not isinstance(market_cap_value, (int, float)) or market_cap_value <= 0:
        fallback_market_cap = _extract_market_cap(financial_metrics)
        if fallback_market_cap is not None:
            market_cap_value = fallback_market_cap
            market_data["market_cap"] = fallback_market_cap
        else:
            market_cap_value = 0

    prices_dict = prices_df.to_dict("records")

    price_ok = len(prices_dict) > 0
    metrics_ok = _has_meaningful_financial_metrics(financial_metrics)
    statements_ok = _has_meaningful_financial_statements(financial_line_items)
    market_ok = _has_meaningful_market_data(market_data)

    missing_components = []
    if not price_ok:
        missing_components.append("price_history")
    if not metrics_ok:
        missing_components.append("financial_metrics")
    if not statements_ok:
        missing_components.append("financial_statements")
    if not market_ok:
        missing_components.append("market_data")

    component_labels = {
        "price_history": "价格历史",
        "financial_metrics": "财务指标",
        "financial_statements": "财务报表",
        "market_data": "市场行情",
    }
    missing_components_cn = [component_labels.get(item, item) for item in missing_components]

    if missing_components:
        summary = (
            f"已完成 {ticker} 在 {start_date} 至 {end_date} 区间的部分数据采集。"
            f"缺失项：{', '.join(missing_components_cn)}。"
        )
    else:
        summary = (
            f"已完成 {ticker} 在 {start_date} 至 {end_date} 区间的数据采集，"
            "包含价格历史、财务指标、财务报表与市场画像。"
        )

    if latest_available_price is not None and price_as_of:
        summary += f" 价格统一按最近可用收盘价口径处理（{price_as_of}，{latest_available_price:.2f}）。"

    coverage_ratio = round(
        (4 - len(missing_components)) / 4,
        2,
    )

    critical_data_complete = metrics_ok and statements_ok and market_ok

    market_data_summary = {
        "agent_type": "data_layer",
        "signal": "neutral",
        "confidence": f"{int(coverage_ratio * 100)}%",
        "ticker": ticker,
        "start_date": start_date,
        "end_date": end_date,
        "data_collected": {
            "price_history": price_ok,
            "financial_metrics": metrics_ok,
            "financial_statements": statements_ok,
            "market_data": market_ok,
        },
        "critical_data_complete": critical_data_complete,
        "missing_critical_data": [
            component
            for component in missing_components
            if component in {"financial_metrics", "financial_statements", "market_data"}
        ],
        "latest_available_price": market_data.get("current_price"),
        "price_source": market_data.get("price_source"),
        "price_as_of": market_data.get("price_as_of"),
        "price_is_realtime": market_data.get("price_is_realtime", False),
        "data_quality": {
            "missing_components": missing_components,
            "missing_components_readable": missing_components_cn,
            "coverage_ratio": coverage_ratio,
        },
        "reasoning": summary,
        "summary": summary,
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
        "market_cap": market_cap_value,
        "market_data": market_data,
        "critical_data_complete": critical_data_complete,
        "missing_critical_data": market_data_summary["missing_critical_data"],
    }
    agent_outputs = _ensure_agent_outputs(updated_data)
    agent_outputs["market_data"] = market_data_summary

    return {
        "messages": [message],
        "data": updated_data,
        "metadata": state["metadata"],
    }

