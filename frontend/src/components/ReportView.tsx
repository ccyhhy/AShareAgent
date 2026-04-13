import React, { useMemo } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Divider,
  Empty,
  Row,
  Space,
  Tag,
  Typography,
} from 'antd';
import {
  ArrowRightOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { buildReportDashboard } from '../utils/reportView';

const { Paragraph, Text, Title } = Typography;

interface ReportViewProps {
  data: any;
  onOpenDcfWorkbench?: () => void;
}

const toneColor = (tone: 'bullish' | 'bearish' | 'neutral' | 'warning'): string => {
  if (tone === 'bullish') {
    return 'error';
  }
  if (tone === 'bearish') {
    return 'success';
  }
  if (tone === 'warning') {
    return 'warning';
  }
  return 'processing';
};

const toneIcon = (tone: 'bullish' | 'bearish' | 'neutral' | 'warning') => {
  if (tone === 'bullish') {
    return <CheckCircleOutlined />;
  }
  if (tone === 'bearish') {
    return <ExclamationCircleOutlined />;
  }
  return <InfoCircleOutlined />;
};

const ReportView: React.FC<ReportViewProps> = ({ data, onOpenDcfWorkbench }) => {
  const dashboard = useMemo(() => (data ? buildReportDashboard(data) : null), [data]);

  if (!data || !dashboard) {
    return (
      <Alert
        message="暂无报告数据"
        description="当前没有可展示的详细报告，请重新发起分析后再查看。"
        type="warning"
        showIcon
      />
    );
  }

  return (
    <div className="report-dashboard">
      <Card className="report-decision-hero">
        <div className="report-decision-head">
          <div>
            <span className="report-kicker">最终建议</span>
            <Title level={3} style={{ margin: '12px 0 8px' }}>
              {dashboard.actionLabel}
            </Title>
            <Paragraph className="report-decision-reason">{dashboard.heroReason}</Paragraph>
          </div>
          <Space direction="vertical" align="end" size={10}>
            <Tag color={toneColor(dashboard.actionTone)} icon={toneIcon(dashboard.actionTone)}>
              {dashboard.dataIntegrityLabel}
            </Tag>
            <Tag>{dashboard.confidenceText} 置信度</Tag>
          </Space>
        </div>

        <div className="report-hero-metrics">
          <div className="report-hero-metric">
            <span>股票代码</span>
            <strong>{dashboard.ticker}</strong>
          </div>
          <div className="report-hero-metric">
            <span>结论类型</span>
            <strong>{dashboard.actionLabel}</strong>
          </div>
          <div className="report-hero-metric">
            <span>数据完整度</span>
            <strong>{dashboard.dataIntegrityLabel}</strong>
          </div>
          <div className="report-hero-metric">
            <span>DCF 说明</span>
            <strong>{dashboard.dcfHeadline}</strong>
          </div>
        </div>
      </Card>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} xl={8}>
          <Card className="report-panel-card" title="支持理由">
            {dashboard.supportPoints.length > 0 ? (
              <ul className="report-bullet-list">
                {dashboard.supportPoints.map((item, index) => (
                  <li key={`support-${index}`}>{item}</li>
                ))}
              </ul>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无明确支持理由" />
            )}
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card className="report-panel-card" title="反对理由">
            {dashboard.concernPoints.length > 0 ? (
              <ul className="report-bullet-list">
                {dashboard.concernPoints.map((item, index) => (
                  <li key={`concern-${index}`}>{item}</li>
                ))}
              </ul>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无明确反对理由" />
            )}
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card className="report-panel-card" title="最终平衡判断">
            <Paragraph className="report-balance-copy">{dashboard.balanceSummary}</Paragraph>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} xl={12}>
          <Card className="report-panel-card" title="风险提示">
            <Paragraph className="report-balance-copy">{dashboard.riskSummary}</Paragraph>
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card className="report-panel-card" title="数据可靠度">
            <Paragraph className="report-balance-copy">{dashboard.reliabilitySummary}</Paragraph>
          </Card>
        </Col>
      </Row>

      <Divider orientation="left" plain>
        四大分析模块
      </Divider>

      <div className="report-module-grid">
        {dashboard.modules.map((module) => (
          <Card key={module.key} className="report-module-card">
            <div className="report-module-head">
              <div>
                <span className="report-module-kicker">{module.title}</span>
                <Title level={5} style={{ margin: '8px 0 0' }}>
                  {module.statusLabel}
                </Title>
              </div>
              <Tag color={toneColor(module.tone)}>{module.statusLabel}</Tag>
            </div>
            <Paragraph className="report-module-summary">{module.summary}</Paragraph>
            {module.bullets.length > 0 && (
              <ul className="report-bullet-list report-bullet-list-compact">
                {module.bullets.map((item, index) => (
                  <li key={`${module.key}-${index}`}>{item}</li>
                ))}
              </ul>
            )}
          </Card>
        ))}
      </div>

      <Card
        className="report-panel-card report-dcf-panel"
        title="DCF 假设透明度"
        extra={
          onOpenDcfWorkbench ? (
            <Button type="primary" icon={<ArrowRightOutlined />} onClick={onOpenDcfWorkbench}>
              打开 DCF 工具页
            </Button>
          ) : null
        }
      >
        <Paragraph className="report-balance-copy">{dashboard.dcfHeadline}</Paragraph>
        <div className="report-dcf-chip-grid">
          {dashboard.dcfAssumptionChips.map((chip) => (
            <div className="report-dcf-chip" key={chip.label}>
              <span>{chip.label}</span>
              <strong>{chip.value}</strong>
              <p>{chip.note}</p>
            </div>
          ))}
        </div>
      </Card>

      <Divider orientation="left" plain>
        多智能体观点区
      </Divider>

      {dashboard.agentCards.length > 0 ? (
        <div className="report-agent-grid">
          {dashboard.agentCards.map((card) => (
            <Card key={card.key} className="report-agent-card-v2">
              <div className="report-agent-card-head">
                <Text strong>{card.label}</Text>
                <Tag color={toneColor(card.tone)}>{card.confidenceText}</Tag>
              </div>
              <Paragraph className="report-agent-card-summary">{card.summary}</Paragraph>
            </Card>
          ))}
        </div>
      ) : (
        <Card className="report-panel-card">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本轮结果没有可展示的 Agent 摘要。" />
        </Card>
      )}

      <Collapse
        style={{ marginTop: 16 }}
        items={[
          {
            key: 'raw-report',
            label: '查看原始数据与调试信息',
            children: (
              <pre className="report-raw-json">{JSON.stringify(data, null, 2)}</pre>
            ),
          },
        ]}
      />
    </div>
  );
};

export default ReportView;
