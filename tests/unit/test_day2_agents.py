from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

try:
    import langchain_core  # noqa: F401
except ModuleNotFoundError:
    LANGCHAIN_CORE_AVAILABLE = False
    risk_management_agent = None
    technical_analyst_agent = None
    valuation_agent = None
    LocalCSVProvider = None
else:
    LANGCHAIN_CORE_AVAILABLE = True

    from src.agents.risk_manager import risk_management_agent
    from src.agents.technicals import technical_analyst_agent
    from src.agents.valuation import valuation_agent
    from src.tools.local_csv_provider import LocalCSVProvider


def _make_state(data: dict, *, messages: list | None = None) -> dict:
    return {
        "messages": list(messages or []),
        "data": data,
        "metadata": {"show_reasoning": False},
    }


@pytest.mark.skipif(not LANGCHAIN_CORE_AVAILABLE, reason="langchain_core is not installed in this environment")
def test_technical_agent_uses_pb_percentile_and_standardized_output():
    pb_history = pd.DataFrame(
        {
            "date": pd.to_datetime(
                [
                    "2020-12-31",
                    "2021-12-31",
                    "2022-12-31",
                    "2023-12-31",
                    "2024-12-31",
                ]
            ),
            "pb": [1.0, 2.0, 3.0, 4.0, 5.0],
            "ts_code": ["000001.SZ"] * 5,
        }
    )
    state = _make_state(
        {
            "ticker": "000001",
            "end_date": "2024-12-31",
            "metadata": {"source": "unit-test"},
        }
    )

    with patch.object(LocalCSVProvider, "get_pb_history", return_value=pb_history) as mock_get_pb:
        result = technical_analyst_agent(state)

    assert mock_get_pb.called
    assert result["messages"][0].name == "technical_analyst_agent"

    assert "agent_outputs" in result["data"]
    agent_output = result["data"]["agent_outputs"]["technicals"]
    assert agent_output["agent_type"] == "rule_engine"
    assert agent_output["analysis_domain"] == "relative_valuation"
    assert agent_output["analysis_metric"] == "pb_percentile_5y"
    assert "pb_percentile_5y" in agent_output
    assert "valuation_score" in agent_output
    assert result["data"]["technical_analysis"] == agent_output
    assert result["data"]["relative_valuation_analysis"] == agent_output


@pytest.mark.skipif(not LANGCHAIN_CORE_AVAILABLE, reason="langchain_core is not installed in this environment")
def test_valuation_agent_writes_quantitative_model_output():
    state = _make_state(
        {
            "financial_line_items": [
                {
                    "free_cash_flow": 120.0,
                    "net_income": 150.0,
                },
                {
                    "free_cash_flow": 100.0,
                    "net_income": 130.0,
                },
            ],
            "financial_metrics": [
                {
                    "earnings_growth": 0.15,
                    "revenue_growth": 0.10,
                }
            ],
            "market_cap": 1000.0,
        }
    )

    result = valuation_agent(state)

    assert result["messages"][0].name == "valuation_agent"

    assert "agent_outputs" in result["data"]
    agent_output = result["data"]["agent_outputs"]["valuation"]
    assert agent_output["agent_type"] == "quantitative_model"
    assert "intrinsic_value" in agent_output
    assert "margin_of_safety" in agent_output
    assert "assumptions" in agent_output
    assert isinstance(agent_output["assumptions"], dict)
    assert result["data"]["valuation_analysis"] == agent_output


@pytest.mark.skipif(not LANGCHAIN_CORE_AVAILABLE, reason="langchain_core is not installed in this environment")
def test_risk_manager_writes_statistical_model_output():
    prices = []
    for idx, close in enumerate(
        [
            10.0,
            10.2,
            10.1,
            10.4,
            10.6,
            10.5,
            10.8,
            11.0,
            10.9,
            11.1,
            11.3,
            11.2,
            11.4,
            11.6,
            11.5,
            11.8,
            12.0,
            11.9,
            12.1,
            12.3,
            12.2,
            12.4,
            12.6,
            12.5,
            12.8,
            13.0,
            12.9,
            13.1,
            13.3,
            13.2,
        ]
    ):
        prices.append(
            {
                "date": f"2024-01-{idx + 1:02d}",
                "open": close - 0.1,
                "high": close + 0.2,
                "low": close - 0.3,
                "close": close,
                "volume": 100000 + idx * 1000,
            }
        )

    state = _make_state(
        {
            "prices": prices,
            "portfolio": {"cash": 5000.0, "stock": 100.0},
        }
    )

    result = risk_management_agent(state)

    assert result["messages"][-1].name == "risk_management_agent"

    assert "agent_outputs" in result["data"]
    agent_output = result["data"]["agent_outputs"]["risk_manager"]
    assert agent_output["agent_type"] == "statistical_model"
    assert "risk_score" in agent_output
    assert "margin_of_safety_score" in agent_output
    assert "max_position" in agent_output
    assert "max_position_size" in agent_output
    assert result["data"]["risk_analysis"] == agent_output
