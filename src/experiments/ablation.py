"""Compatibility helper for ablation configuration."""

from __future__ import annotations

from typing import Any


def build_ablation_config(
    profile: str = "full_heterogeneous",
    *,
    remove_single_agent: str | None = None,
    homogeneous_agent_type: str | None = None,
    disabled_agents: list[str] | None = None,
    disable_agent_types: list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build a normalized ablation config payload expected by legacy callers."""
    config: dict[str, Any] = {"profile": profile}
    if remove_single_agent:
        config["remove_single_agent"] = remove_single_agent
    if homogeneous_agent_type:
        config["homogeneous_agent_type"] = homogeneous_agent_type
    if disabled_agents:
        config["disabled_agents"] = list(disabled_agents)
    if disable_agent_types:
        config["disable_agent_types"] = list(disable_agent_types)
    config.update(extra)
    return config
