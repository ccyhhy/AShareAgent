from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.tools.api import get_financial_metrics, get_market_data, get_price_history


def test_get_price_history_prefers_tencent_before_akshare(tmp_path: Path):
    tencent_df = pd.DataFrame(
        {
            "date": ["2024-01-02"],
            "open": [100.0],
            "high": [101.0],
            "low": [99.5],
            "close": [100.5],
            "volume": [100000.0],
        }
    )

    with patch("src.tools.api._get_price_history_tencent", return_value=tencent_df), patch(
        "src.tools.api.ak.stock_zh_a_hist",
        side_effect=AssertionError("akshare should not be used when tencent succeeds"),
    ):
        result = get_price_history(
            "600519",
            "2024-01-01",
            "2024-01-31",
            provider_preference="remote_api",
            csv_dir=tmp_path,
        )

    assert not result.empty
    assert list(result["close"]) == [100.5]


def test_get_financial_metrics_prefers_tencent_before_akshare(tmp_path: Path):
    tencent_metrics = [
        {
            "pe_ratio": 20.1,
            "price_to_book": 7.8,
            "price_to_sales": None,
            "market_cap": 1.8e12,
            "current_price": 1450.0,
        }
    ]

    with patch.dict("os.environ", {"ASHAREAGENT_SNAPSHOT_DIR": str(tmp_path)}), patch(
        "src.tools.api._get_financial_metrics_tencent",
        return_value=tencent_metrics,
    ), patch(
        "src.tools.api._get_financial_fundamentals_sina",
        side_effect=Exception("sina supplement unavailable"),
    ), patch(
        "src.tools.api._get_financial_metrics_akshare",
        side_effect=AssertionError("akshare should not be used when tencent succeeds"),
    ):
        result = get_financial_metrics("600519")

    assert result[0]["pe_ratio"] == 20.1
    assert result[0]["data_source"] == "tencent"
    assert result[0]["cache_status"] == "remote_live"


def test_get_financial_metrics_merges_tencent_with_sina_fundamentals(tmp_path: Path):
    tencent_metrics = [
        {
            "pe_ratio": 20.1,
            "price_to_book": 7.8,
            "price_to_sales": None,
            "market_cap": 1.8e12,
            "current_price": 1450.0,
        }
    ]
    sina_metrics = {
        "return_on_equity": 0.16,
        "net_margin": 0.27,
        "revenue_growth": 0.08,
        "earnings_growth": 0.11,
    }

    with patch.dict("os.environ", {"ASHAREAGENT_SNAPSHOT_DIR": str(tmp_path)}), patch(
        "src.tools.api._get_financial_metrics_tencent",
        return_value=tencent_metrics,
    ), patch(
        "src.tools.api._get_financial_fundamentals_sina",
        return_value=sina_metrics,
    ), patch(
        "src.tools.api._get_financial_metrics_akshare",
        side_effect=AssertionError("akshare should not be used when tencent succeeds"),
    ):
        result = get_financial_metrics("600519")

    row = result[0]
    assert row["pe_ratio"] == 20.1
    assert row["return_on_equity"] == 0.16
    assert row["net_margin"] == 0.27
    assert row["revenue_growth"] == 0.08
    assert row["earnings_growth"] == 0.11
    assert row["data_source"] == "tencent+sina_finance"


def test_get_market_data_prefers_tencent_before_akshare(tmp_path: Path):
    tencent_market_data = {
        "current_price": 1450.0,
        "market_cap": 1.8e12,
        "volume": 1000000.0,
        "average_volume": 1000000.0,
        "pe_ratio": 20.0,
        "price_to_book": 7.9,
        "price_to_sales": None,
        "fifty_two_week_high": 1600.0,
        "fifty_two_week_low": 1300.0,
        "price_source": "tencent_quote",
        "price_is_realtime": False,
    }

    with patch.dict("os.environ", {"ASHAREAGENT_SNAPSHOT_DIR": str(tmp_path)}), patch(
        "src.tools.api._get_market_data_tencent",
        return_value=tencent_market_data,
    ), patch(
        "src.tools.api._get_market_data_akshare",
        side_effect=AssertionError("akshare should not be used when tencent succeeds"),
    ):
        result = get_market_data("600519")

    assert result["current_price"] == 1450.0
    assert result["data_source"] == "tencent"
    assert result["cache_status"] == "remote_live"
