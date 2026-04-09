from pathlib import Path
from unittest.mock import patch

import pandas as pd

import src.tools.api as api_module
from src.tools.api import get_price_data, get_price_history


def _write_csv(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_get_price_history_prefers_local_csv_when_requested(tmp_path: Path):
    _write_csv(
        tmp_path / "prices.csv",
        "\n".join(
            [
                "date,ts_code,open,close",
                "2024-01-01,600519.SH,100,101",
                "2024-01-02,600519.SH,101,102",
            ]
        ),
    )

    with patch("src.tools.api.ak.stock_zh_a_hist", side_effect=AssertionError("network should not be used")):
        with patch.object(api_module.logger, "info") as mock_info:
            result = get_price_history(
                "600519",
                "2024-01-01",
                "2024-01-31",
                provider_preference="local_csv",
                local_only=True,
                csv_dir=tmp_path,
            )

    assert list(result["close"]) == [101, 102]
    for column in ["open", "high", "low", "close", "volume"]:
        assert column in result.columns
    assert any("[DATA_SOURCE] local_csv symbol=600519" in str(call.args[0]) for call in mock_info.call_args_list)


def test_get_price_history_local_only_returns_empty_when_csv_missing(tmp_path: Path):
    with patch("src.tools.api.ak.stock_zh_a_hist", side_effect=AssertionError("network should not be used")):
        result = get_price_history(
            "600519",
            "2024-01-01",
            "2024-01-31",
            provider_preference="local_csv",
            local_only=True,
            csv_dir=tmp_path,
        )

    assert result.empty


def test_get_price_data_passes_through_local_csv_options(tmp_path: Path):
    _write_csv(
        tmp_path / "prices.csv",
        "\n".join(
            [
                "date,ts_code,open,close",
                "2024-01-01,600519.SH,100,101",
            ]
        ),
    )

    result = get_price_data(
        "600519",
        "2024-01-01",
        "2024-01-31",
        provider_preference="local_csv",
        local_only=True,
        csv_dir=tmp_path,
    )

    assert list(result["close"]) == [101]


def test_get_price_data_uses_repo_level_data_directory_by_default(tmp_path: Path):
    _write_csv(
        tmp_path / "prices.csv",
        "\n".join(
            [
                "date,ts_code,open,close",
                "2024-01-01,600519.SH,100,101",
            ]
        ),
    )

    original_default = api_module.DEFAULT_LOCAL_CSV_DIR
    api_module.DEFAULT_LOCAL_CSV_DIR = tmp_path
    try:
        with patch("src.tools.api.ak.stock_zh_a_hist", side_effect=AssertionError("network should not be used")):
            result = get_price_data(
                "600519",
                "2024-01-01",
                "2024-01-31",
                provider_preference="local_csv",
                local_only=True,
            )
    finally:
        api_module.DEFAULT_LOCAL_CSV_DIR = original_default

    assert list(result["close"]) == [101]


def test_default_local_csv_dir_points_to_repo_data_directory():
    assert api_module.DEFAULT_LOCAL_CSV_DIR == Path(r"E:\codework\graduation design\data")


def test_get_price_history_blocks_remote_fallback_by_default(tmp_path: Path):
    with patch("src.tools.api.ak.stock_zh_a_hist", side_effect=AssertionError("remote should not be used")):
        result = get_price_history(
            "600519",
            "2024-01-01",
            "2024-01-31",
            csv_dir=tmp_path,
        )

    assert result.empty


def test_get_price_history_allows_remote_when_preference_is_remote_api(tmp_path: Path):
    remote_df = pd.DataFrame(
        {
            "日期": ["2024-01-02"],
            "开盘": [100.0],
            "最高": [101.0],
            "最低": [99.5],
            "收盘": [100.5],
            "成交量": [100000],
            "成交额": [10050000],
            "振幅": [1.5],
            "涨跌幅": [0.5],
            "涨跌额": [0.5],
            "换手率": [0.8],
        }
    )

    with patch.dict("os.environ", {"ASHAREAGENT_ALLOW_REMOTE_FALLBACK": "0"}, clear=False):
        with patch("src.tools.api.ak.stock_zh_a_hist", return_value=remote_df):
            with patch.object(api_module.logger, "info") as mock_info:
                result = get_price_history(
                    "600519",
                    "2024-01-01",
                    "2024-01-31",
                    provider_preference="remote_api",
                    csv_dir=tmp_path,
                )

    assert not result.empty
    assert "date" in result.columns
    assert list(result["close"]) == [100.5]
    assert any(
        "[DATA_SOURCE] remote_api(" in str(call.args[0]) and "symbol=600519" in str(call.args[0])
        for call in mock_info.call_args_list
    )


def test_get_price_history_disables_remote_when_backtest_mode_enabled(tmp_path: Path):
    with patch.dict("os.environ", {"ASHAREAGENT_BACKTEST_MODE": "1"}, clear=False):
        with patch("src.tools.api.ak.stock_zh_a_hist", side_effect=AssertionError("remote should not be used")):
            with patch.object(api_module.logger, "warning") as mock_warning:
                result = get_price_history(
                    "600519",
                    "2024-01-01",
                    "2024-01-31",
                    provider_preference="remote_api",
                    csv_dir=tmp_path,
                )

    assert result.empty
    assert any("backtest_mode=True,no_remote" in str(call.args[0]) for call in mock_warning.call_args_list)
