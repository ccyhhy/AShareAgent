# 14天毕设冲刺指南（最终版 v6）

> 基于 AShareAgent + CS视角创新 + 多维度评价体系 + Codex辅助

---

## 一、项目定位

- **Clone**: https://github.com/1517005260/AShareAgent
- **你的数据**: `E:\codework\A股测试\data\`（60MB全A股离线数据）
- **LLM**: DeepSeek API
- **定位**: 计算机专业毕设，创新点重点放在系统架构、协议设计、RAG与实验方法，不把论文重心放在金融理论堆砌上

---

## 二、三个创新点（CS专业版）

| # | 创新点 | 一句话说明 |
|:---|:---|:---|
| 1 | **异构多智能体架构** | 在 LangGraph 工作流中融合规则引擎、量化模型、统计方法和 LLM 增强分析 |
| 2 | **RAG检索增强** | 引入 ChromaDB 向量数据库，让护城河Agent具备历史分析检索与复用能力 |
| 3 | **多维度消融实验** | 不只比收益率，还系统比较成本、响应、鲁棒性和可解释性 |

---

## 三、与 AShareAgent 实际结构对齐

> [!IMPORTANT]
> 以下内容已经按 `AShareAgent` 真实仓库结构修正。后续实施时，均以这里的真实文件名和目录为准。

- 真实存在的分析Agent文件是：
  - `src/agents/technicals.py`
  - `src/agents/valuation.py`
  - `src/agents/fundamentals.py`
  - `src/agents/sentiment.py`
  - `src/agents/macro_analyst.py`
  - `src/agents/risk_manager.py`
- 原仓库还有：
  - `src/agents/market_data.py`
  - `src/agents/macro_news_agent.py`
  - `src/agents/debate_room.py`
  - `src/agents/researcher_bull.py`
  - `src/agents/researcher_bear.py`
  - `src/agents/portfolio_manager.py`
- 本地离线数据统一放在仓库顶层 `data/`
- `LangGraph` 中的Agent返回值不能直接改成只返回 Pydantic 对象，外层必须继续保持原项目的 state dict 结构

---

## 四、文件改动总表

```text
重点重写Agent（6个）：
  src/agents/technicals.py       → 估值分析Agent         (rule_engine)
  src/agents/valuation.py        → DCF估值Agent          (quantitative_model)
  src/agents/risk_manager.py     → 安全边际/风险Agent     (statistical_model)
  src/agents/fundamentals.py     → 护城河+RAG Agent       (llm_rag)
  src/agents/sentiment.py        → 财报质量Agent          (hybrid_rule_llm)
  src/agents/macro_analyst.py    → 行业周期Agent          (llm)

改Prompt（3个）：
  src/agents/researcher_bull.py   → 价值投资多头视角
  src/agents/researcher_bear.py   → 价值投资空头视角
  src/agents/portfolio_manager.py → 价值投资决策框架

新增模块（4个）：
  src/rag/knowledge_base.py       → RAG知识库（ChromaDB）
  src/common/protocol.py          → 统一通信协议（AgentMessage）
  src/experiments/ablation.py     → 消融实验框架
  src/tools/local_csv_provider.py → 本地CSV数据适配层

重点修改（4个）：
  src/tools/api.py                → 优先走本地CSV，回测时禁外网
  src/agents/market_data.py       → 接入本地CSV数据入口
  frontend/src/components/AnalysisStatus.tsx → 展示异构Agent输出与性能
  frontend/src/services/api.ts    → 增加AgentMessage与性能字段类型

保留但配合使用：
  src/agents/macro_news_agent.py  → 宏观新闻补充
  src/agents/debate_room.py       → 辩论室
  src/backtesting/                → 原有回测系统直接复用
  backend/                        → FastAPI后端
  frontend/                       → React前端
```

---

## 五、14天日程

### Day 1：环境搭建 + 跑通基线

```powershell
cd E:\codework
git clone https://github.com/1517005260/AShareAgent.git
cd AShareAgent

poetry install
cd frontend
npm install
cd ..

copy .env.example .env
# 编辑 .env 填入 DeepSeek API Key

if (!(Test-Path data)) { New-Item -ItemType Directory -Path data | Out-Null }
copy E:\codework\A股测试\data\*.csv data\

poetry run python -m src.main --ticker 600519 --show-reasoning
```

**Day 1 目标：**
- 先确认原项目在你的机器上能跑
- 记录 Python / Poetry / Node / npm 版本
- 截图原始系统运行结果，后续论文里做“改造前 vs 改造后”对比

**论文素材：**
- 运行环境表
- 原项目分析结果截图
- 前端初始界面截图

---

### Day 2-3：先接本地CSV，再重写3个非LLM Agent

> [!IMPORTANT]
> 这两天不要先改 Prompt。先把“离线数据入口”打通，否则后续所有异构Agent都还会偷偷走原始外部 API。

#### 第一步：创建本地CSV适配层

给 Codex：

```text
创建 src/tools/local_csv_provider.py，作为 AShareAgent 的离线数据适配层。

要求：
1. 所有数据默认从 data/ 目录读取
2. 统一提供以下能力：
   - get_price_history(symbol, start_date, end_date)
   - get_pb_history(symbol, start_date=None, end_date=None)
   - get_listing_info(symbol)
   - get_trading_calendar(start_date=None, end_date=None)
3. 自动做列名标准化、日期过滤、股票代码格式统一
4. 对缺失数据返回空DataFrame或None，不直接抛未处理异常
5. 给读取结果加基础缓存，避免回测时重复读盘
```

#### 第二步：修改 `src/tools/api.py`

给 Codex：

```text
修改 src/tools/api.py，使其在 AShareAgent 中优先走本地CSV数据。

要求：
1. get_price_history 优先调用 local_csv_provider
2. 回测模式下禁止外部网络请求
3. 如果本地数据不存在，再按显式开关决定是否允许回退到原API
4. 保持原函数签名不变，避免影响已有调用链
5. 在日志中明确记录“本次数据来自本地CSV还是远程API”
```

#### Agent 1：估值分析Agent（替换 `src/agents/technicals.py`）

给 Codex：

```text
重写 src/agents/technicals.py 为估值分析Agent。

要求：
1. 不用LLM，agent_type="rule_engine"
2. 从 data/pb.csv 读取PB历史，计算近5年PB百分位
3. PB百分位评分：
   - <20% → 90分
   - <40% → 70分
   - <60% → 50分
   - >60% → 30分
   - >80% → 10分
4. 保持 technical_analyst_agent 函数签名不变
5. 外层仍返回原项目 LangGraph state dict
6. 标准化结果写入 state["data"]["agent_outputs"]["technicals"]
7. 代码顶部注明“规则引擎型异构Agent”
```

#### Agent 2：DCF估值Agent（替换 `src/agents/valuation.py`）

给 Codex：

```text
重写 src/agents/valuation.py 为DCF自由现金流折现Agent。

要求：
1. 不用LLM，agent_type="quantitative_model"
2. 两阶段DCF：
   - 第一阶段5年增长期，增长率=历史复合增长率，上限20%
   - 第二阶段永续增长率3%
   - 折现率10%
3. 输出内在价值、安全边际、安全边际评分
4. 保持 valuation_agent 函数签名与 LangGraph state 返回结构不变
5. 标准化结果写入 state["data"]["agent_outputs"]["valuation"]
6. 数学计算过程写清注释，论文第4章可直接引用
```

#### Agent 3：安全边际/风险Agent（替换 `src/agents/risk_manager.py`）

给 Codex：

```text
重写 src/agents/risk_manager.py 为安全边际/风险评估Agent。

要求：
1. 不用LLM，agent_type="statistical_model"
2. 从价格历史中计算：
   - 年化波动率
   - 最大回撤
   - VaR(95%)
   - 夏普比率
3. 根据风险水平输出：
   - risk_score
   - margin_of_safety_score
   - max_position 建议
4. 保持 risk_management_agent 函数签名不变
5. 外层继续返回原项目 state dict
6. 标准化结果写入 state["data"]["agent_outputs"]["risk_manager"]
7. 可参考 E:\codework\A股测试\src\core\stats.py 的统计方法
```

**论文素材：**
- 本地CSV适配层代码截图
- 3个非LLM Agent代码截图
- “不调用LLM”的证明截图
- 运行耗时记录

---

### Day 4-5：重写3个LLM Agent + 接入RAG + 改3个Prompt

#### Agent 4：护城河+RAG Agent（替换 `src/agents/fundamentals.py`）

**这是创新点2的核心。**

给 Codex：

```text
重写 src/agents/fundamentals.py 为护城河+RAG Agent。

要求：
1. agent_type="llm_rag"
2. 分析前先查 ChromaDB：
   - search_by_stock(stock_code, top_k=5)
   - search_by_industry(industry, top_k=3)
3. 把检索到的历史分析拼进Prompt，再调用DeepSeek
4. 输出维度：
   - 品牌壁垒
   - 成本优势
   - 转换成本
   - 网络效应
   - 政策壁垒
5. 输出JSON：
   {"moat_rating":"wide/narrow/none","score":0-100,"analysis":"...","retrieved_refs":[...]}
6. 分析完成后自动把结果写回知识库
7. JSON解析必须 try-except + 3次重试 + 默认兜底
8. 回测时按季度频率运行
9. 保持 fundamentals_agent 函数签名与 LangGraph state 返回结构不变
10. 标准化结果写入 state["data"]["agent_outputs"]["fundamentals"]
```

#### 同时创建 `src/rag/knowledge_base.py`

给 Codex：

```text
创建 src/rag/knowledge_base.py，实现 ChromaDB 知识库封装。

要求：
1. 使用 ChromaDB 本地持久化
2. 提供：
   - add_analysis(stock_code, analysis_text, metadata)
   - search_similar(query, top_k=3)
   - search_by_stock(stock_code, top_k=5)
   - search_by_industry(industry, top_k=3)
3. Embedding 使用 sentence-transformers 中文模型
4. 失败时优雅降级，不能因为知识库异常导致主流程崩掉
```

#### Agent 5：财报质量Agent（替换 `src/agents/sentiment.py`）

给 Codex：

```text
重写 src/agents/sentiment.py 为财报质量Agent。

要求：
1. agent_type="hybrid_rule_llm"
2. 第一步做规则红旗检测：
   - 应收账款增速 > 营收增速 × 1.5
   - 经营现金流 < 净利润 × 0.5
   - 商誉 / 净资产 > 30%
   - 存货周转率持续下降
3. 第二步把红旗列表交给LLM解释
4. 即使LLM失败，也必须至少输出红旗数量和规则结果
5. JSON容错 + 回测季度频率
6. 保持 sentiment_agent 函数签名与 state 返回结构不变
7. 标准化结果写入 state["data"]["agent_outputs"]["sentiment"]
```

#### Agent 6：行业周期Agent（替换 `src/agents/macro_analyst.py`）

给 Codex：

```text
重写 src/agents/macro_analyst.py 为行业周期Agent。

要求：
1. agent_type="llm"
2. 用行业周期视角分析：成长期 / 成熟期 / 衰退期
3. 输出行业景气判断、政策敏感度、周期风险
4. JSON容错：try-except + 3次重试 + 默认hold
5. 保持 macro_analyst_agent 函数签名与 state 返回结构不变
6. 标准化结果写入 state["data"]["agent_outputs"]["macro_analyst"]
```

#### 修改3个Prompt

- `src/agents/researcher_bull.py`
  - 改成“从安全边际、护城河、内在价值角度论证买入理由”
- `src/agents/researcher_bear.py`
  - 改成“从估值泡沫、财报风险、行业下行角度论证不买理由”
- `src/agents/portfolio_manager.py`
  - 改成“格雷厄姆式价值投资组合经理，以安全边际和风险暴露为核心”

**论文素材：**
- 各Agent系统Prompt
- RAG检索日志截图
- 护城河Agent“检索前/检索后”样例
- 规则Agent与LLM Agent耗时对比

---

### Day 6：统一通信协议 + 联调

#### 创建 `src/common/protocol.py`

给 Codex：

```text
创建 src/common/protocol.py，定义异构Agent统一通信协议 AgentMessage。

要求：
1. 使用 Pydantic BaseModel
2. 字段包含：
   - agent_id: str
   - agent_type: str
   - signal: str
   - confidence: float
   - reasoning: str
   - structured_data: dict
   - execution_time_ms: float
   - token_usage: int
   - timestamp: datetime
3. 注意：
   - 不能让 LangGraph 节点直接只返回 AgentMessage
   - 外层必须继续返回 {"messages": ..., "data": ..., "metadata": ...}
4. 每个Agent把标准化 AgentMessage 写入：
   state["data"]["agent_outputs"][agent_name] = agent_message.model_dump()
5. portfolio_manager 和前端统一从 agent_outputs 读取
```

#### 联调测试5只股票

```powershell
poetry run python -m src.main --ticker 600519 --show-reasoning
poetry run python -m src.main --ticker 000333 --show-reasoning
poetry run python -m src.main --ticker 601398 --show-reasoning
poetry run python -m src.main --ticker 002415 --show-reasoning
poetry run python -m src.main --ticker 601857 --show-reasoning
```

**论文素材：**
- AgentMessage协议图
- 统一输出样例
- 5只股票完整分析截图

---

### Day 7-8：前端微调 + 消融实验框架

#### 前端微调

给 Codex：

```text
修改 AShareAgent 前端，围绕异构Agent展示做最小但关键的可视化增强。

重点文件：
1. frontend/src/App.tsx
   - 标题改为“基于异构多智能体的A股价值投资分析系统”
2. frontend/src/components/AnalysisStatus.tsx
   - 展示 agent_outputs
   - 显示每个Agent的 agent_type、signal、confidence、execution_time_ms、token_usage
3. frontend/src/components/AgentDashboard.tsx
   - 把 agent_type 标签颜色映射成异构类别
4. frontend/src/services/api.ts
   - 新增 AgentMessage 类型定义
   - 为分析结果补充 agent_outputs 字段类型
```

#### 消融实验框架（创新点3）

给 Codex：

```text
创建 src/experiments/ablation.py，实现自动化消融实验框架。

要求：
1. 复用 src/backtesting/ 现有回测能力
2. 支持以下实验配置：
   - full_heterogeneous
   - full_homogeneous
   - no_rule_agents
   - no_llm_agents
   - single_agent_removed_x
3. 评价6个维度：
   - 年化收益
   - 夏普比率
   - Token消耗总量
   - 平均响应时间
   - API故障可用率
   - 可解释性得分
4. 输出CSV、Markdown报告和图表
```

**论文素材：**
- 前端异构展示截图
- 消融实验框架代码截图
- 实验配置说明图

---

### Day 9-10：跑实验 + 收集核心数据

```powershell
poetry run python -m src.experiments.ablation `
  --stocks 600519,000858,000333,601398,600036,002415,300750,603288,600028,601857 `
  --start 2023-01-01 `
  --end 2025-12-31
```

#### 论文核心数据

**表5-1：异构 vs 同构 多维度对比**

| 指标 | 异构系统 | 同构基线 | 差异 | 谁赢 |
|:---|:---|:---|:---|:---|
| 平均年化收益 | XX% | XX% | | 看结果 |
| 平均夏普比率 | XX | XX | | 看结果 |
| 单次Token消耗 | XX | XX | -XX% | 异构 |
| 平均响应时间 | XX秒 | XX秒 | -XX% | 异构 |
| API故障可用率 | XX% | XX% | | 看结果 |
| 可解释性得分 | XX | XX | | 异构 |

> [!IMPORTANT]
> 论文结论不要只押宝收益率。你的主结论应该写成：
> “异构架构在综合评价体系下优于同构架构，尤其在成本、响应速度、鲁棒性和可解释性方面更有优势。”

**表5-2：逐一消融分析**

| 去掉的Agent | 收益变化 | 夏普变化 | 响应变化 | 说明 |
|:---|:---|:---|:---|:---|
| -估值Agent | XX% | XX | XX | 说明其贡献 |
| -DCF Agent | XX% | XX | XX | |
| -风险Agent | XX% | XX | XX | |
| -护城河+RAG Agent | XX% | XX | XX | |
| -财报质量Agent | XX% | XX | XX | |
| -行业周期Agent | XX% | XX | XX | |

**表5-3：与传统策略对比**

用你已有的 PB 回测系统跑同期数据，对比：
- 本系统
- Buy & Hold
- PB价值策略
- 均线策略

---

### Day 11-12：论文撰写

```text
第1章 绪论（5页）
  1.1 研究背景
  1.2 国内外现状
  1.3 研究内容与贡献

第2章 相关技术（8页）
  2.1 多智能体系统
  2.2 大语言模型
  2.3 检索增强生成（RAG）
  2.4 LangGraph工作流编排
  2.5 价值投资理论（简述，不喧宾夺主）

第3章 系统设计（14页）核心
  3.1 系统总体架构
  3.2 异构智能体设计
      3.2.1 规则引擎型（technicals.py）
      3.2.2 量化模型型（valuation.py）
      3.2.3 统计模型型（risk_manager.py）
      3.2.4 LLM+RAG型（fundamentals.py）
      3.2.5 混合型（sentiment.py）
      3.2.6 LLM型（macro_analyst.py）
  3.3 统一通信协议设计（AgentMessage）
  3.4 本地CSV数据适配设计
  3.5 异构时间频率策略
  3.6 多智能体协作机制
  3.7 容错与缓存机制

第4章 系统实现（10页）
  4.1 开发环境
  4.2 本地CSV数据层实现
  4.3 各Agent实现
  4.4 RAG模块实现
  4.5 前后端联动实现
  4.6 系统运行展示

第5章 实验与分析（10页）
  5.1 实验方案设计
  5.2 多维度评价指标体系
  5.3 异构vs同构实验
  5.4 逐一消融分析
  5.5 与传统策略对比
  5.6 典型案例分析

第6章 总结与展望（3页）
  6.1 主要工作与创新点
  6.2 不足
  6.3 展望

附录A：各Agent提示词模板
附录B：AgentMessage协议定义
附录C：本地CSV适配层关键代码
```

---

### Day 13：答辩PPT

**必背3句话：**

**1. 异构含义**
> “本系统不是给同一个LLM分配不同角色，而是在 LangGraph 工作流中真正融合了规则引擎、量化模型、统计方法和 LLM 增强分析，并通过统一协议协作。”

**2. RAG贡献**
> “我们为护城河分析Agent引入了 ChromaDB 知识库，使其能够检索历史分析结果，在新一轮分析中复用历史上下文，从而提升一致性和可追溯性。”

**3. 实验方法**
> “我们采用多维度消融实验，不仅比较收益率，还比较Token成本、响应速度、系统鲁棒性和可解释性，因此更适合作为计算机系统设计类毕业设计的评价方法。”

---

### Day 14：缓冲

- [ ] 系统完整演示
- [ ] 论文排版
- [ ] PPT排练
- [ ] 截图清晰

---

## 六、工作量分布（回答“你到底做了什么”）

```text
复用原项目（35%）：
  - FastAPI后端
  - React前端
  - LangGraph工作流
  - 原有回测框架

结构化改造（25%）：
  - 6个核心Agent重构
  - 3个Prompt改造
  - 本地CSV数据接入
  - 协议兼容改造

原创工作（40%）：
  - RAG知识库模块（ChromaDB）
  - AgentMessage统一通信协议
  - 消融实验自动化框架
  - 多维度评价指标体系
  - 前端异构可视化与性能展示
```

---

## 七、Codex项目级指令

```text
这是计算机专业毕业设计“基于异构多智能体的A股价值投资分析系统”。
基础代码：https://github.com/1517005260/AShareAgent
技术栈：FastAPI + React + LangGraph + ChromaDB + DeepSeek API

核心要求：
1. 真实仓库文件名以 AShareAgent 当前结构为准：
   - technicals.py
   - valuation.py
   - risk_manager.py
   - fundamentals.py
   - sentiment.py
   - macro_analyst.py
2. 本地离线数据统一放在 data/
3. 优先通过 src/tools/local_csv_provider.py + src/tools/api.py 读取本地CSV
4. 回测时禁止外部网络请求
5. LLM型Agent回测中按季度运行
6. 所有LLM JSON输出必须 try-except + 3次重试 + 默认HOLD兜底
7. 统一协议使用 AgentMessage，但 LangGraph 节点外层返回值仍保持原 state dict 结构
8. 每个Agent都要把标准化结果写入 state["data"]["agent_outputs"]
9. 每个Agent必须记录：
   - agent_type
   - signal
   - confidence
   - execution_time_ms
   - token_usage

异构Agent类型：
- rule_engine: 纯规则，不调LLM
- quantitative_model: 纯数学公式
- statistical_model: 纯统计风险评估
- llm_rag: LLM + ChromaDB 检索
- hybrid_rule_llm: 先规则后LLM
- llm: 纯LLM
```
