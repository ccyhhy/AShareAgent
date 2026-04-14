import os
import uuid
import json
import time
import pandas as pd
from datetime import datetime, timedelta
from src.core.engine.main import run_hedge_fund
from src.experiments.ablation import build_ablation_config

def run_ablation_experiment(ticker="600519", profiles=None):
    if profiles is None:
        profiles = [
            {"name": "Full Heterogeneous", "config": build_ablation_config(profile="full_heterogeneous")},
            {"name": "No LLM Agents", "config": build_ablation_config(profile="no_llm_agents")},
            {"name": "No Rule Agents", "config": build_ablation_config(profile="no_rule_agents")},
            {"name": "Single Agent (Sentiment Only)", "config": build_ablation_config(profile="remove_single_agent_x", remove_single_agent="fundamentals")},
        ]

    results = []
    end_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    portfolio = {"cash": 100000.0, "stock": 0}

    print(f"开始消融实验 - 股票: {ticker}, 时间范围: {start_date} 至 {end_date}")
    
    for p in profiles:
        print(f"\n正在运行配置: {p['name']}...")
        start_time = time.time()
        run_id = str(uuid.uuid4())
        
        try:
            # 执行工作流
            # 注意：这里我们捕获控制台输出或直接从返回结果分析指标
            output = run_hedge_fund(
                run_id=run_id,
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                portfolio=portfolio,
                ablation_config=p['config']
            )
            
            elapsed = time.time() - start_time
            print(f"完成! 耗时: {elapsed:.2f}s")
            
            results.append({
                "profile_name": p['name'],
                "run_id": run_id,
                "elapsed_time": elapsed,
                "status": "success",
                "output_decision": output
            })
        except Exception as e:
            print(f"配置 {p['name']} 运行失败: {str(e)}")
            results.append({
                "profile_name": p['name'],
                "run_id": run_id,
                "status": "failed",
                "error": str(e)
            })

    # 保存结果
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"artifacts/ablation_results_{timestamp}.json"
    os.makedirs("artifacts", exist_ok=True)
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    # 导出 CSV 概览
    df = pd.DataFrame(results)
    df.to_csv(f"artifacts/ablation_summary_{timestamp}.csv", index=False)
    
    print(f"\n消融实验结束。结果已保存至 {output_file}")
    return results

if __name__ == "__main__":
    run_ablation_experiment()
