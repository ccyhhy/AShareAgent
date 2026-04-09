"""
股票分析服务模块

提供股票分析相关的后台功能服务
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable

from ..models.api_models import StockAnalysisRequest
from ..utils.context_managers import workflow_run
from ..state import api_state
from ..schemas import AgentExecutionLog
from ..dependencies import get_log_storage
from ..utils.api_utils import safe_parse_json, serialize_for_api

logger = logging.getLogger("analysis_service")


_CANONICAL_AGENT_KEYS = {
    "market_data": "market_data",
    "market_data_agent": "market_data",
    "technical_analyst": "technicals",
    "technical_analyst_agent": "technicals",
    "technicals": "technicals",
    # Day5 semantics convergence: treat relative_valuation* as technicals compatibility aliases.
    "relative_valuation": "technicals",
    "relative_valuation_agent": "technicals",
    "relative_valuation_analysis": "technicals",
    "fundamentals": "fundamentals",
    "fundamentals_agent": "fundamentals",
    "sentiment": "sentiment",
    "sentiment_agent": "sentiment",
    "valuation": "valuation",
    "valuation_agent": "valuation",
    "risk_management": "risk_manager",
    "risk_management_agent": "risk_manager",
    "risk_manager": "risk_manager",
    "macro_analyst": "macro_analyst",
    "macro_analyst_agent": "macro_analyst",
    "macro_news": "macro_news",
    "macro_news_agent": "macro_news",
    "researcher_bull": "researcher_bull",
    "researcher_bull_agent": "researcher_bull",
    "researcher_bear": "researcher_bear",
    "researcher_bear_agent": "researcher_bear",
    "debate_room": "debate_room",
    "debate_room_agent": "debate_room",
    "portfolio_management": "portfolio_manager",
    "portfolio_management_agent": "portfolio_manager",
}

_LEGACY_DATA_KEYS = {
    "market_data": ("market_data",),
    # Day5 semantics convergence: prefer relative_valuation_analysis, keep technical_analysis as compatibility fallback.
    "technicals": ("relative_valuation_analysis", "technical_analysis"),
    "fundamentals": ("fundamental_analysis",),
    "sentiment": ("sentiment_analysis",),
    "valuation": ("valuation_analysis",),
    "risk_manager": ("risk_analysis",),
    "macro_analyst": ("macro_analysis",),
}


def _map_agent_name(agent_name: str) -> str:
    """Map internal agent names to the canonical API contract keys."""
    return _CANONICAL_AGENT_KEYS.get(agent_name, agent_name)


def _normalize_agent_name(agent_name: str) -> str:
    """Stable public alias used by Day4 tests and normalization helpers."""
    return _map_agent_name(agent_name)


def _parse_payload(candidate: Any) -> Any:
    if isinstance(candidate, str):
        return safe_parse_json(candidate)
    return candidate


def _extract_last_message_payload(output_state: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(output_state, dict):
        return None

    messages = output_state.get("messages")
    if not isinstance(messages, list) or not messages:
        return None

    last_message = messages[-1]
    if isinstance(last_message, dict):
        candidate = _parse_payload(last_message.get("content"))
    elif hasattr(last_message, "content"):
        candidate = _parse_payload(last_message.content)
    else:
        candidate = None

    return candidate if isinstance(candidate, dict) else None


def _extract_agent_outputs_from_output_state(output_state: dict[str, Any] | None) -> dict[str, Any]:
    """Extract the normalized Day4 agent_outputs map from a serialized output_state."""
    if not isinstance(output_state, dict):
        return {}

    data_section = output_state.get("data")
    if not isinstance(data_section, dict):
        return {}

    agent_outputs = data_section.get("agent_outputs")
    if not isinstance(agent_outputs, dict):
        return {}

    return {
        _normalize_agent_name(str(key)): serialize_for_api(value)
        for key, value in agent_outputs.items()
    }


def _extract_output_state_payload(agent_name: str, latest_data: dict[str, Any]) -> dict[str, Any] | None:
    output_state = latest_data.get("output_state")
    canonical_key = _map_agent_name(agent_name)

    if isinstance(output_state, dict):
        data_section = output_state.get("data")
        if isinstance(data_section, dict):
            agent_outputs = data_section.get("agent_outputs")
            if isinstance(agent_outputs, dict):
                candidate = agent_outputs.get(canonical_key)
                if isinstance(candidate, dict):
                    return candidate

            for legacy_key in _LEGACY_DATA_KEYS.get(canonical_key, ()):
                candidate = data_section.get(legacy_key)
                if isinstance(candidate, dict):
                    return candidate

        message_payload = _extract_last_message_payload(output_state)
        if isinstance(message_payload, dict):
            return message_payload

    return None


def _extract_reasoning_payload(agent_name: str, latest_data: dict[str, Any]) -> dict[str, Any] | None:
    candidate_keys = [f"{agent_name}_reasoning"]

    if agent_name in {"researcher_bull", "researcher_bear", "researcher_bull_agent", "researcher_bear_agent"}:
        candidate_keys.append(f"{agent_name}_agent_reasoning")

    candidate_keys.extend(["reasoning", "agent_reasoning"])

    for key in candidate_keys:
        candidate = _parse_payload(latest_data.get(key))
        if isinstance(candidate, dict):
            return candidate

    return None


def _is_valid_payload(agent_name: str, payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict) or not payload:
        return False

    canonical_key = _map_agent_name(agent_name)
    if canonical_key in {"researcher_bull", "researcher_bear"}:
        return any(field in payload for field in ("perspective", "thesis_points", "signal"))

    return True


def _collect_agent_outputs(agent_names: Iterable[str], all_agents: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    agent_outputs: dict[str, dict[str, Any]] = {}

    for agent_name in agent_names:
        agent_data = all_agents.get(agent_name)
        if not isinstance(agent_data, dict):
            continue

        latest_data = agent_data.get("latest", agent_data)
        if not isinstance(latest_data, dict):
            continue

        payload = _extract_output_state_payload(agent_name, latest_data)
        if not _is_valid_payload(agent_name, payload):
            payload = _extract_reasoning_payload(agent_name, latest_data)

        if _is_valid_payload(agent_name, payload):
            agent_outputs[_map_agent_name(agent_name)] = serialize_for_api(payload)

    return agent_outputs


def _extract_agent_results_from_state(raw_result: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(raw_result, dict):
        return {}

    data_section = raw_result.get("data")
    if not isinstance(data_section, dict):
        return {}

    extracted: dict[str, dict[str, Any]] = {}
    agent_outputs = data_section.get("agent_outputs")
    if isinstance(agent_outputs, dict):
        for key, value in agent_outputs.items():
            canonical_key = _map_agent_name(key)
            if isinstance(value, dict):
                extracted[canonical_key] = serialize_for_api(value)

    for canonical_key, legacy_keys in _LEGACY_DATA_KEYS.items():
        if canonical_key in extracted:
            continue
        for legacy_key in legacy_keys:
            candidate = data_section.get(legacy_key)
            if isinstance(candidate, dict):
                extracted[canonical_key] = serialize_for_api(candidate)
                break

    return extracted


def _fill_missing_agent_results_from_api_state(
    agent_results: dict[str, dict[str, Any]],
    candidate_agent_names: Iterable[str],
    all_agents: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    merged = dict(agent_results)
    fallback_results = _collect_agent_outputs(candidate_agent_names, all_agents)

    for key, value in fallback_results.items():
        merged.setdefault(key, value)

    return merged


def _collect_agent_results(
    *,
    all_agents: dict[str, dict[str, Any]],
    participating_agents: Iterable[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Collect stable Day4 outputs, preferring final serialized agent_outputs."""
    participant_list = list(participating_agents or all_agents.keys())

    preferred_sources = [
        "portfolio_management",
        "portfolio_management_agent",
        "macro_analyst",
        "macro_analyst_agent",
        "risk_management",
        "risk_management_agent",
        "valuation",
        "valuation_agent",
        "technical_analyst",
        "technical_analyst_agent",
        "market_data",
        "market_data_agent",
    ]

    collected: dict[str, dict[str, Any]] = {}

    for agent_name in [*preferred_sources, *participant_list]:
        if agent_name not in all_agents:
            continue

        agent_data = all_agents.get(agent_name)
        latest_data = agent_data.get("latest", agent_data) if isinstance(agent_data, dict) else None
        if not isinstance(latest_data, dict):
            continue

        extracted_outputs = _extract_agent_outputs_from_output_state(
            latest_data.get("output_state")
        )
        for key, value in extracted_outputs.items():
            collected.setdefault(key, value)

    fallback_results = _collect_agent_outputs(participant_list, all_agents)
    for key, value in fallback_results.items():
        collected.setdefault(key, value)

    return collected


def _extract_portfolio_decision(agent_data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(agent_data, dict):
        return None

    latest_data = agent_data.get("latest", agent_data)
    if not isinstance(latest_data, dict):
        return None

    payload = _extract_last_message_payload(latest_data.get("output_state"))
    return serialize_for_api(payload) if isinstance(payload, dict) else None


def _ensure_primary_contract(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    agent_outputs = normalized.get("agent_outputs")
    agent_results = normalized.get("agent_results")

    if not isinstance(agent_outputs, dict) and isinstance(agent_results, dict):
        agent_outputs = agent_results
    if not isinstance(agent_results, dict) and isinstance(agent_outputs, dict):
        agent_results = agent_outputs

    if isinstance(agent_outputs, dict):
        normalized["agent_outputs"] = {
            _normalize_agent_name(str(key)): value for key, value in agent_outputs.items()
        }
    if isinstance(agent_results, dict):
        normalized["agent_results"] = {
            _normalize_agent_name(str(key)): value for key, value in agent_results.items()
        }

    normalized.setdefault("protocol_version", "day4")

    return normalized


def _build_analysis_payload(
    *,
    ticker: str,
    run_id: str,
    final_decision: dict[str, Any] | None,
    agent_outputs: dict[str, dict[str, Any]],
    completion_time: str,
) -> dict[str, Any]:
    payload = {
        "ticker": ticker,
        "run_id": run_id,
        "final_decision": serialize_for_api(final_decision),
        "agent_outputs": serialize_for_api(agent_outputs),
        "agent_results": serialize_for_api(agent_outputs),
        "completion_time": completion_time,
    }
    return _ensure_primary_contract(payload)


def execute_stock_analysis(request: StockAnalysisRequest, run_id: str) -> Dict[str, Any]:
    """执行股票分析任务"""
    from src.main import run_hedge_fund  # 避免循环导入

    try:
        # 获取日志存储器
        log_storage = get_log_storage()

        # 初始化投资组合
        portfolio = {
            "cash": request.initial_capital,
            "stock": request.initial_position
        }

        # 执行分析 - 让系统自动计算日期
        logger.info(f"开始执行股票 {request.ticker} 的分析任务 (运行ID: {run_id})")

        # 创建主工作流日志记录
        workflow_log = AgentExecutionLog(
            agent_name="workflow_manager",
            run_id=run_id,
        timestamp_start=datetime.now(timezone.utc),
        timestamp_end=datetime.now(timezone.utc),  # 初始化为相同值，稍后更新
            input_state={"request": request.dict()},
            output_state=None  # 稍后更新
        )

        # 还不添加到存储，等待工作流完成后再更新

        with workflow_run(run_id):
            # Execute the analysis workflow  
            raw_result = run_hedge_fund(
                run_id=run_id,
                ticker=request.ticker,
                start_date=request.start_date,  # 使用用户指定日期或None(系统默认)
                end_date=request.end_date,      # 使用用户指定日期或None(系统默认)
                portfolio=portfolio,
                show_reasoning=request.show_reasoning,
                num_of_news=request.num_of_news,
                show_summary=request.show_summary
            )

        run_info = api_state.get_run(run_id)

        # Get all available agents from api_state
        all_agents = api_state.get_all_agent_data()
        logger.info(f"Available agents: {list(all_agents.keys())}")

        if run_info and run_info.agents:
            logger.info(f"Agents that participated in run {run_id}: {run_info.agents}")
            agent_outputs = _collect_agent_results(
                all_agents=all_agents,
                participating_agents=run_info.agents,
            )
        else:
            logger.warning(f"No agent list found in run_info for {run_id}, checking all agents")
            agent_outputs = _collect_agent_results(
                all_agents=all_agents,
                participating_agents=all_agents.keys(),
            )
        
        logger.info(f"Collected agent outputs: {list(agent_outputs.keys())}")
        
        # Log detailed agent results for debugging
        for agent_name, result in agent_outputs.items():
            logger.info(f"Agent {agent_name} result keys: {list(result.keys()) if isinstance(result, dict) else type(result)}")
            logger.info(f"Agent {agent_name} first 100 chars of data: {str(result)[:100]}...")
            
            # Add specific debugging for critical agents
            if agent_name in ['researcher_bull', 'researcher_bear']:
                logger.info(f"Agent {agent_name} perspective: {result.get('perspective') if isinstance(result, dict) else 'N/A'}")
                logger.info(f"Agent {agent_name} confidence: {result.get('confidence') if isinstance(result, dict) else 'N/A'}")
                logger.info(f"Agent {agent_name} thesis_points count: {len(result.get('thesis_points', [])) if isinstance(result, dict) else 'N/A'}")
                if isinstance(result, dict) and result.get('thesis_points'):
                    logger.info(f"Agent {agent_name} first thesis point: {result['thesis_points'][0][:50]}..." if result['thesis_points'] else 'No thesis points')
            elif agent_name in ['fundamentals', 'sentiment', 'valuation']:
                logger.info(f"Agent {agent_name} signal: {result.get('signal') if isinstance(result, dict) else 'N/A'}")
                logger.info(f"Agent {agent_name} confidence: {result.get('confidence') if isinstance(result, dict) else 'N/A'}")
                logger.info(f"Agent {agent_name} reasoning type: {type(result.get('reasoning')) if isinstance(result, dict) else 'N/A'}")

        final_decision = _parse_payload(raw_result)
        structured_result = _build_analysis_payload(
            ticker=request.ticker,
            run_id=run_id,
            final_decision=final_decision if isinstance(final_decision, dict) else None,
            agent_outputs=agent_outputs,
            completion_time=datetime.now(timezone.utc).isoformat(),
        )
        
        logger.info(f"Final structured result keys: {list(structured_result.keys())}")
        logger.info(f"Agent outputs count: {len(agent_outputs)}")

        logger.info(f"股票分析任务完成 (运行ID: {run_id})")
        return structured_result
    except Exception as e:
        logger.error(f"股票分析任务失败: {str(e)}")

        # 在出错时也记录日志
        # try:
    #     workflow_log.timestamp_end = datetime.now(timezone.utc)
        #     workflow_log.output_state = {"error": str(e)}
        #     log_storage.add_agent_log(workflow_log)
        # except Exception as log_err:
        #     logger.error(f"记录错误日志时发生异常: {str(log_err)}")

        # 更新运行状态为错误
        api_state.complete_run(run_id, "error")
        raise
