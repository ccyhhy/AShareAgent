from __future__ import annotations

import json

import pytest

try:
    import langchain_core  # noqa: F401
except ModuleNotFoundError:
    LANGCHAIN_CORE_AVAILABLE = False
else:
    LANGCHAIN_CORE_AVAILABLE = True
    from src.agents import portfolio_manager as portfolio_module


def _build_state(*, with_agent_outputs: bool) -> dict:
    technical_message_payload = {"marker": "MESSAGE_TECH", "signal": "bearish"}
    fundamentals_message_payload = {"marker": "MESSAGE_FUND", "signal": "bearish"}
    sentiment_message_payload = {"marker": "MESSAGE_SENT", "signal": "bearish"}
    valuation_message_payload = {"marker": "MESSAGE_VAL", "signal": "bearish"}
    risk_message_payload = {"marker": "MESSAGE_RISK", "signal": "bearish"}
    macro_message_payload = {"marker": "MESSAGE_MACRO", "signal": "bearish"}

    state = {
        "messages": [
            portfolio_module.HumanMessage(
                name="technical_analyst_agent",
                content=json.dumps(technical_message_payload),
            ),
            portfolio_module.HumanMessage(
                name="fundamentals_agent",
                content=json.dumps(fundamentals_message_payload),
            ),
            portfolio_module.HumanMessage(
                name="sentiment_agent",
                content=json.dumps(sentiment_message_payload),
            ),
            portfolio_module.HumanMessage(
                name="valuation_agent",
                content=json.dumps(valuation_message_payload),
            ),
            portfolio_module.HumanMessage(
                name="risk_management_agent",
                content=json.dumps(risk_message_payload),
            ),
            portfolio_module.HumanMessage(
                name="macro_analyst_agent",
                content=json.dumps(macro_message_payload),
            ),
            portfolio_module.HumanMessage(
                name="researcher_bull",
                content=json.dumps({"signal": "bullish", "reasoning": "bull side"}),
            ),
            portfolio_module.HumanMessage(
                name="researcher_bear",
                content=json.dumps({"signal": "bearish", "reasoning": "bear side"}),
            ),
        ],
        "data": {
            "portfolio": {"cash": 10000.0, "stock": 200},
            "macro_news_analysis_result": "MARKET_MACRO_SUMMARY",
        },
        "metadata": {"show_reasoning": False},
    }

    if with_agent_outputs:
        state["data"]["agent_outputs"] = {
            "technicals": {"marker": "AGENT_OUTPUT_TECH", "signal": "bullish"},
            "fundamentals": {"marker": "AGENT_OUTPUT_FUND", "signal": "bullish"},
            "sentiment": {"marker": "AGENT_OUTPUT_SENT", "signal": "bullish"},
            "valuation": {"marker": "AGENT_OUTPUT_VAL", "signal": "bullish"},
            "risk_manager": {"marker": "AGENT_OUTPUT_RISK", "signal": "neutral"},
            "macro_analyst": {"marker": "AGENT_OUTPUT_MACRO", "signal": "neutral"},
        }

    return state


@pytest.mark.skipif(not LANGCHAIN_CORE_AVAILABLE, reason="langchain_core is not installed in this environment")
def test_portfolio_manager_prefers_agent_outputs_when_available(monkeypatch):
    captured = {}

    def fake_llm(messages):
        captured["user_prompt"] = messages[1]["content"]
        return json.dumps(
            {
                "action": "hold",
                "quantity": 0,
                "confidence": 0.66,
                "agent_signals": [],
                "reasoning": "ok",
            }
        )

    monkeypatch.setattr(portfolio_module, "show_workflow_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(portfolio_module, "show_agent_reasoning", lambda *args, **kwargs: None)
    monkeypatch.setattr(portfolio_module, "log_llm_interaction", lambda _state: (lambda fn: fn))
    monkeypatch.setattr(portfolio_module, "get_chat_completion", fake_llm)

    result = portfolio_module.portfolio_management_agent(_build_state(with_agent_outputs=True))

    prompt = captured["user_prompt"]
    assert "AGENT_OUTPUT_TECH" in prompt
    assert "AGENT_OUTPUT_FUND" in prompt
    assert "AGENT_OUTPUT_MACRO" in prompt
    assert "MESSAGE_TECH" not in prompt
    assert "MESSAGE_FUND" not in prompt
    assert "MESSAGE_MACRO" not in prompt

    decision = json.loads(result["messages"][0].content)
    assert decision["action"] == "hold"
    assert decision["reasoning"] == "ok"


@pytest.mark.skipif(not LANGCHAIN_CORE_AVAILABLE, reason="langchain_core is not installed in this environment")
def test_portfolio_manager_falls_back_to_messages_without_agent_outputs(monkeypatch):
    captured = {}

    def fake_llm(messages):
        captured["user_prompt"] = messages[1]["content"]
        return json.dumps(
            {
                "action": "hold",
                "quantity": 0,
                "confidence": 0.51,
                "agent_signals": [],
                "reasoning": "fallback-ok",
            }
        )

    monkeypatch.setattr(portfolio_module, "show_workflow_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(portfolio_module, "show_agent_reasoning", lambda *args, **kwargs: None)
    monkeypatch.setattr(portfolio_module, "log_llm_interaction", lambda _state: (lambda fn: fn))
    monkeypatch.setattr(portfolio_module, "get_chat_completion", fake_llm)

    result = portfolio_module.portfolio_management_agent(_build_state(with_agent_outputs=False))

    prompt = captured["user_prompt"]
    assert "MESSAGE_TECH" in prompt
    assert "MESSAGE_FUND" in prompt
    assert "MESSAGE_MACRO" in prompt
    assert "AGENT_OUTPUT_TECH" not in prompt

    decision = json.loads(result["messages"][0].content)
    assert decision["reasoning"] == "fallback-ok"
