from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from src.agents.market_data import market_data_agent

try:
    import langchain_core  # noqa: F401
except ModuleNotFoundError:
    LANGCHAIN_CORE_AVAILABLE = False
else:
    LANGCHAIN_CORE_AVAILABLE = True


def _make_state() -> dict:
    return {
        "messages": [],
        "data": {
            "ticker": "600519",
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        },
        "metadata": {"show_reasoning": False},
    }


@pytest.mark.skipif(
    not LANGCHAIN_CORE_AVAILABLE,
    reason="langchain_core is not installed in this environment",
)
def test_market_data_agent_uses_local_first_price_history_and_preserves_output_shape():
    prices = pd.DataFrame(
        [
            {
                "date": "2024-01-02",
                "open": 100.0,
                "high": 101.0,
                "low": 99.5,
                "close": 100.5,
                "volume": 123456,
            }
        ]
    )

    with patch("src.agents.market_data.get_price_history", return_value=prices) as mock_price_history, patch(
        "src.agents.market_data.get_financial_metrics",
        return_value=[{"pe_ratio": 20.0}],
    ), patch(
        "src.agents.market_data.get_financial_statements",
        return_value=[{"revenue": 1000.0}],
    ), patch(
        "src.agents.market_data.get_market_data",
        return_value={"market_cap": 123456789},
    ), patch(
        "src.agents.market_data.calculate_comprehensive_financial_metrics",
        return_value={"net_margin": 0.25},
    ):
        result = market_data_agent(_make_state())

    mock_price_history.assert_called_once_with(
        "600519",
        "2024-01-01",
        "2024-01-31",
        provider_preference="local_csv",
        local_only=False,
    )

    assert result["messages"][-1].name == "market_data_agent"
    content = result["messages"][-1].content
    assert "600519" in content
    assert result["data"]["prices"] == prices.to_dict("records")
    assert result["data"]["financial_metrics"] == [{"pe_ratio": 20.0, "net_margin": 0.25}]
    assert result["data"]["financial_line_items"] == [{"revenue": 1000.0}]
    assert result["data"]["market_cap"] == 123456789
    assert result["data"]["market_data"] == {"market_cap": 123456789}
    assert result["data"]["start_date"] == "2024-01-01"
    assert result["data"]["end_date"] == "2024-01-31"
    assert result["data"]["agent_outputs"]["market_data"]["ticker"] == "600519"
    assert result["data"]["agent_outputs"]["market_data"]["start_date"] == "2024-01-01"
    assert result["data"]["agent_outputs"]["market_data"]["critical_data_complete"] is True
    assert result["data"]["agent_outputs"]["market_data"]["missing_critical_data"] == []
    assert result["data"]["critical_data_complete"] is True
    assert result["data"]["missing_critical_data"] == []


@pytest.mark.skipif(
    not LANGCHAIN_CORE_AVAILABLE,
    reason="langchain_core is not installed in this environment",
)
def test_market_data_agent_skips_remote_financial_calls_in_backtest_mode():
    prices = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

    with patch.dict("os.environ", {"ASHAREAGENT_BACKTEST_MODE": "1"}, clear=False):
        with patch("src.agents.market_data.get_price_history", return_value=prices) as mock_price_history, patch(
            "src.agents.market_data.get_financial_metrics",
            side_effect=AssertionError("financial metrics should not be called in backtest mode"),
        ), patch(
            "src.agents.market_data.get_financial_statements",
            side_effect=AssertionError("financial statements should not be called in backtest mode"),
        ), patch(
            "src.agents.market_data.get_market_data",
            side_effect=AssertionError("market data should not be called in backtest mode"),
        ), patch(
            "src.agents.market_data.calculate_comprehensive_financial_metrics",
            return_value={},
        ):
            result = market_data_agent(_make_state())

    mock_price_history.assert_called_once_with(
        "600519",
        "2024-01-01",
        "2024-01-31",
        provider_preference="local_csv",
        local_only=True,
    )
    assert result["data"]["financial_metrics"] == [{}]
    assert result["data"]["financial_line_items"] == [{}]
    assert result["data"]["market_data"] == {"market_cap": 0}
    assert result["data"]["agent_outputs"]["market_data"]["ticker"] == "600519"
    assert result["data"]["agent_outputs"]["market_data"]["critical_data_complete"] is False
    assert result["data"]["agent_outputs"]["market_data"]["missing_critical_data"] == [
        "financial_metrics",
        "financial_statements",
        "market_data",
    ]
    assert result["data"]["critical_data_complete"] is False
