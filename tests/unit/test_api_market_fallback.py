from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from src.tools.api import _get_market_data_akshare


def test_get_market_data_akshare_falls_back_to_non_em_spot_snapshot():
    fallback_df = pd.DataFrame(
        [
            {
                "\u4ee3\u7801": "600519",
                "\u540d\u79f0": "\u8d35\u5dde\u8305\u53f0",
                "\u6700\u65b0\u4ef7": 1453.96,
                "\u6210\u4ea4\u91cf": 2886556.0,
                "\u6210\u4ea4\u989d": 4195200000.0,
            }
        ]
    )

    with patch("src.tools.api.ak.stock_zh_a_spot_em", side_effect=Exception("em unavailable")), patch(
        "src.tools.api.ak.stock_zh_a_spot",
        return_value=fallback_df,
    ):
        result = _get_market_data_akshare("600519")

    assert result["current_price"] == 1453.96
    assert result["volume"] == 2886556.0
    assert result["average_volume"] == 2886556.0
    assert result["price_source"] == "akshare_spot"
    assert result["price_is_realtime"] is False
