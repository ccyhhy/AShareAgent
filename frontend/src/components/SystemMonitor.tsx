import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Empty,
  Progress,
  Row,
  Space,
  Statistic,
  Switch,
  Table,
  Tabs,
  Tag,
} from 'antd';
import {
  ApiOutlined,
  CheckCircleOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  ExclamationCircleOutlined,
  MonitorOutlined,
  ReloadOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { ApiService } from '../services/api';

interface SystemHealth {
  status: 'healthy' | 'warning' | 'critical';
  services: {
    database: boolean;
    redis: boolean;
    workers: boolean;
  };
  uptime: number;
  version: string;
}

interface SystemMetrics {
  cpu_usage: number;
  memory_usage: number;
  disk_usage: number;
  active_connections: number;
  request_count_24h: number;
  error_count_24h: number;
  average_response_time: number;
}

interface LogEntry {
  id: number;
  level: 'INFO' | 'WARNING' | 'ERROR' | 'DEBUG';
  message: string;
  timestamp: string;
  module?: string;
}

const SystemMonitor: React.FC = () => {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'health' | 'metrics' | 'logs'>('health');
  const [autoRefresh, setAutoRefresh] = useState(true);

  useEffect(() => {
    loadSystemData();

    let interval: number | undefined;
    if (autoRefresh) {
      interval = window.setInterval(loadSystemData, 30000);
    }

    return () => {
      if (interval) {
        clearInterval(interval);
      }
    };
  }, [autoRefresh]);

  const loadSystemData = async () => {
    try {
      setError(null);

      const [healthResponse, metricsResponse, logsResponse] = await Promise.allSettled([
        ApiService.getSystemHealth(),
        ApiService.getSystemMetrics(),
        ApiService.getSystemLogs(),
      ]);

      if (healthResponse.status === 'fulfilled' && healthResponse.value.success) {
        setHealth(healthResponse.value.data);
      }

      if (metricsResponse.status === 'fulfilled' && metricsResponse.value.success) {
        setMetrics(metricsResponse.value.data);
      }

      if (logsResponse.status === 'fulfilled' && logsResponse.value.success) {
        setLogs(logsResponse.value.data || []);
      }

      if (
        healthResponse.status === 'rejected' &&
        metricsResponse.status === 'rejected' &&
        logsResponse.status === 'rejected'
      ) {
        setError('无法获取系统监控数据，可能是服务暂时不可用或当前账号权限不足。');
      }
    } catch (err: any) {
      setError(err.response?.data?.message || '获取系统监控数据失败');
    } finally {
      setLoading(false);
    }
  };

  const healthMeta = useMemo(() => {
    switch (health?.status) {
      case 'healthy':
        return {
          label: '系统健康',
          color: '#0f9a64',
          icon: <CheckCircleOutlined />,
          badge: 'success' as const,
        };
      case 'warning':
        return {
          label: '系统告警',
          color: '#c97d1d',
          icon: <WarningOutlined />,
          badge: 'warning' as const,
        };
      case 'critical':
        return {
          label: '系统严重异常',
          color: '#c23846',
          icon: <ExclamationCircleOutlined />,
          badge: 'error' as const,
        };
      default:
        return {
          label: '状态未知',
          color: '#70809f',
          icon: <MonitorOutlined />,
          badge: 'default' as const,
        };
    }
  }, [health?.status]);

  const formatUptime = (seconds: number) => {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${days}天 ${hours}小时 ${minutes}分钟`;
  };

  const getUsageColor = (usage: number) => {
    if (usage > 80) return '#c23846';
    if (usage > 60) return '#c97d1d';
    return '#0f9a64';
  };

  const getLogLevelColor = (level: string) => {
    switch (level) {
      case 'INFO':
        return 'blue';
      case 'WARNING':
        return 'orange';
      case 'ERROR':
        return 'red';
      case 'DEBUG':
        return 'purple';
      default:
        return 'default';
    }
  };

  const logColumns = [
    {
      title: '时间',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 180,
      render: (timestamp: string) => new Date(timestamp).toLocaleString('zh-CN'),
    },
    {
      title: '级别',
      dataIndex: 'level',
      key: 'level',
      width: 100,
      render: (level: string) => <Tag color={getLogLevelColor(level)}>{level}</Tag>,
    },
    {
      title: '模块',
      dataIndex: 'module',
      key: 'module',
      width: 140,
      render: (module: string) => module || '-',
    },
    {
      title: '消息',
      dataIndex: 'message',
      key: 'message',
      ellipsis: true,
    },
  ];

  return (
    <div className="system-monitor-page">
      <Card className="feature-card monitor-hero-card mb-4">
        <div className="section-hero">
          <div>
            <span className="section-kicker">运维中心</span>
            <h3 className="section-title">系统运维与运行健康</h3>
            <p className="section-description">
              这里负责呈现平台健康度、资源使用情况和日志观测结果。整体视觉和分析页统一，方便你后续做系统架构与运维章节的展示。
            </p>
          </div>
          <div className="monitor-hero-controls">
            <div className="monitor-toggle">
              <span>自动刷新</span>
              <Switch checked={autoRefresh} onChange={setAutoRefresh} />
            </div>
            <Button
              icon={<ReloadOutlined />}
              onClick={loadSystemData}
              loading={loading}
              className="secondary-button"
            >
              立即刷新
            </Button>
          </div>
        </div>
      </Card>

      {error && (
        <Alert
          className="mb-4"
          message="监控数据获取失败"
          description={error}
          type="warning"
          showIcon
        />
      )}

      <div className="dashboard-overview-grid mb-4">
        <div className="overview-stat-card">
          <span className="overview-stat-label">系统健康</span>
          <strong className="overview-stat-value" style={{ color: healthMeta.color }}>
            {healthMeta.label}
          </strong>
          <span className="overview-stat-foot">
            <Space size={6}>
              {healthMeta.icon}
              <Badge status={healthMeta.badge} text="实时状态" />
            </Space>
          </span>
        </div>
        <div className="overview-stat-card">
          <span className="overview-stat-label">运行时长</span>
          <strong className="overview-stat-value">
            {health ? formatUptime(health.uptime || 0) : '--'}
          </strong>
          <span className="overview-stat-foot">持续运行稳定性</span>
        </div>
        <div className="overview-stat-card">
          <span className="overview-stat-label">系统版本</span>
          <strong className="overview-stat-value">{health?.version || '--'}</strong>
          <span className="overview-stat-foot">当前部署版本</span>
        </div>
        <div className="overview-stat-card">
          <span className="overview-stat-label">日志条数</span>
          <strong className="overview-stat-value">{logs.length}</strong>
          <span className="overview-stat-foot">最近一批监控日志</span>
        </div>
      </div>

      <Card className="feature-card monitor-tabs-card">
        <Tabs
          activeKey={activeTab}
          onChange={(key) => setActiveTab(key as 'health' | 'metrics' | 'logs')}
          items={[
            {
              key: 'health',
              label: (
                <span>
                  <CheckCircleOutlined /> 系统健康
                </span>
              ),
              children: health ? (
                <>
                  <div className="monitor-service-grid mb-4">
                    {Object.entries(health.services || {}).map(([service, serviceStatus]) => (
                      <Card className="inner-panel-card monitor-service-card" key={service} bordered={false}>
                        <div className="monitor-service-icon">
                          {service === 'database' && <DatabaseOutlined />}
                          {service === 'redis' && <CloudServerOutlined />}
                          {service === 'workers' && <ApiOutlined />}
                        </div>
                        <h4>
                          {service === 'database'
                            ? '数据库'
                            : service === 'redis'
                              ? 'Redis 缓存'
                              : service === 'workers'
                                ? '后台任务'
                                : service}
                        </h4>
                        <Tag color={serviceStatus ? 'success' : 'error'}>
                          {serviceStatus ? '正常运行' : '服务异常'}
                        </Tag>
                      </Card>
                    ))}
                  </div>
                  <DescriptionsCard
                    items={[
                      ['整体状态', healthMeta.label],
                      ['版本号', health.version || '--'],
                      ['运行时长', formatUptime(health.uptime || 0)],
                      ['最后刷新', new Date().toLocaleTimeString('zh-CN')],
                    ]}
                  />
                </>
              ) : (
                <Empty description="暂无系统健康数据" />
              ),
            },
            {
              key: 'metrics',
              label: (
                <span>
                  <MonitorOutlined /> 性能指标
                </span>
              ),
              children: metrics ? (
                <>
                  <Row gutter={[16, 16]} className="mb-4">
                    {[
                      ['CPU 使用率', metrics.cpu_usage, 'cpu'],
                      ['内存使用率', metrics.memory_usage, 'memory'],
                      ['磁盘使用率', metrics.disk_usage, 'disk'],
                    ].map(([label, value, key]) => (
                      <Col xs={24} md={8} key={key}>
                        <Card className="inner-panel-card monitor-circle-card" bordered={false}>
                          <Progress
                            type="circle"
                            percent={Math.round(Number(value || 0))}
                            strokeColor={getUsageColor(Number(value || 0))}
                            format={(percent) => `${percent}%`}
                          />
                          <div className="monitor-circle-label">{label}</div>
                        </Card>
                      </Col>
                    ))}
                  </Row>
                  <Row gutter={[16, 16]}>
                    <Col xs={24} md={6}>
                      <Card className="inner-panel-card" bordered={false}>
                        <Statistic title="活跃连接数" value={metrics.active_connections || 0} />
                      </Card>
                    </Col>
                    <Col xs={24} md={6}>
                      <Card className="inner-panel-card" bordered={false}>
                        <Statistic title="24 小时请求数" value={(metrics.request_count_24h || 0).toLocaleString()} />
                      </Card>
                    </Col>
                    <Col xs={24} md={6}>
                      <Card className="inner-panel-card" bordered={false}>
                        <Statistic title="24 小时错误数" value={metrics.error_count_24h || 0} />
                      </Card>
                    </Col>
                    <Col xs={24} md={6}>
                      <Card className="inner-panel-card" bordered={false}>
                        <Statistic title="平均响应时间" value={metrics.average_response_time || 0} suffix="ms" />
                      </Card>
                    </Col>
                  </Row>
                </>
              ) : (
                <Empty description="暂无性能指标数据" />
              ),
            },
            {
              key: 'logs',
              label: (
                <span>
                  <DatabaseOutlined /> 系统日志
                </span>
              ),
              children:
                logs.length > 0 ? (
                  <Table
                    dataSource={logs}
                    columns={logColumns}
                    rowKey="id"
                    pagination={{
                      pageSize: 10,
                      showSizeChanger: true,
                      showQuickJumper: true,
                    }}
                    scroll={{ y: 400 }}
                  />
                ) : (
                  <Empty description="暂无系统日志数据" />
                ),
            },
          ]}
        />
      </Card>
    </div>
  );
};

const DescriptionsCard: React.FC<{ items: Array<[string, string]> }> = ({ items }) => (
  <Card className="inner-panel-card monitor-description-card" bordered={false}>
    <div className="monitor-description-grid">
      {items.map(([label, value]) => (
        <div key={label} className="monitor-description-item">
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  </Card>
);

export default SystemMonitor;
