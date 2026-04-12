from __future__ import annotations

import importlib
import sys
from types import ModuleType

import backend.dependencies as dependencies
from src.database import models as database_models


def _install_backend_state_stub(monkeypatch):
    state_module = ModuleType("backend.state")

    class FakeApiState:
        def __init__(self):
            self._agent_data = {}
            self._runs = {}
            self._current_run_id = None

        def register_run(self, run_id):
            self._current_run_id = run_id
            self._runs[run_id] = {"run_id": run_id}

        def complete_run(self, run_id, status="completed"):
            if run_id in self._runs:
                self._runs[run_id]["status"] = status

        def get_run(self, run_id):
            return self._runs.get(run_id)

    state_module.api_state = FakeApiState()
    monkeypatch.setitem(sys.modules, "backend.state", state_module)
    return state_module.api_state


def _remove_backend_module(module_name: str):
    sys.modules.pop(module_name, None)


def test_get_database_manager_returns_cached_singleton(monkeypatch):
    dependencies.get_database_manager.cache_clear()

    constructed = {"count": 0}

    class FakeDatabaseManager:
        def __init__(self):
            constructed["count"] += 1

    monkeypatch.setattr(dependencies, "DatabaseManager", FakeDatabaseManager)

    first = dependencies.get_database_manager()
    second = dependencies.get_database_manager()

    assert first is second
    assert constructed["count"] == 1


def test_agents_router_import_uses_shared_database_manager(monkeypatch):
    dependencies.get_database_manager.cache_clear()
    _install_backend_state_stub(monkeypatch)
    _remove_backend_module("backend.routers.agents")
    _remove_backend_module("backend.routers")

    fake_db_manager = object()

    def fake_get_database_manager():
        return fake_db_manager

    class ForbiddenDatabaseManager:
        def __init__(self, *args, **kwargs):
            raise AssertionError("DatabaseManager() should not be called from agents.py")

    monkeypatch.setattr(dependencies, "get_database_manager", fake_get_database_manager)
    monkeypatch.setattr(database_models, "DatabaseManager", ForbiddenDatabaseManager)

    agents_module = importlib.import_module("backend.routers.agents")

    assert agents_module.db_manager is fake_db_manager
    assert agents_module.agent_model.db_manager is fake_db_manager
    assert agents_module.decision_model.db_manager is fake_db_manager


def test_workflow_run_uses_shared_database_manager(monkeypatch):
    dependencies.get_database_manager.cache_clear()
    _install_backend_state_stub(monkeypatch)
    _remove_backend_module("backend.utils.context_managers")
    _remove_backend_module("backend.utils")

    fake_db_manager = object()
    calls = {"count": 0}

    def fake_get_database_manager():
        calls["count"] += 1
        return fake_db_manager

    class ForbiddenDatabaseManager:
        def __init__(self, *args, **kwargs):
            raise AssertionError("DatabaseManager() should not be called from context_managers.py")

    monkeypatch.setattr(dependencies, "get_database_manager", fake_get_database_manager)
    monkeypatch.setattr(database_models, "DatabaseManager", ForbiddenDatabaseManager)

    context_module = importlib.import_module("backend.utils.context_managers")

    class FakeDecisionModel:
        def __init__(self, db_manager):
            self.db_manager = db_manager

        def save_decision(self, *args, **kwargs):
            return True

    class FakeAnalysisModel:
        def __init__(self, db_manager):
            self.db_manager = db_manager

        def save_result(self, *args, **kwargs):
            return True

    monkeypatch.setattr(context_module, "AgentDecisionModel", FakeDecisionModel)
    monkeypatch.setattr(context_module, "AnalysisResultModel", FakeAnalysisModel)

    with context_module.workflow_run("run-db-init"):
        pass

    assert calls["count"] == 1


def test_main_import_uses_shared_database_manager(monkeypatch):
    dependencies.get_database_manager.cache_clear()
    _install_backend_state_stub(monkeypatch)
    _remove_backend_module("backend.main")

    fake_db_manager = object()
    calls = {"count": 0}

    def fake_get_database_manager():
        calls["count"] += 1
        return fake_db_manager

    class ForbiddenDatabaseManager:
        def __init__(self, *args, **kwargs):
            raise AssertionError("DatabaseManager() should not be called from main.py")

    monkeypatch.setattr(dependencies, "get_database_manager", fake_get_database_manager)
    monkeypatch.setattr(database_models, "DatabaseManager", ForbiddenDatabaseManager)

    main_module = importlib.import_module("backend.main")

    assert main_module.db_manager is fake_db_manager
    assert calls["count"] == 1
