from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.database.slim_maintenance import (
    compact_analysis_result_payload,
    compact_agent_decision_payload,
    rebuild_database_with_compaction,
)


def test_compact_agent_decision_payload_drops_full_state_snapshots():
    raw_payload = {
        "agent_output": {
            "data": {
                "agent_outputs": {
                    "risk_management": {
                        "signal": "neutral",
                        "confidence": "60%",
                    }
                }
            }
        },
        "timestamp": "2026-04-11T10:30:00",
        "input_state": {"raw": "x" * 5000},
        "llm_request": {"messages": [{"content": "q" * 5000}]},
        "llm_response": {"content": "a" * 5000},
    }

    compacted = compact_agent_decision_payload(
        row={
            "run_id": "run-1",
            "agent_name": "risk_management_agent",
            "ticker": "000001",
            "reasoning": "r" * 4000,
        },
        decision_data=raw_payload,
    )

    assert compacted["run_id"] == "run-1"
    assert compacted["agent_output"] == {"signal": "neutral", "confidence": "60%"}
    assert "input_state" not in compacted
    assert "output_state" not in compacted
    assert len(compacted["llm_interaction"]["request_preview"]) <= 280
    assert len(compacted["reasoning"]) <= 1000


def test_rebuild_database_with_compaction_preserves_rows_and_compacts_json(tmp_path: Path):
    source_db = tmp_path / "source.db"
    target_db = tmp_path / "target.db"

    schema_sql = (Path(__file__).resolve().parents[2] / "src" / "models" / "schema.sql").read_text(
        encoding="utf-8"
    )

    with sqlite3.connect(source_db) as conn:
        conn.executescript(schema_sql)
        conn.execute(
            """
            INSERT INTO stock_news (ticker, date, method, query, title, content, publish_time, source, url, keyword)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "000001",
                "2026-04-11",
                "test",
                "query",
                "headline",
                "body",
                "2026-04-11 10:00:00",
                "source",
                "https://example.com",
                "k",
            ),
        )
        conn.execute(
            """
            INSERT INTO agent_decisions (run_id, agent_name, ticker, decision_type, decision_data, confidence_score, reasoning)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "run-1",
                "risk_management_agent",
                "000001",
                "analysis",
                json.dumps(
                    {
                        "agent_output": {
                            "data": {
                                "agent_outputs": {
                                    "risk_management": {
                                        "signal": "neutral",
                                        "confidence": "60%",
                                    }
                                }
                            }
                        },
                        "timestamp": "2026-04-11T10:30:00",
                        "input_state": {"raw": "x" * 5000},
                        "llm_request": {"messages": [{"content": "q" * 5000}]},
                        "llm_response": {"content": "a" * 5000},
                    },
                    ensure_ascii=False,
                ),
                0.6,
                "r" * 5000,
            ),
        )
        conn.execute(
            """
            INSERT INTO analysis_results (run_id, agent_name, ticker, analysis_date, analysis_type, result_data, confidence_score, execution_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "run-1",
                "risk_management_agent",
                "000001",
                "2026-04-11",
                "risk management",
                json.dumps(
                    {
                        "reasoning": {"confidence": "60%", "reasoning": "r" * 5000},
                        "timestamp": "2026-04-11T10:30:00",
                        "output_state": {
                            "data": {
                                "agent_outputs": {
                                    "risk_management": {
                                        "signal": "neutral",
                                        "confidence": "60%",
                                    }
                                }
                            }
                        },
                        "llm_interaction": {
                            "request": {"messages": [{"content": "q" * 5000}]},
                            "response": {"content": "a" * 5000},
                        },
                    },
                    ensure_ascii=False,
                ),
                0.6,
                None,
            ),
        )
        conn.commit()

    summary = rebuild_database_with_compaction(source_db=source_db, target_db=target_db)

    assert summary["tables_copied"] >= 3
    assert summary["agent_decisions_compacted"] == 1
    assert summary["analysis_results_compacted"] == 1

    with sqlite3.connect(target_db) as conn:
        stock_news_count = conn.execute("SELECT COUNT(*) FROM stock_news").fetchone()[0]
        assert stock_news_count == 1

        decision_json = conn.execute(
            "SELECT decision_data FROM agent_decisions WHERE run_id = 'run-1'"
        ).fetchone()[0]
        decision_payload = json.loads(decision_json)
        assert "input_state" not in decision_payload
        assert decision_payload["agent_output"] == {"signal": "neutral", "confidence": "60%"}

        result_json = conn.execute(
            "SELECT result_data FROM analysis_results WHERE run_id = 'run-1'"
        ).fetchone()[0]
        result_payload = json.loads(result_json)
        assert "output_state" not in result_payload
        assert result_payload["agent_output"] == {"signal": "neutral", "confidence": "60%"}


def test_compact_analysis_result_payload_keeps_reasoning_summary():
    raw_payload = {
        "reasoning": {"confidence": "60%", "reasoning": "r" * 5000},
        "timestamp": "2026-04-11T10:30:00",
        "output_state": {
            "data": {
                "agent_outputs": {
                    "risk_management": {
                        "signal": "neutral",
                        "confidence": "60%",
                    }
                }
            }
        },
        "llm_interaction": {
            "request": {"messages": [{"content": "q" * 5000}]},
            "response": {"content": "a" * 5000},
        },
    }

    compacted = compact_analysis_result_payload(
        row={
            "run_id": "run-1",
            "agent_name": "risk_management_agent",
            "ticker": "000001",
        },
        result_data=raw_payload,
    )

    assert compacted["run_id"] == "run-1"
    assert compacted["agent_output"] == {"signal": "neutral", "confidence": "60%"}
    assert len(compacted["reasoning_summary"]) <= 1000
    assert "output_state" not in compacted
