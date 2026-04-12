import React, { useMemo } from 'react';
import { Alert, Card, Col, Divider, Row, Tag, Typography } from 'antd';
import {
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  MinusCircleOutlined,
} from '@ant-design/icons';
import { normalizeAnalysisPayload } from '../utils/analysisResult';

const { Paragraph, Text, Title } = Typography;

interface ReportViewProps {
  data: any;
}

interface AgentReportCard {
  key: string;
  label: string;
  signal: string;
  confidenceText: string;
  summary: string;
  evidence: Array<{ key: string; value: string }>;
}

const AGENT_LABELS: Record<string, string> = {
  market_data: '市场数据',
  technicals: '技术面',
  fundamentals: '基本面',
  sentiment: '情绪面',
  valuation: '估值面',
  macro_news_agent: '宏观新闻',
  researcher_bull: '多方观点',
  researcher_bear: '空方观点',
  debate_room: '多空辩论',
  risk_manager: '风险管理',
  macro_analyst: '宏观判断',
  portfolio_manager: '组合决策',
};

const AGENT_ORDER = [
  'market_data',
  'technicals',
  'fundamentals',
  'sentiment',
  'valuation',
  'macro_news_agent',
  'researcher_bull',
  'researcher_bear',
  'debate_room',
  'risk_manager',
  'macro_analyst',
  'portfolio_manager',
];

const normalizeSignal = (value: unknown): 'bullish' | 'bearish' | 'hold' | 'neutral' => {
  const text = String(value || '').toLowerCase();
  if (text.includes('buy') || text.includes('bull') || text.includes('long')) {
    return 'bullish';
  }
  if (text.includes('sell') || text.includes('bear') || text.includes('short')) {
    return 'bearish';
  }
  if (text.includes('hold')) {
    return 'hold';
  }
  return 'neutral';
};

const signalLabel = (signal: string): string => {
  if (signal === 'bullish') {
    return '偏多';
  }
  if (signal === 'bearish') {
    return '偏空';
  }
  if (signal === 'hold') {
    return '中性持有';
  }
  return '中性';
};

const signalColor = (signal: string): string => {
  if (signal === 'bullish') {
    return 'error';
  }
  if (signal === 'bearish') {
    return 'success';
  }
  if (signal === 'hold') {
    return 'processing';
  }
  return 'default';
};

const signalIcon = (signal: string) => {
  if (signal === 'bullish') {
    return <CheckCircleOutlined />;
  }
  if (signal === 'bearish') {
    return <ExclamationCircleOutlined />;
  }
  return <MinusCircleOutlined />;
};

const actionLabel = (value: unknown): string => {
  const signal = normalizeSignal(value);
  if (signal === 'bullish') {
    return '建议买入';
  }
  if (signal === 'bearish') {
    return '建议卖出';
  }
  return '建议持有';
};

const formatConfidence = (value: unknown): string => {
  if (value == null || value === '') {
    return '--';
  }
  if (typeof value === 'number') {
    return value <= 1 ? `${Math.round(value * 100)}%` : `${Math.round(value)}%`;
  }
  if (typeof value === 'string') {
    const cleaned = value.replace('%', '').trim();
    const parsed = Number.parseFloat(cleaned);
    if (!Number.isNaN(parsed)) {
      return parsed <= 1 ? `${Math.round(parsed * 100)}%` : `${Math.round(parsed)}%`;
    }
    return value;
  }
  return String(value);
};

const toPlainText = (value: unknown, fallback = ''): string => {
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
    const items = value
      .map((item) => toPlainText(item))
      .filter(Boolean);
    return items.length > 0 ? items.join('；') : fallback;
  }

  if (typeof value === 'object') {
    const record = value as Record<string, unknown>;
    const preferredKeys = ['summary', 'analysis', 'reasoning', 'details', 'conclusion'];
    for (const key of preferredKeys) {
      const preferred = toPlainText(record[key]);
      if (preferred) {
        return preferred;
      }
    }

    const pairs = Object.entries(record)
      .filter(([, val]) => val != null)
      .slice(0, 6)
      .map(([key, val]) => `${key}: ${toPlainText(val) || String(val)}`);
    return pairs.length > 0 ? pairs.join('；') : fallback;
  }

  return String(value);
};

const extractHighlights = (text: string): string[] => {
  if (!text) {
    return [];
  }
  return text
    .replace(/\s+/g, ' ')
    .split(/(?<=[。！？!?；;])\s*/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 4);
};

const buildEvidence = (payload: Record<string, any>): Array<{ key: string; value: string }> => {
  const source =
    payload.structured_data && typeof payload.structured_data === 'object' && !Array.isArray(payload.structured_data)
      ? payload.structured_data
      : payload;

  const ignored = new Set([
    'agent_name',
    'agent_type',
    'signal',
    'confidence',
    'summary',
    'reasoning',
    'details',
    'structured_data',
  ]);

  return Object.entries(source)
    .filter(([key, val]) => !ignored.has(key) && val != null)
    .slice(0, 4)
    .map(([key, val]) => ({
      key,
      value: toPlainText(val, '-'),
    }));
};

const buildAgentCards = (agentOutputs: Record<string, any>): AgentReportCard[] => {
  const entries = Object.entries(agentOutputs || {}).map(([key, rawPayload]) => {
    const payload = (rawPayload || {}) as Record<string, any>;
    const signal = normalizeSignal(payload.signal);
    const summary = toPlainText(
      payload.summary ?? payload.reasoning ?? payload.details,
      '该 Agent 已完成分析，建议结合其他模块综合判断。'
    );

    return {
      key,
      label: AGENT_LABELS[key] || key,
      signal,
      confidenceText: formatConfidence(payload.confidence),
      summary,
      evidence: buildEvidence(payload),
    };
  });

  return entries.sort((a, b) => {
    const aIndex = AGENT_ORDER.indexOf(a.key);
    const bIndex = AGENT_ORDER.indexOf(b.key);
    if (aIndex === -1 && bIndex === -1) {
      return a.key.localeCompare(b.key);
    }
    if (aIndex === -1) {
      return 1;
    }
    if (bIndex === -1) {
      return -1;
    }
    return aIndex - bIndex;
  });
};

const ReportView: React.FC<ReportViewProps> = ({ data }) => {
  if (!data) {
    return (
      <Alert
        message="暂无报告数据"
        description="分析结果为空，请重新运行分析。"
        type="warning"
        showIcon
      />
    );
  }

  const { analysisData, agentOutputs } = normalizeAnalysisPayload(data);
  const normalizedDecision = analysisData || {};
  const ticker =
    data?.ticker ||
    data?.result?.ticker ||
    normalizedDecision?.ticker ||
    data?.task_id?.split('-')?.[0] ||
    '--';

  const decisionAction =
    normalizedDecision?.action ||
    normalizedDecision?.decision ||
    data?.final_decision?.action ||
    data?.action ||
    'hold';

  const decisionConfidence = formatConfidence(
    normalizedDecision?.confidence ?? data?.final_decision?.confidence ?? data?.confidence
  );
  const decisionQuantity = normalizedDecision?.quantity ?? data?.final_decision?.quantity ?? '--';
  const decisionReasoning = toPlainText(
    normalizedDecision?.reasoning ??
      normalizedDecision?.summary ??
      data?.reasoning ??
      data?.summary,
    '系统已完成本轮分析，建议结合风险偏好与持仓约束进行决策。'
  );
  const riskNote = toPlainText(
    normalizedDecision?.ashare_considerations ??
      normalizedDecision?.risk_summary ??
      normalizedDecision?.risk_note ??
      agentOutputs?.risk_manager?.reasoning,
    '暂无额外风险提示。'
  );

  const highlights = extractHighlights(decisionReasoning);
  const agentCards = useMemo(() => buildAgentCards(agentOutputs), [agentOutputs]);
  const actionSignal = normalizeSignal(decisionAction);

  return (
    <div className="report-view-layout">
      <Card className="report-overview-card">
        <div className="report-overview-head">
          <Title level={4} style={{ margin: 0 }}>
            答辩版结论
          </Title>
          <Tag color={signalColor(actionSignal)} icon={signalIcon(actionSignal)}>
            {actionLabel(decisionAction)}
          </Tag>
        </div>

        <Paragraph className="report-hero-text">
          {highlights[0] || decisionReasoning}
        </Paragraph>

        <div className="report-kpi-grid">
          <div className="report-kpi-item">
            <span className="report-kpi-label">股票代码</span>
            <span className="report-kpi-value">{ticker}</span>
          </div>
          <div className="report-kpi-item">
            <span className="report-kpi-label">建议操作</span>
            <span className="report-kpi-value">{actionLabel(decisionAction)}</span>
          </div>
          <div className="report-kpi-item">
            <span className="report-kpi-label">置信度</span>
            <span className="report-kpi-value">{decisionConfidence}</span>
          </div>
          <div className="report-kpi-item">
            <span className="report-kpi-label">建议数量</span>
            <span className="report-kpi-value">{decisionQuantity}</span>
          </div>
        </div>
      </Card>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={14}>
          <Card title="结论拆解">
            {highlights.length > 0 ? (
              <ul className="report-highlight-list">
                {highlights.map((item, index) => (
                  <li key={`highlight-${index}`}>{item}</li>
                ))}
              </ul>
            ) : (
              <Paragraph style={{ marginBottom: 0 }}>{decisionReasoning}</Paragraph>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="风险提示">
            <Paragraph style={{ marginBottom: 0 }}>{riskNote}</Paragraph>
          </Card>
        </Col>
      </Row>

      <Divider orientation="left" plain style={{ marginTop: 24 }}>
        多 Agent 观点速览
      </Divider>

      {agentCards.length === 0 ? (
        <Alert
          message="未获取到 Agent 输出"
          description="本次任务没有可展示的 Agent 结果，请查看原始 JSON 或重新运行。"
          type="info"
          showIcon
        />
      ) : (
        <Row gutter={[16, 16]}>
          {agentCards.map((card) => (
            <Col xs={24} md={12} xl={8} key={card.key}>
              <Card className="report-agent-card" size="small">
                <div className="report-agent-head">
                  <Text strong>{card.label}</Text>
                  <Tag color={signalColor(card.signal)}>{signalLabel(card.signal)}</Tag>
                </div>
                <Paragraph className="report-agent-summary">{card.summary}</Paragraph>
                <div className="report-agent-meta">
                  <Text type="secondary">置信度：{card.confidenceText}</Text>
                </div>
                {card.evidence.length > 0 && (
                  <div className="report-agent-evidence">
                    {card.evidence.map((entry) => (
                      <div className="report-agent-evidence-item" key={`${card.key}-${entry.key}`}>
                        <span className="report-agent-evidence-key">{entry.key}</span>
                        <span className="report-agent-evidence-value">{entry.value}</span>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </Col>
          ))}
        </Row>
      )}
    </div>
  );
};

export default ReportView;
