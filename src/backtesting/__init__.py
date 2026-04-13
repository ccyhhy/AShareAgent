"""Compatibility package for legacy `src.backtesting.*` imports."""

from src.backtesting.backtester import IntelligentBacktester  # noqa: F401
from src.backtesting.benchmarks import BenchmarkCalculator  # noqa: F401
from src.backtesting.cache import CacheManager  # noqa: F401
from src.backtesting.metrics import MetricsCalculator  # noqa: F401
from src.backtesting.models import AgentConfig, PerformanceMetrics, RiskMetrics, Trade  # noqa: F401
from src.backtesting.trading import TradeExecutor  # noqa: F401
from src.backtesting.visualizer import PerformanceVisualizer  # noqa: F401
