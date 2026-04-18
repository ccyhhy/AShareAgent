from __future__ import annotations

from backend.routers import analysis


def _stage_status_map(stages: list[dict]) -> dict[str, str]:
    return {stage["key"]: stage["status"] for stage in stages}


def test_stage_progress_forces_later_stage_pending_when_previous_unfinished(monkeypatch):
    run_agent_states = {
        "market_data": {"status": "completed"},
        "technical_analyst": {"status": "completed"},
        "fundamentals": {"status": "completed"},
        "sentiment": {"status": "completed"},
        "valuation": {"status": "completed"},
        "macro_news_agent": {"status": "completed"},
        "researcher_bull": {"status": "completed"},
        "researcher_bear": {"status": "completed"},
        "debate_room": {"status": "completed"},
        "risk_management": {"status": "completed"},
        "macro_analyst": {"status": "running"},
        # Simulate out-of-order completion signal from storage.
        "portfolio_management": {"status": "completed"},
    }
    monkeypatch.setattr(analysis.api_state, "get_run_agent_states", lambda _run_id: run_agent_states)

    progress = analysis._build_analysis_stage_progress_v2("run-1", "running")
    statuses = _stage_status_map(progress["stages"])

    assert statuses["macro"] == "running"
    assert statuses["decision"] == "pending"
    assert progress["current_stage"]["key"] == "macro"


def test_stage_progress_marks_all_completed_when_task_completed(monkeypatch):
    monkeypatch.setattr(
        analysis.api_state,
        "get_run_agent_states",
        lambda _run_id: {"market_data": {"status": "running"}},
    )

    progress = analysis._build_analysis_stage_progress_v2("run-2", "completed")
    statuses = _stage_status_map(progress["stages"])

    assert all(value == "completed" for value in statuses.values())
    assert progress["progress_percent"] == 100
    assert progress["completed_stage_count"] == progress["total_stage_count"]
