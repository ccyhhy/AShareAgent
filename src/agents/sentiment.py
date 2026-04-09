from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from langchain_core.messages import HumanMessage

from src.agents.state import AgentState, show_agent_reasoning, show_workflow_status
from src.tools.news_crawler import get_news_sentiment, get_stock_news
from src.utils.api_utils import agent_endpoint
from src.utils.logging_config import setup_logger

logger = setup_logger("sentiment_agent")

SENTIMENT_ANALYSIS_DOMAIN = "market_sentiment"
SENTIMENT_ANALYSIS_METRIC = "news_sentiment_score_7d"
NEWS_LOOKBACK_DAYS = 7


def _ensure_agent_outputs(data: dict[str, Any]) -> dict[str, Any]:
    agent_outputs = data.get("agent_outputs")
    if not isinstance(agent_outputs, dict):
        agent_outputs = {}
    data["agent_outputs"] = agent_outputs
    return agent_outputs


def _with_sentiment_semantics(payload: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(payload)
    enriched.setdefault("analysis_domain", SENTIMENT_ANALYSIS_DOMAIN)
    enriched.setdefault("analysis_metric", SENTIMENT_ANALYSIS_METRIC)
    return enriched


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
    end_date = data.get("end_date")
    news_list = get_stock_news(symbol, max_news=num_of_news, date=end_date) or []

    cutoff_date = datetime.now() - timedelta(days=NEWS_LOOKBACK_DAYS)
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
            f"Market sentiment from {len(recent_news)} recent news articles; "
            f"sentiment_score={sentiment_score:.2f}."
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
