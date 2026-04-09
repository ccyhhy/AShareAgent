from __future__ import annotations

import json
from datetime import datetime

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
