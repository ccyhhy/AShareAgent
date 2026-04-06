from pathlib import Path

import pandas as pd

from src.tools.local_csv_provider import LocalCSVProvider


def _write_csv(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_get_price_history_filters_by_symbol_and_date_range(tmp_path: Path):
    _write_csv(
        tmp_path / "prices.csv",
        "\n".join(
            [
                "date,ts_code,open,close",
                "2024-01-01,600519.SH,100,101",
                "2024-01-02,600519.SH,101,102",
                "2024-01-03,000001.SZ,10,11",
            ]
        ),
    )

    provider = LocalCSVProvider(base_dir=tmp_path)

    result = provider.get_price_history("600519", start_date="2024-01-02", end_date="2024-01-31")

    assert list(result["ts_code"].unique()) == ["600519.SH"]
    assert list(result["date"].dt.strftime("%Y-%m-%d")) == ["2024-01-02"]
    assert list(result.columns) == ["date", "ts_code", "open", "close"]


def test_get_price_history_prefers_exchange_suffix_for_bare_symbol(tmp_path: Path):
    _write_csv(
        tmp_path / "prices.csv",
        "\n".join(
            [
                "date,ts_code,open,close",
                "2024-01-01,000001.SZ,10,11",
                "2024-01-02,000001.SH,3000,3010",
            ]
        ),
    )

    provider = LocalCSVProvider(base_dir=tmp_path)

    result = provider.get_price_history("000001")

    assert list(result["ts_code"].unique()) == ["000001.SZ"]
    assert list(result["close"]) == [11]


def test_get_price_history_deduplicates_same_symbol_same_date(tmp_path: Path):
    _write_csv(
        tmp_path / "prices.csv",
        "\n".join(
            [
                "date,ts_code,open,close",
                "2024-01-01,600519.SH,100,101",
                "2024-01-01,600519.SH,110,111",
                "2024-01-02,600519.SH,120,121",
            ]
        ),
    )

    provider = LocalCSVProvider(base_dir=tmp_path)

    result = provider.get_price_history("600519")

    assert list(result["date"].dt.strftime("%Y-%m-%d")) == ["2024-01-01", "2024-01-02"]
    assert list(result["close"]) == [111, 121]


def test_get_pb_history_matches_bare_symbol_code(tmp_path: Path):
    _write_csv(
        tmp_path / "pb.csv",
        "\n".join(
            [
                "date,ts_code,pb",
                "2024-03-31,600519.SH,8.5",
                "2024-06-30,600519.SH,8.1",
                "2024-03-31,000001.SZ,1.2",
            ]
        ),
    )

    provider = LocalCSVProvider(base_dir=tmp_path)

    result = provider.get_pb_history("600519")

    assert list(result["ts_code"].unique()) == ["600519.SH"]
    assert list(result["pb"]) == [8.5, 8.1]


def test_get_listing_info_returns_single_stock_record(tmp_path: Path):
    _write_csv(
        tmp_path / "listing.csv",
        "\n".join(
            [
                "ts_code,list_date,delist_date",
                "600519.SH,2001-08-27,",
                "000001.SZ,1991-04-03,",
            ]
        ),
    )

    provider = LocalCSVProvider(base_dir=tmp_path)

    result = provider.get_listing_info("600519")

    assert result == {
        "ts_code": "600519.SH",
        "list_date": "2001-08-27",
        "delist_date": None,
    }


def test_get_trading_calendar_filters_date_range(tmp_path: Path):
    _write_csv(
        tmp_path / "calendar.csv",
        "\n".join(
            [
                "date,is_trading",
                "2024-01-01,0",
                "2024-01-02,1",
                "2024-01-03,1",
            ]
        ),
    )

    provider = LocalCSVProvider(base_dir=tmp_path)

    result = provider.get_trading_calendar(start_date="2024-01-02", end_date="2024-01-02")

    assert list(result["date"].dt.strftime("%Y-%m-%d")) == ["2024-01-02"]
    assert list(result["is_trading"]) == [1]


def test_missing_csv_returns_empty_structures(tmp_path: Path):
    provider = LocalCSVProvider(base_dir=tmp_path)

    price_result = provider.get_price_history("600519")
    pb_result = provider.get_pb_history("600519")
    listing_result = provider.get_listing_info("600519")
    calendar_result = provider.get_trading_calendar()

    assert price_result.empty
    assert pb_result.empty
    assert listing_result is None
    assert calendar_result.empty
