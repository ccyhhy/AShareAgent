import importlib


MODULES = [
    "backend.models.api_models",
    "backend.schemas",
    "backend.state",
    "backend.routers.analysis",
    "backend.services.analysis",
    "backend.services.backtest_service",
    "src.utils.api_utils",
    "src.utils.llm_interaction_logger",
    "src.utils.serialization",
]


def test_modules_using_utc_import_cleanly_on_python310():
    for module_name in MODULES:
        importlib.import_module(module_name)
