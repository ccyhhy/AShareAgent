from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .models.api_models import RunInfo

logger = logging.getLogger("api_state")


class RunHistory(list):
    """List-like run history with deferred cleanup for completed runs."""

    def __init__(self):
        super().__init__()
        self._pending_purge_run_ids: set[str] = set()

    def mark_for_purge(self, run_id: str):
        self._pending_purge_run_ids.add(run_id)

    def purge_pending(self):
        if not self._pending_purge_run_ids:
            return

        pending_run_ids = set(self._pending_purge_run_ids)
        remaining_entries = [
            entry for entry in list.__iter__(self)
            if entry.get("run_id") not in pending_run_ids
        ]
        super().clear()
        super().extend(remaining_entries)
        self._pending_purge_run_ids.difference_update(pending_run_ids)

    def __iter__(self):
        if not self._pending_purge_run_ids:
            return super().__iter__()

        pending_run_ids = set(self._pending_purge_run_ids)
        snapshot = list(list.__iter__(self))

        def generator():
            try:
                for item in snapshot:
                    yield item
            finally:
                self._purge_specific_runs(pending_run_ids)

        return generator()

    def _purge_specific_runs(self, run_ids: set[str]):
        if not run_ids:
            return

        remaining_entries = [
            entry for entry in list.__iter__(self)
            if entry.get("run_id") not in run_ids
        ]
        super().clear()
        super().extend(remaining_entries)
        self._pending_purge_run_ids.difference_update(run_ids)


class ApiState:
    """Global API state container used to track agents and runs."""

    def __init__(self):
        self._lock = threading.RLock()
        self._agent_data: Dict[str, Dict] = {}
        self._runs: Dict[str, RunInfo] = {}
        self._run_agent_states: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._current_run_id: Optional[str] = None
        self._executor = ThreadPoolExecutor(max_workers=5)
        self._analysis_tasks: Dict[str, Future] = {}
        self._backtest_tasks: Dict[str, Future] = {}

    @property
    def current_run_id(self) -> Optional[str]:
        with self._lock:
            return self._current_run_id

    @current_run_id.setter
    def current_run_id(self, run_id: str):
        with self._lock:
            self._current_run_id = run_id

    def register_agent(self, agent_name: str, description: str = ""):
        with self._lock:
            if agent_name not in self._agent_data:
                self._agent_data[agent_name] = {
                    "info": {
                        "name": agent_name,
                        "description": description,
                        "state": "idle",
                        "last_run": None,
                    },
                    "latest": {
                        "input_state": None,
                        "output_state": None,
                        "llm_request": None,
                        "llm_response": None,
                        "reasoning": None,
                        "timestamp": None,
                    },
                    "history": RunHistory(),
                }

    def update_agent_state(self, agent_name: str, state: str):
        with self._lock:
            if agent_name in self._agent_data:
                self._agent_data[agent_name]["info"]["state"] = state
                if state in ["completed", "error"]:
                    self._agent_data[agent_name]["info"]["last_run"] = datetime.now(
                        timezone.utc
                    )

                if self._current_run_id:
                    run_states = self._run_agent_states.setdefault(
                        self._current_run_id, {}
                    )
                    run_states[agent_name] = {
                        "status": state,
                        "updated_at": datetime.now(timezone.utc),
                    }

    def update_agent_data(self, agent_name: str, field: str, data: Any):
        with self._lock:
            if agent_name in self._agent_data:
                self._agent_data[agent_name]["latest"][field] = data
                self._agent_data[agent_name]["latest"]["timestamp"] = datetime.now(
                    timezone.utc
                )

                if self._current_run_id:
                    history_entry = {
                        "run_id": self._current_run_id,
                        "timestamp": datetime.now(timezone.utc),
                        field: data,
                    }
                    history = self._agent_data[agent_name]["history"]
                    if isinstance(history, RunHistory):
                        history.purge_pending()
                    history.append(history_entry)

    def get_agent_info(self, agent_name: str) -> Optional[Dict]:
        with self._lock:
            if agent_name in self._agent_data:
                return self._agent_data[agent_name]["info"]
            return None

    def get_agent_data(self, agent_name: str, field: str = None) -> Optional[Dict]:
        with self._lock:
            if agent_name in self._agent_data:
                if field:
                    return self._agent_data[agent_name]["latest"].get(field)
                return self._agent_data[agent_name]["latest"]
            return None

    def get_all_agents(self) -> List[Dict]:
        with self._lock:
            return [data["info"] for data in self._agent_data.values()]

    def get_all_agent_data(self) -> Dict[str, Dict]:
        with self._lock:
            return self._agent_data.copy()

    def register_run(self, run_id: str):
        with self._lock:
            self._purge_completed_run_history()
            self._runs[run_id] = RunInfo(
                run_id=run_id,
                start_time=datetime.now(timezone.utc),
                status="running",
            )
            self._run_agent_states[run_id] = {}
            self._current_run_id = run_id

    def complete_run(self, run_id: str, status: str = "completed"):
        with self._lock:
            if run_id in self._runs:
                self._runs[run_id].end_time = datetime.now(timezone.utc)
                self._runs[run_id].status = status

                agents = set()
                for agent_name, agent_data in self._agent_data.items():
                    for entry in agent_data["history"]:
                        if entry["run_id"] == run_id:
                            agents.add(agent_name)
                            break

                self._runs[run_id].agents = list(agents)

                for agent_data in self._agent_data.values():
                    history = agent_data["history"]
                    if isinstance(history, RunHistory):
                        history.mark_for_purge(run_id)

                if self._current_run_id == run_id:
                    self._current_run_id = None

    def get_run(self, run_id: str) -> Optional[RunInfo]:
        with self._lock:
            return self._runs.get(run_id)

    def get_run_agent_states(self, run_id: str) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            run_states = self._run_agent_states.get(run_id, {})
            return {
                agent_name: state.copy()
                for agent_name, state in run_states.items()
            }

    def get_all_runs(self) -> List[RunInfo]:
        with self._lock:
            return list(self._runs.values())

    def _purge_completed_run_history(self):
        completed_run_ids = {
            run_id for run_id, run_info in self._runs.items()
            if run_info.status != "running"
        }
        if not completed_run_ids:
            return

        for agent_data in self._agent_data.values():
            history = agent_data["history"]
            if isinstance(history, RunHistory):
                history._purge_specific_runs(completed_run_ids)
            else:
                agent_data["history"] = [
                    entry for entry in history
                    if entry.get("run_id") not in completed_run_ids
                ]

    def cleanup_completed_run_history(self):
        with self._lock:
            self._purge_completed_run_history()

    def register_analysis_task(self, run_id: str, future: Future):
        with self._lock:
            self._analysis_tasks[run_id] = future

    def get_analysis_task(self, run_id: str) -> Optional[Future]:
        with self._lock:
            return self._analysis_tasks.get(run_id)

    def register_backtest_task(self, run_id: str, future: Future):
        with self._lock:
            self._backtest_tasks[run_id] = future

    def get_backtest_task(self, run_id: str) -> Optional[Future]:
        with self._lock:
            return self._backtest_tasks.get(run_id)


api_state = ApiState()
