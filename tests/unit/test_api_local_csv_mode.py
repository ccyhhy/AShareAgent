from pathlib import Path
from unittest.mock import patch

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
