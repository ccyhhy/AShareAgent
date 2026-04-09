from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

try:
    import langchain_core  # noqa: F401
except ModuleNotFoundError:
    LANGCHAIN_CORE_AVAILABLE = False
    technical_analyst_agent = None
    valuation_agent = None
    risk_management_agent = None
    LocalCSVProvider = None
else:
    LANGCHAIN_CORE_AVAILABLE = True

    from src.agents.risk_manager import risk_management_agent
    from src.agents.technicals import technical_analyst_agent
    from src.agents.valuation import valuation_agent
    from src.tools.local_csv_provider import LocalCSVProvider


def _make_day3_state() -> dict:
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

    return {
        "messages": [],
        "data": {
            "ticker": "000001",
            "end_date": "2024-12-31",
            "market_cap": 1000.0,
            "financial_metrics": [
                {
                    "earnings_growth": 0.15,
                    "revenue_growth": 0.10,
                }
            ],
            "financial_line_items": [
                {"free_cash_flow": 120.0, "net_income": 150.0},
                {"free_cash_flow": 100.0, "net_income": 130.0},
            ],
            "prices": prices,
            "portfolio": {"cash": 5000.0, "stock": 100.0},
        },
        "metadata": {"show_reasoning": False},
    }


@pytest.mark.skipif(not LANGCHAIN_CORE_AVAILABLE, reason="langchain_core is not installed in this environment")
def test_day3_non_llm_agents_accumulate_standardized_outputs():
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

    state = _make_day3_state()

    with patch.object(LocalCSVProvider, "get_pb_history", return_value=pb_history):
        technical_state = technical_analyst_agent(state)

    assert technical_state["data"]["agent_outputs"]["technicals"]["agent_type"] == "rule_engine"
    assert set(technical_state["data"]["agent_outputs"]) == {"technicals"}

    valuation_state = valuation_agent(technical_state)
    assert valuation_state["data"]["agent_outputs"]["valuation"]["agent_type"] == "quantitative_model"
    assert set(valuation_state["data"]["agent_outputs"]) == {"technicals", "valuation"}

    risk_state = risk_management_agent(valuation_state)
    assert risk_state["data"]["agent_outputs"]["risk_manager"]["agent_type"] == "statistical_model"
    assert set(risk_state["data"]["agent_outputs"]) == {"technicals", "valuation", "risk_manager"}

    assert risk_state["data"]["technical_analysis"] == risk_state["data"]["agent_outputs"]["technicals"]
    assert risk_state["data"]["valuation_analysis"] == risk_state["data"]["agent_outputs"]["valuation"]
    assert risk_state["data"]["risk_analysis"] == risk_state["data"]["agent_outputs"]["risk_manager"]
