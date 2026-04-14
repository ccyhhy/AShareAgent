from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.tools.api import (
    get_financial_metrics,
    get_financial_statements,
    get_market_data,
)


def _write_snapshot(
    root: Path,
    dataset: str,
    symbol: str,
    data,
    *,
    fetched_at: str,
    source: str = "seed",
) -> Path:
    snapshot_path = root / dataset / f"{symbol}.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps(
            {
                "dataset": dataset,
                "symbol": symbol,
                "source": source,
                "fetched_at": fetched_at,
                "data": data,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return snapshot_path


def test_get_market_data_prefers_fresh_snapshot_before_remote_fetch(tmp_path: Path):
    _write_snapshot(
        tmp_path,
        "market_data",
        "600519",
        {"current_price": 1450.0, "market_cap": 1800000000000.0},
        fetched_at=datetime.now().isoformat(),
        source="snapshot_seed",
    )

    with patch.dict("os.environ", {"ASHAREAGENT_SNAPSHOT_DIR": str(tmp_path)}), patch(
        "src.tools.api._get_market_data_akshare",
        side_effect=AssertionError("remote provider should not be called when snapshot is fresh"),
    ):
        result = get_market_data("600519")

    assert result["current_price"] == 1450.0
    assert result["cache_status"] == "fresh_snapshot"
    assert result["is_snapshot"] is True
    assert result["data_source"] == "snapshot_seed"


def test_get_financial_metrics_writes_snapshot_after_remote_fetch(tmp_path: Path):
    remote_metrics = [
        {
            "return_on_equity": 0.18,
            "net_margin": 0.42,
            "price_to_book": 8.1,
        }
    ]

    with patch.dict("os.environ", {"ASHAREAGENT_SNAPSHOT_DIR": str(tmp_path)}), patch(
        "src.tools.api._get_financial_metrics_tencent",
        return_value=remote_metrics,
    ), patch(
        "src.tools.api._get_financial_fundamentals_sina",
        side_effect=Exception("sina supplement unavailable"),
    ):
        result = get_financial_metrics("600519")

    snapshot_path = tmp_path / "financial_metrics" / "600519.json"
    assert snapshot_path.exists()

    snapshot_payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot_payload["data"][0]["return_on_equity"] == 0.18
    assert result[0]["cache_status"] == "remote_live"
    assert result[0]["is_snapshot"] is False
    assert result[0]["data_source"] == "tencent"


def test_get_financial_statements_falls_back_to_stale_snapshot_when_remote_fetch_fails(tmp_path: Path):
    _write_snapshot(
        tmp_path,
        "financial_statements",
        "600519",
        [
            {
                "net_income": 75000000000.0,
                "operating_revenue": 150000000000.0,
                "free_cash_flow": 52000000000.0,
            }
        ],
        fetched_at=(datetime.now() - timedelta(days=45)).isoformat(),
        source="snapshot_seed",
    )

    with patch.dict("os.environ", {"ASHAREAGENT_SNAPSHOT_DIR": str(tmp_path)}), patch(
        "src.tools.api.ak.stock_financial_report_sina",
        side_effect=Exception("network down"),
    ):
        result = get_financial_statements("600519")

    assert result[0]["net_income"] == 75000000000.0
    assert result[0]["cache_status"] == "stale_snapshot"
    assert result[0]["is_snapshot"] is True
    assert result[0]["data_source"] == "snapshot_seed"


def test_get_financial_statements_derives_from_offline_market_payload_when_statements_missing(tmp_path: Path):
    offline_payload = {
        "600519": {
            "market_data": {
                "netIncomeToCommon": 90_000_000_000,
                "totalRevenue": 180_000_000_000,
                "freeCashflow": 51_000_000_000,
                "ebitda": 120_000_000_000,
            },
            "metrics": {},
        }
    }
    offline_path = tmp_path / "offline_financials_600519.json"
    offline_path.write_text(json.dumps(offline_payload, ensure_ascii=False), encoding="utf-8")

    with patch.dict("os.environ", {"ASHAREAGENT_SNAPSHOT_DIR": str(tmp_path)}), patch(
        "src.tools.api._build_offline_financials_path",
        return_value=offline_path,
    ), patch("src.tools.api.ak.stock_financial_report_sina", side_effect=Exception("network down")):
        result = get_financial_statements("600519")

    assert result[0]["net_income"] == 90_000_000_000
    assert result[0]["operating_revenue"] == 180_000_000_000
    assert result[0]["free_cash_flow"] == 51_000_000_000
    assert result[0]["cache_status"] == "offline_derived"
    assert result[0]["data_source"] == "offline_json_derived"
