from __future__ import annotations

import json

from src.utils import structured_terminal as terminal_module


class _Message:
    def __init__(self, *, name: str, content: str):
        self.name = name
        self.content = content


def test_extract_agent_data_matches_canonical_researcher_message_name():
    payload = {
        "perspective": "bullish",
        "confidence": 0.72,
        "thesis_points": ["cash flow improving"],
        "reasoning": "Bull thesis",
    }
    state = {
        "messages": [
            _Message(name="researcher_bull", content=json.dumps(payload, ensure_ascii=False))
        ],
        "metadata": {},
    }

    result = terminal_module.extract_agent_data(state, "researcher_bull")

    assert result == payload


def test_structured_terminal_formats_canonical_researcher_section():
    output = terminal_module.StructuredTerminalOutput()

    lines = output._format_agent_section(
        "researcher_bull",
        {
            "perspective": "bullish",
            "confidence": 0.72,
            "thesis_points": ["cash flow improving"],
            "reasoning": "Bull thesis",
        },
    )

    assert lines[0] == "[BU] researcher_bull"
    assert "- perspective: bullish" in lines
    assert "- thesis: cash flow improving" in lines
    assert "- reasoning: Bull thesis" in lines


def test_process_final_state_collects_canonical_researcher_data():
    state = {
        "messages": [
            _Message(
                name="researcher_bull",
                content=json.dumps(
                    {
                        "perspective": "bullish",
                        "confidence": 0.72,
                        "thesis_points": ["cash flow improving"],
                    },
                    ensure_ascii=False,
                ),
            )
        ],
        "metadata": {},
        "data": {"ticker": "600519"},
    }

    terminal = terminal_module.StructuredTerminalOutput()
    original_terminal = terminal_module.terminal
    terminal_module.terminal = terminal
    try:
        terminal_module.process_final_state(state)
    finally:
        terminal_module.terminal = original_terminal

    assert "researcher_bull" in terminal.data
    assert terminal.data["researcher_bull"]["perspective"] == "bullish"
