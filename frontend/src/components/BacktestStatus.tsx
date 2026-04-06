import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Progress,
  Result,
  Space,
  Spin,
  Typography,
  message,
} from 'antd';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  EyeOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import ApiService, { type BacktestStatus as BacktestStatusType } from '../services/api';

const { Text } = Typography;

interface BacktestStatusProps {
  runId: string;
  onComplete: (result: any) => void;
}

const BacktestStatus: React.FC<BacktestStatusProps> = ({ runId, onComplete }) => {
  const [status, setStatus] = useState<BacktestStatusType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = async () => {
    try {
      const response = await ApiService.getBacktestStatus(runId);
      if (response.success && response.data) {
        setStatus(response.data);
        setError(null);

        if (response.data.status === 'completed') {
          const resultResponse = await ApiService.getBacktestResult(runId);
          if (resultResponse.success && resultResponse.data) {
            onComplete(resultResponse.data);
          }
        }
      } else {
        setError(response.message || '获取回测状态失败');
      }
    } catch (err: any) {
      console.error('Get status error:', err);
      setError(err.response?.data?.message || '获取回测状态失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();

    const interval = setInterval(() => {
      if (status?.status === 'running' || status?.status === 'pending') {
        fetchStatus();
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [runId, status?.status]);

  const statusMeta = useMemo(() => {
    switch (status?.status) {
      case 'completed':
        return {
          title: '回测已完成',
          icon: <CheckCircleOutlined />,
          color: '#0f9a64',
          progress: 100,
        };
      case 'failed':
        return {
          title: '回测执行失败',
          icon: <ExclamationCircleOutlined />,
          color: '#c23846',
          progress: 0,
        };
      case 'running':
        return {
          title: '回测执行中',
          icon: <ClockCircleOutlined />,
          color: '#1b4dd8',
          progress: 62,
        };
      default:
        return {
          title: '回测排队中',
          icon: <ClockCircleOutlined />,
          color: '#c97d1d',
          progress: 18,
        };
    }
  }, [status?.status]);

  const handleViewResult = async () => {
    try {
      const response = await ApiService.getBacktestResult(runId);
      if (response.success && response.data) {
        onComplete(response.data);
      } else {
        message.error('获取回测结果失败');
      }
    } catch {
      message.error('获取回测结果失败');
    }
  };

  if (loading) {
    return (
      <Card className="feature-card backtest-status-card">
        <div className="loading-container">
          <Spin size="large" />
          <div className="loading-text">正在获取回测状态...</div>
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="feature-card backtest-status-card">
        <Result
          status="error"
          title="回测状态获取失败"
          subTitle={error}
          extra={
            <Button icon={<ReloadOutlined />} onClick={fetchStatus}>
              重试
            </Button>
          }
        />
      </Card>
    );
  }

  if (!status) {
    return (
      <Card className="feature-card backtest-status-card">
        <Alert message="未找到回测状态" type="warning" showIcon />
      </Card>
    );
  }

  return (
    <Card
      className="feature-card backtest-status-card"
      title={
        <Space>
          {statusMeta.icon}
          <span>回测状态监控</span>
        </Space>
      }
      extra={
        <Space>
          <Button
            icon={<ReloadOutlined />}
            onClick={fetchStatus}
            className="secondary-button"
          >
            刷新
          </Button>
          {status.status === 'completed' && (
            <Button type="primary" icon={<EyeOutlined />} onClick={handleViewResult}>
              查看结果
            </Button>
          )}
        </Space>
      }
    >
      <div className="status-hero">
        <div className="status-hero-main">
          <span className="section-kicker">Experiment Runtime</span>
          <h3>
            {status.ticker} · {statusMeta.title}
          </h3>
          <p>
            任务编号 #{status.task_id.slice(0, 8)}，系统会在后台持续更新该回测任务的执行进度与最终结果。
          </p>
        </div>
        <div className="status-hero-side">
          <span className="status-chip" style={{ color: statusMeta.color }}>
            {status.status?.toUpperCase()}
          </span>
        </div>
      </div>

      <div className="status-progress-panel">
        <div className="analysis-status-row">
          <span className="analysis-status-label">任务进度</span>
          <span>{statusMeta.progress}%</span>
        </div>
        <Progress
          percent={statusMeta.progress}
          showInfo={false}
          strokeColor={statusMeta.color}
          status={status.status === 'failed' ? 'exception' : 'active'}
        />
      </div>

      <Descriptions bordered column={2} className="status-descriptions">
        <Descriptions.Item label="股票代码">{status.ticker}</Descriptions.Item>
        <Descriptions.Item label="回测区间">
          {status.start_date} 至 {status.end_date}
        </Descriptions.Item>
        <Descriptions.Item label="创建时间">
          {new Date(status.created_at).toLocaleString('zh-CN')}
        </Descriptions.Item>
        <Descriptions.Item label="开始时间">
          {status.started_at ? new Date(status.started_at).toLocaleString('zh-CN') : '等待执行'}
        </Descriptions.Item>
        <Descriptions.Item label="完成时间">
          {status.completed_at ? new Date(status.completed_at).toLocaleString('zh-CN') : '尚未完成'}
        </Descriptions.Item>
        <Descriptions.Item label="后台运行">
          {status.is_running ? '是' : '否'}
        </Descriptions.Item>
      </Descriptions>

      {status.error_message && (
        <Alert
          className="mb-4"
          message="错误信息"
          description={status.error_message}
          type="error"
          showIcon
        />
      )}

      {status.runtime_error && (
        <Alert
          className="mb-4"
          message="运行时异常"
          description={status.runtime_error}
          type="error"
          showIcon
        />
      )}

      {status.is_running && (
        <Alert
          message="后台任务正在运行"
          description="你可以继续停留在本页，系统会自动刷新；也可以切换到别的模块，稍后回来查看结果。"
          type="info"
          showIcon
        />
      )}

      {!status.is_running && status.status === 'pending' && (
        <Text type="secondary">任务正在排队，通常会在短时间内开始执行。</Text>
      )}
    </Card>
  );
};

export default BacktestStatus;
