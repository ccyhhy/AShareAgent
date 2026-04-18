"""
API工具模块 - 提供Agent共享的API功能组件

此模块定义了全局FastAPI应用实例和路由注册机制，
为各个Agent提供统一的API暴露方式。

注意: 大部分功能已被重构到backend目录，此模块仅为向后兼容性而保留。
"""
import os
import pandas as pd
import akshare as ak
import yfinance as yf
from datetime import datetime, timedelta
import json
import numpy as np
import requests
import re
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import time
import warnings
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, TimeoutError as ConcurrentTimeoutError
from src.tools.local_csv_provider import LocalCSVProvider
from src.utils.logging_config import setup_logger

# 设置日志记录
logger = setup_logger('api')

# 抑制警告信息
warnings.filterwarnings('ignore')

# 数据源配置 - 增加超时时间和重试次数
DATA_SOURCES = {
    'eastmoney': {'priority': 1, 'timeout': 45, 'retries': 3, 'rate_limit': 0.5},  # 每2秒一次
    'akshare': {'priority': 2, 'timeout': 60, 'retries': 2, 'rate_limit': 1},     # 每秒一次
    'tencent': {'priority': 3, 'timeout': 30, 'retries': 2, 'rate_limit': 0.5},   # 每2秒一次
    'yfinance': {'priority': 3, 'timeout': 30, 'retries': 2, 'rate_limit': 1},    # 每秒一次
}

DEFAULT_LOCAL_CSV_DIR = Path(__file__).resolve().parent.parent.parent / "data"

REMOTE_PROVIDER_HINTS = {"remote", "remote_api", "akshare", "yfinance", "eastmoney", "tencent"}

# 扩展数据集TTL配置
DATASET_SNAPSHOT_TTLS = {
    "financial_metrics": 72,
    "financial_statements": 24 * 45,
    "market_data": 24,  # 缩短市场数据TTL
    "price_history": 12,  # 短期价格数据
}

SNAPSHOT_METADATA_KEYS = {
    "data_source",
    "data_as_of",
    "cache_status",
    "is_snapshot",
    "snapshot_fetched_at",
    "snapshot_ttl_hours",
    "data_quality_score",
    "hit_count",
}

def safe_float(value, default=None):
    """安全的浮点数转换，增强版本"""
    try:
        if value is None or (isinstance(value, str) and value.strip() == '') or pd.isna(value):
            return default

        # 处理numpy类型
        if hasattr(value, 'item'):
            value = value.item()

        # 处理百分号
        if isinstance(value, str) and '%' in value:
            value = value.replace('%', '')

        result = float(value)

        # 检查是否为有效数字
        if np.isnan(result) or np.isinf(result):
            return default

        return result
    except (ValueError, TypeError, OverflowError):
        return default

def convert_percentage(value: Union[float, str, None]) -> Optional[float]:
    """将百分比值转换为小数，修复版本"""
    try:
        if value is None or (isinstance(value, str) and value.strip() == '') or pd.isna(value):
            return None

        # 处理字符串百分号
        has_percent_sign = False
        if isinstance(value, str):
            if '%' in value:
                has_percent_sign = True
                value = value.replace('%', '').strip()
            if not value:
                return None

        float_val = safe_float(value)
        if float_val is None:
            return None

        # 如果原始值有百分号，直接除以100
        if has_percent_sign:
            return float_val / 100.0
        # 对于从财务数据源获取的数据，通常已经是百分比格式(例如：15.5表示15.5%)
        # 需要除以100转换为小数形式(0.155)
        elif abs(float_val) > 5.0:  # 大于5%的值通常是百分比格式
            return float_val / 100.0
        else:
            # 小值可能已经是小数格式，直接返回
            return float_val
    except (ValueError, TypeError, OverflowError, AttributeError):
        return None

def get_stock_code_for_yfinance(symbol: str) -> str:
    """获取yfinance的股票代码格式"""
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return normalized

    if normalized.endswith(".SH"):
        return f"{normalized[:-3]}.SS"
    if normalized.endswith((".SZ", ".SS", ".HK")):
        return normalized

    if normalized.isdigit():
        if len(normalized) == 6:
            if normalized.startswith(("00", "30")):
                return f"{normalized}.SZ"
            if normalized.startswith(("60", "68", "90")):
                return f"{normalized}.SS"
        if len(normalized) == 5:
            return f"{normalized}.HK"

    return normalized

def _is_a_share_symbol(symbol: str) -> bool:
    """判断是否为A股代码"""
    normalized = str(symbol or "").strip().upper()
    if normalized.endswith((".SZ", ".SS", ".SH")):
        return True
    if normalized.endswith(".HK"):
        return False
    return normalized.isdigit() and len(normalized) == 6 and normalized.startswith(("0", "3", "6", "8", "9"))

def _get_local_csv_provider(csv_dir: Union[str, Path, None] = None) -> LocalCSVProvider:
    """获取本地CSV提供程序实例"""
    base_dir = Path(csv_dir) if csv_dir else DEFAULT_LOCAL_CSV_DIR
    return LocalCSVProvider(base_dir=base_dir)

def _is_truthy_env_var(name: str) -> bool:
    """检查环境变量是否为真值"""
    value = os.getenv(name, "").strip().lower()
    return value in {"1", "true", "yes", "on"}

def _allow_remote_fallback(
    provider_preference: str | None,
    local_only: bool,
    *,
    backtest_mode: bool,
) -> bool:
    """判断是否允许远程回退"""
    if local_only or backtest_mode:
        return False

    explicit_preference = (provider_preference or "").strip().lower() in REMOTE_PROVIDER_HINTS
    explicit_env_switch = _is_truthy_env_var("ASHAREAGENT_ALLOW_REMOTE_FALLBACK")
    return explicit_preference or explicit_env_switch

def _normalize_local_price_df(df: pd.DataFrame) -> pd.DataFrame:
    """标准化本地价格数据框"""
    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

    normalized = df.copy()

    if "high" not in normalized.columns:
        normalized["high"] = normalized["close"]
    if "low" not in normalized.columns:
        normalized["low"] = normalized["close"]
    if "volume" not in normalized.columns:
        normalized["volume"] = 0.0

    for column in ["open", "high", "low", "close", "volume"]:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    normalized = normalized.dropna(subset=["date", "open", "close"]).reset_index(drop=True)
    if len(normalized) < 20:
        normalized = normalized.sort_values("date").reset_index(drop=True)
        normalized["momentum_1m"] = 0.0
        normalized["momentum_3m"] = 0.0
        normalized["momentum_6m"] = 0.0
        normalized["volume_ma20"] = normalized["volume"].astype(float)
        normalized["volume_momentum"] = 1.0
        normalized["historical_volatility"] = 0.0
        normalized["volatility_regime"] = 0.5
        normalized["volatility_z_score"] = 0.0
        normalized["atr"] = (normalized["high"] - normalized["low"]).fillna(0.0)
        normalized["atr_ratio"] = 0.0
        normalized["hurst_exponent"] = 0.5
        normalized["skewness"] = 0.0
        normalized["kurtosis"] = 0.0
        return normalized

    return _add_technical_indicators(normalized)

def _add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """为数据框添加技术指标"""
    if df.empty:
        return df

    df_sorted = df.sort_values('date').copy()

    # 计算技术指标
    df_sorted['returns'] = df_sorted['close'].pct_change()
    df_sorted['sma_20'] = df_sorted['close'].rolling(window=20).mean()
    df_sorted['sma_50'] = df_sorted['close'].rolling(window=50).mean()
    df_sorted['ema_12'] = df_sorted['close'].ewm(span=12).mean()
    df_sorted['ema_26'] = df_sorted['close'].ewm(span=26).mean()
    df_sorted['rsi'] = _calculate_rsi(df_sorted['close'])

    # 波动率指标
    df_sorted['historical_volatility'] = df_sorted['returns'].rolling(window=20).std() * np.sqrt(252)

    # 动量指标
    df_sorted['momentum_1m'] = df_sorted['close'].pct_change(periods=20)
    df_sorted['momentum_3m'] = df_sorted['close'].pct_change(periods=60)
    df_sorted['momentum_6m'] = df_sorted['close'].pct_change(periods=120)

    return df_sorted

def _calculate_rsi(prices, window=14):
    """计算RSI指标"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def _rename_remote_price_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(
        columns={
            "日期": "date",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close",
            "成交量": "volume",
            "date": "date",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
        }
    )


def _get_tencent_symbol(symbol: str) -> str:
    normalized = _normalize_a_share_symbol(symbol)
    if normalized.startswith(("60", "68", "90")):
        return f"sh{normalized}"
    return f"sz{normalized}"


def _parse_tencent_quote(text: str) -> list[str]:
    match = re.search(r'="(.*)";?$', text.strip())
    if not match:
        raise ValueError("Unexpected Tencent quote response format")
    payload = match.group(1)
    parts = payload.split("~")
    if len(parts) < 47:
        raise ValueError(f"Incomplete Tencent quote payload: len={len(parts)}")
    return parts


def _extract_tencent_quote_metrics(symbol: str) -> Dict[str, Any]:
    tencent_symbol = _get_tencent_symbol(symbol)
    url = f"https://qt.gtimg.cn/q={tencent_symbol}"
    response = requests.get(
        url,
        timeout=DATA_SOURCES["tencent"]["timeout"],
        headers={
            "Referer": "https://gu.qq.com",
            "User-Agent": "Mozilla/5.0 (compatible; AShareAgent/1.0)",
            "Accept": "text/plain,*/*",
        },
    )
    response.raise_for_status()
    parts = _parse_tencent_quote(response.text)

    current_price = safe_float(parts[3])
    previous_close = safe_float(parts[4])
    open_price = safe_float(parts[5])
    volume_lot = safe_float(parts[6], 0) or 0
    volume_shares = volume_lot * 100
    intraday_high = safe_float(parts[33])
    intraday_low = safe_float(parts[34])
    pe_ratio = safe_float(parts[39])
    pb_ratio = safe_float(parts[46])
    market_cap_yi = safe_float(parts[44])
    market_cap = market_cap_yi * 1e8 if market_cap_yi is not None else None

    quote_time = parts[30] if len(parts) > 30 else ""
    price_as_of = None
    if isinstance(quote_time, str) and len(quote_time) >= 8:
        price_as_of = f"{quote_time[:4]}-{quote_time[4:6]}-{quote_time[6:8]}"

    return {
        "current_price": current_price or previous_close,
        "previous_close": previous_close,
        "open_price": open_price,
        "market_cap": market_cap,
        "volume": volume_shares,
        "average_volume": volume_shares,
        "pe_ratio": pe_ratio,
        "price_to_book": pb_ratio,
        "price_to_sales": None,
        "fifty_two_week_high": intraday_high,
        "fifty_two_week_low": intraday_low,
        "price_source": "tencent_quote",
        "price_is_realtime": False,
        "price_as_of": price_as_of,
    }


def _get_price_history_tencent(symbol: str, start_date: str, end_date: str, adjust: str = "qfq") -> pd.DataFrame:
    tencent_symbol = _get_tencent_symbol(symbol)
    normalized_adjust = "hfq" if str(adjust).lower() == "hfq" else "qfq"
    params = {
        "param": f"{tencent_symbol},day,{start_date},{end_date},640,{normalized_adjust}",
    }
    response = requests.get(
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
        params=params,
        timeout=DATA_SOURCES["tencent"]["timeout"],
        headers={
            "Referer": "https://gu.qq.com",
            "User-Agent": "Mozilla/5.0 (compatible; AShareAgent/1.0)",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    response.raise_for_status()
    payload = response.json()
    symbol_payload = payload.get("data", {}).get(tencent_symbol, {})
    kline_key = "hfqday" if normalized_adjust == "hfq" else "qfqday"
    rows = symbol_payload.get(kline_key, [])
    if not rows:
        raise Exception("Tencent kline returned empty dataset")

    df = pd.DataFrame(rows, columns=["date", "open", "close", "high", "low", "volume"])
    for column in ["open", "close", "high", "low", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.dropna(subset=["date", "close"]).reset_index(drop=True)


def get_price_history(
    symbol: str,
    start_date: str = None,
    end_date: str = None,
    adjust: str = "qfq",
    provider_preference: str | None = None,
    local_only: bool = False,
    csv_dir: Union[str, Path, None] = None,
) -> pd.DataFrame:
    """
    获取价格历史数据，使用多数据源策略和增强的错误处理
    """
    backtest_mode = _is_truthy_env_var("ASHAREAGENT_BACKTEST_MODE")
    allow_remote = _allow_remote_fallback(
        provider_preference,
        local_only,
        backtest_mode=backtest_mode,
    )

    # 首先尝试本地CSV提供程序
    local_df = _get_local_csv_provider(csv_dir).get_price_history(symbol, start_date, end_date)
    if not local_df.empty:
        logger.info(f"[DATA_SOURCE] local_csv symbol={symbol}")
        return _normalize_local_price_df(local_df)

    if local_only:
        logger.warning(f"[DATA_SOURCE] local_csv_miss(local_only=True) symbol={symbol}")
        return pd.DataFrame()

    if backtest_mode:
        logger.warning(f"[DATA_SOURCE] local_csv_miss(backtest_mode=True,no_remote) symbol={symbol}")
        return pd.DataFrame()

    if not allow_remote:
        logger.warning(
            f"[DATA_SOURCE] local_csv_miss(remote_fallback_disabled) symbol={symbol}. "
            "Set ASHAREAGENT_ALLOW_REMOTE_FALLBACK=1 or provider_preference='remote_api' to enable fallback."
        )
        return pd.DataFrame()

    # 尝试多数据源获取
    if not end_date:
        end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    if not start_date:
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

    try:
        tencent_df = _get_price_history_tencent(symbol, start_date, end_date, adjust=adjust)
        if tencent_df is not None and not tencent_df.empty:
            logger.info(f"[DATA_SOURCE] remote_api(tencent_kline) symbol={symbol}")
            return _normalize_local_price_df(tencent_df)
    except Exception as exc:
        logger.warning(f"Tencent history unavailable for {symbol}: {exc}")

    try:
        remote_df = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
            adjust=adjust,
        )
        if remote_df is not None and not remote_df.empty:
            remote_df = _rename_remote_price_columns(remote_df)
            logger.info(f"[DATA_SOURCE] remote_api(akshare_hist) symbol={symbol}")
            return _normalize_local_price_df(remote_df)
    except Exception as exc:
        logger.warning(f"AkShare history unavailable for {symbol}: {exc}")

    try:
        yf_symbol = get_stock_code_for_yfinance(symbol)
        logger.info(f"Fetching data from yfinance for {yf_symbol}")
        data = yf.Ticker(yf_symbol).history(start=start_date, end=end_date)

        if data is None or data.empty:
            logger.warning(f"No data returned from yfinance for {yf_symbol}")
            return pd.DataFrame()

        data = data.reset_index()
        data.columns = data.columns.str.lower()
        data = data.rename(
            columns={
                "date": "date",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
            }
        )
        data["date"] = pd.to_datetime(data["date"])
        logger.info(f"[DATA_SOURCE] remote_api(yfinance) symbol={symbol}")
        return _normalize_local_price_df(data)
    except Exception as exc:
        logger.error(f"Error fetching data from yfinance: {exc}")
        return pd.DataFrame()


def get_price_data(*args, **kwargs) -> pd.DataFrame:
    """Legacy alias kept for older modules."""
    return get_price_history(*args, **kwargs)


def prices_to_df(prices: Any) -> pd.DataFrame:
    """Convert stored price payloads back to a normalized DataFrame."""
    if isinstance(prices, pd.DataFrame):
        return prices.copy()
    if not prices:
        return pd.DataFrame()
    if isinstance(prices, dict):
        prices = [prices]
    if isinstance(prices, list):
        return _normalize_local_price_df(pd.DataFrame(prices))
    return pd.DataFrame()


def _get_snapshot_root() -> Path:
    env_override = os.getenv("ASHAREAGENT_SNAPSHOT_DIR", "").strip()
    if env_override:
        return Path(env_override)
    return Path(__file__).resolve().parents[2] / "data" / "snapshots"


def _parse_snapshot_time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _strip_snapshot_metadata(payload: Any) -> Any:
    if isinstance(payload, list):
        return [_strip_snapshot_metadata(item) for item in payload]
    if isinstance(payload, dict):
        return {
            key: _strip_snapshot_metadata(val)
            for key, val in payload.items()
            if key not in SNAPSHOT_METADATA_KEYS
        }
    return payload


def _extract_stock_row(df: pd.DataFrame, symbol: str) -> Optional[pd.Series]:
    if df is None or df.empty:
        return None
    normalized_target = _normalize_a_share_symbol(symbol)
    if not normalized_target:
        return None
    for code_column in ("代码", "证券代码", "symbol"):
        if code_column in df.columns:
            normalized_codes = df[code_column].map(_normalize_a_share_symbol)
            matched = df[normalized_codes == normalized_target]
            if not matched.empty:
                return matched.iloc[0]
    return None


def _extract_row_value(row: Optional[pd.Series], *keys: str) -> Any:
    if row is None:
        return None
    for key in keys:
        if key in row.index:
            value = row.get(key)
            if value is not None and not (isinstance(value, float) and np.isnan(value)):
                return value
    return None


def _get_financial_metrics_akshare(symbol: str) -> List[Dict[str, Any]]:
    """Fetch financial metrics from AkShare with spot -> EM fallback."""
    logger.info("Fetching AkShare financial metrics...")

    quotes_df = None
    try:
        quotes_df = ak.stock_zh_a_spot()
    except Exception as exc:
        logger.warning(f"AkShare spot unavailable for {symbol}: {exc}")

    if quotes_df is None or quotes_df.empty:
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                quotes_df = executor.submit(ak.stock_zh_a_spot_em).result(timeout=15)
        except (Exception, ConcurrentTimeoutError) as exc:
            logger.warning(f"AkShare spot_em unavailable for {symbol}: {exc}")

    if quotes_df is None or quotes_df.empty:
        raise Exception("No spot quote data found from akshare")

    stock_row = _extract_stock_row(quotes_df, symbol)
    if stock_row is None:
        raise Exception(f"No stock quote data found for {symbol}")

    current_year = datetime.now().year
    financial_data = None
    for year in range(current_year, current_year - 3, -1):
        try:
            candidate = ak.stock_financial_analysis_indicator(symbol=symbol, start_year=str(year))
            if candidate is not None and not candidate.empty:
                financial_data = candidate
                break
        except Exception as exc:
            logger.warning(f"AkShare financial indicator fetch failed for {symbol} ({year}): {exc}")

    if financial_data is None or financial_data.empty:
        raise Exception(f"No financial indicators available for {symbol}")

    latest_financial = financial_data.iloc[0]
    market_cap = safe_float(_extract_row_value(stock_row, "总市值", "market_cap"))

    return [{
        "return_on_equity": convert_percentage(_extract_row_value(latest_financial, "净资产收益率(%)")),
        "net_margin": convert_percentage(_extract_row_value(latest_financial, "销售净利率(%)")),
        "operating_margin": convert_percentage(_extract_row_value(latest_financial, "营业利润率(%)")),
        "revenue_growth": convert_percentage(_extract_row_value(latest_financial, "主营业务收入增长率(%)")),
        "earnings_growth": convert_percentage(_extract_row_value(latest_financial, "净利润增长率(%)")),
        "book_value_growth": convert_percentage(_extract_row_value(latest_financial, "净资产增长率(%)")),
        "current_ratio": safe_float(_extract_row_value(latest_financial, "流动比率")),
        "debt_to_equity": convert_percentage(_extract_row_value(latest_financial, "资产负债率(%)")),
        "free_cash_flow_per_share": safe_float(_extract_row_value(latest_financial, "每股经营性现金流(元)")),
        "earnings_per_share": safe_float(_extract_row_value(latest_financial, "加权每股收益(元)")),
        "pe_ratio": safe_float(_extract_row_value(stock_row, "市盈率-动态", "市盈率(动态)", "PE")),
        "price_to_book": safe_float(_extract_row_value(stock_row, "市净率", "PB")),
        "price_to_sales": _calculate_ps_ratio(
            market_cap,
            safe_float(_extract_row_value(latest_financial, "营业总收入", "主营业务收入")),
        ),
        "market_cap": market_cap,
        "current_price": safe_float(_extract_row_value(stock_row, "最新价", "现价", "收盘价")),
    }]


def _get_financial_metrics_eastmoney(symbol: str) -> List[Dict[str, Any]]:
    em_data = get_eastmoney_data(symbol, raw_response=False)
    if not em_data:
        raise Exception(f"No EastMoney data for {symbol}")

    return [{
        "pe_ratio": em_data.get("pe_ratio_dynamic"),
        "price_to_book": em_data.get("pb_ratio"),
        "price_to_sales": em_data.get("ps_ratio"),
        "market_cap": em_data.get("market_cap"),
        "current_price": em_data.get("current_price"),
        "change_pct": em_data.get("change_pct"),
    }]


def _get_financial_metrics_tencent(symbol: str) -> List[Dict[str, Any]]:
    quote_metrics = _extract_tencent_quote_metrics(symbol)
    if not quote_metrics:
        raise Exception(f"No Tencent data for {symbol}")
    return [{
        "pe_ratio": quote_metrics.get("pe_ratio"),
        "price_to_book": quote_metrics.get("price_to_book"),
        "price_to_sales": quote_metrics.get("price_to_sales"),
        "market_cap": quote_metrics.get("market_cap"),
        "current_price": quote_metrics.get("current_price"),
    }]


def _get_financial_fundamentals_sina(symbol: str) -> Dict[str, Any]:
    normalized = _normalize_a_share_symbol(symbol)
    if not normalized:
        raise Exception(f"Invalid symbol for sina fundamentals: {symbol}")

    current_year = datetime.now().year
    financial_data = None
    for year in range(current_year, current_year - 3, -1):
        try:
            candidate = ak.stock_financial_analysis_indicator(symbol=normalized, start_year=str(year))
            if candidate is not None and not candidate.empty:
                financial_data = candidate
                break
        except Exception as exc:
            logger.warning(f"Sina financial indicator fetch failed for {symbol} ({year}): {exc}")

    if financial_data is None or financial_data.empty:
        raise Exception(f"No sina financial indicators available for {symbol}")

    latest_financial = financial_data.iloc[0]
    return {
        "return_on_equity": convert_percentage(_extract_row_value(latest_financial, "净资产收益率(%)")),
        "net_margin": convert_percentage(_extract_row_value(latest_financial, "销售净利率(%)")),
        "operating_margin": convert_percentage(_extract_row_value(latest_financial, "营业利润率(%)")),
        "revenue_growth": convert_percentage(_extract_row_value(latest_financial, "主营业务收入增长率(%)")),
        "earnings_growth": convert_percentage(_extract_row_value(latest_financial, "净利润增长率(%)")),
        "book_value_growth": convert_percentage(_extract_row_value(latest_financial, "净资产增长率(%)")),
        "current_ratio": safe_float(_extract_row_value(latest_financial, "流动比率")),
        "debt_to_equity": convert_percentage(_extract_row_value(latest_financial, "资产负债率(%)")),
        "free_cash_flow_per_share": safe_float(_extract_row_value(latest_financial, "每股经营性现金流(元)")),
        "earnings_per_share": safe_float(_extract_row_value(latest_financial, "加权每股收益(元)")),
    }


def _is_missing_metric_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
        return True
    if isinstance(value, (int, float)) and value == 0:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _merge_metric_rows(primary_row: Dict[str, Any], supplement_row: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(primary_row)
    for key, value in supplement_row.items():
        if value is None:
            continue
        if key not in merged or _is_missing_metric_value(merged.get(key)):
            merged[key] = value
    return merged


def get_financial_metrics(symbol: str) -> List[Dict[str, Any]]:
    """Get financial metrics with snapshot-first fallback."""
    logger.info(f"Getting financial indicators for {symbol} with enhanced validation...")

    snapshot_hit = _load_dataset_snapshot("financial_metrics", symbol)
    if snapshot_hit:
        logger.info(f"Using fresh local snapshot for financial metrics ({symbol})")
        if snapshot_hit and len(snapshot_hit) > 0:
            data_quality, quality_msg = validate_data_quality(
                snapshot_hit[0],
                required_fields=["return_on_equity", "pe_ratio", "price_to_book"],
            )
            if data_quality:
                return snapshot_hit
            logger.warning(f"Snapshot data quality issue: {quality_msg}")

    base_row: Dict[str, Any] | None = None
    base_source = ""

    try:
        tencent_result = _get_financial_metrics_tencent(symbol)
        if tencent_result and tencent_result != [{}]:
            base_row = dict(tencent_result[0])
            base_source = "tencent"
    except Exception as exc:
        logger.error(f"Error fetching financial metrics from tencent: {exc}")

    if base_row is None:
        try:
            akshare_result = _get_financial_metrics_akshare(symbol)
            if akshare_result and akshare_result != [{}]:
                base_row = dict(akshare_result[0])
                base_source = "akshare"
        except Exception as exc:
            logger.error(f"Error fetching financial metrics from akshare: {exc}")

    supplemented = False
    if base_row is not None:
        try:
            sina_fundamentals = _get_financial_fundamentals_sina(symbol)
            merged_row = _merge_metric_rows(base_row, sina_fundamentals)
            supplemented = any(
                not _is_missing_metric_value(merged_row.get(key))
                and _is_missing_metric_value(base_row.get(key))
                for key in (
                    "return_on_equity",
                    "net_margin",
                    "revenue_growth",
                    "earnings_growth",
                    "operating_margin",
                )
            )
            base_row = merged_row
        except Exception as exc:
            logger.warning(f"Sina fundamentals supplement unavailable for {symbol}: {exc}")

    if base_row is None:
        try:
            sina_fundamentals = _get_financial_fundamentals_sina(symbol)
            base_row = dict(sina_fundamentals)
            base_source = "sina_finance"
        except Exception as exc:
            logger.error(f"Error fetching financial metrics from sina_finance: {exc}")

    if base_row is not None:
        source_label = base_source
        if base_source == "tencent" and supplemented:
            source_label = "tencent+sina_finance"
        result = [base_row]
        _save_dataset_snapshot("financial_metrics", symbol, result, source=source_label)
        return _attach_snapshot_metadata(
            result,
            data_source=source_label,
            cache_status="remote_live",
            fetched_at=datetime.now().isoformat(),
            is_snapshot=False,
            ttl_hours=DATASET_SNAPSHOT_TTLS["financial_metrics"],
        )

    stale_snapshot = _load_dataset_snapshot("financial_metrics", symbol, allow_stale=True)
    if stale_snapshot:
        logger.warning(f"Remote financial metrics failed, using stale local snapshot ({symbol})")
        return stale_snapshot

    try:
        offline_path = _build_offline_financials_path(symbol)
        if offline_path.exists():
            with offline_path.open("r", encoding="utf-8") as f:
                offline_data = json.load(f)
                offline_payload = _resolve_offline_symbol_payload(offline_data, symbol)
                if offline_payload and isinstance(offline_payload.get("metrics"), dict):
                    logger.info(f"Using OFFLINE CACHE for financial metrics ({symbol})")
                    return _attach_snapshot_metadata(
                        [offline_payload["metrics"]],
                        data_source="offline_json",
                        cache_status="offline_fallback",
                        fetched_at=datetime.now().isoformat(),
                        is_snapshot=False,
                        ttl_hours=DATASET_SNAPSHOT_TTLS["financial_metrics"],
                    )
    except Exception as offline_e:
        logger.error(f"Offline cache also failed: {offline_e}")

    return _attach_snapshot_metadata(
        [_get_default_financial_metrics()],
        data_source="default_empty",
        cache_status="default_empty",
        fetched_at=datetime.now().isoformat(),
        is_snapshot=False,
        ttl_hours=DATASET_SNAPSHOT_TTLS["financial_metrics"],
    )

def _get_default_financial_metrics() -> Dict[str, Any]:
    """获取默认财务指标"""
    return {
        "return_on_equity": None,
        "net_margin": None,
        "operating_margin": None,
        "revenue_growth": None,
        "earnings_growth": None,
        "book_value_growth": None,
        "current_ratio": None,
        "debt_to_equity": None,
        "free_cash_flow_per_share": None,
        "earnings_per_share": None,
        "pe_ratio": None,
        "price_to_book": None,
        "price_to_sales": None,
    }

def validate_data_quality(data: Any, required_fields: List[str] = None) -> tuple[bool, str]:
    """
    验证数据质量

    Args:
        data: 要验证的数据
        required_fields: 必需字段列表

    Returns:
        (是否合格, 验证信息)
    """
    if data is None:
        return False, "Data is None"

    if not isinstance(data, dict):
        return False, "Data is not a dictionary"

    if not data:
        return False, "Data is empty"

    if required_fields:
        missing_fields = []
        for field in required_fields:
            if field not in data or data[field] is None:
                missing_fields.append(field)

        if missing_fields:
            return False, f"Missing required fields: {missing_fields}"

    # 检查是否有合理的非空数据
    non_null_count = sum(1 for v in data.values() if v is not None and str(v).strip() != '')
    total_fields = len(data)

    if total_fields > 0 and non_null_count / total_fields < 0.1:  # 至少10%的数据非空
        return False, f"Too few non-null values: {non_null_count}/{total_fields}"

    return True, "Data quality is acceptable"


def _default_financial_statement_item() -> Dict[str, Any]:
    return {
        "net_income": 0,
        "revenue": 0,
        "operating_revenue": 0,
        "operating_profit": 0,
        "total_assets": 0,
        "current_assets": 0,
        "current_liabilities": 0,
        "total_liabilities": 0,
        "stockholders_equity": 0,
        "working_capital": 0,
        "depreciation_and_amortization": 0,
        "capital_expenditure": 0,
        "free_cash_flow": 0,
    }


def _normalize_a_share_symbol(symbol: Any) -> str:
    raw = str(symbol or "").strip().upper()
    if not raw:
        return ""
    if "." in raw:
        raw = raw.split(".", 1)[0]
    if raw.startswith(("SH", "SZ", "BJ")) and raw[2:].isdigit():
        raw = raw[2:]
    if raw.isdigit():
        return raw.zfill(6)
    return raw


def _get_sina_prefixed_symbol(symbol: str) -> str:
    normalized = _normalize_a_share_symbol(symbol)
    if normalized.startswith(("60", "68", "90")):
        return f"sh{normalized}"
    return f"sz{normalized}"


def _resolve_offline_symbol_payload(offline_data: Dict[str, Any], symbol: str) -> Optional[Dict[str, Any]]:
    normalized_symbol = _normalize_a_share_symbol(symbol)
    candidate_keys = [
        symbol,
        normalized_symbol,
        f"{normalized_symbol}.SH",
        f"{normalized_symbol}.SZ",
        f"{normalized_symbol}.SS",
    ]
    seen: set[str] = set()
    for key in candidate_keys:
        if key and key not in seen:
            seen.add(key)
            payload = offline_data.get(key)
            if isinstance(payload, dict):
                return payload

    for key, payload in offline_data.items():
        if not isinstance(payload, dict):
            continue
        if _normalize_a_share_symbol(key) == normalized_symbol:
            return payload
    return None


def _derive_financial_statements_from_offline_payload(payload: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    if not isinstance(payload, dict):
        return None
    statements = payload.get("statements")
    if isinstance(statements, list) and statements:
        return statements

    market_data = payload.get("market_data") if isinstance(payload.get("market_data"), dict) else {}
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}

    net_income = safe_float(
        market_data.get("netIncomeToCommon"),
        safe_float(metrics.get("net_income"), 0),
    ) or 0
    revenue = safe_float(
        market_data.get("totalRevenue"),
        safe_float(metrics.get("revenue"), 0),
    ) or 0
    free_cash_flow = safe_float(
        market_data.get("freeCashflow"),
        safe_float(metrics.get("free_cash_flow"), 0),
    ) or 0
    operating_profit = safe_float(
        market_data.get("ebitda"),
        safe_float(metrics.get("operating_profit"), 0),
    ) or 0
    total_assets = safe_float(metrics.get("total_assets"), 0) or 0
    total_liabilities = safe_float(metrics.get("total_liabilities"), 0) or 0
    stockholders_equity = safe_float(
        metrics.get("stockholders_equity"),
        safe_float(market_data.get("bookValue"), 0),
    ) or 0

    if net_income <= 0 and revenue <= 0 and free_cash_flow <= 0:
        return None

    derived_item = _default_financial_statement_item()
    derived_item.update(
        {
            "net_income": net_income,
            "revenue": revenue,
            "operating_revenue": revenue,
            "operating_profit": operating_profit,
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "stockholders_equity": stockholders_equity,
            "free_cash_flow": free_cash_flow,
        }
    )
    return [derived_item, derived_item.copy()]


def get_financial_statements(symbol: str) -> List[Dict[str, Any]]:
    snapshot_hit = _load_dataset_snapshot("financial_statements", symbol)
    if snapshot_hit:
        logger.info(f"Using fresh local snapshot for financial statements ({symbol})")
        return snapshot_hit

    stock_code = _get_sina_prefixed_symbol(symbol)
    try:
        balance_sheet = ak.stock_financial_report_sina(stock=stock_code, symbol="资产负债表")
        income_statement = ak.stock_financial_report_sina(stock=stock_code, symbol="利润表")
        cash_flow = ak.stock_financial_report_sina(stock=stock_code, symbol="现金流量表")

        if balance_sheet.empty or income_statement.empty or cash_flow.empty:
            raise Exception(f"Incomplete Sina statements for {symbol}")

        latest_balance = balance_sheet.iloc[0]
        previous_balance = balance_sheet.iloc[1] if len(balance_sheet) > 1 else latest_balance
        latest_income = income_statement.iloc[0]
        previous_income = income_statement.iloc[1] if len(income_statement) > 1 else latest_income
        latest_cash_flow = cash_flow.iloc[0]
        previous_cash_flow = cash_flow.iloc[1] if len(cash_flow) > 1 else latest_cash_flow

        def build_item(balance_row: pd.Series, income_row: pd.Series, cash_row: pd.Series) -> Dict[str, Any]:
            revenue = safe_float(income_row.get("营业总收入"), 0) or safe_float(income_row.get("营业收入"), 0) or 0
            current_assets = safe_float(balance_row.get("流动资产合计"), 0) or 0
            current_liabilities = safe_float(balance_row.get("流动负债合计"), 0) or 0
            equity = (
                safe_float(balance_row.get("所有者权益(或股东权益)合计"), 0)
                or safe_float(balance_row.get("所有者权益合计"), 0)
                or safe_float(balance_row.get("股东权益合计"), 0)
                or 0
            )
            operating_cash_flow = safe_float(cash_row.get("经营活动产生的现金流量净额"), 0) or 0
            capex = abs(safe_float(cash_row.get("购建固定资产、无形资产和其他长期资产支付的现金"), 0) or 0)
            return {
                "net_income": safe_float(income_row.get("净利润"), 0) or 0,
                "revenue": revenue,
                "operating_revenue": revenue,
                "operating_profit": safe_float(income_row.get("营业利润"), 0) or 0,
                "total_assets": safe_float(balance_row.get("资产总计"), 0) or 0,
                "current_assets": current_assets,
                "current_liabilities": current_liabilities,
                "total_liabilities": safe_float(balance_row.get("负债合计"), 0) or 0,
                "stockholders_equity": equity,
                "working_capital": current_assets - current_liabilities,
                "depreciation_and_amortization": safe_float(
                    cash_row.get("固定资产折旧、油气资产折耗、生产性生物资产折旧"),
                    0,
                ) or 0,
                "capital_expenditure": capex,
                "free_cash_flow": operating_cash_flow - capex,
            }

        line_items = [
            build_item(latest_balance, latest_income, latest_cash_flow),
            build_item(previous_balance, previous_income, previous_cash_flow),
        ]
        _save_dataset_snapshot("financial_statements", symbol, line_items, source="akshare_sina")
        return _attach_snapshot_metadata(
            line_items,
            data_source="akshare_sina",
            cache_status="remote_live",
            fetched_at=datetime.now().isoformat(),
            is_snapshot=False,
            ttl_hours=DATASET_SNAPSHOT_TTLS["financial_statements"],
        )
    except Exception as exc:
        logger.error(f"Error getting financial statements for {symbol}: {exc}")

    stale_snapshot = _load_dataset_snapshot("financial_statements", symbol, allow_stale=True)
    if stale_snapshot:
        logger.warning(f"Remote financial statements failed, using stale local snapshot ({symbol})")
        return stale_snapshot

    try:
        offline_path = _build_offline_financials_path(symbol)
        if offline_path.exists():
            with offline_path.open("r", encoding="utf-8") as f:
                offline_data = json.load(f)
                offline_payload = _resolve_offline_symbol_payload(offline_data, symbol)
                if not offline_payload:
                    offline_payload = {}
                derived_statements = _derive_financial_statements_from_offline_payload(offline_payload)
                if derived_statements:
                    cache_status = "offline_fallback"
                    data_source = "offline_json"
                    if not offline_payload.get("statements"):
                        cache_status = "offline_derived"
                        data_source = "offline_json_derived"
                    return _attach_snapshot_metadata(
                        derived_statements,
                        data_source=data_source,
                        cache_status=cache_status,
                        fetched_at=datetime.now().isoformat(),
                        is_snapshot=False,
                        ttl_hours=DATASET_SNAPSHOT_TTLS["financial_statements"],
                    )
    except Exception as exc:
        logger.error(f"Offline financial statements cache failed: {exc}")

    default_item = _default_financial_statement_item()
    return _attach_snapshot_metadata(
        [default_item, default_item.copy()],
        data_source="default_empty",
        cache_status="default_empty",
        fetched_at=datetime.now().isoformat(),
        is_snapshot=False,
        ttl_hours=DATASET_SNAPSHOT_TTLS["financial_statements"],
    )


def calculate_comprehensive_financial_metrics(
    symbol: str,
    financial_statements: List[Dict[str, Any]] = None,
    financial_indicators: List[Dict[str, Any]] = None,
    market_data: Dict[str, Any] = None,
) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}

    if financial_indicators and len(financial_indicators) > 0:
        indicators = financial_indicators[0]
        for key in [
            "return_on_equity",
            "net_margin",
            "operating_margin",
            "current_ratio",
            "debt_to_equity",
            "revenue_growth",
            "earnings_growth",
            "book_value_growth",
            "earnings_per_share",
            "free_cash_flow_per_share",
            "pe_ratio",
            "price_to_book",
            "price_to_sales",
            "market_cap",
        ]:
            if indicators.get(key) is not None:
                metrics[key] = indicators.get(key)

    if market_data:
        for key, value in {
            "pe_ratio": market_data.get("pe_ratio") or market_data.get("pe_ratio_dynamic"),
            "price_to_book": market_data.get("price_to_book") or market_data.get("pb_ratio"),
            "price_to_sales": market_data.get("price_to_sales") or market_data.get("ps_ratio"),
            "market_cap": market_data.get("market_cap"),
        }.items():
            if value is not None and value != 0:
                metrics[key] = value

    if financial_statements and len(financial_statements) >= 1:
        latest = financial_statements[0]
        revenue = safe_float(latest.get("operating_revenue"), 0) or safe_float(latest.get("revenue"), 0)
        net_income = safe_float(latest.get("net_income"), 0)
        operating_profit = safe_float(latest.get("operating_profit"), 0)
        equity = safe_float(latest.get("stockholders_equity"), 0)
        current_assets = safe_float(latest.get("current_assets"), 0)
        current_liabilities = safe_float(latest.get("current_liabilities"), 0)
        total_liabilities = safe_float(latest.get("total_liabilities"), 0)

        if metrics.get("return_on_equity") is None and net_income and equity and equity > 0:
            metrics["return_on_equity"] = net_income / equity
        if metrics.get("net_margin") is None and net_income and revenue and revenue > 0:
            metrics["net_margin"] = net_income / revenue
        if metrics.get("operating_margin") is None and operating_profit and revenue and revenue > 0:
            metrics["operating_margin"] = operating_profit / revenue
        if metrics.get("current_ratio") is None and current_assets and current_liabilities and current_liabilities > 0:
            metrics["current_ratio"] = current_assets / current_liabilities
        if metrics.get("debt_to_equity") is None and total_liabilities and equity and equity > 0:
            metrics["debt_to_equity"] = total_liabilities / equity

        if len(financial_statements) >= 2:
            previous = financial_statements[1]
            previous_revenue = safe_float(previous.get("operating_revenue"), 0) or safe_float(previous.get("revenue"), 0)
            previous_income = safe_float(previous.get("net_income"), 0)
            if metrics.get("revenue_growth") is None and revenue and previous_revenue and previous_revenue > 0:
                metrics["revenue_growth"] = (revenue - previous_revenue) / previous_revenue
            if metrics.get("earnings_growth") is None and net_income and previous_income and previous_income > 0:
                metrics["earnings_growth"] = (net_income - previous_income) / previous_income

        if metrics.get("earnings_per_share") is None and market_data:
            current_price = safe_float(market_data.get("current_price"))
            market_cap = safe_float(market_data.get("market_cap"))
            if current_price and market_cap and current_price > 0 and net_income:
                shares_outstanding = market_cap / current_price
                if shares_outstanding > 0:
                    metrics["earnings_per_share"] = net_income / shares_outstanding

    for metric in [
        "return_on_equity",
        "net_margin",
        "operating_margin",
        "revenue_growth",
        "earnings_growth",
        "book_value_growth",
        "current_ratio",
        "debt_to_equity",
        "free_cash_flow_per_share",
        "earnings_per_share",
        "pe_ratio",
        "price_to_book",
        "price_to_sales",
        "market_cap",
    ]:
        metrics.setdefault(metric, None)

    if metrics.get("pe_ratio") is None and market_data:
        current_price = safe_float(market_data.get("current_price"))
        earnings_per_share = safe_float(metrics.get("earnings_per_share"))
        if current_price and earnings_per_share and earnings_per_share > 0:
            metrics["pe_ratio"] = current_price / earnings_per_share

    return metrics


def _get_market_data_akshare(symbol: str) -> Dict[str, Any]:
    try:
        realtime_data = ak.stock_zh_a_spot()
        spot_source = "akshare_spot"
    except Exception as exc:
        logger.warning(f"AkShare spot market data unavailable for {symbol}: {exc}")
        realtime_data = ak.stock_zh_a_spot_em()
        spot_source = "akshare_spot_em"

    if realtime_data is None or realtime_data.empty:
        raise Exception("No market data from akshare")

    stock_row = _extract_stock_row(realtime_data, symbol)
    if stock_row is None:
        raise Exception(f"No stock data found for {symbol} in akshare")

    volume = safe_float(_extract_row_value(stock_row, "成交量", "volume"))
    return {
        "current_price": safe_float(_extract_row_value(stock_row, "最新价", "现价", "收盘价")),
        "market_cap": safe_float(_extract_row_value(stock_row, "总市值", "market_cap")),
        "volume": volume,
        "average_volume": volume,
        "pe_ratio": safe_float(_extract_row_value(stock_row, "市盈率-动态", "市盈率(动态)", "PE")),
        "price_to_book": safe_float(_extract_row_value(stock_row, "市净率", "PB")),
        "price_to_sales": safe_float(_extract_row_value(stock_row, "市销率", "PS")),
        "fifty_two_week_high": safe_float(_extract_row_value(stock_row, "52周最高", "52周最高价")),
        "fifty_two_week_low": safe_float(_extract_row_value(stock_row, "52周最低", "52周最低价")),
        "price_source": spot_source,
        "price_is_realtime": False,
    }


def _get_market_data_tencent(symbol: str) -> Dict[str, Any]:
    quote_metrics = _extract_tencent_quote_metrics(symbol)
    if not quote_metrics:
        raise Exception("No market data from tencent")
    return {
        "current_price": quote_metrics.get("current_price"),
        "market_cap": quote_metrics.get("market_cap"),
        "volume": quote_metrics.get("volume"),
        "average_volume": quote_metrics.get("average_volume"),
        "pe_ratio": quote_metrics.get("pe_ratio"),
        "price_to_book": quote_metrics.get("price_to_book"),
        "price_to_sales": quote_metrics.get("price_to_sales"),
        "fifty_two_week_high": quote_metrics.get("fifty_two_week_high"),
        "fifty_two_week_low": quote_metrics.get("fifty_two_week_low"),
        "price_source": "tencent_quote",
        "price_is_realtime": False,
        "price_as_of": quote_metrics.get("price_as_of"),
    }


def _get_market_data_eastmoney(symbol: str) -> Dict[str, Any]:
    data = get_eastmoney_data(symbol)
    if not data:
        raise Exception("No market data from eastmoney")
    return {
        "market_cap": data.get("market_cap"),
        "volume": data.get("volume"),
        "average_volume": data.get("volume"),
        "current_price": data.get("current_price"),
        "pe_ratio": data.get("pe_ratio_dynamic"),
        "price_to_book": data.get("pb_ratio"),
        "price_to_sales": data.get("ps_ratio"),
        "fifty_two_week_high": None,
        "fifty_two_week_low": None,
        "price_source": "eastmoney",
        "price_is_realtime": False,
    }


def get_market_data(symbol: str) -> Dict[str, Any]:
    """Get market data with snapshot-first fallback."""
    snapshot_hit = _load_dataset_snapshot("market_data", symbol)
    if snapshot_hit:
        logger.info(f"Using fresh local snapshot for market data ({symbol})")
        return snapshot_hit

    for source, fetcher in (
        ("tencent", _get_market_data_tencent),
        ("akshare", _get_market_data_akshare),
    ):
        try:
            result = fetcher(symbol)
            if result:
                _save_dataset_snapshot("market_data", symbol, result, source=source)
                return _attach_snapshot_metadata(
                    result,
                    data_source=source,
                    cache_status="remote_live",
                    fetched_at=datetime.now().isoformat(),
                    is_snapshot=False,
                    ttl_hours=DATASET_SNAPSHOT_TTLS["market_data"],
                )
        except Exception as exc:
            logger.error(f"Error fetching market data from {source}: {exc}")

    stale_snapshot = _load_dataset_snapshot("market_data", symbol, allow_stale=True)
    if stale_snapshot:
        logger.warning(f"Remote market data failed, using stale local snapshot ({symbol})")
        return stale_snapshot

    try:
        offline_path = _build_offline_financials_path(symbol)
        if offline_path.exists():
            with offline_path.open("r", encoding="utf-8") as f:
                offline_data = json.load(f)
                offline_payload = _resolve_offline_symbol_payload(offline_data, symbol)
                if offline_payload and isinstance(offline_payload.get("market_data"), dict):
                    return _attach_snapshot_metadata(
                        offline_payload["market_data"],
                        data_source="offline_json",
                        cache_status="offline_fallback",
                        fetched_at=datetime.now().isoformat(),
                        is_snapshot=False,
                        ttl_hours=DATASET_SNAPSHOT_TTLS["market_data"],
                    )
    except Exception as exc:
        logger.error(f"Offline market data cache failed: {exc}")

    return _attach_snapshot_metadata(
        {},
        data_source="default_empty",
        cache_status="default_empty",
        fetched_at=datetime.now().isoformat(),
        is_snapshot=False,
        ttl_hours=DATASET_SNAPSHOT_TTLS["market_data"],
    )

def _build_offline_financials_path(symbol: str) -> Path:
    """构建离线财务数据路径"""
    normalized = _normalize_a_share_symbol(symbol)
    return Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))) / "data" / f"offline_financials_{normalized}.json"

def _calculate_ps_ratio(market_cap, revenue):
    """计算市销率"""
    mc = safe_float(market_cap)
    rev = safe_float(revenue)
    if mc and rev and rev > 0:
        return mc / rev
    return None

def _snapshot_symbol_candidates(symbol: str) -> list[str]:
    raw = str(symbol or "")
    stripped = raw.strip()
    normalized = _normalize_a_share_symbol(stripped)
    candidates: list[str] = []
    for item in (normalized, stripped, raw):
        if item and item not in candidates:
            candidates.append(item)
    return candidates


def _resolve_snapshot_path(dataset: str, symbol: str) -> Optional[Path]:
    root = _get_snapshot_root() / dataset
    if not root.exists():
        return None

    for candidate in _snapshot_symbol_candidates(symbol):
        path = root / f"{candidate}.json"
        if path.exists():
            return path

    normalized = _normalize_a_share_symbol(symbol)
    if normalized:
        for path in sorted(root.glob(f"{normalized}*.json")):
            if path.exists():
                return path

    return None


def _load_dataset_snapshot(dataset: str, symbol: str, *, allow_stale: bool = False) -> Optional[Any]:
    """从本地快照目录加载数据集快照。"""
    snapshot_path = _resolve_snapshot_path(dataset, symbol)
    if snapshot_path is None:
        return None

    try:
        snapshot_payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"Failed to read snapshot {snapshot_path}: {exc}")
        return None

    fetched_at = snapshot_payload.get("fetched_at") or snapshot_payload.get("saved_at")
    ttl_hours = DATASET_SNAPSHOT_TTLS.get(dataset, 24)
    fetched_at_dt = _parse_snapshot_time(fetched_at)
    is_stale = True
    if fetched_at_dt is not None:
        now = datetime.now(fetched_at_dt.tzinfo) if fetched_at_dt.tzinfo else datetime.now()
        is_stale = now - fetched_at_dt > timedelta(hours=ttl_hours)

    if is_stale and not allow_stale:
        return None

    return _attach_snapshot_metadata(
        snapshot_payload.get("data"),
        data_source=snapshot_payload.get("source", "snapshot"),
        cache_status="stale_snapshot" if is_stale else "fresh_snapshot",
        fetched_at=fetched_at or datetime.now().isoformat(),
        is_snapshot=True,
        ttl_hours=ttl_hours,
    )

def _save_dataset_snapshot(dataset: str, symbol: str, payload: Any, *, source: str) -> None:
    """保存数据集快照到本地目录。"""
    normalized = _normalize_a_share_symbol(symbol) or str(symbol).strip() or str(symbol)
    snapshot_path = _get_snapshot_root() / dataset / f"{normalized}.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_payload = {
        "dataset": dataset,
        "symbol": normalized,
        "source": source,
        "fetched_at": datetime.now().isoformat(),
        "data": _strip_snapshot_metadata(payload),
    }
    snapshot_path.write_text(
        json.dumps(snapshot_payload, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    for candidate in _snapshot_symbol_candidates(symbol):
        if candidate == normalized:
            continue
        legacy_path = snapshot_path.parent / f"{candidate}.json"
        if legacy_path.exists():
            try:
                legacy_path.unlink()
            except Exception:
                pass

def _attach_snapshot_metadata(payload: Any, *, data_source: str, cache_status: str, fetched_at: str, is_snapshot: bool, ttl_hours: int) -> Any:
    """附加统一的快照元数据。"""
    metadata = {
        "data_source": data_source,
        "data_as_of": fetched_at[:10] if fetched_at else None,
        "cache_status": cache_status,
        "is_snapshot": is_snapshot,
        "snapshot_fetched_at": fetched_at,
        "snapshot_ttl_hours": ttl_hours,
    }

    clean_payload = _strip_snapshot_metadata(payload)
    if isinstance(clean_payload, list):
        enriched = []
        for item in clean_payload:
            if isinstance(item, dict):
                merged = item.copy()
                merged.update(metadata)
                enriched.append(merged)
            else:
                enriched.append(item)
        return enriched

    if isinstance(clean_payload, dict):
        merged = clean_payload.copy()
        merged.update(metadata)
        return merged

    return clean_payload

def get_eastmoney_data(symbol: str, raw_response: bool = False) -> Optional[Dict[str, Any]]:
    """使用东方财富API获取实时数据"""
    try:
        # 东方财富实时数据API
        normalized_symbol = _normalize_a_share_symbol(symbol)
        url = "https://push2.eastmoney.com/api/qt/stock/get"
        secid = f"1.{normalized_symbol}" if normalized_symbol.startswith("60") else f"0.{normalized_symbol}"
        params = {
            'secid': secid,
            # 添加更多财务指标字段: f114(PE动), f115(PE静), f116(总市值), f117(流通市值), f167(PB), f168(PS)
            'fields': 'f43,f57,f58,f162,f173,f170,f46,f60,f44,f45,f47,f48,f49,f50,f51,f52,f114,f115,f116,f117,f167,f168'
        }

        response = requests.get(
            url,
            params=params,
            timeout=DATA_SOURCES['eastmoney']['timeout'],
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; AShareAgent/1.0)",
                "Accept": "application/json,text/plain,*/*",
            },
        )
        response.raise_for_status()

        data = response.json()

        # 如果需要原始响应，直接返回
        if raw_response:
            return data

        if data.get('rc') == 0 and data.get('data'):
            stock_data = data['data']

            current_price = safe_float(stock_data.get('f43', 0)) / 100
            if current_price == 0:
                # 尝试使用昨日收盘价作为参考价格
                yesterday_close = safe_float(stock_data.get('f60', 0)) / 100
                if yesterday_close > 0:
                    current_price = yesterday_close
                    logger.info(f"Using yesterday's closing price for {symbol}: {current_price}")

            result = {
                'current_price': current_price,  # 现价
                'market_cap': safe_float(stock_data.get('f116', 0)),  # 总市值
                'pe_ratio_dynamic': safe_float(stock_data.get('f114', 0)),  # 市盈率动态
                'pe_ratio_static': safe_float(stock_data.get('f115', 0)),  # 市盈率静态
                'pb_ratio': safe_float(stock_data.get('f167', 0)),  # 市净率
                'ps_ratio': safe_float(stock_data.get('f168', 0)),  # 市销率
                'circulation_value': safe_float(stock_data.get('f117', 0)),  # 流通市值
                'volume': safe_float(stock_data.get('f47', 0)),  # 成交量
                'turnover': safe_float(stock_data.get('f48', 0)),  # 成交额
                'change_pct': safe_float(stock_data.get('f170', 0)),  # 涨跌幅
            }

            # 如果价格仍然为0，标记为无效数据
            if result['current_price'] == 0:
                logger.warning(f"No valid price data from eastmoney for {symbol}")
                return None

            return result
        else:
            logger.warning(f"No valid data from eastmoney for {symbol}")
            return None

    except Exception as e:
        logger.error(f"Error fetching data from eastmoney: {e}")
        return None


