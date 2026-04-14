const SIGNAL_NAME_TO_OUTPUT_KEY: Record<string, string> = {
  technical_analysis: 'technicals',
  relative_valuation_analysis: 'technicals',
  relative_valuation: 'technicals',
  relative_valuation_agent: 'technicals',
  fundamental_analysis: 'fundamentals',
  sentiment_analysis: 'sentiment',
  valuation_analysis: 'valuation',
  risk_management: 'risk_manager',
  selected_stock_macro_analysis: 'macro_analyst',
  macro_news_agent: 'macro_news_agent',
  market_wide_news_summary: 'macro_news_agent',
  ashare_policy_impact: 'policy_impact',
  liquidity_assessment: 'liquidity',
  bull_researcher: 'researcher_bull',
  bear_researcher: 'researcher_bear',
};

const OUTPUT_KEY_ALIASES: Record<string, string> = {
  technical_analyst: 'technicals',
  technicals: 'technicals',
  relative_valuation: 'technicals',
  relative_valuation_agent: 'technicals',
  relative_valuation_analysis: 'technicals',
  fundamentals: 'fundamentals',
  sentiment: 'sentiment',
  valuation: 'valuation',
  risk_management: 'risk_manager',
  risk_manager: 'risk_manager',
  macro_analyst: 'macro_analyst',
  macro_news_agent: 'macro_news_agent',
  macro_news: 'macro_news_agent',
  researcher_bull: 'researcher_bull',
  researcher_bear: 'researcher_bear',
  portfolio_management: 'portfolio_manager',
  portfolio_manager: 'portfolio_manager',
  market_data: 'market_data',
  debate_room: 'debate_room',
};

function getDefaultReasoning(agentName: string): string {
  const reasoningMap: Record<string, string> = {
    technical_analysis: '基于 PB 分位数和当前 PB 水平的相对估值。',
    relative_valuation_analysis: '基于 PB 分位数和当前 PB 水平的相对估值。',
    fundamental_analysis: '基本面分析评估公司质量与财务健康状况。',
    sentiment_analysis: '情绪分析评估近期新闻与市场情绪。',
    valuation_analysis: '估值分析对比市场价格与内在价值信号。',
    risk_management: '风险管理评估波动率、最大回撤与仓位限制。',
    selected_stock_macro_analysis: '宏观分析评估政策与经济周期影响。',
  };

  return reasoningMap[agentName] || `${agentName} 专业分析结果`;
}

function buildAgentOutputsFromSignals(signals: Array<Record<string, any>>): Record<string, any> {
  const agentOutputs: Record<string, any> = {};

  signals.forEach((signal) => {
    const rawName = signal.agent_name || signal.agent;
    if (!rawName) {
      return;
    }

    const outputKey = SIGNAL_NAME_TO_OUTPUT_KEY[rawName] || rawName;
    agentOutputs[outputKey] = {
      signal: signal.signal,
      confidence: signal.confidence,
      reasoning: signal.reasoning || getDefaultReasoning(rawName),
      ...(signal.details && { details: signal.details }),
      ...(signal.metrics && { metrics: signal.metrics }),
      ...(signal.risk_score && { risk_score: signal.risk_score }),
      ...(signal.trading_action && { trading_action: signal.trading_action }),
      ...(signal.max_position_size && { max_position_size: signal.max_position_size }),
      ...(signal.risk_metrics && { risk_metrics: signal.risk_metrics }),
      ...(rawName === 'bull_researcher' && { perspective: 'bull' }),
      ...(rawName === 'bear_researcher' && { perspective: 'bear' }),
    };
  });

  return agentOutputs;
}

function normalizeOutputKeys(agentOutputs: Record<string, any> | null | undefined): Record<string, any> {
  if (!agentOutputs || typeof agentOutputs !== 'object') {
    return {};
  }

  const normalized: Record<string, any> = {};
  Object.entries(agentOutputs).forEach(([key, value]) => {
    const normalizedKey = OUTPUT_KEY_ALIASES[key] || key;
    normalized[normalizedKey] = value;
  });

  return normalized;
}

function unwrapResult(data: any): any {
  if (data?.result?.result) {
    return data.result.result;
  }

  if (data?.result) {
    return data.result;
  }

  return data;
}

export function normalizeAnalysisPayload(data: any): {
  analysisData: any;
  agentOutputs: Record<string, any>;
} {
  const root = unwrapResult(data);
  const analysisData = root?.final_decision || (root?.action ? root : data?.final_decision || data);

  let agentOutputs =
    root?.agent_outputs ||
    root?.agent_results ||
    data?.agent_outputs ||
    data?.agent_results ||
    null;

  if ((!agentOutputs || Object.keys(agentOutputs).length === 0) && Array.isArray(analysisData?.agent_signals)) {
    agentOutputs = buildAgentOutputsFromSignals(analysisData.agent_signals);
  }

  return {
    analysisData,
    agentOutputs: normalizeOutputKeys(agentOutputs),
  };
}
