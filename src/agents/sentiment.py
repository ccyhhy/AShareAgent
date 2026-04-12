from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Any

from langchain_core.messages import HumanMessage

from src.agents.state import (
    AgentState,
    _ensure_agent_outputs,
    maybe_return_ablation_stub,
    show_agent_reasoning,
    show_workflow_status,
)
from src.tools.news_crawler import get_news_sentiment, get_stock_news
from src.utils.api_utils import agent_endpoint
from src.utils.logging_config import setup_logger

logger = setup_logger("sentiment_agent")

SENTIMENT_ANALYSIS_DOMAIN = "market_sentiment"
SENTIMENT_ANALYSIS_METRIC = "news_sentiment_score_7d"
NEWS_LOOKBACK_DAYS = 7




def _with_sentiment_semantics(payload: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(payload)
    enriched.setdefault("analysis_domain", SENTIMENT_ANALYSIS_DOMAIN)
    enriched.setdefault("analysis_metric", SENTIMENT_ANALYSIS_METRIC)
    return enriched


def _resolve_reference_datetime(end_date: Any) -> datetime:
    text = str(end_date or "").strip()
    if text:
        candidate = text[:19]
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(candidate, fmt)
                if fmt == "%Y-%m-%d":
                    return parsed.replace(hour=23, minute=59, second=59)
                return parsed
            except ValueError:
                continue
    return datetime.now()


def _is_backtest_mode() -> bool:
    value = os.getenv("ASHAREAGENT_BACKTEST_MODE")
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


@agent_endpoint(
    "sentiment",
    "Market sentiment analyst (rule engine), evaluates recent news sentiment.",
)
def sentiment_agent(state: AgentState):
    """Analyze market sentiment from recent news and expose standardized outputs."""
    show_workflow_status("Sentiment Analyst")
    show_reasoning = state["metadata"]["show_reasoning"]
    data = state["data"]
    symbol = data["ticker"]
    logger.info("Analyzing sentiment for ticker: %s", symbol)

    num_of_news = data.get("num_of_news", 20)

    ablation_result = maybe_return_ablation_stub(
        state,
        agent_key="sentiment",
        agent_type="rule_engine",
        message_name="sentiment_agent",
        output_key="sentiment",
        data_key="sentiment_analysis",
        payload_overrides={
            "analysis_domain": SENTIMENT_ANALYSIS_DOMAIN,
            "analysis_metric": SENTIMENT_ANALYSIS_METRIC,
            "sentiment_score": 0.0,
            "news_count": 0,
            "news_window_days": NEWS_LOOKBACK_DAYS,
        },
    )
    if ablation_result is not None:
        return ablation_result

    if _is_backtest_mode():
        message_content = _with_sentiment_semantics(
            {
                "agent_type": "rule_engine",
                "signal": "neutral",
                "confidence": "50%",
                "reasoning": (
                    "当前为回测模式，已跳过远程新闻抓取与情绪模型调用。"
                ),
                "sentiment_score": 0.0,
                "news_count": 0,
                "news_window_days": NEWS_LOOKBACK_DAYS,
            }
        )

        if show_reasoning:
            show_agent_reasoning(message_content, "Market Sentiment Analysis Agent")

        updated_data = dict(data)
        agent_outputs = _ensure_agent_outputs(updated_data)
        agent_outputs["sentiment"] = message_content
        state["metadata"]["agent_reasoning"] = message_content

        message = HumanMessage(
            content=json.dumps(message_content, ensure_ascii=False),
            name="sentiment_agent",
        )

        show_workflow_status("Sentiment Analyst", "completed")
        return {
            "messages": [message],
            "data": {
                **updated_data,
                "sentiment_analysis": message_content,
            },
            "metadata": state["metadata"],
        }

    end_date = data.get("end_date")
    news_list = get_stock_news(symbol, max_news=num_of_news, date=end_date) or []

    reference_datetime = _resolve_reference_datetime(end_date)
    cutoff_date = reference_datetime - timedelta(days=NEWS_LOOKBACK_DAYS)
    recent_news: list[dict[str, Any]] = []
    for news in news_list:
        if "publish_time" not in news:
            recent_news.append(news)
            continue
        try:
            news_date = datetime.strptime(news["publish_time"], "%Y-%m-%d %H:%M:%S")
            if news_date > cutoff_date:
                recent_news.append(news)
        except ValueError:
            recent_news.append(news)

    sentiment_score = get_news_sentiment(recent_news, num_of_news=num_of_news)

    if sentiment_score >= 0.5:
        signal = "bullish"
        confidence = f"{round(abs(sentiment_score) * 100)}%"
    elif sentiment_score <= -0.5:
        signal = "bearish"
        confidence = f"{round(abs(sentiment_score) * 100)}%"
    else:
        signal = "neutral"
        confidence = f"{round((1 - abs(sentiment_score)) * 100)}%"

    message_content = {
        "agent_type": "rule_engine",
        "signal": signal,
        "confidence": confidence,
        "reasoning": (
            f"基于近 {len(recent_news)} 条新闻计算市场情绪，"
            f"情绪得分={sentiment_score:.2f}。"
        ),
        "sentiment_score": round(sentiment_score, 4),
        "news_count": len(recent_news),
        "news_window_days": NEWS_LOOKBACK_DAYS,
    }
    message_content = _with_sentiment_semantics(message_content)

    if show_reasoning:
        show_agent_reasoning(message_content, "Market Sentiment Analysis Agent")

    updated_data = dict(data)
    agent_outputs = _ensure_agent_outputs(updated_data)
    agent_outputs["sentiment"] = message_content
    state["metadata"]["agent_reasoning"] = message_content

    message = HumanMessage(
        content=json.dumps(message_content, ensure_ascii=False),
        name="sentiment_agent",
    )

    show_workflow_status("Sentiment Analyst", "completed")
    return {
        "messages": [message],
        "data": {
            **updated_data,
            "sentiment_analysis": message_content,
        },
        "metadata": state["metadata"],
    }

