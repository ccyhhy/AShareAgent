import { normalizeAnalysisPayload } from './analysisResult';
import {
  buildDcfDefaultsFromAnalysis,
  formatCurrency,
  formatPercent,
  getMarginTone,
} from './dcfView';

export interface ReportModule {
  key: string;
  title: string;
  tone: 'bullish' | 'bearish' | 'neutral' | 'warning';
  statusLabel: string;
  summary: string;
  bullets: string[];
}

export interface ReportAgentCard {
  key: string;
  label: string;
  tone: 'bullish' | 'bearish' | 'neutral';
  confidenceText: string;
  summary: string;
}

export interface ReportDecisionFact {
  label: string;
  value: string;
  hint: string;
}

export interface ReportDashboard {
  ticker: string;
  actionLabel: string;
  actionTone: 'bullish' | 'bearish' | 'neutral';
  confidenceText: string;
  heroReason: string;
  dataIntegrityLabel: string;
  decisionFacts: ReportDecisionFact[];
  keyEvidence: string[];
  limitationPoints: string[];
  supportPoints: string[];
  concernPoints: string[];
  balanceSummary: string;
  riskSummary: string;
  reliabilitySummary: string;
  dataSourceLines: string[];
  modules: ReportModule[];
  agentCards: ReportAgentCard[];
  dcfHeadline: string;
  dcfAssumptionChips: Array<{ label: string; value: string; note: string }>;
}

const AGENT_LABELS: Record<string, string> = {
  market_data: '数据层',
  technicals: '相对估值',
  fundamentals: '基本面',
  sentiment: '情绪面',
  valuation: 'DCF估值',
  macro_news_agent: '宏观新闻',
  macro_news: '宏观新闻',
  researcher_bull: '多头研究员',
  researcher_bear: '空头研究员',
  debate_room: '多空辩论',
  risk_manager: '风险管理',
  risk_management: '风险管理',
  macro_analyst: '宏观分析师',
  portfolio_manager: '组合经理',
  portfolio_management: '组合经理',
  policy_impact: '政策影响',
  liquidity: '流动性评估',
};

const toText = (value: unknown, fallback = ''): string => {
  if (value == null) {
    return fallback;
  }
  if (typeof value === 'string') {
    const text = value.trim();
    return text || fallback;
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  if (Array.isArray(value)) {
    const items = value.map((item) => toText(item)).filter(Boolean);
    return items.length > 0 ? items.join('；') : fallback;
  }
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>;
    for (const key of ['summary', 'reasoning', 'details', 'analysis', 'conclusion']) {
      const preferred = toText(record[key]);
      if (preferred) {
        return preferred;
      }
    }
    return Object.entries(record)
      .slice(0, 4)
      .map(([key, item]) => `${key}: ${toText(item)}`)
      .filter(Boolean)
      .join('；');
  }
  return String(value);
};

const toTone = (value: unknown): 'bullish' | 'bearish' | 'neutral' => {
  const text = String(value || '').toLowerCase();
  if (
    text.includes('buy') ||
    text.includes('bull') ||
    text.includes('long') ||
    text.includes('买') ||
    text.includes('增持') ||
    text.includes('偏多')
  ) {
    return 'bullish';
  }
  if (
    text.includes('sell') ||
    text.includes('bear') ||
    text.includes('short') ||
    text.includes('卖') ||
    text.includes('减持') ||
    text.includes('回避') ||
    text.includes('偏空')
  ) {
    return 'bearish';
  }
  return 'neutral';
};

const toActionLabel = (value: unknown): string => {
  const tone = toTone(value);
  if (tone === 'bullish') {
    return '建议买入';
  }
  if (tone === 'bearish') {
    return '建议回避';
  }
  return '建议观望';
};

const toConfidenceText = (value: unknown): string => {
  if (value == null || value === '') {
    return '--';
  }
  if (typeof value === 'number') {
    return value <= 1 ? `${Math.round(value * 100)}%` : `${Math.round(value)}%`;
  }
  if (typeof value === 'string') {
    const parsed = Number.parseFloat(value.replace('%', '').trim());
    if (Number.isFinite(parsed)) {
      return parsed <= 1 ? `${Math.round(parsed * 100)}%` : `${Math.round(parsed)}%`;
    }
    return value;
  }
  return String(value);
};

const toNonNegativeInt = (value: unknown): number => {
  if (value == null) {
    return 0;
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0;
  }
  if (typeof value === 'string') {
    const parsed = Number.parseFloat(value.replace(/[^0-9.-]/g, ''));
    return Number.isFinite(parsed) ? Math.max(0, Math.floor(parsed)) : 0;
  }
  return 0;
};

const pickBulletList = (...values: unknown[]): string[] => {
  const collected: string[] = [];

  values.forEach((value) => {
    if (Array.isArray(value)) {
      value.forEach((item) => {
        const text = toText(item);
        if (text) {
          collected.push(text);
        }
      });
      return;
    }

    const text = toText(value);
    if (!text) {
      return;
    }

    text
      .split(/(?<=[。；!！?？])/)
      .map((item) => item.trim())
      .filter(Boolean)
      .forEach((item) => collected.push(item));
  });

  return Array.from(new Set(collected)).slice(0, 6);
};

const normalizeDataReliability = (marketData: Record<string, any>): string => {
  const missing = Array.isArray(marketData.missing_critical_data)
    ? marketData.missing_critical_data
    : [];

  if (missing.length === 0 && marketData.critical_data_complete) {
    return '关键数据完整，本轮结论可作为正式分析参考。';
  }

  if (missing.length > 0) {
    return `关键数据缺失：${missing.join('、')}。本轮结论应偏保守解读，不应把缺失信息当成看多或看空依据。`;
  }

  return '当前分析存在数据缺口，请结合原始结果谨慎解读。';
};

const DATASET_LABELS: Record<string, string> = {
  financial_metrics: '财务指标',
  financial_statements: '财务报表',
  market_data: '市场行情',
  price_reference: '价格口径',
};

const CACHE_STATUS_LABELS: Record<string, string> = {
  remote_live: '实时拉取',
  fresh_snapshot: '本地快照(新鲜)',
  stale_snapshot: '本地快照(过期回退)',
  offline_fallback: '离线回退',
  offline_derived: '离线推导',
  default_empty: '空数据',
  unknown: '未标注',
};

const normalizeCacheStatusLabel = (value: unknown): string => {
  const key = String(value || '').trim().toLowerCase();
  return CACHE_STATUS_LABELS[key] || (key || '未标注');
};

const buildDataSourceLines = (marketData: Record<string, any>): string[] => {
  const dataSources = marketData.data_sources;
  if (!dataSources || typeof dataSources !== 'object' || Array.isArray(dataSources)) {
    return [];
  }

  return Object.entries(dataSources as Record<string, any>)
    .map(([key, rawValue]) => {
      const row = rawValue && typeof rawValue === 'object' ? (rawValue as Record<string, any>) : {};
      const label = DATASET_LABELS[key] || key;
      const source = toText(row.source, '未标注');
      const asOf = toText(row.as_of, '未标注');
      const cacheStatus = normalizeCacheStatusLabel(row.cache_status);
      return `${label}：${source}｜日期 ${asOf}｜${cacheStatus}`;
    })
    .filter(Boolean);
};

const buildValuationModule = (
  valuation: Record<string, any>,
  technicals: Record<string, any>,
): ReportModule => {
  const assumptions = valuation.assumptions || {};
  const margin = typeof valuation.margin_of_safety === 'number' ? valuation.margin_of_safety : null;
  const isDataInsufficient =
    valuation.data_quality === '数据不足' ||
    (!valuation.intrinsic_value && !valuation.market_cap);

  if (isDataInsufficient) {
    return {
      key: 'valuation',
      title: '估值面',
      tone: 'warning',
      statusLabel: '数据不足',
      summary: '估值证据不足，本轮不应把 DCF 或相对估值作为主要买入依据。',
      bullets: pickBulletList(
        valuation.reasoning,
        technicals.reasoning,
        assumptions.discount_rate != null
          ? `折现率 ${toConfidenceText(assumptions.discount_rate)}，第一阶段增长 ${toConfidenceText(
              assumptions.stage1_growth_rate,
            )}，永续增长 ${toConfidenceText(assumptions.terminal_growth_rate)}`
          : null,
      ),
    };
  }

  return {
    key: 'valuation',
    title: '估值面',
    tone: getMarginTone(margin),
    statusLabel: margin != null && margin > 0.15 ? '存在安全边际' : '估值大致合理',
    summary:
      toText(valuation.reasoning) || 'DCF 与相对估值共同构成估值判断，本轮估值结果可作为决策参考。',
    bullets: pickBulletList(
      `内在价值 ${formatCurrency(Number(valuation.intrinsic_value || 0))}`,
      `当前市值 ${formatCurrency(Number(valuation.market_cap || 0))}`,
      margin != null ? `安全边际 ${formatPercent(margin)}` : null,
      technicals.reasoning,
    ),
  };
};

const buildFundamentalModule = (fundamentals: Record<string, any>): ReportModule => {
  const reasoning = toText(fundamentals.reasoning);
  const hasMissing = reasoning.includes('N/A') || reasoning.includes('暂无');

  return {
    key: 'fundamentals',
    title: '基本面',
    tone: hasMissing ? 'warning' : toTone(fundamentals.signal),
    statusLabel: hasMissing ? '数据不足' : toActionLabel(fundamentals.signal).replace('建议', ''),
    summary: hasMissing
      ? '财务关键指标存在缺口，因此本轮基本面判断只能作为弱证据。'
      : reasoning || '基本面用于判断盈利能力、增长质量与财务稳健性。',
    bullets: pickBulletList(
      fundamentals.reasoning,
      fundamentals.memory_delta?.change_type
        ? `信号变化：${fundamentals.memory_delta.change_type}`
        : null,
    ),
  };
};

const buildSentimentModule = (
  sentiment: Record<string, any>,
  macroNews: Record<string, any>,
  macroAnalyst: Record<string, any>,
): ReportModule => {
  const loadedFromFallback = toText(macroNews.reasoning).includes('未返回有效结果');

  return {
    key: 'sentiment',
    title: '消息与情绪面',
    tone: loadedFromFallback ? 'warning' : toTone(macroAnalyst.signal || sentiment.signal),
    statusLabel: loadedFromFallback ? '证据偏弱' : '可参考',
    summary:
      toText(macroAnalyst.reasoning) ||
      toText(sentiment.reasoning) ||
      '消息与情绪模块用于补充短期催化与市场预期变化。',
    bullets: pickBulletList(sentiment.reasoning, macroNews.reasoning, macroAnalyst.reasoning),
  };
};

const buildRiskModule = (riskManager: Record<string, any>): ReportModule => {
  const riskScore = riskManager.risk_score;
  const tone =
    typeof riskScore === 'number' && riskScore <= 35
      ? 'bullish'
      : typeof riskScore === 'number' && riskScore >= 65
        ? 'bearish'
        : 'neutral';

  return {
    key: 'risk',
    title: '风险面',
    tone,
    statusLabel:
      typeof riskScore === 'number' ? `风险评分 ${riskScore.toFixed(2)}` : '风险待确认',
    summary:
      toText(riskManager.reasoning) || '风险模块用于衡量波动、回撤与仓位约束是否支持当前结论。',
    bullets: pickBulletList(
      riskManager.reasoning,
      riskManager.max_position_size != null
        ? `风控上限金额 ${riskManager.max_position_size}`
        : null,
      riskManager.current_price ? `参考价格 ${riskManager.current_price}` : null,
      riskManager.max_buy_quantity != null ? `可买上限 ${riskManager.max_buy_quantity} 股` : null,
    ),
  };
};

const buildDecisionFacts = (
  decision: Record<string, any>,
  marketData: Record<string, any>,
  riskManager: Record<string, any>,
  actionLabel: string,
  confidenceText: string,
): ReportDecisionFact[] => {
  const quantity = toNonNegativeInt(decision.quantity);
  const maxBuyQty = toNonNegativeInt(riskManager.max_buy_quantity);
  const riskScore = typeof riskManager.risk_score === 'number' ? riskManager.risk_score.toFixed(2) : '--';
  const dataState = marketData.critical_data_complete ? '完整' : '不完整';

  return [
    {
      label: '执行动作',
      value: actionLabel,
      hint: quantity > 0 ? `建议数量 ${quantity} 股` : '本轮建议不新增仓位',
    },
    {
      label: '结论置信度',
      value: confidenceText,
      hint: '综合多智能体输出后的最终置信度',
    },
    {
      label: '风控约束',
      value: `${maxBuyQty} 股`,
      hint: `风险评分 ${riskScore}，需遵守仓位与整手约束`,
    },
    {
      label: '数据状态',
      value: dataState,
      hint: marketData.critical_data_complete
        ? '关键数据齐全，可作为正式分析参考'
        : '关键数据缺口存在，结论应保守解读',
    },
  ];
};

const buildKeyEvidence = (
  supportPoints: string[],
  concernPoints: string[],
  modules: ReportModule[],
  balanceSummary: string,
): string[] => {
  const moduleBullets = modules.flatMap((module) => module.bullets || []);
  return Array.from(
    new Set([...supportPoints, ...moduleBullets, ...concernPoints, balanceSummary].filter(Boolean)),
  ).slice(0, 6);
};

const buildLimitationPoints = (
  marketData: Record<string, any>,
  valuation: Record<string, any>,
  fundamentals: Record<string, any>,
  macroNews: Record<string, any>,
): string[] => {
  const limitations: string[] = [];
  const missingCritical = Array.isArray(marketData.missing_critical_data)
    ? marketData.missing_critical_data
    : [];

  if (missingCritical.length > 0) {
    limitations.push(`关键数据缺失：${missingCritical.join('、')}。`);
  }
  if (valuation.data_quality === '数据不足') {
    limitations.push('DCF 输入不足，本轮估值仅能作为弱证据。');
  }
  if (toText(fundamentals.reasoning).includes('N/A')) {
    limitations.push('基本面关键指标存在 N/A，财务侧判断可靠性下降。');
  }
  if (toText(macroNews.reasoning).includes('未返回有效结果')) {
    limitations.push('宏观新闻模块本轮未返回有效结果，情绪证据偏弱。');
  }

  if (limitations.length === 0) {
    limitations.push('未发现明显结构性缺口，但仍需结合个人风险偏好与交易纪律。');
  }

  return limitations.slice(0, 5);
};

const buildAgentCards = (agentOutputs: Record<string, any>): ReportAgentCard[] =>
  Object.entries(agentOutputs)
    .map(([key, value]) => ({
      key,
      label: AGENT_LABELS[key] || key,
      tone: toTone(value?.signal),
      confidenceText: toConfidenceText(value?.confidence),
      summary: toText(value?.summary ?? value?.reasoning, '本模块已参与本轮结论生成。'),
    }))
    .sort((left, right) => left.label.localeCompare(right.label, 'zh-CN'));

export const buildReportDashboard = (result: any): ReportDashboard => {
  const { analysisData, agentOutputs } = normalizeAnalysisPayload(result);
  const decision = analysisData || result || {};
  const marketData = (agentOutputs.market_data || {}) as Record<string, any>;
  const valuation = (agentOutputs.valuation || {}) as Record<string, any>;
  const technicals = (agentOutputs.technicals || {}) as Record<string, any>;
  const fundamentals = (agentOutputs.fundamentals || {}) as Record<string, any>;
  const sentiment = (agentOutputs.sentiment || {}) as Record<string, any>;
  const macroNews = (agentOutputs.macro_news_agent || agentOutputs.macro_news || {}) as Record<string, any>;
  const macroAnalyst = (agentOutputs.macro_analyst || {}) as Record<string, any>;
  const riskManager = (agentOutputs.risk_manager || agentOutputs.risk_management || {}) as Record<string, any>;
  const bull = (agentOutputs.researcher_bull || {}) as Record<string, any>;
  const bear = (agentOutputs.researcher_bear || {}) as Record<string, any>;
  const debate = (agentOutputs.debate_room || {}) as Record<string, any>;
  const portfolio = (
    agentOutputs.portfolio_manager ||
    agentOutputs.portfolio_management ||
    {}
  ) as Record<string, any>;

  const actionLabel = toActionLabel(decision.action || decision.decision || decision.signal);
  const confidenceText = toConfidenceText(decision.confidence || portfolio.confidence);

  const dcfDefaults = buildDcfDefaultsFromAnalysis(result);
  const dcfAssumptionChips = [
    {
      label: '折现率',
      value: `${dcfDefaults.assumptions.discountRatePct.toFixed(2)}%`,
      note: '反映资金成本与风险要求，越高越保守。',
    },
    {
      label: '第一阶段增长',
      value: `${dcfDefaults.assumptions.stage1GrowthRatePct.toFixed(2)}%`,
      note: `对应前 ${dcfDefaults.assumptions.stage1Years} 年现金流增长假设。`,
    },
    {
      label: '永续增长',
      value: `${dcfDefaults.assumptions.terminalGrowthRatePct.toFixed(2)}%`,
      note: '稳定期长期增长假设，决定终值贡献。',
    },
  ];

  const modules = [
    buildValuationModule(valuation, technicals),
    buildFundamentalModule(fundamentals),
    buildSentimentModule(sentiment, macroNews, macroAnalyst),
    buildRiskModule(riskManager),
  ];

  const supportPoints = pickBulletList(
    bull.thesis_points,
    bull.reasoning,
    typeof valuation.margin_of_safety === 'number' && valuation.margin_of_safety > 0
      ? `DCF 显示安全边际 ${formatPercent(valuation.margin_of_safety)}`
      : null,
  );

  const concernPoints = pickBulletList(
    bear.thesis_points,
    bear.reasoning,
    !marketData.critical_data_complete ? normalizeDataReliability(marketData) : null,
    riskManager.reasoning,
  );

  const balanceSummary = toText(
    portfolio.reasoning || debate.reasoning,
    '系统综合多空观点后，当前更适合保持中性解读。',
  );

  const dataInsufficient = valuation.data_quality === '数据不足' || !marketData.critical_data_complete;
  const dataSourceLines = buildDataSourceLines(marketData);

  return {
    ticker: toText(result?.ticker || decision?.ticker, '--'),
    actionLabel,
    actionTone: toTone(decision.action || decision.decision || decision.signal),
    confidenceText,
    heroReason: toText(
      decision.reasoning || decision.summary || portfolio.reasoning,
      '系统已完成本轮分析，请结合各模块证据理解结论。',
    ),
    dataIntegrityLabel: marketData.critical_data_complete ? '关键数据完整' : '关键数据不完整',
    decisionFacts: buildDecisionFacts(decision, marketData, riskManager, actionLabel, confidenceText),
    keyEvidence: buildKeyEvidence(supportPoints, concernPoints, modules, balanceSummary),
    limitationPoints: buildLimitationPoints(marketData, valuation, fundamentals, macroNews),
    supportPoints,
    concernPoints,
    balanceSummary,
    riskSummary: toText(
      decision.ashare_considerations || decision.risk_summary || riskManager.reasoning,
      '暂未识别到额外风险提示。',
    ),
    reliabilitySummary: normalizeDataReliability(marketData),
    dataSourceLines,
    modules,
    agentCards: buildAgentCards(agentOutputs),
    dcfHeadline: dataInsufficient
      ? '本轮 DCF 不可作为主要依据，因为关键输入不足。'
      : `本轮 DCF 估值结论：${toText(valuation.margin_of_safety_assessment, '估值中性')}。`,
    dcfAssumptionChips,
  };
};
