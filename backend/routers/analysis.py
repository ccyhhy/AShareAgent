"""
股票分析相关路由模块

此模块提供与股票分析任务相关的API端点，集成用户认证和权限管理
"""

from fastapi import APIRouter, Depends, HTTPException, status
import uuid
import logging
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.models.api_models import (
    ApiResponse, StockAnalysisRequest, StockAnalysisResponse
)
from backend.models.auth_models import UserInDB
from backend.services.auth_service import get_current_active_user, require_permission
from backend.dependencies import get_database_manager
from backend.state import api_state
from backend.services import execute_stock_analysis
from backend.services.analysis import (
    _build_analysis_payload,
    _collect_agent_results,
    _ensure_primary_contract,
    _extract_portfolio_decision,
)
from backend.utils.api_utils import serialize_for_api, safe_parse_json
from src.database.models import DatabaseManager

logger = logging.getLogger("analysis_router")


ANALYSIS_STAGE_CONFIG = [
    {
        "key": "market_data",
        "title": "市场数据",
        "description": "收集行情、财务与基础资料。",
        "agents": ["market_data"],
    },
    {
        "key": "core_analysis",
        "title": "多维分析",
        "description": "技术面、基本面、情绪、估值与宏观新闻并行分析。",
        "agents": [
            "technical_analyst",
            "fundamentals",
            "sentiment",
            "valuation",
            "macro_news_agent",
        ],
    },
    {
        "key": "research",
        "title": "研究员观点",
        "description": "看多与看空研究员形成初步结论。",
        "agents": ["researcher_bull", "researcher_bear"],
    },
    {
        "key": "debate",
        "title": "多空辩论",
        "description": "整合正反观点，形成辩论结论。",
        "agents": ["debate_room"],
    },
    {
        "key": "risk",
        "title": "风险审查",
        "description": "评估仓位、波动和交易风险。",
        "agents": ["risk_management"],
    },
    {
        "key": "macro",
        "title": "宏观影响",
        "description": "判断宏观与政策对个股的影响。",
        "agents": ["macro_analyst"],
    },
    {
        "key": "decision",
        "title": "最终决策",
        "description": "投资组合经理输出最终建议。",
        "agents": ["portfolio_management"],
    },
]

AGENT_DISPLAY_NAMES = {
    "market_data": "市场数据分析",
    "technical_analyst": "技术面分析",
    "fundamentals": "基本面分析",
    "sentiment": "市场情绪分析",
    "valuation": "估值分析",
    "macro_news_agent": "宏观新闻分析",
    "researcher_bull": "看多研究员",
    "researcher_bear": "看空研究员",
    "debate_room": "多空辩论",
    "risk_management": "风险管理",
    "macro_analyst": "宏观影响分析",
    "portfolio_management": "投资组合经理",
}


def _build_analysis_stage_progress(run_id: str, task_status: str) -> Dict[str, Any]:
    run_agent_states = api_state.get_run_agent_states(run_id)
    stages: List[Dict[str, Any]] = []
    current_stage: Optional[Dict[str, Any]] = None
    completed_count = 0
    total_stage_count = len(ANALYSIS_STAGE_CONFIG)

    for stage in ANALYSIS_STAGE_CONFIG:
        agent_statuses = [
            (run_agent_states.get(agent_name) or {}).get("status")
            for agent_name in stage["agents"]
        ]
        agent_statuses = [state for state in agent_statuses if state]

        if task_status == "completed":
            stage_status = "completed"
        elif any(state == "error" for state in agent_statuses):
            stage_status = "error"
        elif agent_statuses and all(state == "completed" for state in agent_statuses):
            stage_status = "completed"
        elif any(state == "running" for state in agent_statuses):
            stage_status = "running"
        elif agent_statuses:
            stage_status = "running"
        else:
            stage_status = "pending"

        stage_payload = {
            "key": stage["key"],
            "title": stage["title"],
            "description": stage["description"],
            "status": stage_status,
            "agents": [
                {
                    "key": agent_name,
                    "label": AGENT_DISPLAY_NAMES.get(agent_name, agent_name),
                    "status": (run_agent_states.get(agent_name) or {}).get("status", "pending"),
                }
                for agent_name in stage["agents"]
            ],
        }
        stages.append(stage_payload)

        if stage_status == "completed":
            completed_count += 1
        elif current_stage is None:
            current_stage = stage_payload

    if task_status == "completed":
        progress_percent = 100
    else:
        progress_percent = round((completed_count / total_stage_count) * 100)
        if current_stage and current_stage["status"] == "running":
            progress_percent += round(100 / (total_stage_count * 2))
        progress_percent = min(progress_percent, 99)

    active_agents = []
    if current_stage:
        active_agents = [
            agent["label"]
            for agent in current_stage["agents"]
            if agent["status"] == "running"
        ]

    if task_status == "completed":
        progress_text = "分析已完成，结果已生成。"
    elif task_status == "failed":
        failed_stage = current_stage["title"] if current_stage else "执行阶段"
        progress_text = f"分析失败，停止在“{failed_stage}”。"
    elif current_stage:
        progress_text = (
            f"已完成 {completed_count}/{total_stage_count} 个阶段，"
            f"当前正在执行“{current_stage['title']}”。"
        )
    else:
        progress_text = "任务已创建，等待开始执行。"

    return {
        "progress_percent": progress_percent,
        "progress_text": progress_text,
        "current_stage": current_stage,
        "stages": stages,
        "active_agents": active_agents,
        "completed_stage_count": completed_count if task_status != "completed" else total_stage_count,
        "total_stage_count": total_stage_count,
    }

def execute_stock_analysis_with_user(request, run_id: str, user_id: int, db_manager: DatabaseManager):
    """执行股票分析，支持用户关联和数据库记录"""
    try:
        # 调用原始分析函数
        result = execute_stock_analysis(request, run_id)
        
        # 更新任务状态为完成
        update_query = """
        UPDATE user_analysis_tasks 
        SET status = ?, completed_at = ?, result = ? 
        WHERE task_id = ?
        """
        # 确保结果被正确序列化和保存
        if result:
            try:
                result_json = json.dumps(serialize_for_api(result))
                logger.info(f"分析结果序列化成功，大小: {len(result_json)} 字符")
            except Exception as e:
                logger.error(f"分析结果序列化失败: {e}")
                result_json = json.dumps({"error": "序列化失败", "message": str(e)})
        else:
            logger.warning(f"分析任务 {run_id} 返回空结果")
            result_json = json.dumps({"error": "分析结果为空", "message": "分析完成但未返回结果"})
        
        with db_manager.get_connection() as conn:
            conn.execute(update_query, ("completed", datetime.now(), result_json, run_id))
            conn.commit()
        api_state.complete_run(run_id, "completed")
            
        logger.info(f"分析任务 {run_id} 状态已更新为completed")
        
        return result
        
    except Exception as e:
        logger.error(f"执行分析任务失败 {run_id}: {e}")
        
        # 更新任务状态为失败
        error_query = """
        UPDATE user_analysis_tasks 
        SET status = ?, completed_at = ?, error_message = ? 
        WHERE task_id = ?
        """
        with db_manager.get_connection() as conn:
            conn.execute(error_query, ("failed", datetime.now(), str(e), run_id))
            conn.commit()
        api_state.complete_run(run_id, "error")
        
        raise e


# 创建路由器
router = APIRouter(prefix="/api/analysis", tags=["Analysis"])


@router.post("/start", response_model=ApiResponse[StockAnalysisResponse])
async def start_stock_analysis(
    request: StockAnalysisRequest,
    current_user: UserInDB = Depends(require_permission("analysis:basic")),
    db_manager: DatabaseManager = Depends(get_database_manager)
):
    """开始股票分析任务

    此API端点允许前端触发新的股票分析。分析将在后台进行，
    前端可通过返回的run_id查询分析状态和结果。

    参数说明:
    - ticker: 股票代码，如"002848"（必填）
    - show_reasoning: 是否显示分析推理过程，默认为true
    - num_of_news: 用于情感分析的新闻数量(1-100)，默认为5
    - initial_capital: 初始资金，默认为100000
    - initial_position: 初始持仓数量，默认为0

    分析日期说明:
    - 系统会自动使用最近一年的数据进行分析，无需手动指定日期范围

    示例请求:
    ```json
    {
        "ticker": "002848",
        "show_reasoning": true,
        "num_of_news": 5,
        "initial_capital": 100000.0,
        "initial_position": 0
    }
    ```

    简化请求(仅提供必填参数):
    ```json
    {
        "ticker": "002848"
    }
    ```
    """
    try:
        # 生成唯一任务ID
        task_id = str(uuid.uuid4())
        
        # 保存任务到数据库
        query = """
        INSERT INTO user_analysis_tasks (user_id, task_id, ticker, task_type, status, parameters, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        parameters = {
            "show_reasoning": request.show_reasoning,
            "num_of_news": request.num_of_news,
            "initial_capital": request.initial_capital,
            "initial_position": request.initial_position
        }
        
        with db_manager.get_connection() as conn:
            conn.execute(query, (
                current_user.id,
                task_id,
                request.ticker,
                "analysis",
                "pending",
                json.dumps(parameters),
                datetime.now()
            ))
            conn.commit()
        
        # 更新任务状态为运行中
        update_query = "UPDATE user_analysis_tasks SET status = ?, started_at = ? WHERE task_id = ?"
        with db_manager.get_connection() as conn:
            conn.execute(update_query, ("running", datetime.now(), task_id))
            conn.commit()
        
        # 将任务提交到线程池
        api_state.register_run(task_id)

        future = api_state._executor.submit(
            execute_stock_analysis_with_user,
            request=request,
            run_id=task_id,
            user_id=current_user.id,
            db_manager=db_manager
        )

        api_state.register_analysis_task(task_id, future)

        # 创建响应对象
        response = StockAnalysisResponse(
            run_id=task_id,
            ticker=request.ticker,
            status="running",
            message="分析任务已启动",
                submitted_at=datetime.now(timezone.utc)
        )
        
    except Exception as e:
        logger.error(f"启动分析任务失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"启动分析任务失败: {str(e)}"
        )

    # 使用ApiResponse包装返回
    return ApiResponse(
        success=True,
        message="分析任务已成功启动",
        data=response
    )


@router.get("/history", response_model=ApiResponse[Dict])
async def get_user_analysis_history(
    skip: int = 0,
    limit: int = 20,
    status: str = None,
    ticker: str = None,
    current_user: UserInDB = Depends(get_current_active_user),
    db_manager: DatabaseManager = Depends(get_database_manager)
):
    """获取用户的分析历史记录"""
    try:
        # 构建查询条件
        where_conditions = ["user_id = ?"]
        params = [current_user.id]
        
        if status:
            where_conditions.append("status = ?")
            params.append(status)
        
        if ticker:
            where_conditions.append("ticker = ?")
            params.append(ticker)
        
        where_clause = " AND ".join(where_conditions)
        
        # 获取总数
        count_query = f"SELECT COUNT(*) as total FROM user_analysis_tasks WHERE {where_clause}"
        count_result = db_manager.execute_query(count_query, params)
        total = count_result[0]["total"] if count_result else 0
        
        # 获取分页数据
        query = f"""
        SELECT task_id, ticker, task_type, status, parameters, 
               created_at, started_at, completed_at, error_message
        FROM user_analysis_tasks 
        WHERE {where_clause}
        ORDER BY created_at DESC 
        LIMIT ? OFFSET ?
        """
        params.extend([limit, skip])
        
        tasks = db_manager.execute_query(query, params)
        
        # 转换参数JSON字符串为对象
        task_list = []
        for task in tasks:
            task_dict = dict(task)
            if task_dict["parameters"]:
                try:
                    task_dict["parameters"] = json.loads(task_dict["parameters"])
                except json.JSONDecodeError:
                    task_dict["parameters"] = {}
            task_list.append(task_dict)
        
        return ApiResponse(
            success=True,
            message="获取分析历史成功",
            data={
                "tasks": task_list,
                "total": total,
                "skip": skip,
                "limit": limit
            }
        )
        
    except Exception as e:
        logger.error(f"获取分析历史失败: {e}")
        return ApiResponse(
            success=False,
            message=f"获取分析历史失败: {str(e)}",
            data=None
        )


@router.get("/{run_id}/status", response_model=ApiResponse[Dict])
async def get_analysis_status(
    run_id: str,
    current_user: UserInDB = Depends(get_current_active_user),
    db_manager: DatabaseManager = Depends(get_database_manager)
):
    """获取股票分析任务的状态"""
    try:
        # 从数据库获取任务信息
        query = """
        SELECT * FROM user_analysis_tasks 
        WHERE task_id = ? AND user_id = ?
        """
        result = db_manager.execute_query(query, (run_id, current_user.id))
        
        if not result:
            return ApiResponse(
                success=False,
                message=f"分析任务 '{run_id}' 不存在或无权限访问",
                data=None
            )
        
        task_data = dict(result[0])
        
        # 获取内存中的任务状态
        task = api_state.get_analysis_task(run_id)
        run_info = api_state.get_run(run_id)
        stage_progress = _build_analysis_stage_progress(run_id, task_data["status"])
        
        status_data = {
            "task_id": task_data["task_id"],
            "ticker": task_data["ticker"],
            "status": task_data["status"],
            "created_at": task_data["created_at"],
            "started_at": task_data["started_at"],
            "completed_at": task_data["completed_at"],
            "error_message": task_data["error_message"],
            "progress": stage_progress["progress_text"],
            "progress_percent": stage_progress["progress_percent"],
            "current_stage": stage_progress["current_stage"],
            "stages": stage_progress["stages"],
            "active_agents": stage_progress["active_agents"],
            "completed_stage_count": stage_progress["completed_stage_count"],
            "total_stage_count": stage_progress["total_stage_count"],
        }
        
        # 如果任务还在内存中运行，获取实时状态
        if task and not task.done():
            status_data["is_running"] = True
        elif task and task.done():
            status_data["is_running"] = False
            if task.exception():
                status_data["runtime_error"] = str(task.exception())
        
        return ApiResponse(
            success=True,
            message="获取任务状态成功",
            data=status_data
        )
        
    except Exception as e:
        logger.error(f"获取任务状态失败: {e}")
        return ApiResponse(
            success=False,
            message=f"获取任务状态失败: {str(e)}",
            data=None
        )


@router.get("/{run_id}/result", response_model=ApiResponse[Dict])
async def get_analysis_result(
    run_id: str,
    current_user: UserInDB = Depends(get_current_active_user),
    db_manager: DatabaseManager = Depends(get_database_manager)
):
    """获取股票分析任务的结果数据

    此接口返回最终的投资决策结果以及各个Agent的分析数据摘要。
    分析必须已经完成才能获取结果。
    """
    try:
        # 从数据库获取任务信息，确保用户权限
        query = """
        SELECT * FROM user_analysis_tasks 
        WHERE task_id = ? AND user_id = ?
        """
        result = db_manager.execute_query(query, (run_id, current_user.id))
        
        if not result:
            return ApiResponse(
                success=False,
                message=f"分析任务 '{run_id}' 不存在或无权限访问",
                data=None
            )
        
        task_data = dict(result[0])
        
        # 检查任务是否完成
        if task_data["status"] != "completed":
            return ApiResponse(
                success=False,
                message=f"分析任务尚未完成或已失败，当前状态: {task_data['status']}",
                data={"status": task_data["status"]}
            )
        
        # 从数据库获取保存的结果
        if task_data["result"]:
            try:
                stored_result = json.loads(task_data["result"])
                
                # 检查是否是错误结果
                if isinstance(stored_result, dict) and "error" in stored_result:
                    return ApiResponse(
                        success=False,
                        message=f"分析失败: {stored_result.get('message', '未知错误')}",
                        data={
                            "task_id": task_data["task_id"],
                            "ticker": task_data["ticker"],
                            "completion_time": task_data["completed_at"],
                            "error": stored_result
                        }
                    )
                
                return ApiResponse(
                    success=True,
                    message="获取分析结果成功",
                    data={
                        "task_id": task_data["task_id"],
                        "ticker": task_data["ticker"],
                        "completion_time": task_data["completed_at"],
                        "result": _ensure_primary_contract(stored_result),
                    }
                )
            except json.JSONDecodeError as e:
                logger.error(f"解析存储的分析结果失败: {run_id}, 错误: {e}")
                return ApiResponse(
                    success=False,
                    message="分析结果数据格式错误",
                    data={
                        "task_id": task_data["task_id"],
                        "ticker": task_data["ticker"],
                        "completion_time": task_data["completed_at"],
                        "error": {"message": "数据格式错误", "details": str(e)}
                    }
                )
        
        # 如果数据库中没有结果，尝试从内存获取
        task = api_state.get_analysis_task(run_id)
        run_info = api_state.get_run(run_id)
        
        if not run_info:
            return ApiResponse(
                success=False,
                message="分析结果不可用",
                data=None
            )
        
        # 收集所有参与此运行的Agent数据
        agent_outputs = {}
        ticker = task_data["ticker"]
        all_agents = api_state.get_all_agent_data()
        if run_info.agents:
            agent_outputs = _collect_agent_results(
                all_agents=all_agents,
                participating_agents=run_info.agents,
            )

        final_decision = _extract_portfolio_decision(all_agents.get("portfolio_management_agent"))
        result_data = _build_analysis_payload(
            ticker=ticker,
            run_id=run_id,
            final_decision=final_decision,
            agent_outputs=agent_outputs,
            completion_time=str(task_data["completed_at"]),
        )

        return ApiResponse(
            success=True,
            message="获取分析结果成功",
            data=result_data
        )
        
    except Exception as e:
        logger.error(f"获取分析结果时出错: {str(e)}")
        return ApiResponse(
            success=False,
            message=f"获取分析结果时出错: {str(e)}",
            data={"error": str(e)}
        )


@router.delete("/{task_id}", response_model=ApiResponse[bool])
async def delete_analysis_task(
    task_id: str,
    current_user: UserInDB = Depends(get_current_active_user),
    db_manager: DatabaseManager = Depends(get_database_manager)
):
    """删除分析任务记录（仅限已完成或失败的任务）"""
    try:
        # 检查任务是否存在且属于当前用户
        check_query = """
        SELECT status FROM user_analysis_tasks 
        WHERE task_id = ? AND user_id = ?
        """
        result = db_manager.execute_query(check_query, (task_id, current_user.id))
        
        if not result:
            return ApiResponse(
                success=False,
                message="任务不存在或无权限删除",
                data=False
            )
        
        task_status = result[0]["status"]
        
        # 只允许删除已完成或失败的任务
        if task_status in ["running", "pending"]:
            return ApiResponse(
                success=False,
                message="无法删除正在运行或待处理的任务",
                data=False
            )
        
        # 删除任务记录
        delete_query = "DELETE FROM user_analysis_tasks WHERE task_id = ? AND user_id = ?"
        with db_manager.get_connection() as conn:
            cursor = conn.execute(delete_query, (task_id, current_user.id))
            conn.commit()
            
            if cursor.rowcount > 0:
                return ApiResponse(
                    success=True,
                    message="任务删除成功",
                    data=True
                )
            else:
                return ApiResponse(
                    success=False,
                    message="删除任务失败",
                    data=False
                )
                
    except Exception as e:
        logger.error(f"删除分析任务失败: {e}")
        return ApiResponse(
            success=False,
            message=f"删除任务失败: {str(e)}",
            data=False
        )

