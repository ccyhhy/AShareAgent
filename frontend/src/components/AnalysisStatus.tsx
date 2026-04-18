import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Collapse, Progress, Spin, Tabs } from 'antd';
import { EyeOutlined, FileTextOutlined, ReloadOutlined } from '@ant-design/icons';
import { ApiService, type AnalysisStatus as Status } from '../services/api';
import ReportView from './ReportView';
import { normalizeAnalysisPayload } from '../utils/analysisResult';

interface AnalysisStatusProps {
  runId: string;
  onComplete?: (result: any) => void;
  onOpenDcfWorkbench?: (result: any) => void;
}

interface AgentInsight {
  agent_name: string;
  agent_type?: string;
  signal?: string;
  confidence?: number | string;
  summary?: string;
  execution_time_ms?: number;
  token_usage?: number | string | Record<string, any>;
  structured_entries?: Array<{ key: string; value: string }>;
}

interface DataSourceRow {
  key: string;
  label: string;
  source: string;
  asOf: string;
  cacheStatus: string;
  tone: 'good' | 'warn' | 'bad' | 'neutral';
}

type AgentTypeMeta = {
  label: string;
  tone: string;
};

const AGENT_TYPE_META: Record<string, AgentTypeMeta> = {
  rule_engine: { label: '规则引擎', tone: 'rule' },
  quantitative_model: { label: '量化模型', tone: 'quant' },
  statistical_model: { label: '统计模型', tone: 'stats' },
  llm: { label: 'LLM', tone: 'llm' },
  llm_rag: { label: 'LLM + RAG', tone: 'rag' },
  hybrid_rule_llm: { label: '规则 + LLM', tone: 'hybrid' },
};

const getAgentTypeMeta = (agentType?: string): AgentTypeMeta => {
  const normalized = String(agentType || '').trim().toLowerCase();
  return AGENT_TYPE_META[normalized] || {
    label: normalized || '未标注',
    tone: 'default',
  };
};

const normalizeConfidence = (value: unknown): number | null => {
  if (typeof value === 'number') {
    return value <= 1 ? Math.round(value * 100) : Math.round(value);
  }

  if (typeof value === 'string') {
    const parsed = Number.parseFloat(value.replace('%', '').trim());
    if (!Number.isNaN(parsed)) {
      return parsed <= 1 ? Math.round(parsed * 100) : Math.round(parsed);
    }
  }

  return null;
};

const normalizeSignal = (value: unknown): string => {
  const text = String(value || '').toLowerCase();

  if (text.includes('buy') || text.includes('bull')) {
    return 'bullish';
  }
  if (text.includes('sell') || text.includes('bear')) {
    return 'bearish';
  }
  if (text.includes('hold')) {
    return 'hold';
  }
  return 'neutral';
};

const formatDecisionLabel = (value: unknown): string => {
  const signal = normalizeSignal(value);

  if (signal === 'bullish') {
    return '建议买入';
  }
  if (signal === 'bearish') {
    return '建议卖出';
  }
  return '建议持有';
};


const formatAgentName = (name: string) => {
  const AGENT_LABELS: Record<string, string> = {
    market_data: '数据层', technicals: '相对估值', fundamentals: '基本面',
    sentiment: '情绪面', valuation: 'DCF 估值', macro_news_agent: '宏观新闻',
    researcher_bull: '多头研究员', researcher_bear: '空头研究员', debate_room: '多空辩论',
    risk_manager: '风险管理', macro_analyst: '宏观分析师', portfolio_manager: '组合经理',
    policy_impact: '政策影响', liquidity: '流动性评估',
  };
  return AGENT_LABELS[name] || name;
};

const formatStageBadge = (status: string): string => {
  if (status === 'completed') {
    return '已完成';
  }
  if (status === 'running') {
    return '进行中';
  }
  if (status === 'error') {
    return '失败';
  }
  return '等待中';
};

const formatTokenUsage = (value: unknown): string => {
  if (value == null) {
    return '-';
  }
  if (typeof value === 'number' || typeof value === 'string') {
    return String(value);
  }
  if (typeof value === 'object' && 'total' in (value as Record<string, any>)) {
    return String((value as Record<string, any>).total);
  }
  return '-';
};

const normalizeNarrative = (value: unknown): string => {
  if (value == null) {
    return '';
  }

  if (typeof value === 'string') {
    return value.trim();
  }

  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }

  if (Array.isArray(value)) {
    return value
      .map((item) => normalizeNarrative(item))
      .filter(Boolean)
      .join('；');
  }

  if (typeof value === 'object') {
    const record = value as Record<string, unknown>;
    const preferredKeys = ['summary', 'analysis', 'reasoning', 'details', 'conclusion'];

    for (const key of preferredKeys) {
      const preferred = normalizeNarrative(record[key]);
      if (preferred) {
        return preferred;
      }
    }

    const entries = Object.entries(record)
      .filter(([, val]) => val != null)
      .slice(0, 5)
      .map(([key, val]) => `${key}: ${normalizeNarrative(val) || String(val)}`)
      .filter(Boolean);

    if (entries.length > 0) {
      return entries.join('；');
    }
  }

  return String(value);
};

const extractReasoningHighlights = (value: unknown): string[] => {
  if (!value) {
    return [];
  }

  return String(value)
    .replace(/\s+/g, ' ')
    .split(/(?<=[。！？!?；;])\s*/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 3);
};

const toStructuredEntries = (payload: Record<string, any>): Array<{ key: string; value: string }> => {
  const source =
    payload.structured_data && typeof payload.structured_data === 'object' && !Array.isArray(payload.structured_data)
      ? payload.structured_data
      : payload;

  const ignoredKeys = new Set([
    'agent_name',
    'agent_type',
    'signal',
    'confidence',
    'summary',
    'reasoning',
    'execution_time_ms',
    'token_usage',
    'structured_data',
  ]);

  return Object.entries(source)
    .filter(([key, value]) => !ignoredKeys.has(key) && value != null)
    .slice(0, 4)
    .map(([key, value]) => ({
      key,
      value:
        typeof value === 'object'
          ? JSON.stringify(value).slice(0, 120)
          : String(value).slice(0, 120),
    }));
};

const extractAgentInsights = (result: any): AgentInsight[] => {
  if (!result || typeof result !== 'object') {
    return [];
  }

  if (result.agent_outputs && typeof result.agent_outputs === 'object') {
    return Object.entries(result.agent_outputs).map(([agentName, payload]) => {
      const data = (payload || {}) as Record<string, any>;
      return {
        agent_name: data.agent_name || agentName,
        agent_type: data.agent_type,
        signal: data.signal,
        confidence: data.confidence,
        summary: normalizeNarrative(data.summary ?? data.reasoning),
        execution_time_ms: data.execution_time_ms,
        token_usage: data.token_usage,
        structured_entries: toStructuredEntries(data),
      };
    });
  }

  return [];
};

const DATASET_LABELS: Record<string, string> = {
  financial_metrics: '财务指标',
  financial_statements: '财务报表',
  market_data: '市场行情',
  price_reference: '价格口径',
};

const CACHE_STATUS_META: Record<string, { label: string; tone: DataSourceRow['tone'] }> = {
  remote_live: { label: '实时拉取', tone: 'good' },
  fresh_snapshot: { label: '本地快照(新鲜)', tone: 'good' },
  stale_snapshot: { label: '本地快照(过期回退)', tone: 'warn' },
  offline_fallback: { label: '离线回退', tone: 'warn' },
  offline_derived: { label: '离线推导', tone: 'warn' },
  default_empty: { label: '空数据', tone: 'bad' },
  unknown: { label: '未标注', tone: 'neutral' },
};

const normalizeSourceText = (value: unknown): string => {
  const text = String(value || '').trim();
  return text || '未标注';
};

const normalizeAsOf = (value: unknown): string => {
  const text = String(value || '').trim();
  return text || '未标注';
};

const normalizeCacheStatus = (value: unknown): { label: string; tone: DataSourceRow['tone'] } => {
  const key = String(value || '').trim().toLowerCase();
  return CACHE_STATUS_META[key] || { label: key || '未标注', tone: 'neutral' };
};

const extractDataSourceRows = (agentOutputs: Record<string, any>): DataSourceRow[] => {
  const rows: DataSourceRow[] = [];
  const marketData =
    agentOutputs.market_data && typeof agentOutputs.market_data === 'object'
      ? (agentOutputs.market_data as Record<string, any>)
      : {};

  const sourceMap =
    marketData.data_sources &&
    typeof marketData.data_sources === 'object' &&
    !Array.isArray(marketData.data_sources)
      ? (marketData.data_sources as Record<string, any>)
      : null;

  if (sourceMap) {
    Object.entries(sourceMap).forEach(([datasetKey, rawValue]) => {
      const meta = rawValue && typeof rawValue === 'object' ? (rawValue as Record<string, any>) : {};
      const cacheMeta = normalizeCacheStatus(meta.cache_status);
      rows.push({
        key: `market_data:${datasetKey}`,
        label: DATASET_LABELS[datasetKey] || datasetKey,
        source: normalizeSourceText(meta.source),
        asOf: normalizeAsOf(meta.as_of),
        cacheStatus: cacheMeta.label,
        tone: cacheMeta.tone,
      });
    });
  }

  Object.entries(agentOutputs).forEach(([agentKey, payload]) => {
    if (!payload || typeof payload !== 'object') {
      return;
    }
    if (!('data_source' in (payload as Record<string, any>) || 'cache_status' in (payload as Record<string, any>))) {
      return;
    }

    const p = payload as Record<string, any>;
    const cacheMeta = normalizeCacheStatus(p.cache_status);
    rows.push({
      key: `agent:${agentKey}`,
      label: formatAgentName(agentKey),
      source: normalizeSourceText(p.data_source),
      asOf: normalizeAsOf(p.data_as_of),
      cacheStatus: cacheMeta.label,
      tone: cacheMeta.tone,
    });
  });

  const deduped = new Map<string, DataSourceRow>();
  rows.forEach((row) => {
    if (!deduped.has(row.key)) {
      deduped.set(row.key, row);
    }
  });
  return Array.from(deduped.values());
};

const AnalysisStatus: React.FC<AnalysisStatusProps> = ({ runId, onComplete, onOpenDcfWorkbench }) => {
  const [status, setStatus] = useState<Status | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  const fetchStatus = async () => {
    setLoading(true);
    try {
      const response = await ApiService.getAnalysisStatus(runId);
      if (!response.success || !response.data) {
        return;
      }

      setStatus(response.data);

      if (response.data.status === 'completed') {
        const resultResponse = await ApiService.getAnalysisResult(runId);
        if (resultResponse.success && resultResponse.data) {
          const actualResult = resultResponse.data.result || resultResponse.data;
          if (!actualResult.ticker && response.data.ticker) {
            actualResult.ticker = response.data.ticker;
          }
          if (!actualResult.task_id && (resultResponse.data as any).task_id) {
            actualResult.task_id = (resultResponse.data as any).task_id;
          }
          setResult(actualResult);
          onComplete?.(actualResult);
        }
      }
    } catch (error) {
      console.error('Fetch analysis status failed:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();

    let interval: number | undefined;
    if (!status || status.status === 'running') {
      interval = window.setInterval(fetchStatus, 3000);
    }

    return () => {
      if (interval) {
        window.clearInterval(interval);
      }
    };
  }, [runId, status?.status]);

  const progress = useMemo(() => {
    if (!status) {
      return 0;
    }
    if (typeof status.progress_percent === 'number') {
      return status.progress_percent;
    }
    if (status.status === 'completed') {
      return 100;
    }
    return status.status === 'running' ? 10 : 0;
  }, [status]);

  const normalizedPayload = useMemo(() => normalizeAnalysisPayload(result), [result]);
  const insights = useMemo(() => extractAgentInsights(result), [result]);
  const dataSourceRows = useMemo(
    () => extractDataSourceRows(normalizedPayload.agentOutputs || {}),
    [normalizedPayload],
  );
  const analysisData = normalizedPayload.analysisData || result || {};
  const decision =
    analysisData?.action ||
    analysisData?.decision ||
    result?.decision ||
    result?.action ||
    result?.signal ||
    'hold';
  const ticker = result?.ticker || status?.ticker || '--';
  const summary = normalizeNarrative(
    analysisData?.reasoning ??
      analysisData?.summary ??
      result?.reasoning ??
      result?.summary ??
      result?.decision_reasoning
  ) ||
    '系统正在汇总各个分析节点的结果。';
  const summaryHighlights = extractReasoningHighlights(summary);
  const confidence = normalizeConfidence(analysisData?.confidence ?? result?.confidence);
  const riskNote = normalizeNarrative(
    analysisData?.ashare_considerations ??
      analysisData?.risk_note ??
      analysisData?.risk_summary
  ) ||
    '暂无额外风险提示。';
  const stageList = status?.stages || [];
  const currentStageTitle = status?.current_stage?.title || '等待开始';

  return (
    <Card
      title={`分析任务 #${runId.slice(0, 8)}`}
      extra={(
        <Button
          icon={<ReloadOutlined />}
          onClick={fetchStatus}
          loading={loading}
          size="small"
          className="secondary-button"
        >
          刷新
        </Button>
      )}
      className="feature-card analysis-status-card mb-4"
    >
      {!status ? (
        <div className="loading-container">
          <Spin size="large" />
          <div className="loading-text">正在获取分析状态...</div>
        </div>
      ) : (
        <>
          <div className="analysis-progress-rail">
            <div className="analysis-status-row">
              <span className="analysis-status-label">
                {status.status === 'completed'
                  ? 'COMPLETED'
                  : status.status === 'running'
                    ? 'RUNNING'
                    : 'FAILED'}
              </span>
              <span>{status.progress || '任务已创建，等待开始执行。'}</span>
            </div>
            <Progress
              percent={progress}
              showInfo={false}
              status={status.status === 'failed' ? 'exception' : 'active'}
            />
          </div>

          <div className="analysis-stage-panel">
            <div className="analysis-stage-panel-head">
              <div>
                <div className="analysis-stage-panel-kicker">当前阶段</div>
                <h3>{currentStageTitle}</h3>
              </div>
              <div className="analysis-stage-panel-metric">
                {status.completed_stage_count || 0}/{status.total_stage_count || stageList.length || 0}
              </div>
            </div>

            <div className="analysis-stage-list">
              {stageList.map((stage, index) => (
                <div className={`analysis-stage-item analysis-stage-item-${stage.status}`} key={stage.key}>
                  <div className="analysis-stage-index">{index + 1}</div>
                  <div className="analysis-stage-copy">
                    <div className="analysis-stage-title-row">
                      <strong>{stage.title}</strong>
                      <span className={`analysis-stage-badge analysis-stage-badge-${stage.status}`}>
                        {formatStageBadge(stage.status)}
                      </span>
                    </div>
                    <p>{stage.description}</p>
                    <div className="analysis-stage-agents">
                      {stage.agents.map((agent) => (
                        <span className={`analysis-stage-agent analysis-stage-agent-${agent.status}`} key={agent.key}>
                          {formatAgentName(agent.label)}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="analysis-hero">
            <div className="decision-hero-card">
              <span className="decision-hero-kicker">最终建议</span>
              <div className="decision-hero-title">{formatDecisionLabel(decision)}</div>
              <p className="decision-hero-summary">
                {status.status === 'completed'
                  ? (summaryHighlights[0] || summary)
                  : `系统正在执行“${currentStageTitle}”，完成后这里会显示简明结论。`}
              </p>
            </div>

            <div className="analysis-metric-grid">
              <div className="analysis-metric-card">
                <span className="analysis-metric-label">股票代码</span>
                <span className="analysis-metric-value">{ticker}</span>
              </div>
              <div className="analysis-metric-card">
                <span className="analysis-metric-label">当前进度</span>
                <span className="analysis-metric-value">{progress}%</span>
              </div>
              <div className="analysis-metric-card">
                <span className="analysis-metric-label">置信度</span>
                <span className="analysis-metric-value">
                  {confidence != null ? `${confidence}%` : '--'}
                </span>
              </div>
              <div className="analysis-metric-card">
                <span className="analysis-metric-label">Agent 数量</span>
                <span className="analysis-metric-value">{insights.length}</span>
              </div>
            </div>
          </div>

          {status.status === 'completed' && (
            <div className="analysis-summary-panel">
              <div className="analysis-summary-card">
                <h3>结果摘要</h3>
                {summaryHighlights.length > 0 ? (
                  <ul className="analysis-summary-list">
                    {summaryHighlights.map((item, index) => (
                      <li key={`${runId}-summary-${index}`}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p>{summary}</p>
                )}
              </div>
              <div className="analysis-summary-card">
                <h3>风险提示</h3>
                <p>{riskNote}</p>
              </div>
            </div>
          )}

          {dataSourceRows.length > 0 && (
            <div className="analysis-data-source-panel">
              <div className="analysis-section-head">
                <h3>数据来源与时效</h3>
              </div>
              <div className="analysis-data-source-grid">
                {dataSourceRows.map((item) => (
                  <div className="analysis-data-source-item" key={item.key}>
                    <div className="analysis-data-source-head">
                      <strong>{item.label}</strong>
                      <span className={`analysis-data-source-status analysis-data-source-status-${item.tone}`}>
                        {item.cacheStatus}
                      </span>
                    </div>
                    <p>来源：{item.source}</p>
                    <p>数据日期：{item.asOf}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {insights.length > 0 && (
            <div className="analysis-section">
              <div className="analysis-section-head">
                <h3>各 Agent 当前输出</h3>
              </div>
              <div className="agent-grid">
                {insights.map((item) => {
                  const signal = normalizeSignal(item.signal);
                  const confidenceValue = normalizeConfidence(item.confidence);
                  const typeMeta = getAgentTypeMeta(item.agent_type);

                  return (
                    <div className="agent-node-card" key={`${item.agent_name}-${item.agent_type || 'agent'}`}>
                      <div className="agent-node-head">
                        <div>
                          <h4 className="agent-node-name">
                            {{
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
                            }[item.agent_name] || item.agent_name}
                          </h4>
                          <span className={`hetero-type-pill hetero-type-pill--${typeMeta.tone}`}>
                            {typeMeta.label}
                          </span>
                        </div>
                        <span className={`agent-signal-badge agent-signal-${signal}`}>
                          {formatDecisionLabel(item.signal || signal).replace('建议', '') || (item.signal || signal)}
                        </span>
                      </div>
                      <p className="agent-node-summary">
                        {item.summary || '该 Agent 已完成本轮分析。'}
                      </p>
                      {item.structured_entries && item.structured_entries.length > 0 && (
                        <div className="agent-node-structured">
                          {item.structured_entries.map((entry) => (
                            <div className="agent-node-structured-item" key={`${item.agent_name}-${entry.key}`}>
                              <span className="agent-node-structured-key">{entry.key}</span>
                              <span className="agent-node-structured-value">{entry.value}</span>
                            </div>
                          ))}
                        </div>
                      )}
                      <div className="agent-node-meta">
                        <span>{confidenceValue != null ? `置信度 ${confidenceValue}%` : '置信度 --'}</span>
                        <span>
                          {item.execution_time_ms
                            ? `${item.execution_time_ms}ms`
                            : `Tokens ${formatTokenUsage(item.token_usage)}`}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {status.status === 'completed' && result && (
            <Collapse
              items={[
                {
                  key: 'details',
                  label: (
                    <span>
                      <EyeOutlined /> 查看详细结果
                    </span>
                  ),
                  children: (
                    <Tabs
                      defaultActiveKey="report"
                      items={[
                        {
                          key: 'report',
                          label: (
                            <span>
                              <FileTextOutlined /> 分析报告
                            </span>
                          ),
                          children: (
                            <ReportView
                              data={result}
                              onOpenDcfWorkbench={
                                onOpenDcfWorkbench ? () => onOpenDcfWorkbench(result) : undefined
                              }
                            />
                          ),
                        },
                        {
                          key: 'json',
                          label: (
                            <span>
                              <EyeOutlined /> 原始 JSON
                            </span>
                          ),
                          children: (
                            <pre className="json-viewer">
                              {JSON.stringify(result, null, 2)}
                            </pre>
                          ),
                        },
                      ]}
                    />
                  ),
                },
              ]}
            />
          )}

          {status.status === 'failed' && (
            <Alert
              message="分析失败"
              description="任务执行过程中发生错误，请查看后端日志后重新发起分析。"
              type="error"
              showIcon
            />
          )}
        </>
      )}
    </Card>
  );
};

export default AnalysisStatus;
