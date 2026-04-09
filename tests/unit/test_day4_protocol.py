from __future__ import annotations

from unittest.mock import patch

import pytest

try:
    import langchain_core  # noqa: F401
except ModuleNotFoundError:
    LANGCHAIN_CORE_AVAILABLE = False
    fundamentals_agent = None
    sentiment_agent = None
    macro_analyst_agent = None
else:
    LANGCHAIN_CORE_AVAILABLE = True

    from backend.services.analysis import (
        _extract_agent_results_from_state,
        _fill_missing_agent_results_from_api_state,
    )
    from src.agents.fundamentals import fundamentals_agent
    from src.agents.macro_analyst import macro_analyst_agent
    from src.agents.sentiment import sentiment_agent


def _base_state() -> dict:
    return {
        "messages": [],
        "data": {
            "ticker": "000001",
            "financial_metrics": [
                {
                    "return_on_equity": 0.18,
                    "net_margin": 0.22,
                    "operating_margin": 0.17,
                    "revenue_growth": 0.12,
                    "earnings_growth": 0.16,
                    "book_value_growth": 0.11,
                    "current_ratio": 1.8,
                    "debt_to_equity": 0.3,
                    "free_cash_flow_per_share": 4.2,
                    "earnings_per_share": 4.5,
                    "pe_ratio": 18,
                    "price_to_book": 2.1,
                    "price_to_sales": 3.2,
                }
            ],
            "num_of_news": 5,
            "end_date": "2024-12-31",
        },
        "metadata": {"show_reasoning": False},
    }


@pytest.mark.skipif(not LANGCHAIN_CORE_AVAILABLE, reason="langchain_core is not installed in this environment")
def test_extract_agent_results_from_state_prefers_stable_agent_outputs():
    raw_result = {
        "data": {
            "agent_outputs": {
                "technicals": {"signal": "bullish", "confidence": "70%"},
                "risk_manager": {"signal": "bearish", "risk_score": 72.5},
            }
        }
    }

    extracted = _extract_agent_results_from_state(raw_result)

    assert extracted == {
        "technicals": {"signal": "bullish", "confidence": "70%"},
        "risk_manager": {"signal": "bearish", "risk_score": 72.5},
    }


@pytest.mark.skipif(not LANGCHAIN_CORE_AVAILABLE, reason="langchain_core is not installed in this environment")
def test_extract_agent_results_from_state_supports_relative_valuation_legacy_alias():
    raw_result = {
        "data": {
            "relative_valuation_analysis": {"signal": "neutral", "confidence": "55%"},
        }
    }

    extracted = _extract_agent_results_from_state(raw_result)

    assert extracted == {
        "technicals": {"signal": "neutral", "confidence": "55%"},
    }


@pytest.mark.skipif(not LANGCHAIN_CORE_AVAILABLE, reason="langchain_core is not installed in this environment")
def test_fill_missing_agent_results_from_api_state_keeps_existing_and_normalizes_aliases():
    existing = {
        "technicals": {"signal": "bullish", "confidence": "70%"},
    }
    all_agents = {
        "technical_analyst": {
            "latest": {
                "technical_analyst_reasoning": {"signal": "bearish", "confidence": "90%"}
            }
        },
        "fundamentals": {
            "latest": {
                "fundamentals_reasoning": {"signal": "neutral", "confidence": "50%"}
            }
        },
        "researcher_bull": {
            "latest": {
                "researcher_bull_reasoning": {
                    "perspective": "bullish",
                    "confidence": 0.73,
                    "thesis_points": ["example thesis"],
                }
            }
        },
        "risk_management": {
            "latest": {
                "risk_management_reasoning": {"signal": "bearish", "risk_score": 88.0}
            }
        },
    }

    merged = _fill_missing_agent_results_from_api_state(
        agent_results=existing,
        candidate_agent_names=["technical_analyst", "fundamentals", "researcher_bull", "risk_management"],
        all_agents=all_agents,
    )

    assert merged["technicals"]["signal"] == "bullish"
    assert merged["fundamentals"]["signal"] == "neutral"
    assert merged["researcher_bull"]["perspective"] == "bullish"
    assert merged["risk_manager"]["risk_score"] == 88.0


@pytest.mark.skipif(not LANGCHAIN_CORE_AVAILABLE, reason="langchain_core is not installed in this environment")
def test_fundamentals_agent_writes_stable_agent_outputs():
    result = fundamentals_agent(_base_state())

    assert result["data"]["agent_outputs"]["fundamentals"]["signal"] in {"bullish", "neutral", "bearish"}
    assert result["data"]["fundamental_analysis"] == result["data"]["agent_outputs"]["fundamentals"]


@pytest.mark.skipif(not LANGCHAIN_CORE_AVAILABLE, reason="langchain_core is not installed in this environment")
def test_sentiment_agent_writes_stable_agent_outputs():
    state = _base_state()
    mock_news = [
        {
            "title": "Positive catalyst",
            "content": "Demand improved strongly.",
            "publish_time": "2026-04-07 10:00:00",
        }
    ]

    with patch("src.agents.sentiment.get_stock_news", return_value=mock_news), patch(
        "src.agents.sentiment.get_news_sentiment", return_value=0.82
    ):
        result = sentiment_agent(state)

    agent_output = result["data"]["agent_outputs"]["sentiment"]
    assert agent_output["signal"] == "bullish"
    assert agent_output["sentiment_score"] == 0.82
    assert agent_output["analysis_domain"] == "market_sentiment"
    assert agent_output["analysis_metric"] == "news_sentiment_score_7d"
    assert agent_output["news_window_days"] == 7
    assert result["data"]["sentiment_analysis"] == agent_output


@pytest.mark.skipif(not LANGCHAIN_CORE_AVAILABLE, reason="langchain_core is not installed in this environment")
def test_macro_analyst_agent_writes_stable_agent_outputs():
    state = _base_state()
    mock_news = [
        {
            "title": "Macro policy support",
            "content": "Liquidity conditions are improving.",
            "publish_time": "2026-04-07 12:00:00",
        }
    ]
    mock_analysis = {
        "macro_environment": "positive",
        "impact_on_stock": "positive",
        "key_factors": ["policy_support"],
        "reasoning": "Policy support and liquidity are improving.",
    }

    with patch("src.agents.macro_analyst.get_stock_news", return_value=mock_news), patch(
        "src.agents.macro_analyst.get_macro_news_analysis", return_value=mock_analysis
    ):
        result = macro_analyst_agent(state)

    agent_output = result["data"]["agent_outputs"]["macro_analyst"]
    assert agent_output["macro_environment"] == "positive"
    assert agent_output["impact_on_stock"] == "positive"
    assert agent_output["key_factors"] == ["policy_support"]
    assert agent_output["reasoning"] == "Policy support and liquidity are improving."
    assert agent_output["signal"] == "bullish"
    assert agent_output["confidence"] == "65%"
    assert agent_output["agent_type"] == "llm"
    assert agent_output["analysis_domain"] == "macro_cycle_policy"
    assert result["data"]["macro_analysis"] == agent_output
