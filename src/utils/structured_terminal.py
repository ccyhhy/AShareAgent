"""Structured terminal output utilities.

This module formats final workflow state into readable terminal text.
It is intentionally independent from backend API rendering.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from src.utils.logging_config import setup_logger

logger = setup_logger("structured_terminal")

AGENT_MAP = {
    "market_data_agent": {"icon": "MD", "name": "market_data"},
    "technical_analyst_agent": {"icon": "RV", "name": "relative_valuation"},
    "fundamentals_agent": {"icon": "FA", "name": "fundamentals"},
    "sentiment_agent": {"icon": "SM", "name": "market_sentiment"},
    "valuation_agent": {"icon": "VA", "name": "valuation"},
    "researcher_bull_agent": {"icon": "BU", "name": "researcher_bull"},
    "researcher_bear_agent": {"icon": "BE", "name": "researcher_bear"},
    "debate_room_agent": {"icon": "DB", "name": "debate_room"},
    "risk_management_agent": {"icon": "RK", "name": "risk_management"},
    "macro_analyst_agent": {"icon": "MA", "name": "macro_analyst"},
    "macro_news_agent": {"icon": "MN", "name": "macro_news"},
    "portfolio_management_agent": {"icon": "PM", "name": "portfolio_management"},
}

AGENT_ORDER = [
    "market_data_agent",
    "technical_analyst_agent",
    "fundamentals_agent",
    "sentiment_agent",
    "valuation_agent",
    "researcher_bull_agent",
    "researcher_bear_agent",
    "debate_room_agent",
    "risk_management_agent",
    "macro_analyst_agent",
    "macro_news_agent",
    "portfolio_management_agent",
]


class StructuredTerminalOutput:
    """In-memory collector and formatter for agent outputs."""

    def __init__(self):
        self.data: Dict[str, Any] = {}
        self.metadata: Dict[str, Any] = {}

    def set_metadata(self, key: str, value: Any) -> None:
        self.metadata[key] = value

    def add_agent_data(self, agent_name: str, data: Any) -> None:
        self.data[agent_name] = data

    def _format_value(self, value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, float):
            if -1 <= value <= 1:
                return f"{value:.2%}"
            return f"{value:.4f}"
        if value is None:
            return "N/A"
        return str(value)

    def _format_dict_as_tree(self, data: Dict[str, Any], indent: int = 0) -> List[str]:
        result: List[str] = []
        for key, value in data.items():
            prefix = "  " * indent + "- "
            if isinstance(value, dict):
                result.append(f"{prefix}{key}:")
                result.extend(self._format_dict_as_tree(value, indent + 1))
            elif isinstance(value, list):
                result.append(f"{prefix}{key}:")
                for item in value:
                    if isinstance(item, dict):
                        result.extend(self._format_dict_as_tree(item, indent + 1))
                    else:
                        result.append(f"{'  ' * (indent + 1)}- {self._format_value(item)}")
            else:
                result.append(f"{prefix}{key}: {self._format_value(value)}")
        return result

    def _format_agent_section(self, agent_name: str, data: Any) -> List[str]:
        info = AGENT_MAP.get(agent_name, {"icon": "AG", "name": agent_name})
        lines = [f"[{info['icon']}] {info['name']}"]

        if isinstance(data, dict):
            if agent_name == "technical_analyst_agent":
                if "signal" in data:
                    lines.append(f"- signal: {data.get('signal')}")
                if "confidence" in data:
                    lines.append(f"- confidence: {data.get('confidence')}")
                if any(k in data for k in ["pb_percentile_5y", "pb_current", "valuation_score", "sample_size"]):
                    lines.append("- pb_percentile_details:")
                    lines.append(f"  - pb_percentile_5y: {self._format_value(data.get('pb_percentile_5y'))}")
                    lines.append(f"  - pb_current: {self._format_value(data.get('pb_current'))}")
                    lines.append(f"  - valuation_score: {self._format_value(data.get('valuation_score'))}")
                    lines.append(f"  - sample_size: {self._format_value(data.get('sample_size'))}")
                if "strategy_signals" in data:
                    lines.append("- legacy_strategy_signals:")
                    lines.extend([f"  {line}" for line in self._format_dict_as_tree(data.get("strategy_signals", {}))])
            elif agent_name in {"researcher_bull_agent", "researcher_bear_agent"}:
                lines.append(f"- perspective: {data.get('perspective', 'N/A')}")
                lines.append(f"- confidence: {self._format_value(data.get('confidence'))}")
                for point in data.get("thesis_points", []):
                    lines.append(f"- thesis: {point}")
                if data.get("reasoning"):
                    lines.append(f"- reasoning: {data.get('reasoning')}")
            else:
                lines.extend(self._format_dict_as_tree(data))
        elif isinstance(data, list):
            for item in data:
                lines.append(f"- {self._format_value(item)}")
        else:
            lines.append(f"- {self._format_value(data)}")

        lines.append("-" * 80)
        return lines

    def generate_output(self) -> str:
        width = 80
        ticker = self.metadata.get("ticker", "unknown")
        lines = ["=" * width, f"Investment Analysis Report - {ticker}", "=" * width]

        if "start_date" in self.metadata and "end_date" in self.metadata:
            lines.append(f"period: {self.metadata['start_date']} -> {self.metadata['end_date']}")
            lines.append("")

        for agent_name in AGENT_ORDER:
            if agent_name in self.data:
                lines.extend(self._format_agent_section(agent_name, self.data[agent_name]))
                lines.append("")

        return "\n".join(lines)

    def print_output(self) -> None:
        logger.info("\n%s", self.generate_output())


terminal = StructuredTerminalOutput()


def extract_agent_data(state: Dict[str, Any], agent_name: str) -> Any:
    """Extract agent-specific data from final workflow state."""
    if agent_name == "portfolio_management_agent":
        messages = state.get("messages", [])
        if messages and hasattr(messages[-1], "content"):
            content = messages[-1].content
            if isinstance(content, str):
                try:
                    if content.strip().startswith("{") and content.strip().endswith("}"):
                        return json.loads(content)
                except json.JSONDecodeError:
                    return {"message": content}
            return {"message": content}

    metadata = state.get("metadata", {})
    all_reasoning = metadata.get("all_agent_reasoning", {})
    for name, data in all_reasoning.items():
        if agent_name in name:
            return data

    if agent_name == metadata.get("current_agent_name") and "agent_reasoning" in metadata:
        return metadata["agent_reasoning"]

    for message in state.get("messages", []):
        if hasattr(message, "name") and message.name and agent_name in message.name:
            content = getattr(message, "content", None)
            if isinstance(content, str):
                try:
                    if content.startswith("{") or content.startswith("["):
                        return json.loads(content)
                except json.JSONDecodeError:
                    return content
            return content

    return None


def process_final_state(state: Dict[str, Any]) -> None:
    """Extract all relevant data for formatted terminal rendering."""
    data = state.get("data", {})
    terminal.set_metadata("ticker", data.get("ticker", "unknown"))
    if "start_date" in data and "end_date" in data:
        terminal.set_metadata("start_date", data["start_date"])
        terminal.set_metadata("end_date", data["end_date"])

    for agent_name in AGENT_ORDER:
        agent_data = extract_agent_data(state, agent_name)
        if agent_data is not None:
            terminal.add_agent_data(agent_name, agent_data)


def print_structured_output(state: Dict[str, Any]) -> None:
    """Public helper for printing final state in a structured format."""
    try:
        process_final_state(state)
        terminal.print_output()
    except Exception as exc:
        logger.error("Error generating structured output: %s", exc)
        import traceback

        logger.error(traceback.format_exc())
