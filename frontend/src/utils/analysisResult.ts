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
  'market_wide_news_summary(沪深300指数)': 'macro_news',
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
  macro_news: 'macro_news',
  researcher_bull: 'researcher_bull',
  researcher_bear: 'researcher_bear',
  portfolio_management: 'portfolio_manager',
  portfolio_manager: 'portfolio_manager',
  market_data: 'market_data',
  debate_room: 'debate_room',
};

function getDefaultReasoning(agentName: string): string {
  const reasoningMap: Record<string, string> = {
    technical_analysis: 'Relative valuation is based on PB percentile and current PB level.',
    relative_valuation_analysis: 'Relative valuation is based on PB percentile and current PB level.',
    fundamental_analysis: 'Fundamental analysis evaluates company quality and financial health.',
    sentiment_analysis: 'Sentiment analysis evaluates recent news and market mood.',
    valuation_analysis: 'Valuation analysis compares market price and intrinsic value signals.',
    risk_management: 'Risk management evaluates volatility, drawdown, and position limits.',
    selected_stock_macro_analysis: 'Macro analysis evaluates policy and business-cycle impact.',
  };

  return reasoningMap[agentName] || `${agentName} professional analysis result`;
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
