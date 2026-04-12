from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import Mock

from src.agents import macro_analyst as macro_module


def _make_state() -> dict:
    return {
        "messages": [],
        "data": {
            "ticker": "000001.SZ",
            "end_date": "2026-04-08",
        },
        "metadata": {"show_reasoning": False},
    }


def _recent_news_item() -> dict:
    return {
        "title": "Liquidity improves in A-share market",
        "content": "Policy support and improving risk appetite.",
        "publish_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "unit_test",
    }


def test_macro_analyst_normalizes_macro_output_contract(monkeypatch):
    monkeypatch.setattr(macro_module, "show_workflow_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(macro_module, "show_agent_reasoning", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        macro_module,
        "get_stock_news",
        lambda symbol, max_news=100, date=None: [_recent_news_item()],
    )
    monkeypatch.setattr(
        macro_module,
        "get_macro_news_analysis",
        lambda news_list: {
            "macro_environment": "POSITIVE",
            "impact_on_stock": "positive",
            "key_factors": ["policy easing", "credit recovery", "sector demand"],
            "reasoning": "Macro cycle is improving and policy support is visible.",
        },
    )

    result = macro_module.macro_analyst_agent(_make_state())
    output = result["data"]["agent_outputs"]["macro_analyst"]

    assert output["agent_type"] == "llm"
    assert output["analysis_domain"] == "macro_cycle_policy"
    assert output["macro_environment"] == "positive"
    assert output["impact_on_stock"] == "positive"
    assert output["signal"] == "bullish"
    assert output["confidence"] == "75%"
    assert output["reasoning"]
    assert result["data"]["macro_analysis"] == output

    message_payload = json.loads(result["messages"][-1].content)
    assert message_payload["signal"] == "bullish"
    assert message_payload["confidence"] == "75%"


def test_macro_analyst_degrades_gracefully_when_model_output_is_invalid(monkeypatch):
    monkeypatch.setattr(macro_module, "show_workflow_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(macro_module, "show_agent_reasoning", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        macro_module,
        "get_stock_news",
        lambda symbol, max_news=100, date=None: [_recent_news_item()],
    )
    monkeypatch.setattr(macro_module, "get_macro_news_analysis", lambda news_list: "invalid")

    result = macro_module.macro_analyst_agent(_make_state())
    output = result["data"]["agent_outputs"]["macro_analyst"]

    assert output["macro_environment"] == "neutral"
    assert output["impact_on_stock"] == "neutral"
    assert output["signal"] == "neutral"
    assert output["confidence"] == "55%"
    assert output["key_factors"] == []
    assert "fallback" in output["reasoning"].lower()


def test_macro_analyst_backtest_mode_is_deterministic_and_does_not_call_remote_dependencies(monkeypatch):
    monkeypatch.setenv("ASHAREAGENT_BACKTEST_MODE", "1")
    monkeypatch.setattr(macro_module, "show_workflow_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(macro_module, "show_agent_reasoning", lambda *args, **kwargs: None)

    get_stock_news_mock = Mock(side_effect=AssertionError("get_stock_news should not be called in backtest mode"))
    get_macro_news_analysis_mock = Mock(
        side_effect=AssertionError("get_macro_news_analysis should not be called in backtest mode")
    )
    monkeypatch.setattr(macro_module, "get_stock_news", get_stock_news_mock)
    monkeypatch.setattr(macro_module, "get_macro_news_analysis", get_macro_news_analysis_mock)

    result = macro_module.macro_analyst_agent(_make_state())
    output = result["data"]["agent_outputs"]["macro_analyst"]

    assert get_stock_news_mock.call_count == 0
    assert get_macro_news_analysis_mock.call_count == 0
    assert output["macro_environment"] == "neutral"
    assert output["impact_on_stock"] == "neutral"
    assert output["signal"] == "neutral"
    assert output["confidence"] == "50%"
    assert isinstance(output["reasoning"], str)
    assert output["reasoning"] == (
        "Backtest mode active. Remote news crawling and LLM calls skipped for reproducibility."
    )
    assert result["data"]["macro_analysis"] == output


def test_macro_analyst_agent_output_contract_always_exposes_core_fields(monkeypatch):
    monkeypatch.setattr(macro_module, "show_workflow_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(macro_module, "show_agent_reasoning", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        macro_module,
        "get_stock_news",
        lambda symbol, max_news=100, date=None: [_recent_news_item()],
    )
    monkeypatch.setattr(
        macro_module,
        "get_macro_news_analysis",
        lambda news_list: {
            "macro_environment": "POSITIVE",
            "impact_on_stock": "positive",
            "key_factors": ["policy easing", "credit recovery", "sector demand"],
            "reasoning": "Macro cycle is improving and policy support is visible.",
        },
    )

    result = macro_module.macro_analyst_agent(_make_state())
    output = result["data"]["agent_outputs"]["macro_analyst"]

    assert isinstance(output, dict)
    assert isinstance(output["signal"], str)
    assert output["signal"] in {"bullish", "neutral", "bearish"}
    assert isinstance(output["confidence"], str)
    assert output["confidence"].endswith("%")
    assert isinstance(output["reasoning"], str)
    assert output["reasoning"].strip()


def test_macro_analyst_filters_news_relative_to_historical_end_date(monkeypatch):
    monkeypatch.setattr(macro_module, "show_workflow_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(macro_module, "show_agent_reasoning", lambda *args, **kwargs: None)

    captured = {}

    monkeypatch.setattr(
        macro_module,
        "get_stock_news",
        lambda symbol, max_news=100, date=None: [
            {
                "title": "Historical in-window macro news",
                "content": "Within the historical analysis window.",
                "publish_time": "2024-01-08 09:00:00",
                "source": "unit_test",
            },
            {
                "title": "Historical expired macro news",
                "content": "Outside the historical analysis window.",
                "publish_time": "2023-12-20 09:00:00",
                "source": "unit_test",
            },
        ],
    )
    def fake_macro_analysis(news_list):
        captured["titles"] = [item["title"] for item in news_list]
        return {
            "macro_environment": "neutral",
            "impact_on_stock": "neutral",
            "key_factors": [],
            "reasoning": "filtered",
        }

    monkeypatch.setattr(macro_module, "get_macro_news_analysis", fake_macro_analysis)

    state = _make_state()
    state["data"]["end_date"] = "2024-01-10"
    result = macro_module.macro_analyst_agent(state)
    output = result["data"]["agent_outputs"]["macro_analyst"]

    assert captured["titles"] == ["Historical in-window macro news"]
    assert output["reasoning"]


def test_get_macro_news_analysis_returns_cached_result_without_llm_call(monkeypatch):
    cached_result = {
        "macro_environment": "positive",
        "impact_on_stock": "positive",
        "key_factors": ["policy"],
        "reasoning": "cached result",
    }
    data_service = Mock()
    data_service.get_macro_analysis_from_cache.return_value = cached_result
    data_service.save_macro_analysis_to_cache = Mock()

    llm_mock = Mock(side_effect=AssertionError("LLM should not be called on cache hit"))

    monkeypatch.setattr(macro_module, "get_data_service", lambda: data_service)
    monkeypatch.setattr(macro_module, "get_chat_completion", llm_mock)

    result = macro_module.get_macro_news_analysis([_recent_news_item()])

    assert result == cached_result
    assert llm_mock.call_count == 0
    data_service.save_macro_analysis_to_cache.assert_not_called()


def test_get_macro_news_analysis_saves_cache_when_llm_returns_valid_json(monkeypatch):
    data_service = Mock()
    data_service.get_macro_analysis_from_cache.return_value = None
    data_service.save_macro_analysis_to_cache = Mock()

    llm_payload = {
        "macro_environment": "neutral",
        "impact_on_stock": "neutral",
        "key_factors": ["liquidity"],
        "reasoning": "model response",
    }

    monkeypatch.setattr(macro_module, "get_data_service", lambda: data_service)
    monkeypatch.setattr(macro_module, "get_chat_completion", lambda messages: json.dumps(llm_payload))

    result = macro_module.get_macro_news_analysis([_recent_news_item()])

    assert result == llm_payload
    data_service.save_macro_analysis_to_cache.assert_called_once()
