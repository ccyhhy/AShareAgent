from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agents import fundamentals as fundamentals_module
from src.rag.knowledge_base import KnowledgeBase


def _make_state() -> dict:
    return {
        "messages": [],
        "data": {
            "ticker": "000001.SZ",
            "end_date": "2026-04-08",
            "financial_metrics": [
                {
                    "return_on_equity": 0.18,
                    "net_margin": 0.22,
                    "operating_margin": 0.19,
                    "revenue_growth": 0.12,
                    "earnings_growth": 0.11,
                    "book_value_growth": 0.13,
                    "current_ratio": 1.8,
                    "debt_to_equity": 0.4,
                    "free_cash_flow_per_share": 2.5,
                    "earnings_per_share": 2.0,
                    "pe_ratio": 18.0,
                    "price_to_book": 2.2,
                    "price_to_sales": 3.4,
                }
            ],
        },
        "metadata": {"show_reasoning": False},
    }


def test_knowledge_base_retrieve_honors_exact_stock_code_filter(tmp_path: Path):
    kb = KnowledgeBase(db_path=tmp_path / "knowledge_base.sqlite")

    assert kb.save_fundamentals_memory(
        stock_code="000001.SZ",
        analysis_payload={
            "signal": "bullish",
            "confidence": "80%",
            "reasoning": {"source": "same-code"},
        },
        analysis_date="2026-04-01",
    )
    assert kb.save_fundamentals_memory(
        stock_code="000001",
        analysis_payload={
            "signal": "neutral",
            "confidence": "55%",
            "reasoning": {"source": "same-code-normalized"},
        },
        analysis_date="2026-04-02",
    )
    assert kb.save_fundamentals_memory(
        stock_code="000002.SZ",
        analysis_payload={
            "signal": "bearish",
            "confidence": "40%",
            "reasoning": {"source": "different-code"},
        },
        analysis_date="2026-04-03",
    )

    refs = kb.retrieve_fundamentals_refs(stock_code="000001.SZ", limit=10)

    assert [ref["stock_code"] for ref in refs] == ["000001", "000001"]
    assert {ref["analysis_date"] for ref in refs} == {"2026-04-01", "2026-04-02"}
    assert all(ref["payload"]["reasoning"]["source"].startswith("same-code") for ref in refs)


def test_knowledge_base_retrieve_returns_empty_list_when_no_memory_exists(tmp_path: Path):
    kb = KnowledgeBase(db_path=tmp_path / "knowledge_base.sqlite")

    refs = kb.retrieve_fundamentals_refs(stock_code="000001.SZ", limit=5)

    assert refs == []


def test_fundamentals_agent_survives_knowledge_base_failures(monkeypatch):
    monkeypatch.setattr(fundamentals_module, "show_workflow_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(fundamentals_module, "show_agent_reasoning", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        fundamentals_module,
        "_get_knowledge_base",
        lambda: (_ for _ in ()).throw(RuntimeError("kb offline")),
    )

    result = fundamentals_module.fundamentals_agent(_make_state())

    assert result["messages"][0].name == "fundamentals_agent"

    message_content = json.loads(result["messages"][0].content)
    assert message_content["signal"] == result["data"]["fundamental_analysis"]["signal"]
    assert message_content["memory_scope"]["status"] == "unavailable"
    assert "kb offline" in message_content["memory_scope"]["error"]
    assert message_content["retrieved_refs"] == []

    assert "agent_outputs" in result["data"]
    assert result["data"]["agent_outputs"]["fundamentals"] == result["data"]["fundamental_analysis"]
    assert result["data"]["agent_outputs"]["fundamentals"]["memory_scope"]["status"] == "unavailable"
    assert result["metadata"]["agent_reasoning"] == result["data"]["agent_outputs"]["fundamentals"]


def test_fundamentals_agent_reports_longitudinal_memory_delta(monkeypatch):
    monkeypatch.setattr(fundamentals_module, "show_workflow_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(fundamentals_module, "show_agent_reasoning", lambda *args, **kwargs: None)

    class FakeKnowledgeBase:
        def retrieve_fundamentals_refs(
            self,
            stock_code: str,
            limit: int,
            as_of_date: str | None = None,
            include_payload: bool = True,
        ):
            return [
                {
                    "analysis_date": "2026-03-31",
                    "signal": "bearish",
                    "confidence": "25%",
                    "payload": {"signal": "bearish"},
                }
            ]

        def save_fundamentals_memory(self, **kwargs):
            return True

    monkeypatch.setattr(fundamentals_module, "_get_knowledge_base", lambda: FakeKnowledgeBase())

    result = fundamentals_module.fundamentals_agent(_make_state())
    output = result["data"]["agent_outputs"]["fundamentals"]

    assert output["analysis_mode"] == "memory_enhanced_rule_engine"
    assert output["memory_delta"]["status"] == "ok"
    assert output["memory_delta"]["previous_signal"] == "bearish"
    assert output["memory_delta"]["current_signal"] == output["signal"]
    assert output["memory_delta"]["change_type"] in {"signal_reversal", "confidence_shift", "stable"}
    assert output["memory_delta"]["summary"]
    assert output["reasoning"]["memory_comparison"] == output["memory_delta"]["summary"]
