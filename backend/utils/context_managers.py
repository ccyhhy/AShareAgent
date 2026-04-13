"""
上下文管理器模块

提供各种API相关的上下文管理器
"""

from contextlib import contextmanager
import json
import logging
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

from ..state import api_state
from src.agents.state import canonicalize_agent_key

logger = logging.getLogger("context_managers")

_MAX_REASONING_LENGTH = 1000
_MAX_PREVIEW_LENGTH = 280

# 导入数据库模型
try:
    from backend.dependencies import get_database_manager
    from src.database.models import AgentDecisionModel, AnalysisResultModel
    HAS_DATABASE = True
except ImportError:
    HAS_DATABASE = False
    logger.warning("数据库模型导入失败，将不保存到数据库")


@contextmanager
def workflow_run(run_id: str):
    """
    宸ヤ綔娴佽繍琛屼笂涓嬫枃绠＄悊鍣?

    鐢ㄦ硶:
    with workflow_run(run_id):
        # 鎵ц宸ヤ綔娴?
    """
    api_state.register_run(run_id)
    
    # 鍒濆鍖栨暟鎹簱杩炴帴
    db_manager = None
    decision_model = None
    analysis_model = None
    
    if HAS_DATABASE:
        try:
            db_manager = get_database_manager()
            decision_model = AgentDecisionModel(db_manager)
            analysis_model = AnalysisResultModel(db_manager)
        except Exception as e:
            logger.error(f"鍒濆鍖栨暟鎹簱澶辫触: {e}")
    
    try:
        yield
        api_state.complete_run(run_id, "completed")
        
        # 鍦ㄥ伐浣滄祦瀹屾垚鏃朵繚瀛樻暟鎹埌鏁版嵁搴?
        if HAS_DATABASE and decision_model and analysis_model:
            _save_run_data_to_database(run_id, decision_model, analysis_model)
            
    except Exception as e:
        api_state.complete_run(run_id, "error")
        raise
    finally:
        cleanup_history = getattr(api_state, "cleanup_completed_run_history", None)
        if callable(cleanup_history):
            cleanup_history()


def _save_run_data_to_database(run_id: str, decision_model, analysis_model):
    """Persist aggregated run data into the database."""
    try:
        # 鑾峰彇杩愯淇℃伅
        run_info = api_state.get_run(run_id)
        if not run_info:
            logger.warning(f"鏈壘鍒拌繍琛屼俊鎭? {run_id}")
            return
        
        # 缁熻淇濆瓨鐨勮褰曟暟
        saved_decisions = 0
        saved_analyses = 0
        
        # 閬嶅巻鎵€鏈塧gent鐨勫巻鍙茶褰曪紝鍚堝苟鍚屼竴涓猘gent鍦ㄥ悓涓€娆¤繍琛屼腑鐨勬暟鎹?
        for agent_name in api_state._agent_data:
            agent_data = api_state._agent_data[agent_name]
            
            # 鏀堕泦璇gent鍦ㄦ娆¤繍琛岀殑鎵€鏈夋暟鎹?
            run_entries = [entry for entry in agent_data["history"] if entry.get("run_id") == run_id]
            
            if not run_entries:
                continue
            
            # 鍚堝苟鍚屼竴杩愯鐨勬暟鎹?
            merged_entry = {"run_id": run_id, "agent_name": agent_name}
            latest_timestamp = None
            
            for entry in run_entries:
                if entry.get("timestamp"):
                    if not latest_timestamp or entry["timestamp"] > latest_timestamp:
                        latest_timestamp = entry["timestamp"]
                        
                # 鍚堝苟鎵€鏈夊瓧娈?
                for key, value in entry.items():
                    if key not in ["run_id", "timestamp"] and value is not None:
                        merged_entry[key] = value
            
            merged_entry["timestamp"] = latest_timestamp
            
            # 浠巌nput_state鎴杔atest鏁版嵁涓彁鍙杢icker
            ticker = "UNKNOWN"
            if "input_state" in merged_entry:
                input_state = merged_entry["input_state"]
                if isinstance(input_state, dict) and "data" in input_state:
                    ticker = input_state["data"].get("ticker", "UNKNOWN")
            
            # 濡傛灉娌℃湁浠巌nput_state鎵惧埌锛屽皾璇曚粠鏈€鏂版暟鎹腑鑾峰彇
            if ticker == "UNKNOWN":
                latest_data = agent_data.get("latest", {})
                if "input_state" in latest_data and isinstance(latest_data["input_state"], dict):
                    data_section = latest_data["input_state"].get("data", {})
                    ticker = data_section.get("ticker", "UNKNOWN")
            
            # 淇濆瓨鍐崇瓥璁板綍 - 鍙湁褰撴湁杈撳嚭鐘舵€佹椂鎵嶄繚瀛?
            if "output_state" in merged_entry and merged_entry["output_state"]:
                output_state = merged_entry["output_state"]
                decision_data = _build_compact_decision_data(
                    run_id=run_id,
                    agent_name=agent_name,
                    ticker=ticker,
                    merged_entry=merged_entry,
                )
                
                # 鎻愬彇鍐崇瓥绫诲瀷鍜岀疆淇″害
                decision_type = "analysis"
                confidence_score = None
                reasoning = None
                
                # 灏濊瘯浠庢帹鐞嗘暟鎹腑鎻愬彇缃俊搴?
                if "reasoning" in merged_entry and isinstance(merged_entry["reasoning"], dict):
                    reasoning_data = merged_entry["reasoning"]
                    confidence_score = reasoning_data.get("confidence")
                    reasoning = str(reasoning_data)[:1000]
                
                # 濡傛灉output_state鍖呭惈messages锛屽皾璇曡В鏋?
                if isinstance(output_state, dict) and "messages" in output_state and output_state["messages"]:
                    last_message = output_state["messages"][-1]
                    if isinstance(last_message, dict) and "content" in last_message:
                        content = last_message["content"]
                        if not reasoning:  # 鍙湁褰搑easoning涓虹┖鏃舵墠浣跨敤message content
                            reasoning = content[:1000] if isinstance(content, str) else str(content)[:1000]
                
                # 淇濆瓨鍐崇瓥璁板綍
                success = decision_model.save_decision(
                    run_id=run_id,
                    agent_name=agent_name,
                    ticker=ticker,
                    decision_type=decision_type,
                    decision_data=decision_data,
                    confidence_score=confidence_score,
                    reasoning=reasoning
                )
                if success:
                    saved_decisions += 1
                    logger.debug(f"淇濆瓨鍐崇瓥璁板綍: {agent_name} for {ticker}")
            
            # 淇濆瓨鍒嗘瀽缁撴灉 - 鍙湁褰撴湁鎺ㄧ悊鏁版嵁鏃舵墠淇濆瓨
            if "reasoning" in merged_entry and merged_entry["reasoning"]:
                reasoning_data = merged_entry["reasoning"]
                result_data = _build_compact_result_data(
                    run_id=run_id,
                    agent_name=agent_name,
                    ticker=ticker,
                    merged_entry=merged_entry,
                )
                
                # 鎻愬彇鎵ц鏃堕棿鍜岀疆淇″害
                confidence_score = None
                execution_time = None
                if isinstance(reasoning_data, dict):
                    confidence_score = reasoning_data.get("confidence")
                
                success = analysis_model.save_result(
                    run_id=run_id,
                    agent_name=agent_name,
                    ticker=ticker,
                    analysis_date=merged_entry["timestamp"].strftime('%Y-%m-%d') if merged_entry.get("timestamp") else None,
                    analysis_type=agent_name.replace("_agent", "").replace("_", " "),
                    result_data=result_data,
                    confidence_score=confidence_score,
                    execution_time=execution_time
                )
                if success:
                    saved_analyses += 1
                    logger.debug(f"淇濆瓨鍒嗘瀽缁撴灉: {agent_name} for {ticker}")
        
        logger.info(f"鎴愬姛淇濆瓨杩愯鏁版嵁鍒版暟鎹簱: {run_id}, 鍐崇瓥璁板綍: {saved_decisions}, 鍒嗘瀽缁撴灉: {saved_analyses}")
        
    except Exception as e:
        logger.error(f"淇濆瓨杩愯鏁版嵁鍒版暟鎹簱澶辫触: {e}")
        import traceback
        traceback.print_exc()


def _truncate_preview(value, limit: int = _MAX_PREVIEW_LENGTH):
    if value is None:
        return None
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text[:limit]


def _summarize_llm_interaction(request_payload, response_payload):
    request_preview = _truncate_preview(request_payload)
    response_preview = _truncate_preview(response_payload)
    return {
        "request_chars": len(request_preview or "") if request_payload is not None else 0,
        "response_chars": len(response_preview or "") if response_payload is not None else 0,
        "request_preview": request_preview,
        "response_preview": response_preview,
    }


def _extract_agent_output_from_state(output_state, agent_name: str):
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


def _extract_reasoning_summary(reasoning_data):
    if reasoning_data is None:
        return None
    if isinstance(reasoning_data, str):
        return reasoning_data[:_MAX_REASONING_LENGTH]
    if isinstance(reasoning_data, dict):
        if isinstance(reasoning_data.get("reasoning"), str):
            return reasoning_data["reasoning"][:_MAX_REASONING_LENGTH]
        return json.dumps(reasoning_data, ensure_ascii=False, default=str)[:_MAX_REASONING_LENGTH]
    return str(reasoning_data)[:_MAX_REASONING_LENGTH]


def _build_compact_decision_data(*, run_id: str, agent_name: str, ticker: str, merged_entry: dict):
    timestamp = merged_entry["timestamp"].isoformat() if merged_entry.get("timestamp") else None
    output_state = merged_entry.get("output_state")
    return {
        "run_id": run_id,
        "agent_name": agent_name,
        "ticker": ticker,
        "timestamp": timestamp,
        "agent_output": _extract_agent_output_from_state(output_state, agent_name),
        "reasoning": _extract_reasoning_summary(merged_entry.get("reasoning")),
        "llm_interaction": _summarize_llm_interaction(
            merged_entry.get("llm_request"),
            merged_entry.get("llm_response"),
        ),
    }


def _build_compact_result_data(*, run_id: str, agent_name: str, ticker: str, merged_entry: dict):
    timestamp = merged_entry["timestamp"].isoformat() if merged_entry.get("timestamp") else None
    output_state = merged_entry.get("output_state")
    return {
        "run_id": run_id,
        "agent_name": agent_name,
        "ticker": ticker,
        "timestamp": timestamp,
        "reasoning": _extract_reasoning_summary(merged_entry.get("reasoning")),
        "reasoning_summary": _extract_reasoning_summary(merged_entry.get("reasoning")),
        "agent_output": _extract_agent_output_from_state(output_state, agent_name),
        "llm_interaction": _summarize_llm_interaction(
            merged_entry.get("llm_request"),
            merged_entry.get("llm_response"),
        ),
    }

