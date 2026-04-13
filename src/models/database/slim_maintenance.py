from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from src.agents.state import canonicalize_agent_key

MAX_REASONING_LENGTH = 1000
MAX_PREVIEW_LENGTH = 280


def _truncate_preview(value: Any, limit: int = MAX_PREVIEW_LENGTH) -> str | None:
    if value is None:
        return None
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text[:limit]


def _summarize_llm_interaction(request_payload: Any, response_payload: Any) -> dict[str, Any]:
    request_preview = _truncate_preview(request_payload)
    response_preview = _truncate_preview(response_payload)
    return {
        "request_chars": len(request_preview or "") if request_payload is not None else 0,
        "response_chars": len(response_preview or "") if response_payload is not None else 0,
        "request_preview": request_preview,
        "response_preview": response_preview,
    }


def _extract_agent_output_from_state(output_state: Any, agent_name: str) -> dict[str, Any] | None:
    if not isinstance(output_state, dict):
        return None
    data_section = output_state.get("data", {})
    if not isinstance(data_section, dict):
        return None
    agent_outputs = data_section.get("agent_outputs", {})
    if not isinstance(agent_outputs, dict):
        return None

    canonical_name = canonicalize_agent_key(agent_name)
    candidate_keys = [
        canonical_name,
        canonical_name.replace("_agent", ""),
        agent_name,
        agent_name.replace("_agent", ""),
    ]
    for key in candidate_keys:
        candidate = agent_outputs.get(key)
        if isinstance(candidate, dict):
            return candidate
    return None


def _extract_reasoning_summary(reasoning_data: Any) -> str | None:
    if reasoning_data is None:
        return None
    if isinstance(reasoning_data, str):
        return reasoning_data[:MAX_REASONING_LENGTH]
    if isinstance(reasoning_data, dict):
        if isinstance(reasoning_data.get("reasoning"), str):
            return reasoning_data["reasoning"][:MAX_REASONING_LENGTH]
        return json.dumps(reasoning_data, ensure_ascii=False, default=str)[:MAX_REASONING_LENGTH]
    return str(reasoning_data)[:MAX_REASONING_LENGTH]


def compact_agent_decision_payload(*, row: dict[str, Any], decision_data: Any) -> dict[str, Any]:
    payload = decision_data if isinstance(decision_data, dict) else {}
    output_state = payload.get("output_state")
    if output_state is None:
        output_state = payload.get("agent_output")
    return {
        "run_id": row.get("run_id"),
        "agent_name": row.get("agent_name"),
        "ticker": row.get("ticker"),
        "timestamp": payload.get("timestamp") or row.get("created_at"),
        "agent_output": _extract_agent_output_from_state(output_state, str(row.get("agent_name") or "")),
        "reasoning": _extract_reasoning_summary(row.get("reasoning") or payload.get("reasoning")),
        "llm_interaction": _summarize_llm_interaction(
            payload.get("llm_request"),
            payload.get("llm_response"),
        ),
    }


def compact_analysis_result_payload(*, row: dict[str, Any], result_data: Any) -> dict[str, Any]:
    payload = result_data if isinstance(result_data, dict) else {}
    llm_interaction = payload.get("llm_interaction")
    if not isinstance(llm_interaction, dict):
        llm_interaction = {}
    output_state = payload.get("output_state") or payload.get("agent_output")
    reasoning = payload.get("reasoning")
    return {
        "run_id": row.get("run_id"),
        "agent_name": row.get("agent_name"),
        "ticker": row.get("ticker"),
        "timestamp": payload.get("timestamp") or row.get("created_at"),
        "reasoning": reasoning,
        "reasoning_summary": _extract_reasoning_summary(reasoning),
        "agent_output": _extract_agent_output_from_state(output_state, str(row.get("agent_name") or "")),
        "llm_interaction": _summarize_llm_interaction(
            llm_interaction.get("request"),
            llm_interaction.get("response"),
        ),
    }


def _parse_json_maybe(raw_value: Any) -> Any:
    if not isinstance(raw_value, str):
        return raw_value
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return raw_value


def backup_database(source_db: str | Path, backup_path: str | Path | None = None) -> Path:
    source = Path(source_db)
    if backup_path is None:
        backup_dir = source.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{source.stem}.{stamp}.bak{source.suffix}"
    destination = Path(backup_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def _list_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    return [row[0] for row in rows]


def _copy_table_schema(source_conn: sqlite3.Connection, target_conn: sqlite3.Connection, table_name: str) -> None:
    row = source_conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    if row and row[0]:
        target_conn.execute(row[0])


def _copy_indexes(source_conn: sqlite3.Connection, target_conn: sqlite3.Connection, table_name: str) -> None:
    rows = source_conn.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'index' AND tbl_name = ? AND sql IS NOT NULL
        """,
        (table_name,),
    ).fetchall()
    for row in rows:
        target_conn.execute(row[0])


def _copy_table_rows(source_conn: sqlite3.Connection, target_conn: sqlite3.Connection, table_name: str) -> tuple[int, int, int]:
    cursor = source_conn.execute(f"SELECT * FROM {table_name}")
    columns = [description[0] for description in cursor.description]
    placeholders = ", ".join(["?"] * len(columns))
    insert_sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"

    copied = 0
    decisions_compacted = 0
    analyses_compacted = 0

    for raw_row in cursor.fetchall():
        row = dict(zip(columns, raw_row))
        values = [row[column] for column in columns]

        if table_name == "agent_decisions" and "decision_data" in columns:
            index = columns.index("decision_data")
            compacted = compact_agent_decision_payload(
                row=row,
                decision_data=_parse_json_maybe(row["decision_data"]),
            )
            values[index] = json.dumps(compacted, ensure_ascii=False)
            decisions_compacted += 1
        elif table_name == "analysis_results" and "result_data" in columns:
            index = columns.index("result_data")
            compacted = compact_analysis_result_payload(
                row=row,
                result_data=_parse_json_maybe(row["result_data"]),
            )
            values[index] = json.dumps(compacted, ensure_ascii=False)
            analyses_compacted += 1

        target_conn.execute(insert_sql, values)
        copied += 1

    return copied, decisions_compacted, analyses_compacted


def rebuild_database_with_compaction(*, source_db: str | Path, target_db: str | Path) -> dict[str, Any]:
    source = Path(source_db)
    target = Path(target_db)
    if source.resolve() == target.resolve():
        raise ValueError("target_db must be different from source_db")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()

    summary = {
        "source_db": str(source),
        "target_db": str(target),
        "tables_copied": 0,
        "rows_copied": 0,
        "agent_decisions_compacted": 0,
        "analysis_results_compacted": 0,
        "source_size_bytes": source.stat().st_size if source.exists() else 0,
        "target_size_bytes": 0,
    }

    with sqlite3.connect(source) as source_conn, sqlite3.connect(target) as target_conn:
        source_conn.row_factory = sqlite3.Row
        source_conn.execute("PRAGMA foreign_keys=OFF")
        target_conn.execute("PRAGMA foreign_keys=OFF")

        for table_name in _list_tables(source_conn):
            _copy_table_schema(source_conn, target_conn, table_name)
            copied, decisions_compacted, analyses_compacted = _copy_table_rows(
                source_conn,
                target_conn,
                table_name,
            )
            _copy_indexes(source_conn, target_conn, table_name)
            summary["tables_copied"] += 1
            summary["rows_copied"] += copied
            summary["agent_decisions_compacted"] += decisions_compacted
            summary["analysis_results_compacted"] += analyses_compacted

        target_conn.commit()
        target_conn.execute("VACUUM")

    summary["target_size_bytes"] = target.stat().st_size if target.exists() else 0
    return summary
