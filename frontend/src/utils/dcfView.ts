import { normalizeAnalysisPayload } from './analysisResult';
import type {
  DcfAssumptions,
  DcfProjectionRow,
  DcfWorkbenchPayload,
  DcfWorkbenchResult,
} from '../services/api';

const DEFAULT_ASSUMPTIONS: DcfAssumptions = {
  ticker: '',
  currentPrice: 0,
  marketCap: 0,
  sharesOutstanding: 0,
  netDebt: 0,
  baseFreeCashFlow: 0,
  stage1GrowthRatePct: 5,
  stage1Years: 5,
  stage2GrowthRatePct: 3,
  stage2Years: 3,
  terminalGrowthRatePct: 3,
  discountRatePct: 10,
  taxRatePct: 25,
  beta: 1,
  equityRiskPremiumPct: 6,
  riskFreeRatePct: 2.5,
  debtCostPct: 4.5,
  debtRatioPct: 20,
  terminalMethod: 'gordon',
  terminalMultiple: 12,
};

const toNumber = (value: unknown, fallback = 0): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const toPercentInput = (value: unknown, fallback: number): number => {
  const parsed = toNumber(value, fallback);
  if (Math.abs(parsed) <= 1) {
    return Number((parsed * 100).toFixed(2));
  }
  return Number(parsed.toFixed(2));
};

const normalizeTicker = (value: unknown): string => {
  return String(value || '').trim();
};

export const formatCurrency = (value: number): string => {
  if (!Number.isFinite(value)) {
    return '--';
  }

  const absolute = Math.abs(value);
  if (absolute >= 1e8) {
    return `${(value / 1e8).toFixed(2)} 亿元`;
  }
  if (absolute >= 1e4) {
    return `${(value / 1e4).toFixed(2)} 万元`;
  }
  return `${value.toFixed(2)} 元`;
};

export const formatPercent = (value: number | null | undefined): string => {
  if (value == null || !Number.isFinite(value)) {
    return '--';
  }
  return `${(value * 100).toFixed(2)}%`;
};

export const getDcfParameterExplanation = (
  key: keyof DcfAssumptions,
  assumptions: DcfAssumptions,
): string => {
  switch (key) {
    case 'discountRatePct':
      return `折现率 ${assumptions.discountRatePct.toFixed(2)}%，表示模型对资金成本和风险要求的回报水平。`;
    case 'stage1GrowthRatePct':
      return `第一阶段增长率 ${assumptions.stage1GrowthRatePct.toFixed(2)}%，表示前 ${assumptions.stage1Years} 年自由现金流的高增长假设。`;
    case 'stage2GrowthRatePct':
      return `第二阶段增长率 ${assumptions.stage2GrowthRatePct.toFixed(2)}%，表示高增长期结束后的过渡增长速度。`;
    case 'terminalGrowthRatePct':
      return `永续增长率 ${assumptions.terminalGrowthRatePct.toFixed(2)}%，表示企业进入稳定期后的长期增长假设。`;
    case 'baseFreeCashFlow':
      return `基础自由现金流为 ${formatCurrency(assumptions.baseFreeCashFlow)}，它是整个模型预测的起点。`;
    case 'currentPrice':
      return `当前价格为 ${assumptions.currentPrice.toFixed(2)} 元，用于计算每股安全边际。`;
    default:
      return '该参数会直接影响估值结果，请结合业务理解谨慎调整。';
  }
};

export const buildDcfDefaultsFromAnalysis = (result: any): DcfWorkbenchPayload => {
  const { analysisData, agentOutputs } = normalizeAnalysisPayload(result);
  const valuation = (agentOutputs.valuation || analysisData?.valuation || {}) as Record<string, any>;
  const marketData = (agentOutputs.market_data || {}) as Record<string, any>;
  const assumptions = (valuation.assumptions || {}) as Record<string, any>;

  const currentPrice = toNumber(
    marketData.current_price ?? marketData.latest_available_price ?? result?.current_price,
    DEFAULT_ASSUMPTIONS.currentPrice,
  );
  const marketCap = toNumber(
    valuation.market_cap ?? marketData.market_cap ?? result?.market_cap,
    DEFAULT_ASSUMPTIONS.marketCap,
  );

  const derivedShares =
    currentPrice > 0 && marketCap > 0 ? marketCap / currentPrice : DEFAULT_ASSUMPTIONS.sharesOutstanding;

  return {
    sourceLabel: normalizeTicker(result?.ticker || analysisData?.ticker)
      ? '来自当前分析结果'
      : '未检测到分析结果，已使用默认参数',
    assumptions: {
      ...DEFAULT_ASSUMPTIONS,
      ticker: normalizeTicker(result?.ticker || analysisData?.ticker || assumptions.ticker),
      currentPrice,
      marketCap,
      sharesOutstanding: toNumber(assumptions.shares_outstanding, derivedShares),
      netDebt: toNumber(assumptions.net_debt, DEFAULT_ASSUMPTIONS.netDebt),
      baseFreeCashFlow: toNumber(
        assumptions.base_free_cash_flow ?? valuation.base_free_cash_flow,
        DEFAULT_ASSUMPTIONS.baseFreeCashFlow,
      ),
      stage1GrowthRatePct: toPercentInput(
        assumptions.stage1_growth_rate,
        DEFAULT_ASSUMPTIONS.stage1GrowthRatePct,
      ),
      stage1Years: Math.max(1, Math.round(toNumber(assumptions.stage1_years, DEFAULT_ASSUMPTIONS.stage1Years))),
      stage2GrowthRatePct: toPercentInput(
        assumptions.stage2_growth_rate ?? assumptions.terminal_growth_rate,
        DEFAULT_ASSUMPTIONS.stage2GrowthRatePct,
      ),
      stage2Years: Math.max(1, Math.round(toNumber(assumptions.stage2_years, DEFAULT_ASSUMPTIONS.stage2Years))),
      terminalGrowthRatePct: toPercentInput(
        assumptions.terminal_growth_rate,
        DEFAULT_ASSUMPTIONS.terminalGrowthRatePct,
      ),
      discountRatePct: toPercentInput(
        assumptions.discount_rate,
        DEFAULT_ASSUMPTIONS.discountRatePct,
      ),
      taxRatePct: toPercentInput(assumptions.tax_rate, DEFAULT_ASSUMPTIONS.taxRatePct),
      beta: toNumber(assumptions.beta, DEFAULT_ASSUMPTIONS.beta),
      equityRiskPremiumPct: toPercentInput(
        assumptions.equity_risk_premium,
        DEFAULT_ASSUMPTIONS.equityRiskPremiumPct,
      ),
      riskFreeRatePct: toPercentInput(assumptions.risk_free_rate, DEFAULT_ASSUMPTIONS.riskFreeRatePct),
      debtCostPct: toPercentInput(assumptions.debt_cost, DEFAULT_ASSUMPTIONS.debtCostPct),
      debtRatioPct: toPercentInput(assumptions.debt_ratio, DEFAULT_ASSUMPTIONS.debtRatioPct),
      terminalMethod: assumptions.terminal_method === 'multiple' ? 'multiple' : 'gordon',
      terminalMultiple: toNumber(assumptions.terminal_multiple, DEFAULT_ASSUMPTIONS.terminalMultiple),
    },
  };
};

export const computeDcfWorkbench = (assumptions: DcfAssumptions): DcfWorkbenchResult => {
  const projectionRows: DcfProjectionRow[] = [];
  const stage1Growth = assumptions.stage1GrowthRatePct / 100;
  const stage2Growth = assumptions.stage2GrowthRatePct / 100;
  const terminalGrowth = assumptions.terminalGrowthRatePct / 100;
  const discountRate = assumptions.discountRatePct / 100;
  const currentPrice = Math.max(0, assumptions.currentPrice);

  const marketCap =
    assumptions.marketCap > 0
      ? assumptions.marketCap
      : assumptions.sharesOutstanding > 0 && currentPrice > 0
        ? assumptions.sharesOutstanding * currentPrice
        : 0;

  const sharesOutstanding =
    assumptions.sharesOutstanding > 0
      ? assumptions.sharesOutstanding
      : marketCap > 0 && currentPrice > 0
        ? marketCap / currentPrice
        : 0;

  const reasons: string[] = [];

  if (assumptions.baseFreeCashFlow <= 0) {
    reasons.push('基础自由现金流必须大于 0。');
  }
  if (discountRate <= 0) {
    reasons.push('折现率必须大于 0。');
  }
  if (assumptions.terminalMethod === 'gordon' && discountRate <= terminalGrowth) {
    reasons.push('Gordon 永续增长模型要求折现率大于永续增长率。');
  }
  if (assumptions.stage1Years <= 0 || assumptions.stage2Years <= 0) {
    reasons.push('预测年数必须大于 0。');
  }

  if (reasons.length > 0) {
    return {
      isValid: false,
      reasons,
      enterpriseValue: 0,
      equityValue: 0,
      intrinsicValuePerShare: 0,
      marketCap,
      currentPrice,
      marginOfSafety: null,
      conclusion: '数据不足',
      sensitivityHint: '请先修正输入参数，再查看估值结果。',
      projectionRows,
      discountedTerminalValue: 0,
    };
  }

  let lastCashFlow = assumptions.baseFreeCashFlow;
  let totalPresentValue = 0;
  let yearCounter = 0;

  for (let year = 1; year <= assumptions.stage1Years; year += 1) {
    yearCounter += 1;
    lastCashFlow *= 1 + stage1Growth;
    const discountFactor = (1 + discountRate) ** yearCounter;
    const discountedValue = lastCashFlow / discountFactor;
    totalPresentValue += discountedValue;
    projectionRows.push({
      year: yearCounter,
      phase: '第一阶段',
      projectedFcf: lastCashFlow,
      discountedFcf: discountedValue,
    });
  }

  for (let year = 1; year <= assumptions.stage2Years; year += 1) {
    yearCounter += 1;
    lastCashFlow *= 1 + stage2Growth;
    const discountFactor = (1 + discountRate) ** yearCounter;
    const discountedValue = lastCashFlow / discountFactor;
    totalPresentValue += discountedValue;
    projectionRows.push({
      year: yearCounter,
      phase: '第二阶段',
      projectedFcf: lastCashFlow,
      discountedFcf: discountedValue,
    });
  }

  let terminalValue = 0;
  if (assumptions.terminalMethod === 'multiple') {
    terminalValue = lastCashFlow * assumptions.terminalMultiple;
  } else {
    terminalValue = (lastCashFlow * (1 + terminalGrowth)) / (discountRate - terminalGrowth);
  }

  const discountedTerminalValue = terminalValue / ((1 + discountRate) ** yearCounter);
  const enterpriseValue = totalPresentValue + discountedTerminalValue;
  const equityValue = enterpriseValue - assumptions.netDebt;
  const intrinsicValuePerShare =
    sharesOutstanding > 0 ? equityValue / sharesOutstanding : 0;

  const marginOfSafety =
    currentPrice > 0 && intrinsicValuePerShare > 0 ? intrinsicValuePerShare / currentPrice - 1 : null;

  let conclusion = '估值中性';
  if (marginOfSafety != null) {
    if (marginOfSafety >= 0.2) {
      conclusion = '估值偏低';
    } else if (marginOfSafety <= -0.2) {
      conclusion = '估值偏高';
    }
  }

  const sensitivityHint =
    assumptions.discountRatePct >= 12
      ? '当前折现率较高，模型更偏保守，估值会被明显压低。'
      : assumptions.terminalGrowthRatePct >= 4
        ? '当前永续增长率较高，终值贡献较大，估值结果偏乐观。'
        : '当前参数组合相对中性，结果主要受现金流基线和折现率影响。';

  return {
    isValid: true,
    reasons: [],
    enterpriseValue,
    equityValue,
    intrinsicValuePerShare,
    marketCap,
    currentPrice,
    marginOfSafety,
    conclusion,
    sensitivityHint,
    projectionRows,
    discountedTerminalValue,
  };
};

export const getMarginTone = (marginOfSafety: number | null): 'bullish' | 'neutral' | 'bearish' => {
  if (marginOfSafety == null) {
    return 'neutral';
  }
  if (marginOfSafety >= 0.2) {
    return 'bullish';
  }
  if (marginOfSafety <= -0.2) {
    return 'bearish';
  }
  return 'neutral';
};

export const computeReferenceDiscountRatePct = (assumptions: DcfAssumptions): number => {
  const equityWeight = Math.max(0, Math.min(1, 1 - assumptions.debtRatioPct / 100));
  const debtWeight = 1 - equityWeight;
  const costOfEquityPct =
    assumptions.riskFreeRatePct + assumptions.beta * assumptions.equityRiskPremiumPct;
  const afterTaxDebtCostPct = assumptions.debtCostPct * (1 - assumptions.taxRatePct / 100);
  return Number((equityWeight * costOfEquityPct + debtWeight * afterTaxDebtCostPct).toFixed(2));
};
