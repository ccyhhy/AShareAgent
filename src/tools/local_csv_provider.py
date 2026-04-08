from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

DEFAULT_LOCAL_CSV_DIR = Path(__file__).resolve().parents[2] / "data"

_COLUMN_ALIASES = {
    "trade_date": "date",
    "日期": "date",
    "symbol": "ts_code",
    "code": "ts_code",
    "股票代码": "ts_code",
    "证券代码": "ts_code",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
}


@dataclass
class LocalCSVProvider:
    base_dir: Path | str = DEFAULT_LOCAL_CSV_DIR
    _cache: dict[str, pd.DataFrame] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.base_dir = Path(self.base_dir)

    def get_price_history(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        return self._get_symbol_time_series("prices.csv", symbol, start_date, end_date)

    def get_pb_history(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        return self._get_symbol_time_series("pb.csv", symbol, start_date, end_date)

    def get_listing_info(self, symbol: str) -> dict[str, Any] | None:
        df = self._load_csv("listing.csv")
        if df.empty:
            return None

        matched = self._filter_symbol(df, symbol)
        if matched.empty:
            return None

        row = matched.iloc[0].to_dict()
        normalized: dict[str, Any] = {}
        for key, value in row.items():
            if pd.isna(value):
                normalized[key] = None
            elif isinstance(value, pd.Timestamp):
                normalized[key] = value.strftime("%Y-%m-%d")
            else:
                normalized[key] = value
        return normalized

    def get_trading_calendar(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        df = self._load_csv("calendar.csv")
        if df.empty:
            return df
        return self._filter_date_range(df, start_date, end_date)

    def _get_symbol_time_series(
        self,
        filename: str,
        symbol: str,
        start_date: str | None,
        end_date: str | None,
    ) -> pd.DataFrame:
        df = self._load_csv(filename)
        if df.empty:
            return df

        filtered = self._filter_symbol(df, symbol)
        if filtered.empty:
            return filtered
        return self._filter_date_range(filtered, start_date, end_date)

    def _load_csv(self, filename: str) -> pd.DataFrame:
        if filename in self._cache:
            return self._cache[filename].copy()

        path = self.base_dir / filename
        if not path.exists():
            empty = pd.DataFrame()
            self._cache[filename] = empty
            return empty.copy()

        dataframe = self._read_csv_with_fallback(path)
        if dataframe is None:
            empty = pd.DataFrame()
            self._cache[filename] = empty
            return empty.copy()

        dataframe = self._standardize_columns(dataframe)

        if "ts_code" in dataframe.columns:
            dataframe["ts_code"] = dataframe["ts_code"].map(self._normalize_ts_code)

        if "date" in dataframe.columns:
            dataframe["date"] = pd.to_datetime(dataframe["date"], errors="coerce")
            dataframe = dataframe.loc[dataframe["date"].notna()].copy()

        for column in ("list_date", "delist_date"):
            if column in dataframe.columns:
                parsed = pd.to_datetime(dataframe[column], errors="coerce")
                dataframe[column] = parsed.dt.strftime("%Y-%m-%d")
                dataframe.loc[parsed.isna(), column] = None

        self._cache[filename] = dataframe
        return dataframe.copy()

    @staticmethod
    def _read_csv_with_fallback(path: Path) -> pd.DataFrame | None:
        for encoding in ("utf-8", "utf-8-sig", "gbk"):
            try:
                return pd.read_csv(path, encoding=encoding)
            except UnicodeDecodeError:
                continue
            except Exception:
                return None
        return None

    @staticmethod
    def _standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
        rename_map = {
            source: target
            for source, target in _COLUMN_ALIASES.items()
            if source in df.columns and target not in df.columns
        }
        if rename_map:
            df = df.rename(columns=rename_map)
        return df

    def _filter_symbol(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        if "ts_code" not in df.columns:
            return pd.DataFrame(columns=df.columns)

        codes = df["ts_code"].astype(str).str.upper()
        requested = self._normalize_ts_code(symbol)
        bare_symbol = self._bare_symbol(requested)

        if "." in requested:
            exact = df.loc[codes == requested]
            if not exact.empty:
                return exact.reset_index(drop=True)

        preferred = self._preferred_full_code(bare_symbol)
        for candidate in (preferred, self._alternative_full_code(preferred)):
            if not candidate:
                continue
            exact = df.loc[codes == candidate]
            if not exact.empty:
                return exact.reset_index(drop=True)

        bare_matches = df.loc[codes.str.split(".").str[0] == bare_symbol]
        if bare_matches.empty:
            return bare_matches.reset_index(drop=True)

        if preferred:
            preferred_only = bare_matches.loc[bare_matches["ts_code"].astype(str).str.upper() == preferred]
            if not preferred_only.empty:
                return preferred_only.reset_index(drop=True)

        return bare_matches.reset_index(drop=True)

    def _filter_date_range(
        self,
        df: pd.DataFrame,
        start_date: str | None,
        end_date: str | None,
    ) -> pd.DataFrame:
        if "date" not in df.columns:
            return df.reset_index(drop=True)

        filtered = df
        start = pd.to_datetime(start_date, errors="coerce") if start_date else None
        end = pd.to_datetime(end_date, errors="coerce") if end_date else None

        if start is not None and pd.notna(start):
            filtered = filtered.loc[filtered["date"] >= start]
        if end is not None and pd.notna(end):
            filtered = filtered.loc[filtered["date"] <= end]

        dedupe_keys = [column for column in ("date", "ts_code") if column in filtered.columns]
        if dedupe_keys:
            filtered = filtered.drop_duplicates(subset=dedupe_keys, keep="last")

        return filtered.sort_values("date").reset_index(drop=True)

    @staticmethod
    def _normalize_ts_code(symbol: Any) -> str:
        raw = str(symbol).strip().upper()
        if not raw:
            return raw
        if "." in raw:
            code, market = raw.split(".", 1)
            market = "SH" if market in {"SH", "SS"} else "SZ" if market in {"SZ"} else market
            return f"{code}.{market}"
        if raw.isdigit() and len(raw) == 6:
            suffix = "SH" if raw.startswith("6") else "SZ"
            return f"{raw}.{suffix}"
        return raw

    @staticmethod
    def _bare_symbol(symbol: str) -> str:
        return str(symbol).split(".")[0].upper()

    @staticmethod
    def _preferred_full_code(bare_symbol: str) -> str | None:
        if not bare_symbol.isdigit() or len(bare_symbol) != 6:
            return None
        suffix = "SH" if bare_symbol.startswith("6") else "SZ"
        return f"{bare_symbol}.{suffix}"

    @staticmethod
    def _alternative_full_code(preferred_full_code: str | None) -> str | None:
        if not preferred_full_code or "." not in preferred_full_code:
            return None
        code, suffix = preferred_full_code.split(".", 1)
        return f"{code}.SZ" if suffix == "SH" else f"{code}.SH"
