from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from dataclasses import asdict
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.backtesting.backtester import IntelligentBacktester
from src.experiments.ablation import build_ablation_config
from src.main import app, run_hedge_fund


OUT_DIR = Path("artifacts/day9")
OUT_DIR.mkdir(parents=True, exist_ok=True)


EXPECTED_AGENT_OUTPUT_KEYS = {
    "market_data",
    "technicals",
    "fundamentals",
    "sentiment",
    "valuation",
    "researcher_bull",
    "researcher_bear",
    "debate_room",
    "risk_manager",
    "macro_analyst",
    "macro_news_agent",
}


def write_progress(message: str) -> None:
    sys.__stdout__.write(f"{message}\n")
    sys.__stdout__.flush()


def parse_final_decision(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except Exception:
        return {
            "action": "hold",
            "quantity": 0,
            "confidence": 0.0,
            "reasoning": f"Failed to parse final decision JSON. Raw: {content[:200]}",
        }


def sanitize_retrieved_refs(refs: Any, limit: int = 3) -> list[dict[str, Any]]:
    if not isinstance(refs, list):
        return []
    sanitized: list[dict[str, Any]] = []
    for ref in refs[:limit]:
        if not isinstance(ref, dict):
            continue
        sanitized.append(
            {
                "id": ref.get("id"),
                "stock_code": ref.get("stock_code"),
                "analysis_date": ref.get("analysis_date"),
                "signal": ref.get("signal"),
                "confidence": ref.get("confidence"),
                "created_at": ref.get("created_at"),
            }
        )
    return sanitized


def invoke_workflow_once(
    ticker: str,
    start_date: str,
    end_date: str,
    ablation_config: dict[str, Any],
    num_of_news: int = 5,
) -> dict[str, Any]:
    initial_state = {
        "messages": [],
        "data": {
            "ticker": ticker,
            "portfolio": {"cash": 100000.0, "stock": 0},
            "start_date": start_date,
            "end_date": end_date,
            "num_of_news": num_of_news,
        },
        "metadata": {
            "show_reasoning": False,
            "run_id": str(uuid.uuid4()),
            "ablation_config": ablation_config,
        },
    }

    started_at = time.perf_counter()
    final_state = app.invoke(initial_state)
    runtime_sec = time.perf_counter() - started_at

    final_message = final_state["messages"][-1]
    decision = parse_final_decision(final_message.content)

    data = final_state.get("data", {})
    agent_outputs = data.get("agent_outputs", {}) if isinstance(data, dict) else {}
    output_keys = sorted(agent_outputs.keys()) if isinstance(agent_outputs, dict) else []
    missing_keys = sorted(EXPECTED_AGENT_OUTPUT_KEYS - set(output_keys))

    fundamentals_payload = agent_outputs.get("fundamentals", {}) if isinstance(agent_outputs, dict) else {}
    rag_sample = {
        "ticker": ticker,
        "analysis_date": end_date,
        "memory_scope": fundamentals_payload.get("memory_scope"),
        "memory_delta": fundamentals_payload.get("memory_delta"),
        "retrieved_refs_sample": sanitize_retrieved_refs(fundamentals_payload.get("retrieved_refs")),
    }

    return {
        "ticker": ticker,
        "run_id": initial_state["metadata"]["run_id"],
        "ablation_profile": ablation_config.get("profile"),
        "runtime_sec": round(runtime_sec, 3),
        "success": len(missing_keys) == 0,
        "final_action": decision.get("action"),
        "final_quantity": decision.get("quantity"),
        "final_confidence": decision.get("confidence"),
        "agent_outputs_count": len(output_keys),
        "agent_outputs_keys": output_keys,
        "missing_agent_outputs_keys": missing_keys,
        "rag_sample": rag_sample,
    }


def run_five_ticker_integration(start_date: str, end_date: str) -> list[dict[str, Any]]:
    tickers = ["600519", "000333", "601398", "002415", "601857"]
    config = build_ablation_config(profile="full_heterogeneous")
    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        write_progress(f"[FiveTicker] Running {ticker} ...")
        rows.append(invoke_workflow_once(ticker, start_date, end_date, config))
    return rows


def run_ablation_backtests(start_date: str, end_date: str) -> list[dict[str, Any]]:
    specs = [
        {"profile": "full_heterogeneous"},
        {"profile": "full_homogeneous", "homogeneous_agent_type": "llm"},
        {"profile": "no_rule_agents"},
        {"profile": "no_llm_agents"},
        {"profile": "remove_single_agent_x", "remove_single_agent": "sentiment"},
    ]
    rows: list[dict[str, Any]] = []

    for spec in specs:
        profile = spec["profile"]
        write_progress(f"[Ablation] Backtest profile={profile} ...")
        cfg = build_ablation_config(
            profile=profile,
            remove_single_agent=spec.get("remove_single_agent"),
            homogeneous_agent_type=spec.get("homogeneous_agent_type"),
        )
        agent_fn = partial(
            run_hedge_fund,
            show_reasoning=False,
            ablation_config=cfg,
        )
        backtester = IntelligentBacktester(
            agent=agent_fn,
            ticker="600519",
            start_date=start_date,
            end_date=end_date,
            initial_capital=100000.0,
            num_of_news=5,
        )
        started_at = time.perf_counter()
        backtester.run_backtest()
        elapsed = time.perf_counter() - started_at

        perf = backtester.calculate_performance_metrics()
        risk = backtester.calculate_risk_metrics()
        data_points = max(len(backtester.portfolio_values), 1)

        rows.append(
            {
                "profile": profile,
                "remove_single_agent": spec.get("remove_single_agent", ""),
                "homogeneous_agent_type": spec.get("homogeneous_agent_type", ""),
                "annualized_return": perf.annualized_return,
                "sharpe_ratio": perf.sharpe_ratio,
                "max_drawdown": perf.max_drawdown,
                "total_return": perf.total_return,
                "avg_response_time_sec": elapsed / data_points,
                "token_usage_total": 0,
                "trades_count": perf.trades_count,
                "var_95": risk.value_at_risk,
            }
        )

    return rows


def save_table_png(df: pd.DataFrame, title: str, out_path: Path) -> None:
    if df.empty:
        return
    fig, ax = plt.subplots(figsize=(max(10, len(df.columns) * 1.2), max(2.2, len(df) * 0.55)))
    ax.axis("off")
    ax.set_title(title, fontsize=12, pad=10)
    table = ax.table(
        cellText=df.values,
        colLabels=df.columns,
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.25)
    fig.tight_layout()
    fig.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def save_agent_type_chart(agent_type_counts: dict[str, int], out_path: Path) -> None:
    if not agent_type_counts:
        return
    labels = list(agent_type_counts.keys())
    values = [agent_type_counts[key] for key in labels]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    bars = ax.bar(labels, values, color=["#1b4dd8", "#0f9a64", "#c97d1d", "#43506d", "#6a4fd7"])
    ax.set_title("Agent Type Distribution (Day9)")
    ax.set_ylabel("Count")
    ax.set_ylim(0, max(values) + 1)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.05, str(value), ha="center", va="bottom")
    fig.tight_layout()
    fig.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    os.environ["ASHAREAGENT_BACKTEST_MODE"] = "1"
    logging.disable(logging.CRITICAL)

    # Use fixed windows to keep experiment repeatable and runtime controlled.
    integration_start_date = "2025-01-02"
    integration_end_date = "2025-03-31"
    ablation_start_date = "2025-02-03"
    ablation_end_date = "2025-02-14"

    write_progress("=== Day9 artifact generation started ===")
    write_progress(f"Integration window: {integration_start_date} -> {integration_end_date}")
    write_progress(f"Ablation window: {ablation_start_date} -> {ablation_end_date}")

    integration_rows = run_five_ticker_integration(integration_start_date, integration_end_date)
    integration_df = pd.DataFrame(integration_rows)

    # Build a compact view for CSV/PNG.
    integration_compact = integration_df[
        [
            "ticker",
            "success",
            "final_action",
            "final_confidence",
            "runtime_sec",
            "agent_outputs_count",
            "missing_agent_outputs_keys",
        ]
    ].copy()
    integration_compact["missing_agent_outputs_keys"] = integration_compact["missing_agent_outputs_keys"].apply(
        lambda x: ";".join(x) if isinstance(x, list) else ""
    )

    ablation_rows = run_ablation_backtests(ablation_start_date, ablation_end_date)
    ablation_df = pd.DataFrame(ablation_rows)

    # RAG sample from first ticker run.
    rag_sample = integration_rows[0]["rag_sample"] if integration_rows else {}

    # Agent type comparison from latest integration run.
    agent_type_counts: dict[str, int] = {}
    if integration_rows:
        latest_outputs = integration_rows[0].get("agent_outputs_keys", [])
        # Re-run once to capture agent_type map cleanly.
        sample_state = invoke_workflow_once(
            ticker=integration_rows[0]["ticker"],
            start_date=integration_start_date,
            end_date=integration_end_date,
            ablation_config=build_ablation_config(profile="full_heterogeneous"),
        )
        # `invoke_workflow_once` does not return payload map, so take from quick state invocation.
        initial_state = {
            "messages": [],
            "data": {
                "ticker": integration_rows[0]["ticker"],
                "portfolio": {"cash": 100000.0, "stock": 0},
                "start_date": integration_start_date,
                "end_date": integration_end_date,
                "num_of_news": 5,
            },
            "metadata": {
                "show_reasoning": False,
                "run_id": str(uuid.uuid4()),
                "ablation_config": build_ablation_config(profile="full_heterogeneous"),
            },
        }
        fs = app.invoke(initial_state)
        outputs = fs.get("data", {}).get("agent_outputs", {})
        agent_type_map = {
            key: (value.get("agent_type", "unknown") if isinstance(value, dict) else "unknown")
            for key, value in outputs.items()
        }
        for agent_type in agent_type_map.values():
            agent_type_counts[agent_type] = agent_type_counts.get(agent_type, 0) + 1
    else:
        latest_outputs = []
        sample_state = {}
        agent_type_map = {}

    # Save files.
    (OUT_DIR / "five_ticker_integration.json").write_text(
        json.dumps(integration_rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    integration_compact.to_csv(OUT_DIR / "five_ticker_integration.csv", index=False, encoding="utf-8-sig")

    (OUT_DIR / "ablation_metrics.json").write_text(
        json.dumps(ablation_rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ablation_df.to_csv(OUT_DIR / "ablation_metrics.csv", index=False, encoding="utf-8-sig")

    (OUT_DIR / "rag_retrieval_sample.json").write_text(
        json.dumps(rag_sample, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    (OUT_DIR / "agent_type_comparison.json").write_text(
        json.dumps(
            {
                "agent_type_counts": agent_type_counts,
                "agent_type_map": agent_type_map,
                "sample_ticker": integration_rows[0]["ticker"] if integration_rows else None,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    save_table_png(integration_compact, "Day9 Five-Ticker Integration", OUT_DIR / "five_ticker_integration.png")
    save_table_png(ablation_df.round(6), "Day9 Ablation Metrics", OUT_DIR / "ablation_metrics.png")
    save_agent_type_chart(agent_type_counts, OUT_DIR / "agent_type_comparison.png")

    summary_md = f"""# Day9 Artifact Summary

- Generated at: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- Integration window: {integration_start_date} -> {integration_end_date}
- Ablation window: {ablation_start_date} -> {ablation_end_date}
- Backtest mode: ASHAREAGENT_BACKTEST_MODE=1

## Files

- `five_ticker_integration.json` / `five_ticker_integration.csv` / `five_ticker_integration.png`
- `ablation_metrics.json` / `ablation_metrics.csv` / `ablation_metrics.png`
- `rag_retrieval_sample.json`
- `agent_type_comparison.json` / `agent_type_comparison.png`

## Quick Checks

- Five ticker success count: {int(integration_df["success"].sum()) if not integration_df.empty else 0}/{len(integration_df)}
- Ablation profiles: {", ".join(ablation_df["profile"].tolist()) if not ablation_df.empty else "-"}
- Agent type distribution keys: {", ".join(agent_type_counts.keys()) if agent_type_counts else "-"}
"""
    (OUT_DIR / "README.md").write_text(summary_md, encoding="utf-8")

    write_progress(f"Artifacts written to: {OUT_DIR.resolve()}")
    write_progress("=== Day9 artifact generation completed ===")


if __name__ == "__main__":
    main()
