from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class LocalCSVProvider:
    base_dir: Path | str
    _cache: dict[str, pd.DataFrame] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.base_dir = Path(self.base_dir)

    def get_price_history(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        df = self._load_csv("prices.csv")
        if df.empty:
            return df
        return self._filter_symbol_and_date(df, symbol, start_date, end_date)

    def get_pb_history(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        df = self._load_csv("pb.csv")
        if df.empty:
            return df
        return self._filter_symbol_and_date(df, symbol, start_date, end_date)

    def get_listing_info(self, symbol: str) -> dict[str, Any] | None:
        df = self._load_csv("listing.csv")
        if df.empty:
            return None

        match = self._filter_symbol(df, symbol)
        if match.empty:
            return None

        row = match.iloc[0].to_dict()
        if pd.isna(row.get("delist_date")):
            row["delist_date"] = None
        return row

    def get_trading_calendar(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        df = self._load_csv("calendar.csv")
        if df.empty:
            return df
        return self._filter_date_range(df, start_date, end_date)

    def _load_csv(self, filename: str) -> pd.DataFrame:
        if filename in self._cache:
            return self._cache[filename].copy()

        path = self.base_dir / filename
        if not path.exists():
            empty = pd.DataFrame()
            self._cache[filename] = empty
            return empty.copy()

        df = pd.read_csv(path)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])

        for column in ("list_date", "delist_date"):
            if column in df.columns:
                df[column] = df[column].replace({pd.NA: None}).where(df[column].notna(), None)

        self._cache[filename] = df
        return df.copy()

    def _filter_symbol_and_date(
        self,
        df: pd.DataFrame,
        symbol: str,
        start_date: str | None,
        end_date: str | None,
    ) -> pd.DataFrame:
        filtered = self._filter_symbol(df, symbol)
        if filtered.empty:
            return filtered
        return self._filter_date_range(filtered, start_date, end_date)

    def _filter_symbol(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        if "ts_code" not in df.columns:
            return pd.DataFrame(columns=df.columns)

        ts_code_series = df["ts_code"].astype(str)
        requested = str(symbol).upper()

        exact_match = df.loc[ts_code_series == requested]
        if not exact_match.empty:
            return exact_match.reset_index(drop=True)

        bare_symbol = self._bare_symbol(symbol)
        preferred_code = self._preferred_full_code(bare_symbol)
        if preferred_code:
            preferred_match = df.loc[ts_code_series == preferred_code]
            if not preferred_match.empty:
                return preferred_match.reset_index(drop=True)

        bare_codes = ts_code_series.str.split(".").str[0]
        return df.loc[bare_codes == bare_symbol].reset_index(drop=True)

    def _filter_date_range(
        self,
        df: pd.DataFrame,
        start_date: str | None,
        end_date: str | None,
    ) -> pd.DataFrame:
        if "date" not in df.columns:
            return df.reset_index(drop=True)

        filtered = df
        if start_date:
            filtered = filtered.loc[filtered["date"] >= pd.Timestamp(start_date)]
        if end_date:
            filtered = filtered.loc[filtered["date"] <= pd.Timestamp(end_date)]

        dedupe_keys = [column for column in ("date", "ts_code") if column in filtered.columns]
        if dedupe_keys:
            filtered = filtered.drop_duplicates(subset=dedupe_keys, keep="last")

        return filtered.sort_values("date").reset_index(drop=True)

    @staticmethod
    def _bare_symbol(symbol: str) -> str:
        return str(symbol).split(".")[0].upper()

    @staticmethod
    def _preferred_full_code(bare_symbol: str) -> str | None:
        if not bare_symbol.isdigit() or len(bare_symbol) != 6:
            return None
        suffix = "SH" if bare_symbol.startswith("6") else "SZ"
        return f"{bare_symbol}.{suffix}"
