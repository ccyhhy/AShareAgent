import React from 'react';
import { Card, Typography, Tag, Divider, Row, Col, Badge, Alert } from 'antd';
import {
  ArrowUpOutlined,
  ArrowDownOutlined,
  MinusOutlined,
  RiseOutlined,
  FallOutlined,
  RobotOutlined,
  DollarOutlined,
  TrophyOutlined,
  WarningOutlined
} from '@ant-design/icons';
import { normalizeAnalysisPayload } from '../utils/analysisResult';

const { Title, Paragraph, Text } = Typography;

interface ReportViewProps {
  data: any;
}

const ReportView: React.FC<ReportViewProps> = ({ data }) => {
  if (!data) {
    return (
      <Alert
        message="暂无报告数据"
        description="分析结果为空，请重新运行分析"
        type="warning"
        showIcon
      />
    );
  }

  console.log('ReportView received data:', data);
  const { analysisData, agentOutputs } = normalizeAnalysisPayload(data);
  const agent_results = agentOutputs;

  if (!agent_results || Object.keys(agent_results).length === 0) {
    return (
      <Alert
        message="鎶ュ憡鏁版嵁鏍煎紡閿欒"
        description={
          <div>
            <div>鍒嗘瀽缁撴灉涓己灏慳gent_results瀛楁</div>
            <div style={{ marginTop: 8, fontSize: '12px' }}>
              鏁版嵁缁撴瀯: {JSON.stringify(Object.keys(data), null, 2)}
            </div>
            {(data.final_decision || data.reasoning) && (
              <div style={{ marginTop: 8, fontSize: '12px', maxHeight: '200px', overflow: 'auto', background: '#f5f5f5', padding: '8px', borderRadius: '4px' }}>
                <strong>鍘熷鍒嗘瀽缁撴灉:</strong>
                <pre style={{ whiteSpace: 'pre-wrap', fontSize: '11px' }}>
                  {String(data.final_decision || data.reasoning).substring(0, 1000)}...
                </pre>
              </div>
            )}
          </div>
        }
        type="error"
        showIcon
      />
    );
  }

  console.log('Final agent_results:', agent_results);
  console.log('Agent results keys:', agent_results ? Object.keys(agent_results) : 'none');

  // 鑾峰彇淇″彿鍥炬爣
  const getSignalIcon = (signal: string) => {
    switch (signal?.toLowerCase()) {
      case 'bullish':
      case 'buy':
        return <ArrowUpOutlined style={{ color: '#ff4d4f' }} />;  // Red for bullish/buy (A-share convention)
      case 'bearish':
      case 'sell':
        return <ArrowDownOutlined style={{ color: '#52c41a' }} />;  // Green for bearish/sell (A-share convention)
      case 'neutral':
      case 'hold':
        return <MinusOutlined style={{ color: '#d9d9d9' }} />;
      default:
        return <MinusOutlined style={{ color: '#d9d9d9' }} />;
    }
  };

  // 鑾峰彇淇″彿棰滆壊
  const getSignalColor = (signal: string) => {
    switch (signal?.toLowerCase()) {
      case 'bullish':
      case 'buy':
        return 'error';  // Red for bullish/buy (A-share convention)
      case 'bearish':
      case 'sell':
        return 'success';  // Green for bearish/sell (A-share convention)
      case 'neutral':
      case 'hold':
        return 'default';
      default:
        return 'default';
    }
  };

  // 鏍煎紡鍖栫疆淇″害
  const formatConfidence = (confidence: any) => {
    if (typeof confidence === 'string') {
      if (confidence.includes('%')) {
        return confidence;
      }
      // 灏濊瘯瑙ｆ瀽瀛楃涓叉暟瀛?
      const parsed = parseFloat(confidence);
      if (!isNaN(parsed)) {
        return parsed > 1 ? `${parsed.toFixed(1)}%` : `${(parsed * 100).toFixed(1)}%`;
      }
    }
    if (typeof confidence === 'number') {
      return confidence > 1 ? `${confidence.toFixed(1)}%` : `${(confidence * 100).toFixed(1)}%`;
    }
    return confidence || '-';
  };

  // 瀹夊叏鑾峰彇鏁版嵁鐨勫嚱鏁?
  const safeGet = (obj: any, path: string[], defaultValue: any = null) => {
    try {
      return path.reduce((current, key) => current && current[key], obj) || defaultValue;
    } catch {
      return defaultValue;
    }
  };

  const getAgentTypeMeta = (agentType: unknown): { label: string; tone: string } => {
    const normalized = String(agentType || '').trim().toLowerCase();
    const mapping: Record<string, { label: string; tone: string }> = {
      rule_engine: { label: 'Rule Engine', tone: 'rule' },
      quantitative_model: { label: 'Quant Model', tone: 'quant' },
      statistical_model: { label: 'Stat Model', tone: 'stats' },
      llm: { label: 'LLM', tone: 'llm' },
      llm_rag: { label: 'LLM + RAG', tone: 'rag' },
      hybrid_rule_llm: { label: 'Hybrid Rule + LLM', tone: 'hybrid' },
    };
    return mapping[normalized] || { label: normalized || 'untyped', tone: 'default' };
  };

  const getStructuredPreview = (payload: Record<string, any>): Array<{ key: string; value: string }> => {
    const source =
      payload.structured_data && typeof payload.structured_data === 'object' && !Array.isArray(payload.structured_data)
        ? payload.structured_data
        : payload;

    const ignore = new Set([
      'agent_name',
      'agent_type',
      'signal',
      'confidence',
      'summary',
      'reasoning',
      'structured_data',
    ]);

    return Object.entries(source)
      .filter(([key, value]) => !ignore.has(key) && value != null)
      .slice(0, 3)
      .map(([key, value]) => ({
        key,
        value:
          typeof value === 'object'
            ? JSON.stringify(value).slice(0, 120)
            : String(value).slice(0, 120),
      }));
  };

  return (
    <div style={{ padding: '24px 0' }}>
      {/* 鏍囬 */}
      <div style={{ textAlign: 'center', marginBottom: '32px' }}>
        <Title level={2} style={{
          margin: 0,
          background: 'linear-gradient(135deg, #1890ff 0%, #722ed1 100%)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          borderBottom: '3px solid #1890ff',
          paddingBottom: '12px',
          display: 'inline-block'
        }}>
          <TrophyOutlined style={{ marginRight: 8, color: '#1890ff' }} />
          鑲＄エ浠ｇ爜 {
            data.ticker || 
            data.result?.ticker || 
            analysisData?.ticker || 
            data.task_id?.split('-')[0] ||
            data.run_id?.split('-')[0] || 
            // 灏濊瘯浠巃gent_signals涓彁鍙杢icker淇℃伅
            (data.agent_signals && data.agent_signals.length > 0 && data.agent_signals[0].ticker) ||
            // 浠庡綋鍓峌RL鎴栧叾浠栨潵婧愭彁鍙?
            (window.location.pathname.includes('/analysis/') && window.location.pathname.split('/').pop()) ||
            '600054'  // 榛樿浣跨敤鐣岄潰鏄剧ず鐨勮偂绁ㄤ唬鐮?
          } 鎶曡祫鍒嗘瀽鎶ュ憡
        </Title>
        <div style={{ marginTop: 8, color: '#666', fontSize: '14px' }}>
          鍒嗘瀽鍖洪棿: {safeGet(agent_results, ['market_data', 'start_date']) || '2024-07-05'} 鑷?{safeGet(agent_results, ['market_data', 'end_date']) || '2025-07-05'}
        </div>
      </div>

      {Object.keys(agent_results).length > 0 && (
        <Card
          title={<span>Heterogeneous Agent Output Matrix</span>}
          style={{ marginBottom: '24px' }}
          bordered
        >
          <Row gutter={[12, 12]}>
            {Object.entries(agent_results).map(([agentKey, payload]) => {
              const data = (payload || {}) as Record<string, any>;
              const typeMeta = getAgentTypeMeta(data.agent_type);
              const preview = getStructuredPreview(data);
              return (
                <Col xs={24} md={12} xl={8} key={agentKey}>
                  <Card size="small">
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                      <Text strong>{agentKey}</Text>
                      <span className={`hetero-type-pill hetero-type-pill--${typeMeta.tone}`}>
                        {typeMeta.label}
                      </span>
                    </div>
                    <div style={{ marginTop: 8 }}>
                      <Tag color={getSignalColor(data.signal)}>
                        {String(data.signal || 'neutral').toUpperCase()}
                      </Tag>
                      <Tag color="blue">{formatConfidence(data.confidence)}</Tag>
                    </div>
                    {preview.length > 0 && (
                      <div style={{ marginTop: 8, display: 'grid', gap: 6 }}>
                        {preview.map((item) => (
                          <div
                            key={`${agentKey}-${item.key}`}
                            style={{
                              padding: '6px 8px',
                              borderRadius: 8,
                              background: '#f5f8ff',
                              border: '1px solid #dbe6ff',
                            }}
                          >
                            <Text type="secondary" style={{ fontSize: 11 }}>{item.key}</Text>
                            <div style={{ fontSize: 12, marginTop: 2 }}>{item.value}</div>
                          </div>
                        ))}
                      </div>
                    )}
                  </Card>
                </Col>
              );
            })}
          </Row>
        </Card>
      )}

      {/* Relative valuation (PB percentile) */}
      {agent_results.technicals && (
        <Card
          title={
            <span>
              📊 Relative Valuation (PB Percentile)
            </span>
          }
          style={{ marginBottom: '24px' }}
          bordered
        >
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={12}>
              <Text strong>Signal: </Text>
              {getSignalIcon(agent_results.technicals.signal)}
              <Tag color={getSignalColor(agent_results.technicals.signal)} style={{ marginLeft: 8 }}>
                {agent_results.technicals.signal?.toUpperCase() || 'UNKNOWN'}
              </Tag>
            </Col>
            <Col span={12}>
              <Text strong>Confidence: </Text>
              <Tag color="blue">
                {formatConfidence(agent_results.technicals.confidence)}
              </Tag>
            </Col>
          </Row>

          <div style={{ marginTop: '16px' }}>
            <Divider orientation="left" plain>PB Percentile Details</Divider>
            <Row gutter={[16, 16]}>
              <Col span={12}>
                <Card size="small">
                  <Text strong>PB Percentile (5Y): </Text>
                  <Text>{agent_results.technicals.pb_percentile_5y ?? '-'}</Text>
                </Card>
              </Col>
              <Col span={12}>
                <Card size="small">
                  <Text strong>Current PB: </Text>
                  <Text>{agent_results.technicals.pb_current ?? '-'}</Text>
                </Card>
              </Col>
              <Col span={12}>
                <Card size="small">
                  <Text strong>Valuation Score: </Text>
                  <Text>{agent_results.technicals.valuation_score ?? '-'}</Text>
                </Card>
              </Col>
              <Col span={12}>
                <Card size="small">
                  <Text strong>Sample Size: </Text>
                  <Text>{agent_results.technicals.sample_size ?? '-'}</Text>
                </Card>
              </Col>
            </Row>
          </div>
        </Card>
      )}

      {/* 鍩烘湰闈㈠垎鏋?*/}
      {agent_results.fundamentals && (
        <Card
          title={<span>基本面分析</span>}
          style={{ marginBottom: '24px' }}
          bordered
        >
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={12}>
              <Text strong>淇″彿: </Text>
              {getSignalIcon(agent_results.fundamentals.signal)}
              <Tag color={getSignalColor(agent_results.fundamentals.signal)} style={{ marginLeft: 8 }}>
                {agent_results.fundamentals.signal?.toUpperCase() || 'UNKNOWN'}
              </Tag>
            </Col>
            <Col span={12}>
              <Text strong>缃俊搴? </Text>
              <Tag color="blue">
                {formatConfidence(agent_results.fundamentals.confidence)}
              </Tag>
            </Col>
          </Row>
          {agent_results.fundamentals.reasoning && (
            <div style={{ marginTop: '16px' }}>
              <Divider orientation="left" plain>分析详情</Divider>
              {typeof agent_results.fundamentals.reasoning === 'object' ? (
                <Row gutter={[16, 8]}>
                  {Object.entries(agent_results.fundamentals.reasoning).map(([key, data]: [string, any]) => (
                    <Col span={12} key={key}>
                      <Card size="small">
                        <Text strong>{key}: </Text>
                        <Tag color={getSignalColor(data.signal)}>{data.signal}</Tag>
                        <div style={{ marginTop: 4, fontSize: '12px', color: '#666' }}>
                          {data.details}
                        </div>
                      </Card>
                    </Col>
                  ))}
                </Row>
              ) : (
                <Paragraph style={{ background: '#f5f5f5', padding: '12px', borderRadius: '4px' }}>
                  {agent_results.fundamentals.reasoning}
                </Paragraph>
              )}
            </div>
          )}
        </Card>
      )}

      {/* 鎯呮劅鍒嗘瀽 */}
      {agent_results.sentiment && (
        <Card
          title={<span>Market Sentiment (News)</span>}
          style={{ marginBottom: '24px' }}
          bordered
        >
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={12}>
              <Text strong>淇″彿: </Text>
              {getSignalIcon(agent_results.sentiment.signal)}
              <Tag color={getSignalColor(agent_results.sentiment.signal)} style={{ marginLeft: 8 }}>
                {agent_results.sentiment.signal?.toUpperCase() || 'UNKNOWN'}
              </Tag>
            </Col>
            <Col span={12}>
              <Text strong>缃俊搴? </Text>
              <Tag color="blue">
                {formatConfidence(agent_results.sentiment.confidence)}
              </Tag>
            </Col>
          </Row>
          {agent_results.sentiment.reasoning && (
            <Paragraph style={{ marginTop: '16px', background: '#f5f5f5', padding: '12px', borderRadius: '4px' }}>
              {agent_results.sentiment.reasoning}
            </Paragraph>
          )}
        </Card>
      )}

      {/* 浼板€煎垎鏋?*/}
      {agent_results.valuation && (
        <Card
          title={<span>Valuation Analysis</span>}
          style={{ marginBottom: '24px' }}
          bordered
        >
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={12}>
              <Text strong>淇″彿: </Text>
              {getSignalIcon(agent_results.valuation.signal)}
              <Tag color={getSignalColor(agent_results.valuation.signal)} style={{ marginLeft: 8 }}>
                {agent_results.valuation.signal?.toUpperCase() || 'UNKNOWN'}
              </Tag>
            </Col>
            <Col span={12}>
              <Text strong>缃俊搴? </Text>
              <Tag color="blue">
                {formatConfidence(agent_results.valuation.confidence)}
              </Tag>
            </Col>
          </Row>
          {agent_results.valuation.reasoning && (
            <div style={{ marginTop: '16px' }}>
              <Divider orientation="left" plain>估值详情</Divider>
              {typeof agent_results.valuation.reasoning === 'object' ? (
                <Row gutter={[16, 8]}>
                  {Object.entries(agent_results.valuation.reasoning).map(([key, data]: [string, any]) => (
                    <Col span={12} key={key}>
                      <Card size="small">
                        <Text strong>{key}: </Text>
                        <Tag color={getSignalColor(data.signal)}>{data.signal}</Tag>
                        <div style={{ marginTop: 4, fontSize: '12px', color: '#666' }}>
                          {data.details}
                        </div>
                      </Card>
                    </Col>
                  ))}
                </Row>
              ) : (
                <Paragraph style={{ background: '#f5f5f5', padding: '12px', borderRadius: '4px' }}>
                  {agent_results.valuation.reasoning}
                </Paragraph>
              )}
            </div>
          )}
        </Card>
      )}

      {/* 澶氭柟鐮旂┒鍒嗘瀽 */}
      {agent_results.researcher_bull && (
        <Card
          title={<span>Bull Research Analysis</span>}
          style={{ marginBottom: '24px' }}
          bordered
        >
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={12}>
              <Text strong>瑙傜偣: </Text>
              <Tag color="red">
                <RiseOutlined /> {agent_results.researcher_bull.perspective?.toUpperCase() || agent_results.researcher_bull.signal?.toUpperCase() || 'BULL'}
              </Tag>
            </Col>
            <Col span={12}>
              <Text strong>缃俊搴? </Text>
              <Tag color="blue">
                {formatConfidence(agent_results.researcher_bull.confidence)}
              </Tag>
            </Col>
          </Row>
          {agent_results.researcher_bull.thesis_points && Array.isArray(agent_results.researcher_bull.thesis_points) && (
            <div style={{ marginTop: '16px' }}>
              <Divider orientation="left" plain>论点</Divider>
              <div style={{ background: '#f6ffed', padding: '16px', borderRadius: '6px', border: '1px solid #b7eb8f' }}>
                {agent_results.researcher_bull.thesis_points.map((point: string, index: number) => (
                  <div key={index} style={{ marginBottom: '8px', display: 'flex', alignItems: 'flex-start' }}>
                    <span style={{ color: '#52c41a', marginRight: '8px', fontWeight: 'bold' }}>+</span>
                    <Text>{point}</Text>
                  </div>
                ))}
              </div>
            </div>
          )}
          {agent_results.researcher_bull.reasoning && (
            <Paragraph style={{ marginTop: '16px', background: '#f6ffed', padding: '12px', borderRadius: '4px', border: '1px solid #b7eb8f' }}>
              {typeof agent_results.researcher_bull.reasoning === 'string' ? 
                agent_results.researcher_bull.reasoning : 
                (agent_results.researcher_bull.reasoning?.summary || 
                 agent_results.researcher_bull.reasoning?.analysis || 
                 JSON.stringify(agent_results.researcher_bull.reasoning))}
            </Paragraph>
          )}
        </Card>
      )}

      {/* 绌烘柟鐮旂┒鍒嗘瀽 */}
      {agent_results.researcher_bear && (
        <Card
          title={<span>Bear Research Analysis</span>}
          style={{ marginBottom: '24px' }}
          bordered
        >
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={12}>
              <Text strong>瑙傜偣: </Text>
              <Tag color="green">
                <FallOutlined /> {agent_results.researcher_bear.perspective?.toUpperCase() || agent_results.researcher_bear.signal?.toUpperCase() || 'BEAR'}
              </Tag>
            </Col>
            <Col span={12}>
              <Text strong>缃俊搴? </Text>
              <Tag color="blue">
                {formatConfidence(agent_results.researcher_bear.confidence)}
              </Tag>
            </Col>
          </Row>
          {agent_results.researcher_bear.thesis_points && Array.isArray(agent_results.researcher_bear.thesis_points) && (
            <div style={{ marginTop: '16px' }}>
              <Divider orientation="left" plain>论点</Divider>
              <div style={{ background: '#fff2e8', padding: '16px', borderRadius: '6px', border: '1px solid #ffccc7' }}>
                {agent_results.researcher_bear.thesis_points.map((point: string, index: number) => (
                  <div key={index} style={{ marginBottom: '8px', display: 'flex', alignItems: 'flex-start' }}>
                    <span style={{ color: '#ff4d4f', marginRight: '8px', fontWeight: 'bold' }}>-</span>
                    <Text>{point}</Text>
                  </div>
                ))}
              </div>
            </div>
          )}
          {agent_results.researcher_bear.reasoning && (
            <Paragraph style={{ marginTop: '16px', background: '#fff2e8', padding: '12px', borderRadius: '4px', border: '1px solid #ffccc7' }}>
              {typeof agent_results.researcher_bear.reasoning === 'string' ? 
                agent_results.researcher_bear.reasoning : 
                (agent_results.researcher_bear.reasoning?.summary || 
                 agent_results.researcher_bear.reasoning?.analysis || 
                 JSON.stringify(agent_results.researcher_bear.reasoning))}
            </Paragraph>
          )}
        </Card>
      )}

      {/* 椋庨櫓绠＄悊鍒嗘瀽 */}
      {agent_results.risk_manager && (
        <Card
          title={<span><WarningOutlined /> Risk Management Analysis</span>}
          style={{ marginBottom: '24px' }}
          bordered
        >
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={8}>
              <Text strong>椋庨櫓璇勫垎: </Text>
              <Badge 
                count={agent_results.risk_manager.risk_score || 'N/A'} 
                style={{ backgroundColor: '#f50' }} 
              />
              <span style={{ marginLeft: '8px' }}>/10</span>
            </Col>
            <Col span={8}>
              <Text strong>寤鸿鎿嶄綔: </Text>
              <Tag color={getSignalColor(agent_results.risk_manager.trading_action || agent_results.risk_manager.signal)}>
                {(agent_results.risk_manager.trading_action || agent_results.risk_manager.signal)?.toUpperCase() || '鎸佹湁'}
              </Tag>
            </Col>
            <Col span={8}>
              <Text strong>鏈€澶т粨浣? </Text>
              <Text type="secondary">
                {agent_results.risk_manager.max_position_size?.toFixed?.(2) || '未设定'}
              </Text>
            </Col>
          </Row>

          {agent_results.risk_manager.risk_metrics && (
            <div style={{ marginTop: '16px' }}>
              <Divider orientation="left" plain>风险指标</Divider>
              <Row gutter={16}>
                <Col span={6}>
                  <Card size="small" style={{ textAlign: 'center' }}>
                    <Paragraph style={{ margin: 0, fontSize: '12px', fontWeight: 'bold' }}>波动率</Paragraph>
                    <Text style={{ fontSize: '16px', fontWeight: 'bold' }}>
                      {agent_results.risk_manager.risk_metrics?.volatility 
                        ? (agent_results.risk_manager.risk_metrics.volatility * 100).toFixed(2) + '%'
                        : 'N/A'}
                    </Text>
                  </Card>
                </Col>
                <Col span={6}>
                  <Card size="small" style={{ textAlign: 'center' }}>
                    <Paragraph strong style={{ margin: 0, fontSize: '12px' }}>VaR (95%)</Paragraph>
                    <Text style={{ fontSize: '16px', fontWeight: 'bold' }}>
                      {agent_results.risk_manager.risk_metrics?.value_at_risk_95 
                        ? (agent_results.risk_manager.risk_metrics.value_at_risk_95 * 100).toFixed(2) + '%'
                        : 'N/A'}
                    </Text>
                  </Card>
                </Col>
                <Col span={6}>
                  <Card size="small" style={{ textAlign: 'center' }}>
                    <Paragraph style={{ margin: 0, fontSize: '12px', fontWeight: 'bold' }}>最大回撤</Paragraph>
                    <Text style={{ fontSize: '16px', fontWeight: 'bold' }}>
                      {agent_results.risk_manager.risk_metrics?.max_drawdown 
                        ? (agent_results.risk_manager.risk_metrics.max_drawdown * 100).toFixed(2) + '%'
                        : 'N/A'}
                    </Text>
                  </Card>
                </Col>
                <Col span={6}>
                  <Card size="small" style={{ textAlign: 'center' }}>
                    <Paragraph strong style={{ margin: 0, fontSize: '12px' }}>甯傚満椋庨櫓</Paragraph>
                    <Text style={{ fontSize: '16px', fontWeight: 'bold' }}>
                      {agent_results.risk_manager.risk_metrics?.market_risk_score 
                        ? agent_results.risk_manager.risk_metrics.market_risk_score + '/10'
                        : 'N/A'}
                    </Text>
                  </Card>
                </Col>
              </Row>
            </div>
          )}

          {agent_results.risk_manager.reasoning && (
            <Paragraph style={{ marginTop: '16px', background: '#fff2e8', padding: '12px', borderRadius: '4px', border: '1px solid #ffccc7' }}>
              {agent_results.risk_manager.reasoning}
            </Paragraph>
          )}
        </Card>
      )}

      {/* 鎶曡祫缁勫悎绠＄悊鍒嗘瀽 */}
      {(analysisData?.action || data?.final_decision) && (
        <Card
          title={<span><DollarOutlined /> Portfolio Management Analysis</span>}
          style={{ marginBottom: '24px' }}
          bordered
        >
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={8}>
              <Text strong>浜ゆ槗琛屽姩: </Text>
              <Tag color={getSignalColor(analysisData?.action || data?.final_decision?.action)} icon={<DollarOutlined />}>
                {(analysisData?.action || data?.final_decision?.action)?.toUpperCase() || 'UNKNOWN'}
              </Tag>
            </Col>
            <Col span={8}>
              <Text strong>浜ゆ槗鏁伴噺: </Text>
              <Text type="secondary">
                {(analysisData?.quantity || data?.final_decision?.quantity || '-')}
              </Text>
            </Col>
            <Col span={8}>
              <Text strong>鍐崇瓥淇″績: </Text>
              <Tag color="blue">
                {formatConfidence(analysisData?.confidence || data?.final_decision?.confidence)}
              </Tag>
            </Col>
          </Row>

          {(analysisData?.agent_signals || data?.final_decision?.agent_signals) && (
            <div style={{ marginTop: '16px' }}>
              <Divider orientation="left" plain>各分析师意见</Divider>
              <Row gutter={[16, 8]}>
                {(analysisData?.agent_signals || data?.final_decision?.agent_signals)?.map((signal: any, index: number) => (
                  <Col span={12} key={index}>
                    <Card size="small" style={{ background: '#fafafa' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                          <RobotOutlined style={{ marginRight: '8px' }} />
                          <Text strong>{signal.agent_name}</Text>
                        </div>
                        <div>
                          {getSignalIcon(signal.signal)}
                          <Tag color={getSignalColor(signal.signal)} style={{ marginLeft: 8 }}>
                            {signal.signal?.toUpperCase()}
                          </Tag>
                        </div>
                      </div>
                      <div style={{ marginTop: 4, fontSize: '12px', color: '#666' }}>
                        缃俊搴? {formatConfidence(signal.confidence)}
                      </div>
                    </Card>
                  </Col>
                ))}
              </Row>
            </div>
          )}

          {(analysisData?.reasoning || data?.final_decision?.reasoning) && (
            <div style={{ marginTop: '16px' }}>
              <Divider orientation="left" plain>决策理由</Divider>
              <Paragraph style={{ background: '#f5f5f5', padding: '12px', borderRadius: '4px' }}>
                {analysisData?.reasoning || data?.final_decision?.reasoning}
              </Paragraph>
            </div>
          )}
        </Card>
      )}

      {/* 鏈€缁堟姇璧勫喅绛栨憳瑕?*/}
      {analysisData && analysisData.action && (
        <Card
          title={
            <span>
              <TrophyOutlined style={{ color: '#1890ff', marginRight: 8 }} />
              鏈€缁堟姇璧勫喅绛?
            </span>
          }
          style={{ marginBottom: '24px' }}
          bordered
        >
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={8}>
              <Text strong>鎿嶄綔寤鸿: </Text>
              {getSignalIcon(analysisData.action)}
              <Tag color={getSignalColor(analysisData.action)} style={{ marginLeft: 8 }}>
                {analysisData.action === 'buy' ? '涔板叆' : 
                 analysisData.action === 'sell' ? '鍗栧嚭' : '鎸佹湁'}
              </Tag>
            </Col>
            <Col span={8}>
              <Text strong>浜ゆ槗鏁伴噺: </Text>
               <Text type="secondary">{analysisData.quantity || 0} 股</Text>
            </Col>
            <Col span={8}>
              <Text strong>鍐崇瓥缃俊搴? </Text>
              <Tag color="blue">
                {formatConfidence(analysisData.confidence)}
              </Tag>
            </Col>
          </Row>

          {analysisData.reasoning && (
            <div style={{ marginTop: '16px' }}>
              <Divider orientation="left" plain>决策理由</Divider>
              <Paragraph style={{ background: '#f5f5f5', padding: '12px', borderRadius: '4px' }}>
                {analysisData.reasoning}
              </Paragraph>
            </div>
          )}

          {analysisData.ashare_considerations && (
            <div style={{ marginTop: '16px' }}>
              <Divider orientation="left" plain>A股特性考虑</Divider>
              <div style={{ background: '#e6f7ff', padding: '12px', borderRadius: '4px', border: '1px solid #91d5ff' }}>
                {typeof analysisData.ashare_considerations === 'string' ? (
                  <Paragraph style={{ margin: 0 }}>
                    {analysisData.ashare_considerations}
                  </Paragraph>
                ) : (
                  <div>
                    {Object.entries(analysisData.ashare_considerations).map(([key, value]: [string, any]) => (
                      <div key={key} style={{ marginBottom: '8px' }}>
                        <Text strong>{key}: </Text>
                        <Text>{String(value)}</Text>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </Card>
      )}

      {/* 濡傛灉娌℃湁浠讳綍agent缁撴灉锛屾樉绀烘彁绀?*/}
      {Object.keys(agent_results).length === 0 && (
        <Alert
          message="鏆傛棤鍒嗘瀽缁撴灉"
          description="Agent鍒嗘瀽缁撴灉涓虹┖锛岃妫€鏌ュ垎鏋愰厤缃垨閲嶆柊杩愯鍒嗘瀽"
          type="info"
          showIcon
        />
      )}
    </div>
  );
};

export default ReportView;



