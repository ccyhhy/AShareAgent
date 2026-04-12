from __future__ import annotations

from datetime import datetime

from backend.utils import context_managers as context_module


def _merged_entry() -> dict:
    return {
        "timestamp": datetime(2026, 4, 11, 10, 30, 0),
        "reasoning": {
            "confidence": "82%",
            "reasoning": "bullish" * 200,
        },
        "llm_request": {"messages": [{"role": "user", "content": "x" * 1000}]},
        "llm_response": {"content": "y" * 1000},
        "output_state": {
            "data": {
                "agent_outputs": {
                    "risk_management": {
                        "signal": "neutral",
                        "confidence": "60%",
                    }
                }
            }
        },
    }


def test_build_compact_decision_data_drops_full_state_snapshots():
    payload = context_module._build_compact_decision_data(
        run_id="run-1",
        agent_name="risk_management_agent",
        ticker="000001",
        merged_entry=_merged_entry(),
    )

    assert payload["run_id"] == "run-1"
    assert payload["ticker"] == "000001"
    assert payload["agent_output"] == {"signal": "neutral", "confidence": "60%"}
    assert "input_state" not in payload
    assert "output_state" not in payload
    assert payload["llm_interaction"]["request_chars"] > 0
    assert len(payload["llm_interaction"]["request_preview"]) <= 280


def test_build_compact_result_data_caps_reasoning_and_compacts_llm_payloads():
    payload = context_module._build_compact_result_data(
        run_id="run-2",
        agent_name="risk_management_agent",
        ticker="000001",
        merged_entry=_merged_entry(),
    )

    assert payload["run_id"] == "run-2"
    assert isinstance(payload["reasoning"], str)
    assert len(payload["reasoning"]) <= 1000
    assert payload["reasoning_summary"] == payload["reasoning"]
    assert payload["agent_output"] == {"signal": "neutral", "confidence": "60%"}
    assert "output_state" not in payload
    assert len(payload["llm_interaction"]["response_preview"]) <= 280


def test_workflow_run_always_cleans_completed_history_even_without_database(monkeypatch):
    class FakeApiState:
        def __init__(self):
            self.cleanup_calls = 0

        def register_run(self, run_id):
            return None

        def complete_run(self, run_id, status="completed"):
            return None

        def cleanup_completed_run_history(self):
            self.cleanup_calls += 1

    fake_state = FakeApiState()
    monkeypatch.setattr(context_module, "api_state", fake_state)
    monkeypatch.setattr(context_module, "HAS_DATABASE", False)

    with context_module.workflow_run("run-3"):
        pass

    assert fake_state.cleanup_calls == 1
