from __future__ import annotations

from src.agents.state import (
    get_ablation_disable_reason,
    maybe_return_ablation_stub,
    resolve_ablation_config,
)
from src.experiments.ablation import build_ablation_config


def test_resolve_ablation_config_no_rule_agents_disables_rule_engine():
    config = resolve_ablation_config({"ablation_config": {"profile": "no_rule_agents"}})
    assert config["profile"] == "no_rule_agents"
    assert "rule_engine" in config["disabled_agent_types"]


def test_resolve_ablation_config_full_homogeneous_defaults_to_llm():
    config = resolve_ablation_config({"ablation_config": {"profile": "full_homogeneous"}})
    assert "rule_engine" in config["disabled_agent_types"]
    assert "quantitative_model" in config["disabled_agent_types"]
    assert "statistical_model" in config["disabled_agent_types"]
    assert "llm" not in config["disabled_agent_types"]


def test_resolve_ablation_config_remove_single_agent_profile():
    config = resolve_ablation_config(
        {"ablation_config": {"profile": "remove_single_agent_sentiment"}}
    )
    assert "sentiment" in config["disabled_agents"]


def test_get_ablation_disable_reason_matches_aliases():
    state = {"metadata": {"ablation_config": {"profile": "remove_single_agent_x", "remove_single_agent": "macro_analyst_agent"}}}
    reason = get_ablation_disable_reason(
        state,
        agent_key="macro_analyst",
        agent_type="llm",
    )
    assert reason is not None
    assert "macro_analyst" in reason


def test_maybe_return_ablation_stub_writes_agent_outputs_and_data_key():
    state = {
        "messages": [],
        "data": {"ticker": "000001"},
        "metadata": {"ablation_config": {"profile": "remove_single_agent_x", "remove_single_agent": "valuation"}},
    }
    result = maybe_return_ablation_stub(
        state,
        agent_key="valuation",
        agent_type="quantitative_model",
        message_name="valuation_agent",
        output_key="valuation",
        data_key="valuation_analysis",
        payload_overrides={"intrinsic_value": 0.0},
    )

    assert result is not None
    payload = result["data"]["agent_outputs"]["valuation"]
    assert payload["signal"] == "neutral"
    assert payload["intrinsic_value"] == 0.0
    assert result["data"]["valuation_analysis"]["ablation"]["disabled"] is True


def test_build_ablation_config_supports_remove_single_agent():
    config = build_ablation_config(
        profile="remove_single_agent_x",
        remove_single_agent="sentiment",
    )
    assert config["profile"] == "remove_single_agent_x"
    assert config["remove_single_agent"] == "sentiment"
