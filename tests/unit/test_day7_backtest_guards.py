from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

try:
    from langchain_core.messages import HumanMessage
except ModuleNotFoundError:
    LANGCHAIN_CORE_AVAILABLE = False
else:
    LANGCHAIN_CORE_AVAILABLE = True
    from src.agents import debate_room as debate_module
    from src.agents import macro_news_agent as macro_news_module
    from src.agents import portfolio_manager as portfolio_module
    from src.agents import sentiment as sentiment_module


def _base_state() -> dict:
    return {
        "messages": [],
        "data": {
            "ticker": "000001",
            "portfolio": {"cash": 100000.0, "stock": 0},
            "num_of_news": 5,
            "end_date": "2026-04-08",
            "macro_news_analysis_result": "N/A",
        },
        "metadata": {"show_reasoning": False},
    }


@pytest.mark.skipif(not LANGCHAIN_CORE_AVAILABLE, reason="langchain_core is not installed in this environment")
def test_sentiment_agent_backtest_mode_skips_remote_calls(monkeypatch):
    state = _base_state()
    monkeypatch.setenv("ASHAREAGENT_BACKTEST_MODE", "1")
    monkeypatch.setattr(sentiment_module, "show_workflow_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(sentiment_module, "show_agent_reasoning", lambda *args, **kwargs: None)

    stock_news_mock = Mock(side_effect=AssertionError("get_stock_news should not be called in backtest mode"))
    news_sentiment_mock = Mock(
        side_effect=AssertionError("get_news_sentiment should not be called in backtest mode")
    )
    monkeypatch.setattr(sentiment_module, "get_stock_news", stock_news_mock)
    monkeypatch.setattr(sentiment_module, "get_news_sentiment", news_sentiment_mock)

    result = sentiment_module.sentiment_agent(state)
    output = result["data"]["agent_outputs"]["sentiment"]

    assert stock_news_mock.call_count == 0
    assert news_sentiment_mock.call_count == 0
    assert output["signal"] == "neutral"
    assert output["confidence"] == "50%"
    assert output["sentiment_score"] == 0.0
    assert "Backtest mode active" in output["reasoning"]


@pytest.mark.skipif(not LANGCHAIN_CORE_AVAILABLE, reason="langchain_core is not installed in this environment")
def test_macro_news_agent_backtest_mode_skips_remote_calls(monkeypatch):
    state = _base_state()
    monkeypatch.setenv("ASHAREAGENT_BACKTEST_MODE", "1")
    monkeypatch.setattr(macro_news_module, "show_workflow_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(macro_news_module, "show_agent_reasoning", lambda *args, **kwargs: None)

    stock_news_mock = Mock(side_effect=AssertionError("stock_news_em should not be called in backtest mode"))
    llm_mock = Mock(side_effect=AssertionError("get_chat_completion should not be called in backtest mode"))
    monkeypatch.setattr(macro_news_module.ak, "stock_news_em", stock_news_mock)
    monkeypatch.setattr(macro_news_module, "get_chat_completion", llm_mock)

    result = macro_news_module.macro_news_agent(state)
    output = result["data"]["agent_outputs"]["macro_news_agent"]

    assert stock_news_mock.call_count == 0
    assert llm_mock.call_count == 0
    assert output["signal"] == "neutral"
    assert output["confidence"] == "50%"
    assert output["backtest_mode"] is True
    assert result["data"]["macro_news_analysis"] == output


def _build_debate_state() -> dict:
    state = _base_state()
    state["messages"] = [
        HumanMessage(
            name="researcher_bull_agent",
            content=json.dumps(
                {
                    "perspective": "bullish",
                    "confidence": 0.7,
                    "thesis_points": ["policy support", "liquidity recovery"],
                    "reasoning": "Policy and liquidity are improving.",
                }
            ),
        ),
        HumanMessage(
            name="researcher_bear_agent",
            content=json.dumps(
                {
                    "perspective": "bearish",
                    "confidence": 0.6,
                    "thesis_points": ["valuation pressure"],
                    "reasoning": "Valuation still contains downside risk.",
                }
            ),
        ),
    ]
    return state


@pytest.mark.skipif(not LANGCHAIN_CORE_AVAILABLE, reason="langchain_core is not installed in this environment")
def test_debate_room_backtest_mode_skips_llm_call(monkeypatch):
    monkeypatch.setenv("ASHAREAGENT_BACKTEST_MODE", "1")
    llm_mock = Mock(side_effect=AssertionError("debate_room should not call LLM in backtest mode"))
    monkeypatch.setattr(debate_module, "get_chat_completion", llm_mock)
    monkeypatch.setattr(debate_module, "show_workflow_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(debate_module, "show_agent_reasoning", lambda *args, **kwargs: None)
    monkeypatch.setattr(debate_module, "log_llm_interaction", lambda _state: (lambda fn: fn))

    result = debate_module.debate_room_agent(_build_debate_state())
    output = json.loads(result["messages"][0].content)

    assert llm_mock.call_count == 0
    assert output["llm_score"] == 0
    assert "Backtest mode active" in (output.get("llm_analysis") or "")


def _build_portfolio_state() -> dict:
    state = _base_state()
    state["messages"] = [
        portfolio_module.HumanMessage(name="technical_analyst_agent", content=json.dumps({"signal": "bullish"})),
        portfolio_module.HumanMessage(name="fundamentals_agent", content=json.dumps({"signal": "bullish"})),
        portfolio_module.HumanMessage(name="sentiment_agent", content=json.dumps({"signal": "neutral"})),
        portfolio_module.HumanMessage(name="valuation_agent", content=json.dumps({"signal": "neutral"})),
        portfolio_module.HumanMessage(name="risk_management_agent", content=json.dumps({"signal": "hold"})),
        portfolio_module.HumanMessage(name="macro_analyst_agent", content=json.dumps({"signal": "neutral"})),
        portfolio_module.HumanMessage(name="researcher_bull", content=json.dumps({"signal": "bullish"})),
        portfolio_module.HumanMessage(name="researcher_bear", content=json.dumps({"signal": "bearish"})),
    ]
    state["data"]["agent_outputs"] = {
        "technicals": {"signal": "bullish", "confidence": "70%"},
        "fundamentals": {"signal": "bullish", "confidence": "75%"},
        "sentiment": {"signal": "neutral", "confidence": "50%"},
        "valuation": {"signal": "neutral", "confidence": "55%"},
        "risk_manager": {"signal": "hold", "confidence": "80%"},
        "macro_analyst": {"signal": "neutral", "confidence": "50%"},
    }
    return state


@pytest.mark.skipif(not LANGCHAIN_CORE_AVAILABLE, reason="langchain_core is not installed in this environment")
def test_portfolio_manager_backtest_mode_skips_llm_call(monkeypatch):
    monkeypatch.setenv("ASHAREAGENT_BACKTEST_MODE", "1")
    llm_mock = Mock(side_effect=AssertionError("portfolio manager should not call LLM in backtest mode"))
    monkeypatch.setattr(portfolio_module, "get_chat_completion", llm_mock)
    monkeypatch.setattr(portfolio_module, "show_workflow_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(portfolio_module, "show_agent_reasoning", lambda *args, **kwargs: None)
    monkeypatch.setattr(portfolio_module, "log_llm_interaction", lambda _state: (lambda fn: fn))

    result = portfolio_module.portfolio_management_agent(_build_portfolio_state())
    decision = json.loads(result["messages"][0].content)

    assert llm_mock.call_count == 0
    assert decision["action"] == "hold"
    assert "Backtest mode active" in decision["reasoning"]
