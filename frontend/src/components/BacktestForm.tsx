import React, { useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Collapse,
  Col,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Switch,
  Typography,
  message,
} from 'antd';
import {
  PlayCircleOutlined,
  RadarChartOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import ApiService, { type BacktestRequest } from '../services/api';

const { RangePicker } = DatePicker;
const { Paragraph, Text } = Typography;

interface BacktestFormProps {
  onBacktestStart: (runId: string) => void;
}

const BacktestForm: React.FC<BacktestFormProps> = ({ onBacktestStart }) => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const enableAdvanced = Form.useWatch('enable_advanced', form);

  const handleSubmit = async (values: any) => {
    setLoading(true);
    try {
      const request: BacktestRequest = {
        ticker: values.ticker,
        start_date: values.dateRange[0].format('YYYY-MM-DD'),
        end_date: values.dateRange[1].format('YYYY-MM-DD'),
        initial_capital: values.initial_capital || 100000,
        num_of_news: values.num_of_news || 5,
        time_granularity: values.time_granularity,
        benchmark_type: values.benchmark_type,
        rebalance_frequency: values.rebalance_frequency,
      };

      if (values.enable_advanced) {
        request.agent_frequencies = {
          market_data: values.market_data_freq || 'daily',
          technical: values.technical_freq || 'daily',
          fundamentals: values.fundamentals_freq || 'weekly',
          sentiment: values.sentiment_freq || 'daily',
          valuation: values.valuation_freq || 'monthly',
          macro: values.macro_freq || 'weekly',
          portfolio: values.portfolio_freq || 'daily',
        };

        if (values.transaction_cost !== undefined) {
          request.transaction_cost = values.transaction_cost;
        }

        if (values.slippage !== undefined) {
          request.slippage = values.slippage;
        }
      }

      const response = await ApiService.startBacktest(request);
      if (response.success && response.data) {
        message.success('回测任务已启动');
        onBacktestStart(response.data.run_id);
        form.resetFields();
      } else {
        message.error(response.message || '启动回测失败');
      }
    } catch (error: any) {
      console.error('Backtest start error:', error);
      message.error(error.response?.data?.detail || '启动回测失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="backtest-page backtest-form-page">
      <Card className="feature-card backtest-hero-card mb-4">
        <div className="section-hero">
          <div>
            <span className="section-kicker">Strategy Lab</span>
            <h3 className="section-title">多智能体策略回测实验台</h3>
            <p className="section-description">
              这一页用于验证异构多智能体在不同时间区间、成本条件和执行频率下的表现。
              我们保留原有回测能力，但改造成更适合展示和答辩截图的界面结构。
            </p>
          </div>
          <div className="backtest-highlight">
            <span className="backtest-highlight-label">实验焦点</span>
            <strong>收益 / 风险 / 成本 / 执行频率</strong>
          </div>
        </div>
      </Card>

      <Card
        title={
          <Space>
            <PlayCircleOutlined />
            <span>启动策略回测</span>
          </Space>
        }
        className="feature-card"
      >
        <Alert
          className="mb-4"
          type="info"
          showIcon
          message="当前页面会将基础参数和高级配置分层呈现"
          description="默认模式适合快速运行回测；高级配置用于对比异构 Agent 的执行频率、交易成本和时间粒度。"
        />

        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          className="modern-form"
          initialValues={{
            initial_capital: 100000,
            num_of_news: 5,
            enable_advanced: false,
            market_data_freq: 'daily',
            technical_freq: 'daily',
            fundamentals_freq: 'weekly',
            sentiment_freq: 'daily',
            valuation_freq: 'monthly',
            macro_freq: 'weekly',
            portfolio_freq: 'daily',
            time_granularity: 'daily',
            benchmark_type: 'spe',
            rebalance_frequency: 'daily',
            transaction_cost: 0.001,
            slippage: 0.0005,
          }}
        >
          <div className="parameter-grid">
            <Form.Item
              name="ticker"
              label="股票代码"
              rules={[
                { required: true, message: '请输入股票代码' },
                { pattern: /^[0-9]{6}$/, message: '请输入 6 位数字股票代码' },
              ]}
            >
              <Input placeholder="例如：600519" maxLength={6} />
            </Form.Item>

            <Form.Item
              name="dateRange"
              label="回测区间"
              rules={[{ required: true, message: '请选择回测区间' }]}
            >
              <RangePicker
                style={{ width: '100%' }}
                format="YYYY-MM-DD"
                disabledDate={(current) => current && current > dayjs().endOf('day')}
                placeholder={['开始日期', '结束日期']}
              />
            </Form.Item>

            <Form.Item
              name="initial_capital"
              label="初始资金"
              rules={[{ required: true, message: '请输入初始资金' }]}
            >
              <InputNumber
                min={1000}
                max={10000000}
                step={1000}
                style={{ width: '100%' }}
                formatter={(value) =>
                  `¥${String(value ?? '').replace(/\B(?=(\d{3})+(?!\d))/g, ',')}`
                }
                parser={(value) => Number(String(value ?? '').replace(/[¥,\s]/g, '')) as any}
              />
            </Form.Item>

            <Form.Item
              name="num_of_news"
              label="新闻样本数"
              tooltip="情绪与宏观相关分析可参考的新闻条数"
            >
              <InputNumber min={1} max={100} style={{ width: '100%' }} />
            </Form.Item>
          </div>

          <Card className="inner-panel-card backtest-parameter-card" bordered={false}>
            <div className="inner-panel-head">
              <div>
                <span className="section-kicker">Baseline Setup</span>
                <h4 className="inner-panel-title">基础实验参数</h4>
              </div>
              <Text type="secondary">默认配置适合快速验证策略链路</Text>
            </div>

            <Row gutter={16}>
              <Col xs={24} md={8}>
                <Form.Item
                  name="time_granularity"
                  label="时间粒度"
                  tooltip="决定策略执行与回测数据采样频率"
                >
                  <Select
                    options={[
                      { value: 'minute', label: '分钟级' },
                      { value: 'hourly', label: '小时级' },
                      { value: 'daily', label: '日级' },
                      { value: 'weekly', label: '周级' },
                    ]}
                  />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item
                  name="benchmark_type"
                  label="基准策略"
                  tooltip="用于和多智能体策略做对比的参照对象"
                >
                  <Select
                    options={[
                      { value: 'spe', label: 'SPE 买入并持有' },
                      { value: 'csi300', label: 'CSI300 指数' },
                      { value: 'equal_weight', label: '等权组合' },
                      { value: 'momentum', label: '动量策略' },
                      { value: 'mean_reversion', label: '均值回归' },
                    ]}
                  />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item
                  name="rebalance_frequency"
                  label="调仓频率"
                  tooltip="控制组合重平衡节奏"
                >
                  <Select
                    options={[
                      { value: 'daily', label: '每日' },
                      { value: 'weekly', label: '每周' },
                      { value: 'monthly', label: '每月' },
                      { value: 'quarterly', label: '每季度' },
                    ]}
                  />
                </Form.Item>
              </Col>
            </Row>
          </Card>

          <Collapse
            ghost
            className="backtest-collapse"
            items={[
              {
                key: 'advanced',
                label: (
                  <Space>
                    <SettingOutlined />
                    <span>高级配置</span>
                  </Space>
                ),
                children: (
                  <div className="advanced-config-shell">
                    <Form.Item name="enable_advanced" valuePropName="checked">
                      <div className="advanced-toggle-row">
                        <Switch />
                        <div>
                          <strong>启用高级配置</strong>
                          <Paragraph className="advanced-toggle-copy">
                            打开后可以自定义交易成本、滑点和各 Agent 的执行频率。
                          </Paragraph>
                        </div>
                      </div>
                    </Form.Item>

                    {enableAdvanced ? (
                      <>
                        <Card className="inner-panel-card" bordered={false}>
                          <div className="inner-panel-head">
                            <div>
                              <span className="section-kicker">Trading Cost</span>
                              <h4 className="inner-panel-title">交易成本假设</h4>
                            </div>
                            <Text type="secondary">控制手续费和滑点，方便做成本敏感性实验</Text>
                          </div>
                          <Row gutter={16}>
                            <Col xs={24} md={12}>
                              <Form.Item
                                name="transaction_cost"
                                label="手续费率"
                                tooltip="例如 0.001 表示 0.1%"
                              >
                                <InputNumber
                                  min={0}
                                  max={0.01}
                                  step={0.0001}
                                  precision={4}
                                  style={{ width: '100%' }}
                                  formatter={(value) =>
                                    `${(Number(value ?? 0) * 100).toFixed(3)}%`
                                  }
                                  parser={(value) =>
                                    Number(String(value ?? '').replace('%', '')) / 100 as any
                                  }
                                />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={12}>
                              <Form.Item
                                name="slippage"
                                label="滑点率"
                                tooltip="例如 0.0005 表示 0.05%"
                              >
                                <InputNumber
                                  min={0}
                                  max={0.005}
                                  step={0.0001}
                                  precision={4}
                                  style={{ width: '100%' }}
                                  formatter={(value) =>
                                    `${(Number(value ?? 0) * 100).toFixed(3)}%`
                                  }
                                  parser={(value) =>
                                    Number(String(value ?? '').replace('%', '')) / 100 as any
                                  }
                                />
                              </Form.Item>
                            </Col>
                          </Row>
                        </Card>

                        <Card className="inner-panel-card" bordered={false}>
                          <div className="inner-panel-head">
                            <div>
                              <span className="section-kicker">Agent Frequency</span>
                              <h4 className="inner-panel-title">异构 Agent 执行频率</h4>
                            </div>
                            <Text type="secondary">用于模拟不同分析模块的时间尺度差异</Text>
                          </div>
                          <Alert
                            className="mb-4"
                            type="info"
                            showIcon
                            message="频率说明"
                            description="日级适合高频数据、周级适合常规分析、月级适合估值与基本面，条件触发适合波动或事件驱动场景。"
                          />
                          <div className="parameter-grid parameter-grid--compact">
                            {[
                              ['market_data_freq', '市场数据 Agent'],
                              ['technical_freq', '技术分析 Agent'],
                              ['fundamentals_freq', '基本面 Agent'],
                              ['sentiment_freq', '情绪分析 Agent'],
                              ['valuation_freq', '估值 Agent'],
                              ['macro_freq', '宏观 Agent'],
                              ['portfolio_freq', '组合管理 Agent'],
                            ].map(([name, label]) => (
                              <Form.Item key={name} name={name} label={label}>
                                <Select
                                  options={[
                                    { value: 'daily', label: '每日' },
                                    { value: 'weekly', label: '每周' },
                                    { value: 'monthly', label: '每月' },
                                    { value: 'conditional', label: '条件触发' },
                                  ]}
                                />
                              </Form.Item>
                            ))}
                          </div>
                        </Card>
                      </>
                    ) : (
                      <Card className="inner-panel-card advanced-empty-card" bordered={false}>
                        <Space align="start">
                          <RadarChartOutlined className="advanced-empty-icon" />
                          <div>
                            <strong>当前为简化模式</strong>
                            <Paragraph className="advanced-toggle-copy">
                              开启高级配置后，这里会显示异构 Agent 执行频率、交易成本与滑点设置。
                            </Paragraph>
                          </div>
                        </Space>
                      </Card>
                    )}
                  </div>
                ),
              },
            ]}
          />

          <div className="backtest-action-row">
            <Button type="primary" htmlType="submit" loading={loading} size="large">
              运行回测
            </Button>
            <Text type="secondary">提交后系统会在后台执行回测，并在本页实时更新状态。</Text>
          </div>
        </Form>
      </Card>
    </div>
  );
};

export default BacktestForm;
