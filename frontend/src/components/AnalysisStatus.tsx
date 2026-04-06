import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Collapse, Progress, Spin, Tabs } from 'antd';
import { EyeOutlined, FileTextOutlined, ReloadOutlined } from '@ant-design/icons';
import { ApiService, type AnalysisStatus as Status } from '../services/api';
import ReportView from './ReportView';

interface AnalysisStatusProps {
  runId: string;
  onComplete?: (result: any) => void;
}

interface AgentInsight {
  agent_name: string;
  agent_type?: string;
  signal?: string;
  confidence?: number | string;
  summary?: string;
  execution_time_ms?: number;
  token_usage?: number | string | Record<string, any>;
}

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
  if (!value) {
    return 'neutral';
  }

  const text = String(value).toLowerCase();
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
        summary: data.summary || data.reasoning,
        execution_time_ms: data.execution_time_ms,
        token_usage: data.token_usage,
      };
    });
  }

  const signalList = result.agent_signals || result.analyst_signals;
  if (Array.isArray(signalList)) {
    return signalList.map((item: Record<string, any>, index: number) => ({
      agent_name: item.agent_name || item.name || `agent_${index + 1}`,
      agent_type: item.agent_type,
      signal: item.signal,
      confidence: item.confidence,
      summary: item.reasoning || item.summary,
      execution_time_ms: item.execution_time_ms,
      token_usage: item.token_usage,
    }));
  }

  return [];
};

const AnalysisStatus: React.FC<AnalysisStatusProps> = ({ runId, onComplete }) => {
  const [status, setStatus] = useState<Status | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  const fetchStatus = async () => {
    setLoading(true);
    try {
      const response = await ApiService.getAnalysisStatus(runId);
      if (response.success && response.data) {
        setStatus(response.data);

        if (response.data.status === 'completed') {
          const resultResponse = await ApiService.getAnalysisResult(runId);
          if (resultResponse.success && resultResponse.data) {
            const actualResult = resultResponse.data.result || resultResponse.data;
            if (!actualResult.ticker && (response.data as any).ticker) {
              actualResult.ticker = (response.data as any).ticker;
            }
            if (!actualResult.task_id && resultResponse.data.task_id) {
              actualResult.task_id = resultResponse.data.task_id;
            }
            setResult(actualResult);
            onComplete?.(actualResult);
          }
        }
      }
    } catch (error) {
      console.error('Fetch status error:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();

    let interval: number;
    if (status?.status === 'running') {
      interval = setInterval(fetchStatus, 3000);
    }

    return () => {
      if (interval) {
        clearInterval(interval);
      }
    };
  }, [runId, status?.status]);

  const progress = useMemo(() => {
    if (!status) {
      return 0;
    }

    if (status.progress && typeof status.progress === 'string') {
      const progressMatch = status.progress.match(/(\d+)%/);
      if (progressMatch) {
        return Number.parseInt(progressMatch[1], 10);
      }
    }

    if (status.status === 'completed') {
      return 100;
    }
    if (status.status === 'running') {
      return 60;
    }
    return 0;
  }, [status]);

  const insights = useMemo(() => extractAgentInsights(result), [result]);
  const decision = result?.decision || result?.action || result?.signal || 'HOLD';
  const ticker = result?.ticker || status?.run_id?.slice(0, 6) || '--';
  const summary =
    result?.reasoning ||
    result?.summary ||
    result?.decision_reasoning ||
    '系统正在汇总多智能体分析结果。';
  const confidence = normalizeConfidence(result?.confidence);

  return (
    <Card
      title={`分析任务 #${runId.slice(0, 8)}`}
      extra={
        <Button
          icon={<ReloadOutlined />}
          onClick={fetchStatus}
          loading={loading}
          size="small"
          className="secondary-button"
        >
          刷新
        </Button>
      }
      className="feature-card analysis-status-card mb-4"
    >
      {status ? (
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
              {status.progress && <span>{status.progress}</span>}
            </div>
            <Progress
              percent={progress}
              showInfo={false}
              status={status.status === 'failed' ? 'exception' : 'normal'}
            />
          </div>

          <div className="analysis-hero">
            <div className="decision-hero-card">
              <span className="decision-hero-kicker">Joint Decision</span>
              <div className="decision-hero-title">{String(decision).toUpperCase()}</div>
              <p className="decision-hero-summary">{summary}</p>
            </div>

            <div className="analysis-metric-grid">
              <div className="analysis-metric-card">
                <span className="analysis-metric-label">Ticker</span>
                <span className="analysis-metric-value">{ticker}</span>
              </div>
              <div className="analysis-metric-card">
                <span className="analysis-metric-label">Confidence</span>
                <span className="analysis-metric-value">
                  {confidence != null ? `${confidence}%` : '--'}
                </span>
              </div>
              <div className="analysis-metric-card">
                <span className="analysis-metric-label">Agent Nodes</span>
                <span className="analysis-metric-value">{insights.length || 4}</span>
              </div>
              <div className="analysis-metric-card">
                <span className="analysis-metric-label">Run ID</span>
                <span className="analysis-metric-value">#{runId.slice(0, 8)}</span>
              </div>
            </div>
          </div>

          {insights.length > 0 && (
            <div className="analysis-section">
              <div className="analysis-section-head">
                <h3>Agent Intelligence Nodes</h3>
              </div>
              <div className="agent-grid">
                {insights.map((item) => {
                  const signal = normalizeSignal(item.signal);
                  const confidenceValue = normalizeConfidence(item.confidence);
                  return (
                    <div className="agent-node-card" key={`${item.agent_name}-${item.agent_type || 'agent'}`}>
                      <div className="agent-node-head">
                        <div>
                          <h4 className="agent-node-name">{item.agent_name}</h4>
                          <span className="agent-node-type">
                            {item.agent_type || 'analysis'}
                          </span>
                        </div>
                        <span className={`agent-signal-badge agent-signal-${signal}`}>
                          {item.signal || signal}
                        </span>
                      </div>
                      <p className="agent-node-summary">
                        {item.summary || '该 Agent 已完成当前轮分析，等待联合决策汇总。'}
                      </p>
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

          {status.progress && (
            <Alert
              message="进度信息"
              description={status.progress}
              type="info"
              className="mb-4"
            />
          )}

          {status.status === 'completed' && result && (
            <Collapse
              items={[
                {
                  key: '1',
                  label: (
                    <span>
                      <EyeOutlined /> 查看分析结果
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
                              <FileTextOutlined /> 投资分析报告
                            </span>
                          ),
                          children: <ReportView data={result} />,
                        },
                        {
                          key: 'json',
                          label: (
                            <span>
                              <EyeOutlined /> 原始数据 JSON
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
              description="任务执行过程中发生错误，请检查后端日志或重新发起分析。"
              type="error"
              showIcon
            />
          )}
        </>
      ) : (
        <div className="loading-container">
          <Spin size="large" />
          <div className="loading-text">正在获取分析任务状态...</div>
        </div>
      )}
    </Card>
  );
};

export default AnalysisStatus;
