"""Decision report formatting helpers.

This module keeps a stable public surface while formatting agent outputs into
readable multi-section text reports.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List


def _confidence_percent(value: Any) -> str:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.endswith("%"):
            return stripped
        try:
            value = float(stripped)
        except ValueError:
            return stripped or "N/A"

    if isinstance(value, (int, float)):
        if value <= 1:
            return f"{value * 100:.0f}%"
        return f"{value:.0f}%"

    return "N/A"


def get_signal_icon(signal: str) -> str:
    signal_lower = (signal or "").lower()
    if signal_lower in {"bullish", "buy", "positive"}:
        return "UP"
    if signal_lower in {"bearish", "sell", "negative"}:
        return "DOWN"
    if signal_lower in {"neutral", "hold"}:
        return "NEUTRAL"
    return "INFO"


def format_decision_display(decisions: List[Dict], ticker: str = None) -> str:
    if not decisions:
        return "No decision records."

    if not ticker:
        ticker = decisions[0].get("ticker", "000001")

    report_lines: List[str] = []
    title_line = "=" * 80
    report_lines.append(title_line)
    report_lines.append(f"Investment Analysis Report - {ticker}".center(80))
    report_lines.append(title_line)

    today = datetime.now().strftime("%Y-%m-%d")
    last_year = str(int(today[:4]) - 1) + today[4:]
    report_lines.append(f"Period: {last_year} -> {today}".center(80))
    report_lines.append("")

    for decision in decisions:
        decision_data = decision.get("decision_data", {})
        agent_name = (decision.get("agent_name", "") or "").lower()

        if isinstance(decision_data, str):
            try:
                decision_data = json.loads(decision_data)
            except Exception:
                decision_data = {}

        section = ""
        if "technical" in agent_name:
            section = format_technical_analysis(decision_data)
        elif "fundamental" in agent_name:
            section = format_fundamental_analysis(decision_data)
        elif "sentiment" in agent_name:
            section = format_sentiment_analysis(decision_data)
        elif "valuation" in agent_name:
            section = format_valuation_analysis(decision_data)
        elif "risk" in agent_name:
            section = format_risk_analysis(decision_data)
        elif "macro" in agent_name:
            section = format_macro_analysis(decision_data)
        elif "portfolio" in agent_name:
            section = format_portfolio_analysis(decision_data)
        elif "bull" in agent_name:
            section = format_bullish_analysis(decision_data)
        elif "bear" in agent_name:
            section = format_bearish_analysis(decision_data)
        elif "debate" in agent_name:
            section = format_debate_analysis(decision_data)

        if section:
            report_lines.append(section)

    if len(report_lines) <= 4:
        report_lines.extend(generate_sample_report())

    report_lines.append(title_line)
    return "\n".join(report_lines)


def format_technical_analysis(data: Dict[str, Any]) -> str:
    signal = data.get("signal", "neutral")
    confidence = _confidence_percent(data.get("confidence", 0))

    lines = []
    lines.append("[Relative Valuation (PB Percentile)]")
    lines.append(f"Signal: {get_signal_icon(signal)} {signal}")
    lines.append(f"Confidence: {confidence}")

    if any(k in data for k in ("pb_percentile_5y", "pb_current", "valuation_score", "sample_size")):
        lines.append("PB percentile details:")
        lines.append(f"- pb_percentile_5y: {data.get('pb_percentile_5y', 'N/A')}")
        lines.append(f"- pb_current: {data.get('pb_current', 'N/A')}")
        lines.append(f"- valuation_score: {data.get('valuation_score', 'N/A')}")
        lines.append(f"- sample_size: {data.get('sample_size', 'N/A')}")

    strategy_signals = data.get("strategy_signals", {})
    if strategy_signals:
        lines.append("Legacy strategy_signals:")
        for strategy, details in strategy_signals.items():
            lines.append(
                f"- {strategy}: {details.get('signal', 'neutral')} ({_confidence_percent(details.get('confidence', 50))})"
            )

    lines.append("-" * 80)
    lines.append("")
    return "\n".join(lines)


def format_fundamental_analysis(data: Dict[str, Any]) -> str:
    signal = data.get("signal", "neutral")
    confidence = _confidence_percent(data.get("confidence", 0))

    lines = [
        "[Fundamental Analysis]",
        f"Signal: {get_signal_icon(signal)} {signal}",
        f"Confidence: {confidence}",
    ]

    reasoning = data.get("reasoning")
    if isinstance(reasoning, dict):
        lines.append("Reasoning:")
        for item, details in reasoning.items():
            lines.append(f"- {item}: {details}")
    elif reasoning:
        lines.append(f"Reasoning: {reasoning}")

    lines.append("-" * 80)
    lines.append("")
    return "\n".join(lines)


def format_sentiment_analysis(data: Dict[str, Any]) -> str:
    signal = data.get("signal", "neutral")
    confidence = _confidence_percent(data.get("confidence", 0))
    reasoning = data.get("reasoning", "N/A")

    lines = [
        "[Market Sentiment Analysis]",
        f"Signal: {get_signal_icon(signal)} {signal}",
        f"Confidence: {confidence}",
        f"Reasoning: {reasoning}",
    ]

    if "sentiment_score" in data:
        lines.append(f"Sentiment score: {data.get('sentiment_score')}")
    if "news_count" in data:
        lines.append(f"News count: {data.get('news_count')}")

    lines.append("-" * 80)
    lines.append("")
    return "\n".join(lines)


def format_valuation_analysis(data: Dict[str, Any]) -> str:
    signal = data.get("signal", "neutral")
    confidence = _confidence_percent(data.get("confidence", 0))

    lines = [
        "[Valuation Analysis]",
        f"Signal: {get_signal_icon(signal)} {signal}",
        f"Confidence: {confidence}",
    ]

    for key in ["intrinsic_value", "market_cap", "margin_of_safety", "margin_of_safety_assessment"]:
        if key in data:
            lines.append(f"- {key}: {data.get(key)}")

    if data.get("reasoning"):
        lines.append(f"Reasoning: {data.get('reasoning')}")

    lines.append("-" * 80)
    lines.append("")
    return "\n".join(lines)


def format_risk_analysis(data: Dict[str, Any]) -> str:
    lines = [
        "[Risk Analysis]",
        f"trading_action: {data.get('trading_action', 'hold')}",
        f"risk_score: {data.get('risk_score', 'N/A')}",
        f"max_position_size: {data.get('max_position_size', 'N/A')}",
    ]

    if data.get("risk_metrics"):
        lines.append("risk_metrics:")
        for key, value in data["risk_metrics"].items():
            lines.append(f"- {key}: {value}")

    if data.get("reasoning"):
        lines.append(f"Reasoning: {data.get('reasoning')}")

    lines.append("-" * 80)
    lines.append("")
    return "\n".join(lines)


def format_macro_analysis(data: Dict[str, Any]) -> str:
    lines = [
        "[Macro Analysis]",
        f"macro_environment: {data.get('macro_environment', 'N/A')}",
        f"impact_on_stock: {data.get('impact_on_stock', 'N/A')}",
    ]

    key_factors = data.get("key_factors", [])
    if key_factors:
        lines.append("key_factors:")
        for factor in key_factors:
            lines.append(f"- {factor}")

    if data.get("reasoning"):
        lines.append(f"Reasoning: {str(data.get('reasoning'))[:300]}")

    lines.append("-" * 80)
    lines.append("")
    return "\n".join(lines)


def format_portfolio_analysis(data: Dict[str, Any]) -> str:
    confidence = _confidence_percent(data.get("confidence", 0))
    lines = [
        "[Portfolio Analysis]",
        f"action: {data.get('action', 'hold')}",
        f"quantity: {data.get('quantity', 0)}",
        f"confidence: {confidence}",
    ]

    if isinstance(data.get("agent_signals"), list):
        lines.append("agent_signals:")
        for signal in data["agent_signals"]:
            lines.append(
                f"- {signal.get('agent_name', 'unknown')}: {signal.get('signal', 'neutral')} ({_confidence_percent(signal.get('confidence', 0))})"
            )

    if data.get("reasoning"):
        lines.append(f"Reasoning: {data.get('reasoning')}")

    lines.append("-" * 80)
    lines.append("")
    return "\n".join(lines)


def generate_sample_report() -> List[str]:
    return [
        "[Relative Valuation (PB Percentile)]",
        "Signal: NEUTRAL neutral",
        "Confidence: 0%",
        "PB percentile details:",
        "- pb_percentile_5y: N/A",
        "- pb_current: N/A",
        "- valuation_score: N/A",
        "- sample_size: N/A",
        "-" * 80,
        "",
    ]


def format_bullish_analysis(data: Dict[str, Any]) -> str:
    confidence = _confidence_percent(data.get("confidence", 0))
    lines = [
        "[Bull Research Analysis]",
        f"perspective: {data.get('perspective', 'bullish')}",
        f"confidence: {confidence}",
    ]
    for point in data.get("thesis_points", []):
        lines.append(f"+ {point}")
    if data.get("reasoning"):
        lines.append(f"Reasoning: {data.get('reasoning')}")
    lines.append("-" * 80)
    lines.append("")
    return "\n".join(lines)


def format_bearish_analysis(data: Dict[str, Any]) -> str:
    confidence = _confidence_percent(data.get("confidence", 0))
    lines = [
        "[Bear Research Analysis]",
        f"perspective: {data.get('perspective', 'bearish')}",
        f"confidence: {confidence}",
    ]
    for point in data.get("thesis_points", []):
        lines.append(f"- {point}")
    if data.get("reasoning"):
        lines.append(f"Reasoning: {data.get('reasoning')}")
    lines.append("-" * 80)
    lines.append("")
    return "\n".join(lines)


def format_debate_analysis(data: Dict[str, Any]) -> str:
    confidence = _confidence_percent(data.get("confidence", 0))
    lines = [
        "[Debate Analysis]",
        f"signal: {data.get('signal', 'neutral')}",
        f"confidence: {confidence}",
    ]
    for item in data.get("debate_summary", []):
        lines.append(f"- {item}")
    if data.get("reasoning"):
        lines.append(f"Reasoning: {data.get('reasoning')}")
    lines.append("-" * 80)
    lines.append("")
    return "\n".join(lines)
