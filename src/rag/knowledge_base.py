from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_KB_PATH = Path(__file__).resolve().parents[2] / "data" / "knowledge_base.db"


def _normalize_stock_code(stock_code: str | None) -> str:
    raw = str(stock_code or "").strip().upper()
    if not raw:
        return ""
    return raw.split(".")[0]


class KnowledgeBase:
    """SQLite-first knowledge base for agent memory retrieval."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_KB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS fundamentals_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT NOT NULL,
                    analysis_date TEXT NOT NULL,
                    signal TEXT,
                    confidence TEXT,
                    summary TEXT,
                    payload_json TEXT NOT NULL,
                    run_id TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_fundamentals_memory_stock_date
                ON fundamentals_memory(stock_code, analysis_date DESC)
                """
            )
            conn.commit()

    def save_fundamentals_memory(
        self,
        stock_code: str,
        analysis_payload: dict[str, Any],
        run_id: str | None = None,
        analysis_date: str | None = None,
        summary: str | None = None,
    ) -> bool:
        normalized_code = _normalize_stock_code(stock_code)
        if not normalized_code or not isinstance(analysis_payload, dict):
            return False

        payload_json = json.dumps(analysis_payload, ensure_ascii=False)
        date_value = analysis_date or datetime.now().strftime("%Y-%m-%d")
        created_at = datetime.now().isoformat()
        signal = str(analysis_payload.get("signal", ""))
        confidence = str(analysis_payload.get("confidence", ""))
        summary_text = summary or str(analysis_payload.get("reasoning", ""))[:240]

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO fundamentals_memory (
                    stock_code, analysis_date, signal, confidence, summary, payload_json, run_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_code,
                    date_value,
                    signal,
                    confidence,
                    summary_text,
                    payload_json,
                    run_id,
                    created_at,
                ),
            )
            conn.commit()
        return True

    def retrieve_fundamentals_refs(
        self,
        stock_code: str,
        limit: int = 3,
        as_of_date: str | None = None,
        include_payload: bool = True,
    ) -> list[dict[str, Any]]:
        normalized_code = _normalize_stock_code(stock_code)
        if not normalized_code:
            return []

        safe_limit = max(1, min(int(limit), 20))
        select_cols = (
            "id, stock_code, analysis_date, signal, confidence, summary, payload_json, run_id, created_at"
            if include_payload
            else "id, stock_code, analysis_date, signal, confidence, summary, run_id, created_at"
        )
        query = f"""
            SELECT {select_cols}
            FROM fundamentals_memory
            WHERE stock_code = ?
        """
        params: list[Any] = [normalized_code]

        if as_of_date:
            query += " AND analysis_date <= ?"
            params.append(as_of_date)

        query += " ORDER BY analysis_date DESC, id DESC LIMIT ?"
        params.append(safe_limit)

        refs: list[dict[str, Any]] = []
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            for row in rows:
                payload = {}
                if include_payload:
                    try:
                        payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
                    except json.JSONDecodeError:
                        payload = {}

                refs.append(
                    {
                        "id": row["id"],
                        "stock_code": row["stock_code"],
                        "analysis_date": row["analysis_date"],
                        "signal": row["signal"],
                        "confidence": row["confidence"],
                        "summary": row["summary"],
                        "run_id": row["run_id"],
                        "created_at": row["created_at"],
                        "payload": payload,
                    }
                )

        return refs
