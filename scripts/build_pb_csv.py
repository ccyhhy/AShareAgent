from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

import akshare as ak
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_PRICES_CSV = DEFAULT_DATA_DIR / "prices.csv"
DEFAULT_PB_CSV = DEFAULT_DATA_DIR / "pb.csv"


def _normalize_symbol(raw: str) -> str:
    text = str(raw or "").strip().upper()
    if not text:
        return ""
    if "." in text:
        text = text.split(".", 1)[0]
    if text.startswith(("SH", "SZ", "BJ")) and text[2:].isdigit():
        text = text[2:]
    if text.isdigit():
        return text.zfill(6)
    return text


def _to_ts_code(symbol: str) -> str:
    normalized = _normalize_symbol(symbol)
    if not normalized:
        return ""
    suffix = "SH" if normalized.startswith(("6", "9")) else "SZ"
    return f"{normalized}.{suffix}"


def _load_symbols_from_prices(prices_csv: Path) -> list[str]:
    if not prices_csv.exists():
        return []
    df = pd.read_csv(prices_csv, encoding="utf-8")
    for column in ("ts_code", "symbol", "code", "ticker"):
        if column in df.columns:
            return sorted(
                {
                    _normalize_symbol(value)
                    for value in df[column].dropna().astype(str).tolist()
                    if _normalize_symbol(value)
                }
            )
    return []


def _iter_symbols(cli_symbols: str, prices_csv: Path) -> list[str]:
    if cli_symbols.strip():
        return sorted(
            {
                _normalize_symbol(item)
                for item in cli_symbols.split(",")
                if _normalize_symbol(item)
            }
        )
    return _load_symbols_from_prices(prices_csv)


def _load_all_a_share_symbols() -> list[str]:
    df = ak.stock_info_a_code_name()
    if df is None or df.empty:
        return []
    for column in ("code", "symbol", "股票代码"):
        if column in df.columns:
            return sorted(
                {
                    _normalize_symbol(value)
                    for value in df[column].dropna().astype(str).tolist()
                    if _normalize_symbol(value)
                }
            )
    return []


def _fetch_pb_history(symbol: str, period: str) -> pd.DataFrame:
    raw_df = ak.stock_zh_valuation_baidu(
        symbol=symbol,
        indicator="市净率",
        period=period,
    )
    if raw_df is None or raw_df.empty:
        return pd.DataFrame(columns=["date", "ts_code", "pb"])

    df = raw_df.rename(columns={"value": "pb"}).copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["pb"] = pd.to_numeric(df["pb"], errors="coerce")
    df = df.dropna(subset=["date", "pb"])
    df = df.loc[df["pb"] > 0].copy()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    df["ts_code"] = _to_ts_code(symbol)
    return df[["date", "ts_code", "pb"]]


def _merge_with_existing(new_df: pd.DataFrame, pb_csv: Path) -> pd.DataFrame:
    if pb_csv.exists():
        old_df = pd.read_csv(pb_csv, encoding="utf-8")
        merged = pd.concat([old_df, new_df], ignore_index=True)
    else:
        merged = new_df.copy()

    merged["date"] = pd.to_datetime(merged["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    merged["pb"] = pd.to_numeric(merged["pb"], errors="coerce")
    merged = merged.dropna(subset=["date", "ts_code", "pb"])
    merged = merged.loc[merged["pb"] > 0]
    merged = merged.drop_duplicates(subset=["date", "ts_code"], keep="last")
    merged = merged.sort_values(["ts_code", "date"]).reset_index(drop=True)
    return merged[["date", "ts_code", "pb"]]


def _chunked(items: Iterable[str], size: int) -> Iterable[list[str]]:
    batch: list[str] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _fetch_one(symbol: str, period: str) -> tuple[str, pd.DataFrame | None, str | None]:
    try:
        df = _fetch_pb_history(symbol, period)
        if df is None or df.empty:
            return symbol, None, "empty pb history"
        return symbol, df, None
    except Exception as exc:  # noqa: BLE001
        return symbol, None, str(exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build local data/pb.csv from Baidu valuation API via AkShare.")
    parser.add_argument(
        "--symbols",
        type=str,
        default="",
        help="Comma-separated symbols, e.g. 600519,000001. If omitted, read symbols from data/prices.csv.",
    )
    parser.add_argument(
        "--all-a-shares",
        action="store_true",
        help="Fetch symbol universe from AkShare stock_info_a_code_name() instead of prices.csv.",
    )
    parser.add_argument(
        "--prices-csv",
        type=str,
        default=str(DEFAULT_PRICES_CSV),
        help="Path to prices.csv used for symbol discovery when --symbols is empty.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(DEFAULT_PB_CSV),
        help="Output pb.csv path.",
    )
    parser.add_argument(
        "--period",
        type=str,
        default="近十年",
        choices=["近一年", "近三年", "近五年", "近十年", "全部"],
        help="Baidu valuation lookback period.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.25,
        help="Sleep seconds between symbol requests.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Progress print batch size.",
    )
    parser.add_argument(
        "--max-symbols",
        type=int,
        default=0,
        help="Optional cap for symbols count (0 means no cap).",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=8,
        help="Concurrent workers for fetching symbols.",
    )
    args = parser.parse_args()

    prices_csv = Path(args.prices_csv)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    if args.all_a_shares:
        symbols = _load_all_a_share_symbols()
    else:
        symbols = _iter_symbols(args.symbols, prices_csv)
    if not symbols:
        raise SystemExit("No symbols found. Provide --symbols or ensure prices.csv has ts_code/symbol/code/ticker column.")
    if args.max_symbols > 0:
        symbols = symbols[: args.max_symbols]

    all_frames: list[pd.DataFrame] = []
    ok = 0
    fail = 0

    max_workers = max(1, int(args.max_workers))
    if max_workers == 1:
        for batch in _chunked(symbols, max(1, args.batch_size)):
            for symbol in batch:
                symbol, df, err = _fetch_one(symbol, args.period)
                if err:
                    fail += 1
                    print(f"[WARN] {symbol}: {err}")
                else:
                    all_frames.append(df)  # type: ignore[arg-type]
                    ok += 1
                time.sleep(max(0.0, args.sleep))
            print(f"[INFO] progress ok={ok}, fail={fail}, total={ok + fail}/{len(symbols)}")
    else:
        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_fetch_one, symbol, args.period): symbol
                for symbol in symbols
            }
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    _, df, err = future.result()
                except Exception as exc:  # noqa: BLE001
                    df = None
                    err = str(exc)

                if err:
                    fail += 1
                    print(f"[WARN] {symbol}: {err}")
                else:
                    all_frames.append(df)  # type: ignore[arg-type]
                    ok += 1

                completed += 1
                if completed % max(1, args.batch_size) == 0 or completed == len(symbols):
                    print(f"[INFO] progress ok={ok}, fail={fail}, total={completed}/{len(symbols)}")

    if not all_frames:
        raise SystemExit("No PB data fetched; pb.csv not updated.")

    merged = _merge_with_existing(pd.concat(all_frames, ignore_index=True), output)
    merged.to_csv(output, index=False, encoding="utf-8")
    print(f"[DONE] wrote {len(merged)} rows to {output}")
    print(f"[DONE] symbols requested={len(symbols)}, success={ok}, failed={fail}")


if __name__ == "__main__":
    main()
