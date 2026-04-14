import React, { useMemo, useState } from 'react';
import {
  Alert,
  Card,
  Col,
  Image,
  Row,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  AreaChartOutlined,
  DollarCircleOutlined,
  FallOutlined,
  PictureOutlined,
  RiseOutlined,
  SafetyCertificateOutlined,
  TrophyOutlined,
} from '@ant-design/icons';

const { Text } = Typography;

interface BacktestResultProps {
  result: any;
}

const BacktestResult: React.FC<BacktestResultProps> = ({ result }) => {
  const [imageError, setImageError] = useState(false);
  const [imageLoading, setImageLoading] = useState(true);

  const payload = result?.result ?? result;

  const metrics = useMemo(() => {
    if (!payload) {
      return [];
    }

    return [
      {
        key: 'total_return',
        label: '总收益率',
        value: payload.performance_metrics?.total_return,
        formatter: 'percent',
        icon: <RiseOutlined />,
      },
      {
        key: 'annualized_return',
        label: '年化收益率',
        value: payload.performance_metrics?.annualized_return,
        formatter: 'percent',
        icon: <TrophyOutlined />,
      },
      {
        key: 'sharpe_ratio',
        label: '夏普比率',
        value: payload.performance_metrics?.sharpe_ratio,
        formatter: 'number',
        icon: <DollarCircleOutlined />,
      },
      {
        key: 'max_drawdown',
        label: '最大回撤',
        value: payload.performance_metrics?.max_drawdown,
        formatter: 'percent',
        icon: <FallOutlined />,
      },
    ];
  }, [payload]);

  const riskMetrics = useMemo(
    () => [
      { key: 'var_95', label: 'VaR (95%)', value: payload?.risk_metrics?.var_95, formatter: 'percent' },
      { key: 'expected_shortfall', label: '预期损失', value: payload?.risk_metrics?.expected_shortfall, formatter: 'percent' },
      { key: 'beta', label: 'Beta', value: payload?.risk_metrics?.beta, formatter: 'number' },
      { key: 'alpha', label: 'Alpha', value: payload?.risk_metrics?.alpha, formatter: 'number' },
    ],
    [payload],
  );

  if (!payload) {
    return (
      <Alert
        message="暂无回测结果"
        description="请先运行一个回测任务，完成后这里会展示策略表现、风险指标和交易明细。"
        type="warning"
        showIcon
      />
    );
  }

  const trades = payload.trades || [];
  const plotUrl = payload.plot_url || payload.plot_path;
  const plotSrc = plotUrl
    ? plotUrl.startsWith('http')
      ? plotUrl
      : `http://127.0.0.1:8000${plotUrl}`
    : null;

  const formatValue = (value: number | null | undefined, formatter: 'percent' | 'number') => {
    if (value == null) {
      return '--';
    }

    if (formatter === 'percent') {
      return `${(value * 100).toFixed(2)}%`;
    }
    return value.toFixed(2);
  };

  const metricColor = (value: number | null | undefined, inverse = false) => {
    if (value == null) {
      return undefined;
    }
    if (inverse) {
      return value <= 0 ? '#0f9a64' : '#c23846';
    }
    return value >= 0 ? '#c23846' : '#0f9a64';
  };

  const tradeColumns = [
    {
      title: '日期',
      dataIndex: 'date',
      key: 'date',
    },
    {
      title: '动作',
      dataIndex: 'action',
      key: 'action',
      render: (action: string) => {
        const normalized = String(action || '').toLowerCase();
        const tagColor =
          normalized === 'buy' ? 'error' : normalized === 'sell' ? 'success' : 'default';
        const label =
          normalized === 'buy' ? '买入' : normalized === 'sell' ? '卖出' : '持有';
        return <Tag color={tagColor}>{label}</Tag>;
      },
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      key: 'quantity',
    },
    {
      title: '价格',
      dataIndex: 'price',
      key: 'price',
      render: (price: number) => `¥${price?.toFixed(2) || '--'}`,
    },
    {
      title: '总金额',
      dataIndex: 'total_amount',
      key: 'total_amount',
      render: (value: number) => `¥${value?.toFixed(2) || '--'}`,
    },
  ];

  return (
    <div className="backtest-page backtest-result-page">
      <Card className="feature-card backtest-result-hero-card mb-4">
        <div className="section-hero">
          <div>
            <span className="section-kicker">回测复盘</span>
            <h3 className="section-title">策略结果复盘</h3>
            <p className="section-description">
              这里集中展示收益表现、风险指标、图形结果和交易明细，适合直接作为实验章节或答辩展示页截图来源。
            </p>
          </div>
          <div className="backtest-highlight">
            <span className="backtest-highlight-label">回测标的</span>
            <strong>{result.ticker || payload.ticker || '--'}</strong>
            <Text type="secondary">
              {result.start_date || payload.start_date || '--'} 至 {result.end_date || payload.end_date || '--'}
            </Text>
          </div>
        </div>
      </Card>

      {plotSrc && (
        <Card
          className="feature-card mb-4"
          title={
            <Space>
              <PictureOutlined />
              <span>回测图表</span>
            </Space>
          }
        >
          <div className="backtest-image-shell">
            <Image
              src={plotSrc}
              alt="回测图表"
              style={{ maxWidth: '100%', display: imageLoading ? 'none' : 'block' }}
              onLoad={() => setImageLoading(false)}
              onError={() => {
                setImageLoading(false);
                setImageError(true);
                message.error('回测图表加载失败');
              }}
              preview={{ mask: '点击查看大图' }}
            />
            {imageLoading && <div className="backtest-image-placeholder">图表加载中...</div>}
            {imageError && (
              <Alert
                message="图表加载失败"
                description="请检查后端静态资源路径或重新生成该次回测图表。"
                type="error"
                showIcon
              />
            )}
          </div>
        </Card>
      )}

      <div className="dashboard-overview-grid mb-4">
        {metrics.map((item) => (
          <div className="overview-stat-card" key={item.key}>
            <span className="overview-stat-label">{item.label}</span>
            <strong
              className="overview-stat-value"
              style={{
                color:
                  item.key === 'max_drawdown'
                    ? metricColor(item.value, true)
                    : metricColor(item.value),
              }}
            >
              {formatValue(item.value, item.formatter as 'percent' | 'number')}
            </strong>
            <span className="overview-stat-foot">
              <Space size={6}>
                {item.icon}
                <span>核心回测指标</span>
              </Space>
            </span>
          </div>
        ))}
      </div>

      <Card
        className="feature-card mb-4"
        title={
          <Space>
            <SafetyCertificateOutlined />
            <span>风险指标</span>
          </Space>
        }
      >
        <Row gutter={[16, 16]}>
          {riskMetrics.map((item) => (
            <Col xs={24} sm={12} md={6} key={item.key}>
              <Card className="inner-panel-card backtest-mini-card" bordered={false}>
                <Statistic
                  title={item.label}
                  value={formatValue(item.value, item.formatter as 'percent' | 'number')}
                  prefix={<AreaChartOutlined />}
                />
              </Card>
            </Col>
          ))}
        </Row>
      </Card>

      {trades.length > 0 && (
        <Card
          className="feature-card"
          title={
            <Space>
              <DollarCircleOutlined />
              <span>交易明细</span>
            </Space>
          }
        >
          <Table
            dataSource={trades.map((trade: any, index: number) => ({ ...trade, key: index }))}
            columns={tradeColumns}
            pagination={{ pageSize: 10 }}
            scroll={{ x: true }}
          />
        </Card>
      )}
    </div>
  );
};

export default BacktestResult;
