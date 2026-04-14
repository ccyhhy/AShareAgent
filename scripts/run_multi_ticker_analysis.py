import os
import uuid
import json
import time
from datetime import datetime, timedelta
from src.core.engine.main import run_hedge_fund

def run_multi_ticker_analysis(tickers=None):
    if tickers is None:
        # 建议的 5 只测试标的 (贵州茅台, 美的集团, 工商银行, 海康威视, 中国石油)
        tickers = ["600519", "000333", "601398", "002415", "601857"]

    print(f"🚀 开始多股票批量联调 - 目标数量: {len(tickers)}")
    
    results = {}
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 默认时间范围：最近一年
    end_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    portfolio = {"cash": 100000.0, "stock": 0}

    for ticker in tickers:
        print(f"\n[{ticker}] 正在启动全流程分析...")
        start_time = time.time()
        run_id = str(uuid.uuid4())
        
        try:
            # 运行多智能体工作流
            decision = run_hedge_fund(
                run_id=run_id,
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                portfolio=portfolio,
                show_reasoning=True
            )
            
            elapsed = time.time() - start_time
            print(f"[{ticker}] 分析完成! 耗时: {elapsed:.2f}s, 决策结果: {decision}")
            
            results[ticker] = {
                "run_id": run_id,
                "elapsed": elapsed,
                "decision": decision,
                "status": "success"
            }
        except Exception as e:
            print(f"[{ticker}] 分析发生异常: {str(e)}")
            results[ticker] = {
                "status": "error",
                "error": str(e)
            }

    # 保存批量运行结果
    output_path = f"artifacts/multi_ticker_run_{timestamp}.json"
    os.makedirs("artifacts", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 批量分析任务结束。详细日志已保存至: {output_path}")
    return results

if __name__ == "__main__":
    run_multi_ticker_analysis()
