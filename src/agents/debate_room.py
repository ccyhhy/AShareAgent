from langchain_core.messages import HumanMessage
from src.agents.state import AgentState, show_agent_reasoning, show_workflow_status
from src.tools.openrouter_config import get_chat_completion
from src.utils.api_utils import agent_endpoint, log_llm_interaction
import json
import ast
import logging

# 获取日志记录器
logger = logging.getLogger('debate_room')


@agent_endpoint("debate_room", "辩论室，分析多空双方观点，得出平衡的投资结论")
def debate_room_agent(state: AgentState):
    """Facilitates debate between bull and bear researchers to reach a balanced conclusion."""
    show_workflow_status("Debate Room")
    show_reasoning = state["metadata"]["show_reasoning"]
    researcher_aliases = {
        "researcher_bull_agent": "researcher_bull",
        "researcher_bear_agent": "researcher_bear",
    }

    def _canonical_researcher_name(name: str) -> str:
        return researcher_aliases.get(name, name)

    logger.info("开始分析研究员观点并进行辩论...")

    # 收集所有研究员信息 - 向前兼容设计（添加防御性检查）
    researcher_messages = {}
    for msg in state["messages"]:
        # 添加防御性检查，确保 msg 和 msg.name 不为 None
        if msg is None:
            continue
        if not hasattr(msg, 'name') or msg.name is None:
            continue
        if isinstance(msg.name, str) and msg.name.startswith("researcher_"):
            canonical_name = _canonical_researcher_name(msg.name)
            researcher_messages[canonical_name] = msg
            logger.debug(f"收集到研究员信息: {msg.name} -> {canonical_name}")

    # 确保至少有看多和看空两个研究员
    if "researcher_bull" not in researcher_messages or "researcher_bear" not in researcher_messages:
        logger.error(
            "缺少必要的研究员数据: researcher_bull 或 researcher_bear")
        raise ValueError(
            "Missing required researcher_bull or researcher_bear messages")

    # 处理研究员数据
    researcher_data = {}
    for name, msg in researcher_messages.items():
        # 添加防御性检查，确保 msg.content 不为 None
        if not hasattr(msg, 'content') or msg.content is None:
            logger.warning(f"研究员 {name} 的消息内容为空")
            continue
        try:
            data = json.loads(msg.content)
            logger.debug(f"成功解析 {name} 的 JSON 内容")
        except (json.JSONDecodeError, TypeError):
            try:
                data = ast.literal_eval(msg.content)
                logger.debug(f"通过 ast.literal_eval 解析 {name} 的内容")
            except (ValueError, SyntaxError, TypeError):
                # 如果无法解析内容，跳过此消息
                logger.warning(f"无法解析 {name} 的消息内容，已跳过")
                continue
        researcher_data[name] = data

    # 获取看多和看空研究员数据（为了兼容原有逻辑）
    if "researcher_bull" not in researcher_data or "researcher_bear" not in researcher_data:
        logger.error("无法解析必要的研究员数据")
        raise ValueError(
            "Could not parse required researcher_bull or researcher_bear messages")

    bull_thesis = researcher_data["researcher_bull"]
    bear_thesis = researcher_data["researcher_bear"]
    logger.info(
        f"已获取看多观点(置信度: {bull_thesis.get('confidence', 0)})和看空观点(置信度: {bear_thesis.get('confidence', 0)})")

    # 比较置信度级别
    bull_confidence = bull_thesis.get("confidence", 0)
    bear_confidence = bear_thesis.get("confidence", 0)

    # 分析辩论观点
    debate_summary = []
    debate_summary.append("Bullish Arguments:")
    for point in bull_thesis.get("thesis_points", []):
        debate_summary.append(f"+ {point}")

    debate_summary.append("\nBearish Arguments:")
    for point in bear_thesis.get("thesis_points", []):
        debate_summary.append(f"- {point}")

    # 收集所有研究员的论点，准备发给 LLM
    all_perspectives = {}
    for name, data in researcher_data.items():
        perspective = data.get("perspective", name.replace(
            "researcher_", "").replace("_agent", ""))
        all_perspectives[perspective] = {
            "confidence": data.get("confidence", 0),
            "thesis_points": data.get("thesis_points", [])
        }

    logger.info(f"准备让 LLM 分析 {len(all_perspectives)} 个研究员的观点")

    # 构建发送给 LLM 的提示
    llm_prompt = """
你是一位专业的金融分析师，请分析以下投资研究员的观点，并给出你的第三方分析:

"""
    for perspective, data in all_perspectives.items():
        llm_prompt += f"\n{perspective.upper()} 观点 (置信度: {data['confidence']}):\n"
        for point in data["thesis_points"]:
            llm_prompt += f"- {point}\n"

    llm_prompt += """
请提供以下格式的 JSON 回复:
{
    "analysis": "你的详细分析，评估各方观点的优劣，并指出你认为最有说服力的论点",
    "score": 0.5,  // 你的评分，从 -1.0(极度看空) 到 1.0(极度看多)，0 表示中性
    "reasoning": "你给出这个评分的简要理由"
}

务必确保你的回复是有效的 JSON 格式，且包含上述所有字段。回复必须使用英文，不要使用中文或其他语言。
"""

    # 调用 LLM 获取第三方观点
    llm_response = None
    llm_analysis = None
    llm_score = 0  # 默认为中性
    try:
        logger.info("开始调用 LLM 获取第三方分析...")
        messages = [
            {"role": "system", "content": "You are a professional financial analyst. Please provide your analysis in English only, not in Chinese or any other language."},
            {"role": "user", "content": llm_prompt}
        ]

        # 使用log_llm_interaction装饰器记录LLM交互
        llm_response = log_llm_interaction(state)(
            lambda: get_chat_completion(messages)
        )()

        logger.info("LLM 返回响应完成")

        # 解析 LLM 返回的 JSON
        if llm_response:
            try:
                # 尝试提取 JSON 部分
                json_start = llm_response.find('{')
                json_end = llm_response.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = llm_response[json_start:json_end]
                    llm_analysis = json.loads(json_str)
                    llm_score = float(llm_analysis.get("score", 0))
                    # 确保分数在有效范围内
                    llm_score = max(min(llm_score, 1.0), -1.0)
                    logger.info(f"成功解析 LLM 回复，评分: {llm_score}")
                    logger.debug(
                        f"LLM 分析内容: {llm_analysis.get('analysis', '未提供分析')[:100]}...")
            except Exception as e:
                # 如果解析失败，记录错误并使用默认值
                logger.error(f"解析 LLM 回复失败: {e}")
                llm_analysis = {"analysis": "Failed to parse LLM response",
                                "score": 0, "reasoning": "Parsing error"}
    except Exception as e:
        logger.error(f"调用 LLM 失败: {e}")
        llm_analysis = {"analysis": "LLM API call failed",
                        "score": 0, "reasoning": "API error"}

    # Enhanced A-share specific confidence calculation
    confidence_diff = bull_confidence - bear_confidence
    
    # A股特色因素调整
    ashare_adjustments = {
        'policy_factor': 0.0,
        'liquidity_factor': 0.0, 
        'volatility_factor': 0.0,
        'sentiment_extreme': 0.0
    }
    
    # 检查政策敏感性
    bull_reasoning = str(bull_thesis.get('reasoning', ''))
    bear_reasoning = str(bear_thesis.get('reasoning', ''))
    
    if 'policy' in bull_reasoning.lower() or 'policy' in bear_reasoning.lower():
        ashare_adjustments['policy_factor'] = 0.1 if bull_confidence > bear_confidence else -0.1
        
    # 检查流动性风险
    if 'liquidity' in bear_reasoning.lower():
        ashare_adjustments['liquidity_factor'] = -0.05
        
    # 检查情绪极端情况
    if abs(confidence_diff) > 0.7:
        ashare_adjustments['sentiment_extreme'] = -0.1 * abs(confidence_diff)
    
    # 应用A股调整
    total_adjustment = sum(ashare_adjustments.values())
    adjusted_confidence_diff = confidence_diff + total_adjustment
    
    # 增加LLM权重以更好处理A股复杂性
    llm_weight = 0.4
    
    # 综合计算，结合调整后的置信度和LLM分析
    mixed_confidence_diff = (1 - llm_weight) * adjusted_confidence_diff + llm_weight * llm_score
    
    logger.info(
        f"A股特色调整: 原始差异={confidence_diff:.3f}, 调整后={adjusted_confidence_diff:.3f}, LLM评分={llm_score:.3f}, 最终差异={mixed_confidence_diff:.3f}")
    logger.info(f"A股调整因素: {ashare_adjustments}")

    # A股特色决策逻辑优化
    market_volatility = abs(bull_confidence - bear_confidence)
    adaptive_threshold = 0.1 + min(market_volatility * 0.1, 0.05)  # 动態阈值
    
    # 特殊情况检查
    special_conditions = {
        'policy_sensitive': ashare_adjustments['policy_factor'] != 0,
        'high_volatility': market_volatility > 0.6,
        'extreme_sentiment': abs(adjusted_confidence_diff) > 0.8,
        'liquidity_concern': ashare_adjustments['liquidity_factor'] < 0
    }
    
    # 决策逻辑优化
    if abs(mixed_confidence_diff) < adaptive_threshold:
        final_signal = "neutral"
        reasoning = f"A股辩论均衡，双方论点都有合理性。阈值: {adaptive_threshold:.3f}"
        confidence = max(bull_confidence, bear_confidence)
    elif mixed_confidence_diff > 0:
        confidence_level = "强烈" if mixed_confidence_diff > 0.5 else "温和"
        final_signal = "bullish"
        reasoning = f"{confidence_level}看多信号，多头论点更有说服力。评分: {mixed_confidence_diff:.3f}"
        confidence = bull_confidence
    else:
        risk_level = "高风险" if mixed_confidence_diff < -0.5 else "中等风险"
        final_signal = "bearish"
        reasoning = f"{risk_level}看空信号，空头论点更有说服力。评分: {mixed_confidence_diff:.3f}"
        confidence = bear_confidence
    
    # 特殊情况调整
    if special_conditions['policy_sensitive']:
        reasoning += " ❗政策敏感性高"
    if special_conditions['liquidity_concern']:
        reasoning += " ⚠️流动性风险"
    if special_conditions['high_volatility']:
        reasoning += " 📈波动性较大"

    logger.info(f"最终投资信号: {final_signal}, 置信度: {confidence}")

    # A股特色辩论结果
    message_content = {
        "signal": final_signal,
        "confidence": confidence,
        "bull_confidence": bull_confidence,
        "bear_confidence": bear_confidence,
        "confidence_diff": confidence_diff,
        "adjusted_confidence_diff": adjusted_confidence_diff,
        "llm_score": llm_score if llm_analysis else None,
        "llm_analysis": llm_analysis["analysis"] if llm_analysis and "analysis" in llm_analysis else None,
        "llm_reasoning": llm_analysis["reasoning"] if llm_analysis and "reasoning" in llm_analysis else None,
        "mixed_confidence_diff": mixed_confidence_diff,
        "debate_summary": debate_summary,
        "reasoning": reasoning,
        "ashare_factors": {
            "policy_sensitivity": special_conditions['policy_sensitive'],
            "liquidity_concerns": special_conditions['liquidity_concern'],
            "volatility_level": market_volatility,
            "adaptive_threshold": adaptive_threshold,
            "adjustments_applied": ashare_adjustments
        },
        "decision_quality": {
            "consensus_strength": 1 - market_volatility,
            "argument_balance": min(bull_confidence, bear_confidence) / max(bull_confidence, bear_confidence) if max(bull_confidence, bear_confidence) > 0 else 0,
            "llm_agreement": 1 - abs(llm_score - (adjusted_confidence_diff / 2)) if llm_score is not None else 0
        }
    }

    message = HumanMessage(
        content=json.dumps(message_content, ensure_ascii=False),
        name="debate_room_agent",
    )

    if show_reasoning:
        show_agent_reasoning(message_content, "Debate Room")
    
    # 始终保存推理信息到metadata供API使用
    state["metadata"]["agent_reasoning"] = message_content

    show_workflow_status("A股特色辩论室", "completed")
    logger.info(f"A股辩论室分析完成: {final_signal}, 置信度: {confidence:.3f}")
    return {
        "messages": [message],
        "data": {
            **state["data"],
            "debate_analysis": message_content,
            "ashare_debate_metrics": {
                "volatility_level": market_volatility,
                "policy_sensitivity": special_conditions['policy_sensitive'],
                "decision_confidence": confidence,
                "consensus_quality": message_content["decision_quality"]["consensus_strength"]
            }
        },
        "metadata": {
            **state["metadata"],
            "debate_enhanced": True,
            "adaptive_threshold": adaptive_threshold,
            "special_conditions": special_conditions
        },
    }
