from backend.state import ApiState


def test_cleanup_completed_run_history_clears_only_completed_runs_and_preserves_latest_state():
    api_state = ApiState()
    api_state.register_agent("technical_analyst_agent")

    api_state.register_run("run-1")
    api_state.update_agent_data("technical_analyst_agent", "input_state", {"run": 1})
    api_state.update_agent_data("technical_analyst_agent", "reasoning", {"signal": "bullish"})

    api_state.complete_run("run-1")
    assert api_state._agent_data["technical_analyst_agent"]["history"] != []

    api_state.cleanup_completed_run_history()

    run_1 = api_state.get_run("run-1")
    assert run_1 is not None
    assert "technical_analyst_agent" in run_1.agents
    assert api_state.current_run_id is None
    assert api_state._agent_data["technical_analyst_agent"]["history"] == []
    assert api_state._agent_data["technical_analyst_agent"]["latest"]["input_state"] == {"run": 1}
    assert api_state._agent_data["technical_analyst_agent"]["latest"]["reasoning"] == {"signal": "bullish"}

    api_state.register_run("run-2")
    api_state.update_agent_data("technical_analyst_agent", "output_state", {"run": 2})
    api_state.complete_run("run-2")
    api_state.cleanup_completed_run_history()

    run_2 = api_state.get_run("run-2")
    assert run_2 is not None
    assert "technical_analyst_agent" in run_2.agents
    assert api_state.current_run_id is None
    assert api_state._agent_data["technical_analyst_agent"]["history"] == []
    assert api_state._agent_data["technical_analyst_agent"]["latest"]["output_state"] == {"run": 2}
