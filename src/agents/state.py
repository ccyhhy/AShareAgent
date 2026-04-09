from typing import Annotated, Any, Dict, Sequence, TypedDict

import operator
from langchain_core.messages import BaseMessage, HumanMessage
import json
from src.utils.logging_config import setup_logger

# 设置日志记录
logger = setup_logger('agent_state')


_SUPPORTED_AGENT_TYPES = {
    "rule_engine",
    "quantitative_model",
    "statistical_model",
    "llm",
    "data_layer",
}

_AGENT_ALIAS_TO_CANONICAL = {
    "market_data": "market_data",
    "market_data_agent": "market_data",
    "technical_analyst": "technical_analyst",
    "technical_analyst_agent": "technical_analyst",
    "technicals": "technical_analyst",
    "fundamentals": "fundamentals",
    "fundamentals_agent": "fundamentals",
    "sentiment": "sentiment",
    "sentiment_agent": "sentiment",
    "valuation": "valuation",
    "valuation_agent": "valuation",
    "researcher_bull": "researcher_bull",
    "researcher_bull_agent": "researcher_bull",
    "researcher_bear": "researcher_bear",
    "researcher_bear_agent": "researcher_bear",
    "debate_room": "debate_room",
    "debate_room_agent": "debate_room",
    "risk_management": "risk_management",
    "risk_management_agent": "risk_management",
    "risk_manager": "risk_management",
    "macro_analyst": "macro_analyst",
    "macro_analyst_agent": "macro_analyst",
    "macro_news": "macro_news_agent",
    "macro_news_agent": "macro_news_agent",
    "portfolio_management": "portfolio_management",
    "portfolio_management_agent": "portfolio_management",
    "portfolio_manager": "portfolio_management",
}


def merge_dicts(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Merge two dicts with one-level deep merge for nested dict values.

    This prevents parallel agents from overwriting each other's entries
    when writing to shared nested dicts like ``agent_outputs``.
    """
    merged = {**a}
    for key, value in b.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged


def canonicalize_agent_key(agent_key: str | None) -> str:
    normalized = str(agent_key or "").strip().lower().replace("-", "_")
    return _AGENT_ALIAS_TO_CANONICAL.get(normalized, normalized)


def _ensure_agent_outputs(data: Dict[str, Any]) -> Dict[str, Any]:
    agent_outputs = data.get("agent_outputs")
    if not isinstance(agent_outputs, dict):
        agent_outputs = {}
    data["agent_outputs"] = agent_outputs
    return agent_outputs


def _normalize_agent_type(agent_type: str | None) -> str:
    normalized = str(agent_type or "").strip().lower().replace("-", "_")
    return normalized if normalized in _SUPPORTED_AGENT_TYPES else "rule_engine"


def resolve_ablation_config(metadata: Dict[str, Any] | None) -> Dict[str, Any]:
    metadata = metadata or {}
    raw_config = metadata.get("ablation_config")
    if not isinstance(raw_config, dict):
        raw_config = {}

    profile = str(raw_config.get("profile", "full_heterogeneous")).strip().lower()
    if not profile:
        profile = "full_heterogeneous"

    disabled_agents = set()
    for item in raw_config.get("disabled_agents", []) or []:
        disabled_agents.add(canonicalize_agent_key(str(item)))

    disabled_types = {
        _normalize_agent_type(str(item))
        for item in (raw_config.get("disable_agent_types", []) or [])
    }
    disabled_types.discard("")

    remove_single_agent = raw_config.get("remove_single_agent") or raw_config.get("target_agent")
    if isinstance(remove_single_agent, str) and remove_single_agent.strip():
        disabled_agents.add(canonicalize_agent_key(remove_single_agent))

    if profile.startswith("remove_single_agent_"):
        suffix = profile[len("remove_single_agent_") :]
        if suffix:
            disabled_agents.add(canonicalize_agent_key(suffix))

    if profile == "no_rule_agents":
        disabled_types.add("rule_engine")
    elif profile == "no_llm_agents":
        disabled_types.add("llm")
    elif profile == "full_homogeneous":
        homogeneous_type = _normalize_agent_type(
            str(raw_config.get("homogeneous_agent_type", "llm"))
        )
        for agent_type in _SUPPORTED_AGENT_TYPES:
            if agent_type == "data_layer":
                continue
            if agent_type != homogeneous_type:
                disabled_types.add(agent_type)

    return {
        "profile": profile,
        "disabled_agents": disabled_agents,
        "disabled_agent_types": disabled_types,
    }


def get_ablation_disable_reason(
    state: Dict[str, Any], *, agent_key: str, agent_type: str
) -> str | None:
    metadata = state.get("metadata", {}) if isinstance(state, dict) else {}
    config = resolve_ablation_config(metadata if isinstance(metadata, dict) else {})
    canonical_agent = canonicalize_agent_key(agent_key)
    normalized_type = _normalize_agent_type(agent_type)

    if canonical_agent in config["disabled_agents"]:
        return (
            f"Ablation disabled agent '{canonical_agent}' "
            f"(profile={config['profile']})."
        )
    if normalized_type in config["disabled_agent_types"]:
        return (
            f"Ablation disabled agent_type '{normalized_type}' "
            f"(profile={config['profile']})."
        )
    return None


def maybe_return_ablation_stub(
    state: Dict[str, Any],
    *,
    agent_key: str,
    agent_type: str,
    message_name: str,
    output_key: str | None = None,
    data_key: str | None = None,
    payload_overrides: Dict[str, Any] | None = None,
    data_updates: Dict[str, Any] | None = None,
) -> Dict[str, Any] | None:
    reason = get_ablation_disable_reason(state, agent_key=agent_key, agent_type=agent_type)
    if reason is None:
        return None

    metadata = state.get("metadata", {}) if isinstance(state, dict) else {}
    profile = resolve_ablation_config(metadata if isinstance(metadata, dict) else {})["profile"]

    payload = {
        "agent_type": _normalize_agent_type(agent_type),
        "signal": "neutral",
        "confidence": "50%",
        "reasoning": reason,
        "ablation": {
            "disabled": True,
            "profile": profile,
            "agent_key": canonicalize_agent_key(agent_key),
        },
    }
    if isinstance(payload_overrides, dict):
        payload.update(payload_overrides)

    message = HumanMessage(
        content=json.dumps(payload, ensure_ascii=False),
        name=message_name,
    )

    existing_data = state.get("data", {}) if isinstance(state, dict) else {}
    updated_data = dict(existing_data if isinstance(existing_data, dict) else {})
    agent_outputs = _ensure_agent_outputs(updated_data)
    if output_key:
        agent_outputs[output_key] = payload
    if data_key:
        updated_data[data_key] = payload
    if isinstance(data_updates, dict):
        updated_data.update(data_updates)

    metadata = dict(metadata if isinstance(metadata, dict) else {})
    metadata["agent_reasoning"] = payload

    return {
        "messages": [message],
        "data": updated_data,
        "metadata": metadata,
    }

# Define agent state


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    data: Annotated[Dict[str, Any], merge_dicts]
    metadata: Annotated[Dict[str, Any], merge_dicts]


def show_workflow_status(agent_name: str, status: str = "processing"):
    """Display agent workflow status in a clean format.

    Args:
        agent_name: Name of the agent
        status: Status of the agent's work ("processing" or "completed")
    """
    if status == "processing":
        logger.info(f"🔄 {agent_name} is analyzing...")
    else:
        logger.info(f"✅ {agent_name} analysis completed")


def show_agent_reasoning(output, agent_name):
    """Display agent's analysis results."""
    def convert_to_serializable(obj):
        if hasattr(obj, 'to_dict'):  # Handle Pandas Series/DataFrame
            return obj.to_dict()
        elif hasattr(obj, '__dict__'):  # Handle custom objects
            return obj.__dict__
        elif isinstance(obj, (int, float, bool, str)):
            return obj
        elif isinstance(obj, (list, tuple)):
            return [convert_to_serializable(item) for item in obj]
        elif isinstance(obj, dict):
            return {key: convert_to_serializable(value) for key, value in obj.items()}
        else:
            return str(obj)  # Fallback to string representation

    # logger.info(f"{'='*20} {agent_name} Analysis Details {'='*20}")

    if isinstance(output, (dict, list)):
        # Convert the output to JSON-serializable format
        serializable_output = convert_to_serializable(output)
        logger.info(json.dumps(serializable_output, indent=2, ensure_ascii=False))
    else:
        try:
            # Parse the string as JSON and pretty print it
            parsed_output = json.loads(output)
            logger.info(json.dumps(parsed_output, indent=2, ensure_ascii=False))
        except json.JSONDecodeError:
            # Fallback to original string if not valid JSON
            logger.info(output)
