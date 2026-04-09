"""Shared mock objects and fixtures for tests."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pandas as pd


class MockLLMResponse:
    """Simple mock LLM response container."""

    def __init__(self, signal: str = "neutral", confidence: float = 0.5, reasoning: str = "default reasoning"):
        self.signal = signal
        self.confidence = confidence
        self.reasoning = reasoning

    def to_json(self) -> str:
        return json.dumps(
            {
                "signal": self.signal,
                "confidence": self.confidence,
                "reasoning": self.reasoning,
            },
            ensure_ascii=False,
        )


class MockAkshareData:
    """Mock akshare-like market and history data."""

    @staticmethod
    def stock_zh_a_spot_em() -> pd.DataFrame:
        return pd.DataFrame(
            {
                "代码": ["000001", "000002", "600519"],
                "名称": ["平安银行", "万科A", "贵州茅台"],
                "最新价": [12.50, 18.30, 1680.00],
                "涨跌幅": [2.45, -1.20, 0.80],
                "总市值": [241_728_000_000, 201_564_000_000, 2_107_200_000_000],
                "市盈率-动态": [5.23, 7.89, 28.50],
                "市净率": [0.67, 0.98, 9.80],
                "成交量": [42_156_789, 15_234_567, 8_765_432],
            }
        )

    @staticmethod
    def stock_zh_a_hist(symbol: str, period: str = "daily", start_date: str | None = None, end_date: str | None = None) -> pd.DataFrame:
        del period  # Kept for compatibility with call sites.
        if not start_date:
            start_date = (datetime.now() - timedelta(days=100)).strftime("%Y%m%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")

        dates = pd.date_range(start=start_date, end=end_date, freq="D")
        base_price = 12.50 if symbol == "000001" else 18.30
        seq = pd.Series(range(len(dates)), index=dates)
        open_price = base_price + seq * 0.01
        close_price = open_price + 0.1

        return pd.DataFrame(
            {
                "日期": dates,
                "开盘": open_price.values,
                "收盘": close_price.values,
                "最高": (open_price + 0.2).values,
                "最低": (open_price - 0.1).values,
                "成交量": [1_000_000 + i * 10_000 for i in range(len(dates))],
                "成交额": [base_price * 1_000_000 * (1 + i * 0.001) for i in range(len(dates))],
                "振幅": [2.5] * len(dates),
                "涨跌幅": [0.8] * len(dates),
                "涨跌额": [0.1] * len(dates),
                "换手率": [1.2] * len(dates),
            }
        )


class MockEastmoneyAPI:
    """Mock Eastmoney API response."""

    @staticmethod
    def get_stock_data(stock_code: str) -> dict:
        del stock_code  # Kept for compatibility.
        return {
            "rc": 0,
            "rt": 1,
            "data": {
                "f43": 1250,
                "f44": 25,
                "f45": 2.04,
                "f46": 120000,
                "f47": 150000000,
                "f116": 241728000000,
                "f117": 180000000000,
                "f114": 5.23,
                "f115": 5.23,
                "f167": 0.67,
                "f168": 1.8,
                "f169": 15.2,
            },
        }


class MockNewsData:
    """Mock stock news data."""

    @staticmethod
    def get_stock_news(stock_code: str, count: int = 10) -> list[dict]:
        items = [
            {
                "title": f"{stock_code}公司发布三季报，业绩超预期",
                "content": "公司营收同比增长15%，净利润增长20%，超出市场预期。",
                "publish_time": "2024-01-15 09:30:00",
                "source": "财经网",
                "sentiment_score": 0.8,
            },
            {
                "title": f"{stock_code}获得大额订单，业务前景向好",
                "content": "公司与多家知名企业签署战略合作协议，未来增长可期。",
                "publish_time": "2024-01-14 14:20:00",
                "source": "证券时报",
                "sentiment_score": 0.7,
            },
            {
                "title": f"行业监管政策调整，{stock_code}面临挑战",
                "content": "新的行业政策对公司业务模式提出了更高要求。",
                "publish_time": "2024-01-13 16:45:00",
                "source": "财新网",
                "sentiment_score": -0.3,
            },
        ]
        return items[:count]


class MockFinancialData:
    """Mock financial metrics payload."""

    @staticmethod
    def get_financial_metrics(stock_code: str) -> dict:
        return {
            "basic_info": {
                "stock_code": stock_code,
                "stock_name": "测试股票",
                "industry": "金融业",
                "market_cap": 241728000000,
                "total_shares": 19356000000,
            },
            "profitability": {
                "roe": 12.5,
                "roa": 0.8,
                "gross_margin": 45.2,
                "net_margin": 28.6,
                "operating_margin": 35.8,
            },
            "growth": {
                "revenue_growth_yoy": 15.2,
                "profit_growth_yoy": 18.7,
                "revenue_growth_3y_avg": 12.8,
                "profit_growth_3y_avg": 16.3,
            },
            "financial_health": {
                "current_ratio": 1.45,
                "quick_ratio": 1.12,
                "debt_to_equity": 0.38,
                "interest_coverage": 8.5,
            },
            "valuation": {
                "pe_ratio": 12.5,
                "pb_ratio": 1.8,
                "ps_ratio": 2.2,
                "peg_ratio": 0.8,
                "ev_ebitda": 8.5,
            },
        }


def create_mock_agent_state(stock_symbol: str = "000001", portfolio_cash: float = 100000.0) -> dict:
    """Build a common mock agent state."""

    return {
        "messages": [],
        "data": {
            "stock_symbol": stock_symbol,
            "portfolio": {
                "cash": portfolio_cash,
                "stock": 0,
                "total_value": portfolio_cash,
            },
            "market_data": MockFinancialData.get_financial_metrics(stock_symbol),
            "price_data": MockAkshareData.stock_zh_a_hist(stock_symbol),
            "news_data": MockNewsData.get_stock_news(stock_symbol),
        },
        "metadata": {
            "show_reasoning": False,
            "current_agent_name": "test_agent",
            "analysis_timestamp": datetime.now().isoformat(),
            "market_session": "regular",
        },
    }


def create_mock_llm_client():
    """Create a mock LLM client with intent-aware responses."""

    mock_client = MagicMock()

    def mock_chat_completion(messages, *args, **kwargs):
        del args, kwargs
        message_text = " ".join(str(msg) for msg in messages)
        if any(keyword in message_text for keyword in ["Relative Valuation", "PB Percentile", "技术分析", "估值位置"]):
            return MockLLMResponse("bullish", 0.75, "PB百分位显示当前估值偏低，存在修复空间。").to_json()
        if any(keyword in message_text for keyword in ["基本面", "Fundamental"]):
            return MockLLMResponse("bullish", 0.7, "基本面指标稳健，盈利质量较好。").to_json()
        if any(keyword in message_text for keyword in ["情绪分析", "Sentiment", "Market Sentiment"]):
            return MockLLMResponse("neutral", 0.6, "新闻情绪中性偏积极。").to_json()
        return MockLLMResponse().to_json()

    mock_client.chat_completion = mock_chat_completion
    return mock_client
