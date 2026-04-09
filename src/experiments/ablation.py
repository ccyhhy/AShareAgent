from __future__ import annotations

from typing import Any

SUPPORTED_ABLATION_PROFILES = {
    "full_heterogeneous",
    "full_homogeneous",
    "no_rule_agents",
    "no_llm_agents",
    "remove_single_agent_x",
}


def build_ablation_config(
    *,
    profile: str = "full_heterogeneous",
    remove_single_agent: str | None = None,
    homogeneous_agent_type: str = "llm",
    disabled_agents: list[str] | None = None,
    disable_agent_types: list[str] | None = None,
) -> dict[str, Any]:
    normalized_profile = str(profile or "full_heterogeneous").strip().lower()
    if normalized_profile not in SUPPORTED_ABLATION_PROFILES and not normalized_profile.startswith(
        "remove_single_agent_"
    ):
        raise ValueError(
            f"Unsupported ablation profile: {profile}. "
            f"Supported={sorted(SUPPORTED_ABLATION_PROFILES)}"
        )

    config: dict[str, Any] = {
        "profile": normalized_profile,
        "disabled_agents": list(disabled_agents or []),
        "disable_agent_types": list(disable_agent_types or []),
        "homogeneous_agent_type": str(homogeneous_agent_type or "llm").strip().lower(),
    }
    if remove_single_agent:
        config["remove_single_agent"] = remove_single_agent
    return config
