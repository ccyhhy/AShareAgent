import React, { useEffect, useState } from 'react';
import {
  Alert,
  Card,
  Col,
  Empty,
  Progress,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Tag,
} from 'antd';
import {
  BarChartOutlined,
  DollarOutlined,
  FundOutlined,
  LineChartOutlined,
  PieChartOutlined,
  TrophyOutlined,
} from '@ant-design/icons';
import { ApiService } from '../services/api';

interface PersonalSummary {
  user_stats: {
    total_analyses: number;
    total_backtests: number;
    total_portfolios: number;
    success_rate: number;
    avg_return: number;
  };
  recent_activity: {
    analyses: any[];
    backtests: any[];
    portfolios: any[];
  };
  performance_summary: {
    best_return: number;
    worst_return: number;
    total_invested: number;
    current_value: number;
    profit_loss: number;
  };
}

const PersonalStats: React.FC = () => {
  const [summary, setSummary] = useState<PersonalSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [timeRange, setTimeRange] = useState<'7d' | '30d' | '90d' | 'all'>('30d');

  useEffect(() => {
    loadPersonalSummary();
  }, [timeRange]);

  const loadPersonalSummary = async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await ApiService.getPersonalSummary();
      if (response.success && response.data) {
        setSummary(response.data);
      } else {
        setError('获取个人统计失败');
      }
    } catch (err: any) {
      if (err.response?.status === 403) {
        setError('当前账号暂无权限查看个人统计数据');
      } else {
        setError(err.response?.data?.message || '获取个人统计失败');
      }
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (value: number) =>
    new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(value || 0);

  const formatPercent = (value: number) => `${((value || 0) * 100).toFixed(2)}%`;

  const getReturnColor = (value: number) => {
    if (value > 0) return '#c23846';
    if (value < 0) return '#0f9a64';
    return '#70809f';
  };

  const renderActivityEmpty = (icon: React.ReactNode, text: string) => (
    <div className="activity-empty">
      <div className="activity-empty-icon">{icon}</div>
      <div>{text}</div>
    </div>
  );

  if (loading) {
    return (
      <div className="loading-container">
        <Spin size="large" />
        <div className="loading-text">正在加载个人统计...</div>
      </div>
    );
  }

  if (error) {
    return (
      <Alert
        message="统计数据获取失败"
        description={error}
        type="error"
        showIcon
      />
    );
  }

  return (
    <div className="personal-stats-page">
      <Card className="feature-card personal-stats-hero-card mb-4">
        <div className="section-hero">
          <div>
            <span className="section-kicker">个人表现</span>
            <h3 className="section-title">个人统计与使用表现</h3>
            <p className="section-description">
              用统一的高质量面板展示分析次数、回测频率、组合表现和最近活动，适合作为系统用户侧价值的展示窗口。
            </p>
          </div>
          <div className="stats-range-switcher">
            <span>时间范围</span>
            <Select
              value={timeRange}
              onChange={setTimeRange}
              style={{ width: 132 }}
              options={[
                { value: '7d', label: '近 7 天' },
                { value: '30d', label: '近 30 天' },
                { value: '90d', label: '近 90 天' },
                { value: 'all', label: '全部时间' },
              ]}
            />
          </div>
        </div>
      </Card>

      {summary ? (
        <>
          <div className="dashboard-overview-grid mb-4">
            <div className="overview-stat-card">
              <span className="overview-stat-label">分析次数</span>
              <strong className="overview-stat-value">{summary.user_stats?.total_analyses || 0}</strong>
              <span className="overview-stat-foot"><Space size={6}><BarChartOutlined /><span>累计分析任务</span></Space></span>
            </div>
            <div className="overview-stat-card">
              <span className="overview-stat-label">回测次数</span>
              <strong className="overview-stat-value">{summary.user_stats?.total_backtests || 0}</strong>
              <span className="overview-stat-foot"><Space size={6}><TrophyOutlined /><span>累计实验任务</span></Space></span>
            </div>
            <div className="overview-stat-card">
              <span className="overview-stat-label">投资组合</span>
              <strong className="overview-stat-value">{summary.user_stats?.total_portfolios || 0}</strong>
              <span className="overview-stat-foot"><Space size={6}><FundOutlined /><span>当前管理中的组合</span></Space></span>
            </div>
            <div className="overview-stat-card">
              <span className="overview-stat-label">平均收益率</span>
              <strong className="overview-stat-value" style={{ color: getReturnColor(summary.user_stats?.avg_return || 0) }}>
                {formatPercent(summary.user_stats?.avg_return || 0)}
              </strong>
              <span className="overview-stat-foot">面向最近统计区间</span>
            </div>
          </div>

          <Card className="feature-card mb-4" title="投资表现">
            <Row gutter={[16, 16]}>
              <Col xs={24} md={6}>
                <Card className="inner-panel-card" bordered={false}>
                  <Statistic title="总投入资金" value={formatCurrency(summary.performance_summary?.total_invested || 0)} prefix={<DollarOutlined />} />
                </Card>
              </Col>
              <Col xs={24} md={6}>
                <Card className="inner-panel-card" bordered={false}>
                  <Statistic title="当前总市值" value={formatCurrency(summary.performance_summary?.current_value || 0)} prefix={<FundOutlined />} />
                </Card>
              </Col>
              <Col xs={24} md={6}>
                <Card className="inner-panel-card" bordered={false}>
                  <Statistic
                    title="累计盈亏"
                    value={formatCurrency(summary.performance_summary?.profit_loss || 0)}
                    valueStyle={{ color: getReturnColor(summary.performance_summary?.profit_loss || 0) }}
                  />
                </Card>
              </Col>
              <Col xs={24} md={6}>
                <Card className="inner-panel-card" bordered={false}>
                  <Statistic title="成功率" value={formatPercent(summary.user_stats?.success_rate || 0)} prefix={<PieChartOutlined />} />
                </Card>
              </Col>
            </Row>

            <div className="stats-range-panel">
              <div className="stats-range-head">
                <span className="section-kicker">收益区间</span>
                <span>展示近阶段的收益区间与平均水平</span>
              </div>
              <Progress
                percent={50}
                showInfo={false}
                strokeColor={{ '0%': '#0f9a64', '50%': '#c97d1d', '100%': '#c23846' }}
              />
              <div className="stats-range-labels">
                <span>最差 {formatPercent(summary.performance_summary?.worst_return || 0)}</span>
                <span>平均 {formatPercent(summary.user_stats?.avg_return || 0)}</span>
                <span>最佳 {formatPercent(summary.performance_summary?.best_return || 0)}</span>
              </div>
            </div>
          </Card>

          <Row gutter={[16, 16]}>
            <Col xs={24} lg={8}>
              <Card className="feature-card" title={<span><BarChartOutlined /> 最近分析</span>}>
                {(summary.recent_activity?.analyses || []).length === 0 ? (
                  renderActivityEmpty(<PieChartOutlined />, '暂无分析记录')
                ) : (
                  <div className="activity-list">
                    {(summary.recent_activity?.analyses || []).slice(0, 5).map((analysis, index) => (
                      <div className="activity-item" key={`${analysis.run_id || analysis.ticker}-${index}`}>
                        <div>
                          <strong>{analysis.ticker || analysis.stock_code || '--'}</strong>
                          <p>{analysis.created_at ? new Date(analysis.created_at).toLocaleDateString('zh-CN') : '未知时间'}</p>
                        </div>
                        <Tag color={analysis.status === 'completed' ? 'success' : analysis.status === 'running' ? 'processing' : 'error'}>
                          {analysis.status === 'completed' ? '完成' : analysis.status === 'running' ? '运行中' : '失败'}
                        </Tag>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </Col>

            <Col xs={24} lg={8}>
              <Card className="feature-card" title={<span><TrophyOutlined /> 最近回测</span>}>
                {(summary.recent_activity?.backtests || []).length === 0 ? (
                  renderActivityEmpty(<LineChartOutlined />, '暂无回测记录')
                ) : (
                  <div className="activity-list">
                    {(summary.recent_activity?.backtests || []).slice(0, 5).map((backtest, index) => (
                      <div className="activity-item" key={`${backtest.task_id || backtest.ticker}-${index}`}>
                        <div>
                          <strong>{backtest.ticker || '--'}</strong>
                          <p>{backtest.created_at ? new Date(backtest.created_at).toLocaleDateString('zh-CN') : '未知时间'}</p>
                        </div>
                        <Tag color={backtest.status === 'completed' ? 'success' : backtest.status === 'running' ? 'processing' : 'error'}>
                          {backtest.status === 'completed' ? '完成' : backtest.status === 'running' ? '运行中' : '失败'}
                        </Tag>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </Col>

            <Col xs={24} lg={8}>
              <Card className="feature-card" title={<span><FundOutlined /> 组合概况</span>}>
                {(summary.recent_activity?.portfolios || []).length === 0 ? (
                  renderActivityEmpty(<FundOutlined />, '暂无投资组合')
                ) : (
                  <div className="activity-list">
                    {(summary.recent_activity?.portfolios || []).slice(0, 5).map((portfolio, index) => (
                      <div className="activity-item activity-item--portfolio" key={`${portfolio.id || portfolio.name}-${index}`}>
                        <div>
                          <strong>{portfolio.name || '--'}</strong>
                          <p>{formatCurrency(portfolio.current_value || 0)}</p>
                        </div>
                        <div className="activity-item-side">
                          <span style={{ color: getReturnColor(portfolio.profit_loss_percent || 0) }}>
                            {formatPercent(portfolio.profit_loss_percent || 0)}
                          </span>
                          <Tag color="blue">
                            {portfolio.risk_level === 'high'
                              ? '高风险'
                              : portfolio.risk_level === 'medium'
                                ? '中风险'
                                : '低风险'}
                          </Tag>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </Col>
          </Row>
        </>
      ) : (
        <Card className="feature-card">
          <Empty description="暂无统计数据" />
        </Card>
      )}
    </div>
  );
};

export default PersonalStats;
