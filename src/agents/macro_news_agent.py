import os
import json
from datetime import datetime
import akshare as ak
from src.utils.logging_config import setup_logger
# from langgraph.graph import AgentState # Changed import
# Added for alignment
from src.agents.state import (
    AgentState,
    _ensure_agent_outputs,
    maybe_return_ablation_stub,
    show_agent_reasoning,
    show_workflow_status,
)
from typing import Dict, Any, List
from src.utils.api_utils import agent_endpoint  # Added for alignment
from src.tools.openrouter_config import get_chat_completion
from langchain_core.messages import HumanMessage  # Added import

# LLM Prompt for analyzing full news data
LLM_PROMPT_MACRO_ANALYSIS = """浣犳槸涓€鍚嶈祫娣辩殑A鑲″競鍦哄畯瑙傚垎鏋愬笀銆傝鏍规嵁浠ヤ笅鎻愪緵鐨勬勃娣?00鎸囨暟锛堜唬鐮侊細000300锛夊綋鏃ョ殑**鍏ㄩ儴鏂伴椈鏁版嵁**锛岃繘琛屾繁鍏ュ垎鏋愬苟鐢熸垚涓€浠戒笓涓氱殑瀹忚鎬荤粨鎶ュ憡銆?

鎶ュ憡搴斿寘鍚互涓嬪嚑涓柟闈細
1.  **甯傚満鎯呯华瑙ｈ**锛氭暣浣撹瘎浼板綋鍓嶅競鍦烘儏缁紙濡傦細涔愯銆佽皑鎱庛€佹偛瑙傦級锛屽苟绠€杩板垽鏂緷鎹€?
2.  **鐑偣鏉垮潡璇嗗埆**锛氭壘鍑烘柊闂讳腑鍙嶆槧鍑虹殑1-3涓富瑕佺儹鐐规澘鍧楁垨涓婚锛屽苟璇存槑鍏堕┍鍔ㄥ洜绱犮€?
3.  **娼滃湪椋庨櫓鎻愮ず**锛氭彮绀烘柊闂讳腑鍙兘闅愯棌鐨?-2涓畯瑙傚眰闈㈡垨甯傚満灞傞潰鐨勬綔鍦ㄩ闄╃偣銆?
4.  **鏀跨瓥褰卞搷鍒嗘瀽**锛氬鏋滄柊闂绘彁鍙婇噸瑕佹斂绛栧彉鍔紝璇峰垎鏋愬叾鍙兘瀵瑰競鍦轰骇鐢熺殑鐭湡鍜岄暱鏈熷奖鍝嶃€?
5.  **缁煎悎灞曟湜**锛氬熀浜庝互涓婂垎鏋愶紝瀵圭煭鏈熷競鍦鸿蛋鍔跨粰鍑轰竴涓畝鏄庢壖瑕佺殑灞曟湜銆?

璇风‘淇濆垎鏋愬瑙傘€侀€昏緫娓呮櫚锛岃瑷€涓撲笟銆傜洿鎺ヨ繑鍥炲垎鏋愭姤鍛婂唴瀹癸紝涓嶈鍖呭惈浠讳綍棰濆璇存槑鎴栧濂楄瘽銆?

**褰撴棩鏂伴椈鏁版嵁濡備笅锛?*
{news_data_json_string}
"""

# 鍒濆鍖?logger
logger = setup_logger('macro_news_agent')


def _is_backtest_mode() -> bool:
    value = os.getenv("ASHAREAGENT_BACKTEST_MODE")
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}




@agent_endpoint("macro_news_agent", "Macro market-news agent for monthly market-wide news synthesis")
def macro_news_agent(state: AgentState) -> Dict[str, Any]:
    """
    鑾峰彇娌繁300鍏ㄩ噺鏂伴椈锛岃皟鐢↙LM杩涜瀹忚鍒嗘瀽锛屽苟淇濆瓨缁撴灉銆?
    璇gent鐙珛杩愯锛屼笉渚濊禆鐗瑰畾涓婃父鏁版嵁锛岀粨鏋滄敞鍏gentState銆?
    """
    agent_name = "macro_news_agent"
    show_workflow_status(f"{agent_name}: --- Executing Macro News Agent ---")
    symbol = "000300"  # 娌繁300鎸囨暟
    news_list_for_llm: List[Dict[str, str]] = []
    summary = f"瀹忚鏂伴椈鍒嗘瀽杩囩▼涓彂鐢熼敊璇? 鏈煡閿欒"  # Default error summary
    retrieved_news_count = 0
    from_cache = False  # Flag to indicate if summary was loaded from cache

    today_str = datetime.now().strftime("%Y-%m-%d")
    # 鏀逛负鎸夋湀缂撳瓨锛氫娇鐢ㄥ勾-鏈堜綔涓虹紦瀛橀敭
    month_str = datetime.now().strftime("%Y-%m")
    output_file_path = os.path.join("data", "macro_summary.json")

    ablation_result = maybe_return_ablation_stub(
        state,
        agent_key="macro_news_agent",
        agent_type="llm",
        message_name=agent_name,
        output_key="macro_news_agent",
        data_key="macro_news_analysis",
        payload_overrides={
            "analysis_domain": "macro_market_news",
            "news_count": 0,
            "summary": "Ablation 已禁用 macro_news_agent，已跳过全市场新闻综合。",
            "loaded_from_cache": False,
            "analysis_period": "monthly",
            "summary_generated_on": month_str,
            "backtest_mode": False,
        },
        data_updates={
            "macro_news_analysis_result": "Ablation 已禁用 macro_news_agent，已跳过全市场新闻综合。"
        },
    )
    if ablation_result is not None:
        ablation_result["metadata"][f"{agent_name}_details"] = {
            "summary_generated_on": month_str,
            "analysis_period": "monthly",
            "news_count_for_summary": 0,
            "llm_summary_preview": "Ablation 已禁用 macro_news_agent 节点。",
            "loaded_from_cache": False,
            "backtest_mode": False,
            "ablation_disabled": True,
        }
        return ablation_result

    if _is_backtest_mode():
        summary = "当前为回测模式，已跳过全市场宏观新闻抓取与LLM摘要。"
        macro_news_payload = {
            "agent_type": "llm",
            "analysis_domain": "macro_market_news",
            "signal": "neutral",
            "confidence": "50%",
            "news_count": 0,
            "summary": summary,
            "loaded_from_cache": False,
            "analysis_period": "monthly",
            "summary_generated_on": month_str,
            "backtest_mode": True,
        }
        new_message_content = (
            f"宏观新闻代理分析（{month_str}，from_cache=False）：\n{summary}"
        )
        new_message = HumanMessage(content=new_message_content, name=agent_name)
        updated_data = dict(state["data"])
        agent_outputs = _ensure_agent_outputs(updated_data)
        agent_outputs["macro_news_agent"] = macro_news_payload
        show_workflow_status(f"{agent_name}: 执行完成（回测确定性回退）。")
        return {
            "messages": [new_message],
            "data": {
                **updated_data,
                "macro_news_analysis_result": summary,
                "macro_news_analysis": macro_news_payload,
            },
            "metadata": {
                **state["metadata"],
                f"{agent_name}_details": {
                    "summary_generated_on": month_str,
                    "analysis_period": "monthly",
                    "news_count_for_summary": 0,
                    "llm_summary_preview": summary,
                    "loaded_from_cache": False,
                    "backtest_mode": True,
                },
            },
        }

    # Attempt to load from cache first
    if os.path.exists(output_file_path):
        try:
            with open(output_file_path, 'r', encoding='utf-8') as f:
                all_summaries = json.load(f)
            # 妫€鏌ユ湰鏈堟槸鍚﹀凡鏈夌紦瀛?
            if month_str in all_summaries and all_summaries[month_str].get("summary_content"):
                cached_data = all_summaries[month_str]
                summary = cached_data["summary_content"]
                legacy_summary_map = {
                    "LLM analysis did not return a valid result.": "LLM分析未返回有效结果。",
                    "No macro news data was retrieved today.": "今日未检索到可用的宏观新闻数据。",
                }
                summary = legacy_summary_map.get(summary, summary)
                retrieved_news_count = cached_data.get(
                    "retrieved_news_count", 0)  # Get cached news count
                from_cache = True
                show_workflow_status(
                    f"{agent_name}: loaded cached macro summary for {month_str}."
                )
                show_agent_reasoning(
                    f"Loaded macro summary for {month_str} from cache. News count: {retrieved_news_count}", agent_name)
        except json.JSONDecodeError:
            show_agent_reasoning(
                f"JSONDecodeError for {output_file_path} when trying to load cache. Will fetch fresh data.", agent_name)
            all_summaries = {}  # Reset if file is corrupt
        except Exception as e:
            show_agent_reasoning(
                f"Error loading cache from {output_file_path}: {str(e)}. Will fetch fresh data.", agent_name)
            all_summaries = {}  # Reset on other errors

    if not from_cache:
        show_workflow_status(
            f"{agent_name}: cache miss for {month_str}; fetching live news."
        )
        try:
            show_workflow_status(f"{agent_name}: Fetching news for symbol {symbol}")
            news_df = ak.stock_news_em(symbol=symbol)
            if news_df is None or news_df.empty:
                message = f"No news data was retrieved for {symbol}."
                show_workflow_status(f"{agent_name}: {message}")
                show_agent_reasoning(
                    f"No news found for {symbol}. Proceeding with no data summary.", agent_name
                )
                summary = "今日未检索到可用的宏观新闻数据。"
            else:
                retrieved_news_count = len(news_df)
                message = f"已为 {symbol} 抓取 {retrieved_news_count} 条新闻。"
                show_workflow_status(f"{agent_name}: {message}")
                show_agent_reasoning(
                    f"成功抓取 {retrieved_news_count} 条新闻，准备进入LLM分析。",
                    agent_name,
                )
                for _, row in news_df.iterrows():
                    news_item = {
                        "title": str(row.get("新闻标题", "")).strip(),
                        "content": str(row.get("新闻内容", "")).strip(),
                        "publish_time": str(row.get("发布时间", "")).strip(),
                    }
                    news_list_for_llm.append(news_item)

                news_data_json_string = json.dumps(
                    news_list_for_llm, ensure_ascii=False, indent=2
                )
                prompt_filled = LLM_PROMPT_MACRO_ANALYSIS.format(
                    news_data_json_string=news_data_json_string
                )

                show_workflow_status(f"{agent_name}: Calling LLM for analysis.")
                llm_response = get_chat_completion(
                    messages=[{"role": "user", "content": prompt_filled}]
                )
                summary = (
                    llm_response.strip() if llm_response else "LLM分析未返回有效结果。"
                )
                show_workflow_status(f"{agent_name}: LLM macro analysis completed.")
                show_agent_reasoning(
                    f"LLM分析完成，摘要前100字：{summary[:100]}...",
                    agent_name,
                )

        except Exception as e:
            error_message = f"{agent_name}: execution failed: {e}"
            show_workflow_status(error_message)
            show_agent_reasoning(
                f"Exception during execution: {str(e)}", agent_name
            )
            summary = f"宏观新闻分析失败：{str(e)}"

    # 淇濆瓨鎬荤粨鍒癑SON鏂囦欢 (only if not from cache and successful, or if updating existing)
    if not from_cache:  # Also save if summary was updated, even if initially from cache but e.g. re-analyzed
        show_workflow_status(
            f"{agent_name}: Preparing to save summary to {output_file_path}")

        # Ensure all_summaries is initialized if cache loading failed or file didn't exist
        if not os.path.exists(output_file_path) or 'all_summaries' not in locals():
            all_summaries = {}
            # if file exists but all_summaries wasn't set (e.g. decode error)
            if os.path.exists(output_file_path):
                try:
                    with open(output_file_path, 'r', encoding='utf-8') as f:
                        all_summaries = json.load(f)
                except json.JSONDecodeError:
                    all_summaries = {}  # If still error, start fresh

        os.makedirs(os.path.dirname(output_file_path),
                    exist_ok=True)  # Ensure directory exists

        current_summary_details = {
            "summary_content": summary,
            "retrieved_news_count": retrieved_news_count,
            "last_updated": datetime.now().isoformat(),
            "analysis_date": today_str  # 璁板綍瀹為檯鍒嗘瀽鐨勬棩鏈?
        }
        all_summaries[month_str] = current_summary_details

        try:
            with open(output_file_path, 'w', encoding='utf-8') as f:
                json.dump(all_summaries, f, ensure_ascii=False, indent=4)
            show_workflow_status(
                f"{agent_name}: 瀹忚鏂伴椈鎬荤粨宸蹭繚瀛樺埌: {output_file_path}")
        except Exception as e:
            show_workflow_status(f"{agent_name}: 淇濆瓨瀹忚鏂伴椈鎬荤粨鏂囦欢澶辫触: {e}")
            show_agent_reasoning(
                f"Failed to save summary to {output_file_path}: {str(e)}", agent_name)

    show_workflow_status(f"{agent_name}: Execution finished.")

    new_message_content = f"宏观新闻代理分析（{month_str}，from_cache={from_cache}）：\\n{summary}"
    new_message = HumanMessage(content=new_message_content, name=agent_name)

    agent_details_for_metadata = {
        "summary_generated_on": month_str,
        "analysis_period": "monthly",  # 鏂板瀛楁琛ㄧず鍒嗘瀽鍛ㄦ湡
        "news_count_for_summary": retrieved_news_count,
        "llm_summary_preview": summary[:150] + "..." if len(summary) > 150 else summary,
        "loaded_from_cache": from_cache
    }
    macro_news_payload = {
        "agent_type": "llm",
        "analysis_domain": "macro_market_news",
        "signal": "neutral",
        "confidence": "60%",
        "news_count": retrieved_news_count,
        "summary": summary,
        "loaded_from_cache": from_cache,
        "analysis_period": "monthly",
        "summary_generated_on": month_str,
        "backtest_mode": False,
    }
    updated_data = dict(state["data"])
    agent_outputs = _ensure_agent_outputs(updated_data)
    agent_outputs["macro_news_agent"] = macro_news_payload
    # logger.info(f"--- DEBUG: macro_news_agent COMPLETED ---")
    # logger.info(
    # f"--- DEBUG: macro_news_agent RETURN messages: {[msg.name for msg in [new_message]]} ---")
    return {
        "messages": [new_message],
        "data": {
            **updated_data,
            "macro_news_analysis_result": summary,
            "macro_news_analysis": macro_news_payload,
        },
        "metadata": {
            **state["metadata"],
            f"{agent_name}_details": agent_details_for_metadata
        }
    }


