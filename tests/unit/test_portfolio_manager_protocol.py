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
            "critical_data_complete": True,
            "missing_critical_data": [],
        },
        "metadata": {"show_reasoning": False},
    }

    if with_agent_outputs:
        state["data"]["agent_outputs"] = {
            "technicals": {"marker": "AGENT_OUTPUT_TECH", "signal": "bullish"},
            "fundamentals": {"marker": "AGENT_OUTPUT_FUND", "signal": "bullish"},
            "sentiment": {"marker": "AGENT_OUTPUT_SENT", "signal": "bullish"},
            "valuation": {"marker": "AGENT_OUTPUT_VAL", "signal": "bullish"},
            "risk_manager": {
                "marker": "AGENT_OUTPUT_RISK",
                "signal": "neutral",
                "current_price": 50.0,
                "max_buy_quantity": 300,
                "quantity_lot_size": 100,
            },
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


@pytest.mark.skipif(not LANGCHAIN_CORE_AVAILABLE, reason="langchain_core is not installed in this environment")
def test_portfolio_manager_reasoning_uses_output_then_agent_name_in_backtest(monkeypatch):
    reasoning_calls = []

    monkeypatch.setenv("ASHAREAGENT_BACKTEST_MODE", "1")
    monkeypatch.setattr(portfolio_module, "show_workflow_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        portfolio_module,
        "show_agent_reasoning",
        lambda output, agent_name: reasoning_calls.append((output, agent_name)),
    )
    monkeypatch.setattr(portfolio_module, "log_llm_interaction", lambda _state: (lambda fn: fn))

    portfolio_module.portfolio_management_agent(_build_state(with_agent_outputs=True))

    assert reasoning_calls == [
        (
            "当前为回测模式，跳过远程LLM调用并使用确定性保守决策。",
            "portfolio_management_agent",
        )
    ]


@pytest.mark.skipif(not LANGCHAIN_CORE_AVAILABLE, reason="langchain_core is not installed in this environment")
def test_portfolio_manager_reasoning_uses_output_then_agent_name_on_llm_success(monkeypatch):
    reasoning_calls = []

    def fake_llm(_messages):
        return json.dumps(
            {
                "action": "hold",
                "quantity": 0,
                "confidence": 0.66,
                "agent_signals": [],
                "reasoning": "ok",
            }
        )

    state = _build_state(with_agent_outputs=True)
    state["metadata"]["show_reasoning"] = True

    monkeypatch.delenv("ASHAREAGENT_BACKTEST_MODE", raising=False)
    monkeypatch.setattr(portfolio_module, "show_workflow_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        portfolio_module,
        "show_agent_reasoning",
        lambda output, agent_name: reasoning_calls.append((output, agent_name)),
    )
    monkeypatch.setattr(portfolio_module, "log_llm_interaction", lambda _state: (lambda fn: fn))
    monkeypatch.setattr(portfolio_module, "get_chat_completion", fake_llm)

    portfolio_module.portfolio_management_agent(state)

    assert reasoning_calls[0] == (
        "正在汇总相对估值、基本面、情绪、估值、风控、宏观与多空研究观点，准备调用LLM。",
        "portfolio_management_agent",
    )
    assert reasoning_calls[1][1] == "portfolio_management_agent"
    assert reasoning_calls[1][0].startswith("Final LLM decision JSON: ")


@pytest.mark.skipif(not LANGCHAIN_CORE_AVAILABLE, reason="langchain_core is not installed in this environment")
def test_portfolio_manager_reasoning_uses_output_then_agent_name_on_llm_failure(monkeypatch):
    reasoning_calls = []

    state = _build_state(with_agent_outputs=True)

    monkeypatch.delenv("ASHAREAGENT_BACKTEST_MODE", raising=False)
    monkeypatch.setattr(portfolio_module, "show_workflow_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        portfolio_module,
        "show_agent_reasoning",
        lambda output, agent_name: reasoning_calls.append((output, agent_name)),
    )
    monkeypatch.setattr(portfolio_module, "log_llm_interaction", lambda _state: (lambda fn: fn))
    monkeypatch.setattr(portfolio_module, "get_chat_completion", lambda _messages: None)

    portfolio_module.portfolio_management_agent(state)

    assert reasoning_calls == [
        (
            "正在汇总相对估值、基本面、情绪、估值、风控、宏观与多空研究观点，准备调用LLM。",
            "portfolio_management_agent",
        ),
        (
            "LLM调用失败，回退为默认保守决策。",
            "portfolio_management_agent",
        ),
    ]


@pytest.mark.skipif(not LANGCHAIN_CORE_AVAILABLE, reason="langchain_core is not installed in this environment")
def test_portfolio_manager_blocks_buy_when_critical_data_missing(monkeypatch):
    def fake_llm(_messages):
        return json.dumps(
            {
                "action": "buy",
                "quantity": 123,
                "confidence": 0.8,
                "agent_signals": [],
                "reasoning": "llm wanted buy",
            }
        )

    state = _build_state(with_agent_outputs=True)
    state["data"]["critical_data_complete"] = False
    state["data"]["missing_critical_data"] = ["financial_metrics", "market_data"]

    monkeypatch.setattr(portfolio_module, "show_workflow_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(portfolio_module, "show_agent_reasoning", lambda *args, **kwargs: None)
    monkeypatch.setattr(portfolio_module, "log_llm_interaction", lambda _state: (lambda fn: fn))
    monkeypatch.setattr(portfolio_module, "get_chat_completion", fake_llm)

    result = portfolio_module.portfolio_management_agent(state)
    decision = json.loads(result["messages"][0].content)

    assert decision["action"] == "hold"
    assert decision["quantity"] == 0
    assert decision["signal"] == "neutral"
    assert decision["data_sufficiency"]["critical_data_complete"] is False
    assert "关键数据缺失" in decision["reasoning"]


@pytest.mark.skipif(not LANGCHAIN_CORE_AVAILABLE, reason="langchain_core is not installed in this environment")
def test_portfolio_manager_caps_buy_quantity_by_risk_and_cash_and_lot(monkeypatch):
    def fake_llm(_messages):
        return json.dumps(
            {
                "action": "buy",
                "quantity": 65000,
                "confidence": 0.7,
                "agent_signals": [],
                "reasoning": "llm wanted large buy",
            }
        )

    state = _build_state(with_agent_outputs=True)
    state["data"]["critical_data_complete"] = True
    state["data"]["missing_critical_data"] = []
    state["data"]["portfolio"] = {"cash": 10000.0, "stock": 0}
    state["data"]["agent_outputs"]["risk_manager"]["current_price"] = 50.0
    state["data"]["agent_outputs"]["risk_manager"]["max_buy_quantity"] = 300
    state["data"]["agent_outputs"]["risk_manager"]["quantity_lot_size"] = 100

    monkeypatch.setattr(portfolio_module, "show_workflow_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(portfolio_module, "show_agent_reasoning", lambda *args, **kwargs: None)
    monkeypatch.setattr(portfolio_module, "log_llm_interaction", lambda _state: (lambda fn: fn))
    monkeypatch.setattr(portfolio_module, "get_chat_completion", fake_llm)

    result = portfolio_module.portfolio_management_agent(state)
    decision = json.loads(result["messages"][0].content)

    # cash cap: 10000/50=200; risk cap=300; lot=100 => final 200
    assert decision["action"] == "buy"
    assert decision["quantity"] == 200
    assert decision["quantity_constraints"]["risk_cap_quantity"] == 300
    assert decision["quantity_constraints"]["cash_cap_quantity"] == 200
    assert decision["quantity_constraints"]["lot_size"] == 100
    assert "数量约束生效" in decision["reasoning"]


@pytest.mark.skipif(not LANGCHAIN_CORE_AVAILABLE, reason="langchain_core is not installed in this environment")
def test_portfolio_manager_turns_buy_to_hold_when_caps_result_zero_quantity(monkeypatch):
    def fake_llm(_messages):
        return json.dumps(
            {
                "action": "buy",
                "quantity": 500,
                "confidence": 0.7,
                "agent_signals": [],
                "reasoning": "llm wanted buy",
            }
        )

    state = _build_state(with_agent_outputs=True)
    state["data"]["critical_data_complete"] = True
    state["data"]["missing_critical_data"] = []
    state["data"]["portfolio"] = {"cash": 1000.0, "stock": 0}
    state["data"]["agent_outputs"]["risk_manager"]["current_price"] = 1500.0
    state["data"]["agent_outputs"]["risk_manager"]["max_buy_quantity"] = 100
    state["data"]["agent_outputs"]["risk_manager"]["quantity_lot_size"] = 100

    monkeypatch.setattr(portfolio_module, "show_workflow_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(portfolio_module, "show_agent_reasoning", lambda *args, **kwargs: None)
    monkeypatch.setattr(portfolio_module, "log_llm_interaction", lambda _state: (lambda fn: fn))
    monkeypatch.setattr(portfolio_module, "get_chat_completion", fake_llm)

    result = portfolio_module.portfolio_management_agent(state)
    decision = json.loads(result["messages"][0].content)

    assert decision["action"] == "hold"
    assert decision["signal"] == "neutral"
    assert decision["quantity"] == 0
    assert "无法形成有效买入股数" in decision["reasoning"]
