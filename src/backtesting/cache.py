"""
Cache manager for backtesting price data and agent outputs.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as ConcurrentTimeoutError
from typing import Any, Dict, Optional

import pandas as pd

try:
    from src.tools import api as api_module
except ImportError:
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from src.tools import api as api_module


class CacheManager:
    """Small in-memory cache used by the backtesting workflow."""

    def __init__(self):
        self._price_data_cache: Dict[str, pd.DataFrame] = {}
        self._agent_result_cache: Dict[str, Any] = {}
        self._market_condition_cache: Dict[str, Any] = {}
        self._cache_hits = 0
        self._cache_misses = 0

    def get_cached_price_data(
        self, ticker: str, start_date: str, end_date: str
    ) -> Optional[pd.DataFrame]:
        """Return cached price data or fetch it via the unified local-first API."""
        cache_key = f"{ticker}_{start_date}_{end_date}"

        if cache_key in self._price_data_cache:
            self._cache_hits += 1
            return self._price_data_cache[cache_key]

        self._cache_misses += 1
        df = None
        max_retries = 3

        for attempt in range(max_retries):
            try:
                # Fetch in a worker thread so stalled I/O cannot block the workflow.
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(
                        api_module.get_price_data,
                        ticker,
                        start_date,
                        end_date,
                        provider_preference="local_csv",
                        local_only=True,
                    )
                    try:
                        df = future.result(timeout=30)
                        if df is not None and not df.empty:
                            self._price_data_cache[cache_key] = df
                            return df
                    except ConcurrentTimeoutError:
                        print(f"Price fetch timed out (attempt {attempt + 1}/{max_retries})")
                        if attempt < max_retries - 1:
                            import time

                            time.sleep(2**attempt)
                        continue
            except Exception as exc:
                print(f"Price fetch failed (attempt {attempt + 1}/{max_retries}): {exc}")
                if attempt < max_retries - 1:
                    import time

                    time.sleep(2**attempt)

        if df is None or df.empty:
            df = self._get_fallback_data(ticker, start_date, end_date)

        return df

    def _get_fallback_data(
        self, ticker: str, start_date: str, end_date: str
    ) -> Optional[pd.DataFrame]:
        """Try to satisfy a miss from a broader cached date range for the same ticker."""
        for key, cached_df in self._price_data_cache.items():
            if not key.startswith(ticker) or cached_df is None or cached_df.empty:
                continue

            try:
                cached_df = cached_df.copy()
                cached_df["date"] = pd.to_datetime(cached_df["date"])
                filtered_df = cached_df[
                    (cached_df["date"] >= start_date) & (cached_df["date"] <= end_date)
                ]
                if not filtered_df.empty:
                    return filtered_df
            except Exception:
                continue

        return None

    def get_agent_result(self, cache_key: str) -> Optional[Any]:
        """Return a cached agent result if available."""
        if cache_key in self._agent_result_cache:
            self._cache_hits += 1
            return self._agent_result_cache[cache_key]

        self._cache_misses += 1
        return None

    def cache_agent_result(self, cache_key: str, result: Any) -> None:
        """Store an agent result in memory."""
        self._agent_result_cache[cache_key] = result

    def get_last_decision(self) -> Dict[str, Any]:
        """Return the most recent cached decision or a conservative default."""
        if self._agent_result_cache:
            last_result = list(self._agent_result_cache.values())[-1]
            last_result["execution_type"] = "cached"
            return last_result

        return {
            "decision": {"action": "hold", "quantity": 0},
            "analyst_signals": {},
            "execution_type": "default",
        }

    @property
    def cache_hits(self) -> int:
        return self._cache_hits

    @property
    def cache_misses(self) -> int:
        return self._cache_misses

    @property
    def cache_hit_rate(self) -> float:
        total = self._cache_hits + self._cache_misses
        return (self._cache_hits / total * 100) if total > 0 else 0
