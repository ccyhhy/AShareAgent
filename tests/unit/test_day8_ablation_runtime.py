from __future__ import annotations

import json
from unittest.mock import Mock

from src.agents import macro_news_agent as macro_news_module
from src.agents import portfolio_manager as portfolio_module
from src.agents import sentiment as sentiment_module
from src.agents import technicals as technicals_module


def _base_state() -> dict:
    return {
        "messages": [],
        "data": {
            "ticker": "000001",
            "portfolio": {"cash": 100000.0, "stock": 0},
            "num_of_news": 5,
            "end_date": "2026-04-09",
            "macro_news_analysis_result": "N/A",
        },
        "metadata": {"show_reasoning": False},
    }


def test_sentiment_agent_returns_ablation_stub_without_remote_calls(monkeypatch):
    state = _base_state()
    state["metadata"]["ablation_config"] = {"profile": "no_rule_agents"}

    stock_news_mock = Mock(side_effect=AssertionError("should not call get_stock_news"))
    sentiment_model_mock = Mock(side_effect=AssertionError("should not call get_news_sentiment"))

    monkeypatch.setattr(sentiment_module, "get_stock_news", stock_news_mock)
    monkeypatch.setattr(sentiment_module, "get_news_sentiment", sentiment_model_mock)
    monkeypatch.setattr(sentiment_module, "show_workflow_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(sentiment_module, "show_agent_reasoning", lambda *args, **kwargs: None)

    result = sentiment_module.sentiment_agent(state)
    payload = result["data"]["agent_outputs"]["sentiment"]

    assert stock_news_mock.call_count == 0
    assert sentiment_model_mock.call_count == 0
    assert payload["signal"] == "neutral"
    assert payload["ablation"]["disabled"] is True


def test_macro_news_agent_remove_single_profile_returns_stub(monkeypatch):
    state = _base_state()
    state["metadata"]["ablation_config"] = {
        "profile": "remove_single_agent_x",
        "remove_single_agent": "macro_news_agent",
    }
    monkeypatch.setattr(macro_news_module, "show_workflow_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(macro_news_module, "show_agent_reasoning", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        macro_news_module.ak,
        "stock_news_em",
        Mock(side_effect=AssertionError("should not call stock_news_em")),
    )
    monkeypatch.setattr(
        macro_news_module,
        "get_chat_completion",
        Mock(side_effect=AssertionError("should not call get_chat_completion")),
    )

    result = macro_news_module.macro_news_agent(state)
    payload = result["data"]["agent_outputs"]["macro_news_agent"]

    assert payload["ablation"]["disabled"] is True
    assert "macro_news_analysis_result" in result["data"]
    assert "Ablation disabled macro_news_agent" in result["data"]["macro_news_analysis_result"]


def test_technical_agent_no_rule_profile_returns_alias_data_fields(monkeypatch):
    state = _base_state()
    state["metadata"]["ablation_config"] = {"profile": "no_rule_agents"}
    monkeypatch.setattr(technicals_module, "show_workflow_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(technicals_module, "show_agent_reasoning", lambda *args, **kwargs: None)

    result = technicals_module.technical_analyst_agent(state)
    payload = result["data"]["agent_outputs"]["technicals"]

    assert payload["ablation"]["disabled"] is True
    assert result["data"]["technical_analysis"]["signal"] == "neutral"
    assert result["data"]["relative_valuation_analysis"]["signal"] == "neutral"


def test_portfolio_manager_no_llm_profile_returns_deterministic_hold(monkeypatch):
    state = _base_state()
    state["metadata"]["ablation_config"] = {"profile": "no_llm_agents"}
    state["messages"] = [
        portfolio_module.HumanMessage(name="technical_analyst_agent", content=json.dumps({"signal": "neutral"})),
        portfolio_module.HumanMessage(name="fundamentals_agent", content=json.dumps({"signal": "neutral"})),
        portfolio_module.HumanMessage(name="sentiment_agent", content=json.dumps({"signal": "neutral"})),
        portfolio_module.HumanMessage(name="valuation_agent", content=json.dumps({"signal": "neutral"})),
        portfolio_module.HumanMessage(name="risk_management_agent", content=json.dumps({"signal": "neutral"})),
        portfolio_module.HumanMessage(name="macro_analyst_agent", content=json.dumps({"signal": "neutral"})),
        portfolio_module.HumanMessage(name="researcher_bull", content=json.dumps({"signal": "neutral"})),
        portfolio_module.HumanMessage(name="researcher_bear", content=json.dumps({"signal": "neutral"})),
    ]

    llm_mock = Mock(side_effect=AssertionError("no_llm_agents should skip LLM call"))
    monkeypatch.setattr(portfolio_module, "get_chat_completion", llm_mock)
    monkeypatch.setattr(portfolio_module, "show_workflow_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(portfolio_module, "show_agent_reasoning", lambda *args, **kwargs: None)

    result = portfolio_module.portfolio_management_agent(state)
    decision = json.loads(result["messages"][0].content)

    assert llm_mock.call_count == 0
    assert decision["action"] == "hold"
    assert "Ablation disabled agent_type 'llm'" in decision["reasoning"]
