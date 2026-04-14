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

export interface ReportDashboard {
  ticker: string;
  actionLabel: string;
  actionTone: 'bullish' | 'bearish' | 'neutral';
  confidenceText: string;
  heroReason: string;
  dataIntegrityLabel: string;
  supportPoints: string[];
  concernPoints: string[];
  balanceSummary: string;
  riskSummary: string;
  reliabilitySummary: string;
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
  valuation: 'DCF 估值',
  macro_news_agent: '宏观新闻',
  researcher_bull: '多头研究员',
  researcher_bear: '空头研究员',
  debate_room: '多空辩论',
  risk_manager: '风险管理',
  macro_analyst: '宏观分析师',
  portfolio_manager: '组合经理',
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
  if (text.includes('buy') || text.includes('bull')) {
    return 'bullish';
  }
  if (text.includes('sell') || text.includes('bear')) {
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

  return Array.from(new Set(collected)).slice(0, 4);
};

const normalizeDataReliability = (marketData: Record<string, any>): string => {
  const missing = Array.isArray(marketData.missing_critical_data)
    ? marketData.missing_critical_data
    : [];

  if (missing.length === 0 && marketData.critical_data_complete) {
    return '关键数据完整，本轮结论可以作为正式分析参考。';
  }

  if (missing.length > 0) {
    return `关键数据缺失：${missing.join('、')}。因此本轮结论应偏保守解读，尤其不能把缺失数据误当成看多或看空信号。`;
  }

  return '当前分析存在数据缺口，请结合原始结果谨慎解读。';
};

const buildValuationModule = (valuation: Record<string, any>, technicals: Record<string, any>): ReportModule => {
  const assumptions = valuation.assumptions || {};
  const margin = typeof valuation.margin_of_safety === 'number' ? valuation.margin_of_safety : null;

  if (valuation.data_quality === '数据不足') {
    return {
      key: 'valuation',
      title: '估值面',
      tone: 'warning',
      statusLabel: '数据不足',
      summary: '估值证据不足，本轮不能把 DCF 或相对估值作为主要买入依据。',
      bullets: pickBulletList(
        valuation.reasoning,
        technicals.reasoning,
        `折现率 ${toConfidenceText(assumptions.discount_rate)}，第一阶段增长 ${toConfidenceText(
          assumptions.stage1_growth_rate,
        )}，永续增长 ${toConfidenceText(assumptions.terminal_growth_rate)}`,
      ),
    };
  }

  return {
    key: 'valuation',
    title: '估值面',
    tone: getMarginTone(margin),
    statusLabel: margin != null && margin > 0.15 ? '存在安全边际' : '估值大致合理',
    summary:
      toText(valuation.reasoning) ||
      'DCF 与相对估值共同构成估值判断，本轮估值结果可作为决策参考。',
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
      : reasoning || '基本面主要用于判断盈利能力、增长质量与财务稳健性。',
    bullets: pickBulletList(
      fundamentals.reasoning,
      fundamentals.memory_delta?.change_type ? `信号变化：${fundamentals.memory_delta.change_type}` : null,
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
      '消息与情绪模块主要用于补充短期催化和市场预期变化。',
    bullets: pickBulletList(
      sentiment.reasoning,
      macroNews.reasoning,
      macroAnalyst.reasoning,
    ),
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
      typeof riskScore === 'number'
        ? `风险评分 ${riskScore.toFixed(2)}`
        : '风险待确认',
    summary:
      toText(riskManager.reasoning) ||
      '风险模块用于衡量波动、回撤和仓位约束是否支持当前结论。',
    bullets: pickBulletList(
      riskManager.reasoning,
      riskManager.max_position_size ? `风控上限金额 ${riskManager.max_position_size}` : null,
      riskManager.current_price ? `参考价格 ${riskManager.current_price}` : null,
    ),
  };
};

const buildAgentCards = (agentOutputs: Record<string, any>): ReportAgentCard[] => {
  return Object.entries(agentOutputs)
    .map(([key, value]) => ({
      key,
      label: AGENT_LABELS[key] || key,
      tone: toTone(value?.signal),
      confidenceText: toConfidenceText(value?.confidence),
      summary: toText(value?.summary ?? value?.reasoning, '本模块已参与本轮结论生成。'),
    }))
    .sort((left, right) => left.label.localeCompare(right.label, 'zh-CN'));
};

export const buildReportDashboard = (result: any): ReportDashboard => {
  const { analysisData, agentOutputs } = normalizeAnalysisPayload(result);
  const decision = analysisData || result || {};
  const marketData = (agentOutputs.market_data || {}) as Record<string, any>;
  const valuation = (agentOutputs.valuation || {}) as Record<string, any>;
  const technicals = (agentOutputs.technicals || {}) as Record<string, any>;
  const fundamentals = (agentOutputs.fundamentals || {}) as Record<string, any>;
  const sentiment = (agentOutputs.sentiment || {}) as Record<string, any>;
  const macroNews = (agentOutputs.macro_news_agent || {}) as Record<string, any>;
  const macroAnalyst = (agentOutputs.macro_analyst || {}) as Record<string, any>;
  const riskManager = (agentOutputs.risk_manager || {}) as Record<string, any>;
  const bull = (agentOutputs.researcher_bull || {}) as Record<string, any>;
  const bear = (agentOutputs.researcher_bear || {}) as Record<string, any>;
  const debate = (agentOutputs.debate_room || {}) as Record<string, any>;
  const portfolio = (agentOutputs.portfolio_manager || {}) as Record<string, any>;

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
      note: '稳定期长期增长假设，决定终值贡献。 ',
    },
  ];

  return {
    ticker: toText(result?.ticker || decision?.ticker, '--'),
    actionLabel: toActionLabel(decision.action || decision.decision || decision.signal),
    actionTone: toTone(decision.action || decision.decision || decision.signal),
    confidenceText: toConfidenceText(decision.confidence || portfolio.confidence),
    heroReason:
      toText(
        decision.reasoning || decision.summary || portfolio.reasoning,
        '系统已完成本轮分析，请结合各模块证据理解结论。',
      ),
    dataIntegrityLabel: marketData.critical_data_complete ? '关键数据完整' : '关键数据不完整',
    supportPoints: pickBulletList(
      bull.thesis_points,
      bull.reasoning,
      typeof valuation.margin_of_safety === 'number' && valuation.margin_of_safety > 0
        ? `DCF 显示安全边际 ${formatPercent(valuation.margin_of_safety)}`
        : null,
    ),
    concernPoints: pickBulletList(
      bear.thesis_points,
      bear.reasoning,
      !marketData.critical_data_complete ? normalizeDataReliability(marketData) : null,
      riskManager.reasoning,
    ),
    balanceSummary:
      toText(portfolio.reasoning || debate.reasoning, '系统综合多空观点后，当前更适合保持中性解读。'),
    riskSummary:
      toText(
        decision.ashare_considerations || decision.risk_summary || riskManager.reasoning,
        '暂未识别到额外风险提示。',
      ),
    reliabilitySummary: normalizeDataReliability(marketData),
    modules: [
      buildValuationModule(valuation, technicals),
      buildFundamentalModule(fundamentals),
      buildSentimentModule(sentiment, macroNews, macroAnalyst),
      buildRiskModule(riskManager),
    ],
    agentCards: buildAgentCards(agentOutputs),
    dcfHeadline:
      valuation.data_quality === '数据不足'
        ? '本轮 DCF 不可作为主要依据，因为关键输入不足。'
        : `本轮 DCF 估值结论：${toText(valuation.margin_of_safety_assessment, '估值中性')}。`,
    dcfAssumptionChips,
  };
};

