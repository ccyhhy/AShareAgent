import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Divider,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import {
  CalculatorOutlined,
  FundProjectionScreenOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import type { DcfAssumptions } from '../services/api';
import {
  buildDcfDefaultsFromAnalysis,
  computeReferenceDiscountRatePct,
  computeDcfWorkbench,
  formatCurrency,
  formatPercent,
  getDcfParameterExplanation,
} from '../utils/dcfView';

const { Paragraph, Text, Title } = Typography;

interface DcfWorkbenchPageProps {
  initialData?: any;
}

const percentFormatter = (value?: number | string | null) =>
  value == null || value === '' ? '' : `${value}%`;

const DcfWorkbenchPage: React.FC<DcfWorkbenchPageProps> = ({ initialData }) => {
  const defaults = useMemo(() => buildDcfDefaultsFromAnalysis(initialData), [initialData]);
  const [inputs, setInputs] = useState<DcfAssumptions>(defaults.assumptions);

  useEffect(() => {
    setInputs(defaults.assumptions);
  }, [defaults]);

  const result = useMemo(() => computeDcfWorkbench(inputs), [inputs]);
  const referenceDiscountRatePct = useMemo(() => computeReferenceDiscountRatePct(inputs), [inputs]);

  const updateField = <K extends keyof DcfAssumptions>(key: K, value: DcfAssumptions[K]) => {
    setInputs((current) => ({
      ...current,
      [key]: value,
    }));
  };

  const summaryTone =
    !result.isValid ? 'default' : result.marginOfSafety != null && result.marginOfSafety >= 0.2
      ? 'error'
      : result.marginOfSafety != null && result.marginOfSafety <= -0.2
        ? 'success'
        : 'processing';

  const columns = [
    { title: '年份', dataIndex: 'year', key: 'year', width: 80 },
    { title: '阶段', dataIndex: 'phase', key: 'phase', width: 120 },
    {
      title: '预测自由现金流',
      dataIndex: 'projectedFcf',
      key: 'projectedFcf',
      render: (value: number) => formatCurrency(value),
    },
    {
      title: '折现后现金流',
      dataIndex: 'discountedFcf',
      key: 'discountedFcf',
      render: (value: number) => formatCurrency(value),
    },
  ];

  return (
    <div className="dcf-workbench-page">
      <Card className="dcf-workbench-hero">
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <Space align="center" wrap>
            <Tag color="blue" icon={<CalculatorOutlined />}>
              DCF 估值工具
            </Tag>
            <Tag>{defaults.sourceLabel}</Tag>
          </Space>
          <Title level={3} style={{ margin: 0 }}>
            DCF 假设调参与估值演示
          </Title>
          <Paragraph style={{ marginBottom: 0 }}>
            这个页面把 DCF 的主观假设显式展开。你可以直接修改现金流、增长率、折现率和终值口径，观察估值如何变化。
          </Paragraph>
        </Space>
      </Card>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} xl={12}>
          <Card
            className="dcf-panel-card"
            title="核心输入"
            extra={
              <Button
                icon={<ReloadOutlined />}
                onClick={() => setInputs(defaults.assumptions)}
                className="secondary-button"
                size="small"
              >
                恢复默认值
              </Button>
            }
          >
            <div className="dcf-form-grid">
              <div className="dcf-form-item">
                <Text className="dcf-form-label">股票代码</Text>
                <Input value={inputs.ticker} onChange={(event) => updateField('ticker', event.target.value)} />
              </div>
              <div className="dcf-form-item">
                <Text className="dcf-form-label">当前价格</Text>
                <InputNumber
                  value={inputs.currentPrice}
                  min={0}
                  precision={2}
                  style={{ width: '100%' }}
                  onChange={(value) => updateField('currentPrice', Number(value || 0))}
                />
              </div>
              <div className="dcf-form-item">
                <Text className="dcf-form-label">基础自由现金流</Text>
                <InputNumber
                  value={inputs.baseFreeCashFlow}
                  min={0}
                  precision={2}
                  style={{ width: '100%' }}
                  onChange={(value) => updateField('baseFreeCashFlow', Number(value || 0))}
                />
              </div>
              <div className="dcf-form-item">
                <Text className="dcf-form-label">折现率</Text>
                <InputNumber
                  value={inputs.discountRatePct}
                  min={0.1}
                  max={50}
                  precision={2}
                  formatter={percentFormatter}
                  parser={(value) => Number(String(value || '').replace('%', ''))}
                  style={{ width: '100%' }}
                  onChange={(value) => updateField('discountRatePct', Number(value || 0))}
                />
              </div>
              <div className="dcf-form-item">
                <Text className="dcf-form-label">第一阶段增长率</Text>
                <InputNumber
                  value={inputs.stage1GrowthRatePct}
                  min={-50}
                  max={100}
                  precision={2}
                  formatter={percentFormatter}
                  parser={(value) => Number(String(value || '').replace('%', ''))}
                  style={{ width: '100%' }}
                  onChange={(value) => updateField('stage1GrowthRatePct', Number(value || 0))}
                />
              </div>
              <div className="dcf-form-item">
                <Text className="dcf-form-label">第一阶段年数</Text>
                <InputNumber
                  value={inputs.stage1Years}
                  min={1}
                  max={15}
                  precision={0}
                  style={{ width: '100%' }}
                  onChange={(value) => updateField('stage1Years', Number(value || 1))}
                />
              </div>
              <div className="dcf-form-item">
                <Text className="dcf-form-label">第二阶段增长率</Text>
                <InputNumber
                  value={inputs.stage2GrowthRatePct}
                  min={-50}
                  max={100}
                  precision={2}
                  formatter={percentFormatter}
                  parser={(value) => Number(String(value || '').replace('%', ''))}
                  style={{ width: '100%' }}
                  onChange={(value) => updateField('stage2GrowthRatePct', Number(value || 0))}
                />
              </div>
              <div className="dcf-form-item">
                <Text className="dcf-form-label">第二阶段年数</Text>
                <InputNumber
                  value={inputs.stage2Years}
                  min={1}
                  max={15}
                  precision={0}
                  style={{ width: '100%' }}
                  onChange={(value) => updateField('stage2Years', Number(value || 1))}
                />
              </div>
              <div className="dcf-form-item">
                <Text className="dcf-form-label">永续增长率</Text>
                <InputNumber
                  value={inputs.terminalGrowthRatePct}
                  min={-5}
                  max={20}
                  precision={2}
                  formatter={percentFormatter}
                  parser={(value) => Number(String(value || '').replace('%', ''))}
                  style={{ width: '100%' }}
                  onChange={(value) => updateField('terminalGrowthRatePct', Number(value || 0))}
                />
              </div>
            </div>

            <Collapse
              className="dcf-advanced-panel"
              items={[
                {
                  key: 'advanced',
                  label: '高级参数',
                  children: (
                    <div className="dcf-form-grid">
                      <div className="dcf-form-item">
                        <Text className="dcf-form-label">总股本</Text>
                        <InputNumber
                          value={inputs.sharesOutstanding}
                          min={0}
                          precision={2}
                          style={{ width: '100%' }}
                          onChange={(value) => updateField('sharesOutstanding', Number(value || 0))}
                        />
                      </div>
                      <div className="dcf-form-item">
                        <Text className="dcf-form-label">当前市值</Text>
                        <InputNumber
                          value={inputs.marketCap}
                          min={0}
                          precision={2}
                          style={{ width: '100%' }}
                          onChange={(value) => updateField('marketCap', Number(value || 0))}
                        />
                      </div>
                      <div className="dcf-form-item">
                        <Text className="dcf-form-label">净债务</Text>
                        <InputNumber
                          value={inputs.netDebt}
                          precision={2}
                          style={{ width: '100%' }}
                          onChange={(value) => updateField('netDebt', Number(value || 0))}
                        />
                      </div>
                      <div className="dcf-form-item">
                        <Text className="dcf-form-label">税率</Text>
                        <InputNumber
                          value={inputs.taxRatePct}
                          min={0}
                          max={100}
                          precision={2}
                          formatter={percentFormatter}
                          parser={(value) => Number(String(value || '').replace('%', ''))}
                          style={{ width: '100%' }}
                          onChange={(value) => updateField('taxRatePct', Number(value || 0))}
                        />
                      </div>
                      <div className="dcf-form-item">
                        <Text className="dcf-form-label">Beta</Text>
                        <InputNumber
                          value={inputs.beta}
                          min={0}
                          max={5}
                          precision={2}
                          style={{ width: '100%' }}
                          onChange={(value) => updateField('beta', Number(value || 0))}
                        />
                      </div>
                      <div className="dcf-form-item">
                        <Text className="dcf-form-label">权益风险溢价</Text>
                        <InputNumber
                          value={inputs.equityRiskPremiumPct}
                          min={0}
                          max={20}
                          precision={2}
                          formatter={percentFormatter}
                          parser={(value) => Number(String(value || '').replace('%', ''))}
                          style={{ width: '100%' }}
                          onChange={(value) => updateField('equityRiskPremiumPct', Number(value || 0))}
                        />
                      </div>
                      <div className="dcf-form-item">
                        <Text className="dcf-form-label">无风险利率</Text>
                        <InputNumber
                          value={inputs.riskFreeRatePct}
                          min={0}
                          max={20}
                          precision={2}
                          formatter={percentFormatter}
                          parser={(value) => Number(String(value || '').replace('%', ''))}
                          style={{ width: '100%' }}
                          onChange={(value) => updateField('riskFreeRatePct', Number(value || 0))}
                        />
                      </div>
                      <div className="dcf-form-item">
                        <Text className="dcf-form-label">债务成本</Text>
                        <InputNumber
                          value={inputs.debtCostPct}
                          min={0}
                          max={30}
                          precision={2}
                          formatter={percentFormatter}
                          parser={(value) => Number(String(value || '').replace('%', ''))}
                          style={{ width: '100%' }}
                          onChange={(value) => updateField('debtCostPct', Number(value || 0))}
                        />
                      </div>
                      <div className="dcf-form-item">
                        <Text className="dcf-form-label">债务占比</Text>
                        <InputNumber
                          value={inputs.debtRatioPct}
                          min={0}
                          max={100}
                          precision={2}
                          formatter={percentFormatter}
                          parser={(value) => Number(String(value || '').replace('%', ''))}
                          style={{ width: '100%' }}
                          onChange={(value) => updateField('debtRatioPct', Number(value || 0))}
                        />
                      </div>
                      <div className="dcf-form-item">
                        <Text className="dcf-form-label">终值口径</Text>
                        <Select
                          value={inputs.terminalMethod}
                          style={{ width: '100%' }}
                          onChange={(value) => updateField('terminalMethod', value)}
                          options={[
                            { value: 'gordon', label: 'Gordon 永续增长' },
                            { value: 'multiple', label: '现金流倍数法' },
                          ]}
                        />
                      </div>
                      {inputs.terminalMethod === 'multiple' && (
                        <div className="dcf-form-item">
                          <Text className="dcf-form-label">终值倍数</Text>
                          <InputNumber
                            value={inputs.terminalMultiple}
                            min={1}
                            max={50}
                            precision={2}
                            style={{ width: '100%' }}
                            onChange={(value) => updateField('terminalMultiple', Number(value || 0))}
                          />
                        </div>
                      )}
                    </div>
                  ),
                },
              ]}
            />
            <div className="dcf-reference-rate">
              <div>
                <Text strong>高级参数推导参考 WACC</Text>
                <Paragraph style={{ margin: '6px 0 0' }}>
                  当前高级参数推导出的参考折现率约为 {referenceDiscountRatePct.toFixed(2)}%。
                  如果你希望它直接作用到估值，可以一键回填到折现率。
                </Paragraph>
              </div>
              <Button
                className="secondary-button"
                onClick={() => updateField('discountRatePct', referenceDiscountRatePct)}
              >
                用参考 WACC 回填折现率
              </Button>
            </div>
          </Card>
        </Col>

        <Col xs={24} xl={12}>
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Card className="dcf-panel-card" title="估值结果">
              {!result.isValid ? (
                <Alert
                  type="warning"
                  showIcon
                  message="当前参数组合无法形成有效 DCF 结论"
                  description={result.reasons.join('；')}
                />
              ) : (
                <>
                  <div className="dcf-result-grid">
                    <div className="dcf-result-item">
                      <span>企业价值</span>
                      <strong>{formatCurrency(result.enterpriseValue)}</strong>
                    </div>
                    <div className="dcf-result-item">
                      <span>股权价值</span>
                      <strong>{formatCurrency(result.equityValue)}</strong>
                    </div>
                    <div className="dcf-result-item">
                      <span>每股估值</span>
                      <strong>{result.intrinsicValuePerShare.toFixed(2)} 元</strong>
                    </div>
                    <div className="dcf-result-item">
                      <span>安全边际</span>
                      <strong>{formatPercent(result.marginOfSafety)}</strong>
                    </div>
                  </div>
                  <Divider />
                  <Space direction="vertical" size={10} style={{ width: '100%' }}>
                    <Tag color={summaryTone}>{result.conclusion}</Tag>
                    <Paragraph style={{ marginBottom: 0 }}>{result.sensitivityHint}</Paragraph>
                    <Text type="secondary">
                      当前价格 {inputs.currentPrice.toFixed(2)} 元，对应市值参考 {formatCurrency(result.marketCap)}。
                    </Text>
                  </Space>
                </>
              )}
            </Card>

            <Card className="dcf-panel-card" title="参数解释">
              <div className="dcf-explanation-list">
                {[
                  'discountRatePct',
                  'stage1GrowthRatePct',
                  'stage2GrowthRatePct',
                  'terminalGrowthRatePct',
                  'baseFreeCashFlow',
                  'currentPrice',
                ].map((key) => (
                  <div className="dcf-explanation-item" key={key}>
                    {getDcfParameterExplanation(key as keyof DcfAssumptions, inputs)}
                  </div>
                ))}
              </div>
            </Card>
          </Space>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} xl={14}>
          <Card
            className="dcf-panel-card"
            title="现金流投影明细"
            extra={<Tag icon={<FundProjectionScreenOutlined />}>实时重算</Tag>}
          >
            <Table
              rowKey={(record) => `${record.phase}-${record.year}`}
              size="small"
              pagination={false}
              dataSource={result.projectionRows}
              columns={columns}
            />
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          <Card className="dcf-panel-card" title="建模说明">
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Paragraph style={{ marginBottom: 0 }}>
                当前工具页使用“两段增长 + 终值”的 DCF 演示口径。前两段增长对应高增长期和过渡期，最后通过永续增长或倍数法计算终值。
              </Paragraph>
              <Paragraph style={{ marginBottom: 0 }}>
                如果你把折现率调高，估值通常会明显下降；如果把永续增长率调高，终值贡献会迅速放大。这也是 DCF 主观性的来源。
              </Paragraph>
              <Alert
                type="info"
                showIcon
                message="答辩建议"
                description="演示时优先调折现率、第一阶段增长率和永续增长率，这三个参数最能体现估值对假设的敏感性。"
              />
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default DcfWorkbenchPage;
