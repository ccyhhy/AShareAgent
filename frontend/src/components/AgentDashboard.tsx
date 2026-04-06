import React, { useEffect, useMemo, useState } from 'react';
import {
  Badge,
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  Input,
  Modal,
  Row,
  Select,
  Space,
  Table,
  Typography,
  message,
} from 'antd';
import {
  EditOutlined,
  EyeOutlined,
  PlusOutlined,
  ReloadOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import {
  ApiService,
  type AgentCreateRequest,
  type AgentUpdateRequest,
  type ManagedAgent,
} from '../services/api';
import moment from 'moment';

const { TextArea } = Input;
const { Paragraph, Text } = Typography;

type AgentFormValues = AgentCreateRequest & {
  config?: string | Record<string, any>;
};

type AgentTypeMeta = {
  label: string;
  tone: string;
  description: string;
};

const AGENT_TYPE_META: Record<string, AgentTypeMeta> = {
  rule_engine: {
    label: '规则引擎',
    tone: 'rule',
    description: '基于阈值和规则集做快速决策，适合技术面和估值边界判断。',
  },
  quantitative_model: {
    label: '量化模型',
    tone: 'quant',
    description: '依赖数学公式与财务模型，强调可解释性与复现性。',
  },
  statistical_model: {
    label: '统计模型',
    tone: 'stats',
    description: '聚焦风险暴露、波动与历史分布特征。',
  },
  llm_rag: {
    label: 'LLM + RAG',
    tone: 'rag',
    description: '结合检索增强与大模型推理，适合护城河与知识复用场景。',
  },
  hybrid_rule_llm: {
    label: '规则 + LLM',
    tone: 'hybrid',
    description: '先规则筛查，再让大模型做深度补充与解释。',
  },
  llm: {
    label: '纯 LLM',
    tone: 'llm',
    description: '以语言模型为主，适合行业周期、宏观语义类分析。',
  },
  analysis: {
    label: '分析型',
    tone: 'rule',
    description: '原系统中的分析节点。',
  },
  trading: {
    label: '交易型',
    tone: 'quant',
    description: '原系统中的交易执行节点。',
  },
  risk: {
    label: '风控型',
    tone: 'stats',
    description: '原系统中的风险评估节点。',
  },
  sentiment: {
    label: '情绪型',
    tone: 'hybrid',
    description: '原系统中的情绪与文本分析节点。',
  },
  macro: {
    label: '宏观型',
    tone: 'llm',
    description: '原系统中的宏观分析节点。',
  },
};

const AGENT_TYPE_OPTIONS = [
  { value: 'rule_engine', label: '规则引擎型 Agent' },
  { value: 'quantitative_model', label: '量化模型型 Agent' },
  { value: 'statistical_model', label: '统计模型型 Agent' },
  { value: 'llm_rag', label: 'LLM + RAG Agent' },
  { value: 'hybrid_rule_llm', label: '规则 + LLM Agent' },
  { value: 'llm', label: '纯 LLM Agent' },
  { value: 'analysis', label: '分析型 Agent（兼容旧系统）' },
  { value: 'trading', label: '交易型 Agent（兼容旧系统）' },
  { value: 'risk', label: '风控型 Agent（兼容旧系统）' },
  { value: 'sentiment', label: '情绪型 Agent（兼容旧系统）' },
  { value: 'macro', label: '宏观型 Agent（兼容旧系统）' },
];

const STATUS_LABELS: Record<string, string> = {
  active: '活跃',
  inactive: '停用',
  maintenance: '维护中',
  running: '运行中',
  idle: '空闲',
  error: '异常',
};

const getTypeMeta = (agentType?: string): AgentTypeMeta => {
  const key = agentType?.toLowerCase() || '';
  return (
    AGENT_TYPE_META[key] || {
      label: agentType || '未分类',
      tone: 'default',
      description: '当前节点尚未声明异构类别，可在后续联调时补齐。',
    }
  );
};

const getStatusTone = (status?: string): string => {
  switch ((status || '').toLowerCase()) {
    case 'active':
    case 'running':
      return 'active';
    case 'maintenance':
      return 'maintenance';
    case 'error':
      return 'error';
    default:
      return 'inactive';
  }
};

const parseConfigPayload = (
  values: AgentCreateRequest | AgentUpdateRequest | AgentFormValues,
): AgentCreateRequest | AgentUpdateRequest | null => {
  const nextValues = { ...values } as AgentCreateRequest | AgentUpdateRequest;

  if ('config' in values) {
    const rawConfig = values.config;
    if (typeof rawConfig === 'string') {
      const trimmed = rawConfig.trim();
      if (!trimmed) {
        delete (nextValues as AgentCreateRequest).config;
      } else {
        try {
          (nextValues as AgentCreateRequest).config = JSON.parse(trimmed);
        } catch {
          message.error('配置 JSON 格式不正确，请检查后再提交。');
          return null;
        }
      }
    }
  }

  return nextValues;
};

const AgentDashboard: React.FC = () => {
  const [managedAgents, setManagedAgents] = useState<ManagedAgent[]>([]);
  const [loading, setLoading] = useState(false);
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<ManagedAgent | null>(null);
  const [createForm] = Form.useForm<AgentFormValues>();
  const [editForm] = Form.useForm<AgentFormValues>();

  const fetchManagedAgents = async () => {
    setLoading(true);
    try {
      const response = await ApiService.getManagedAgents();
      if (response.success && response.data) {
        setManagedAgents(response.data);
      }
    } catch (error) {
      message.error('获取 Agent 列表失败');
      console.error('Fetch managed agents error:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchManagedAgents();
  }, []);

  const metrics = useMemo(() => {
    const activeCount = managedAgents.filter((item) =>
      ['active', 'running'].includes((item.status || '').toLowerCase()),
    ).length;
    const maintenanceCount = managedAgents.filter(
      (item) => (item.status || '').toLowerCase() === 'maintenance',
    ).length;
    const heterogeneousKinds = new Set(
      managedAgents
        .map((item) => item.agent_type)
        .filter(Boolean)
        .map((item) => item.toLowerCase()),
    );

    return {
      total: managedAgents.length,
      active: activeCount,
      maintenance: maintenanceCount,
      heterogeneousKinds: heterogeneousKinds.size,
    };
  }, [managedAgents]);

  const handleCreateAgent = async (values: AgentFormValues) => {
    const payload = parseConfigPayload(values);
    if (!payload) {
      return;
    }

    try {
      const response = await ApiService.createAgent(payload as AgentCreateRequest);
      if (response.success) {
        message.success('Agent 创建成功');
        setCreateModalVisible(false);
        createForm.resetFields();
        fetchManagedAgents();
      } else {
        message.error(response.message || '创建 Agent 失败');
      }
    } catch (error) {
      message.error('创建 Agent 失败');
      console.error('Create agent error:', error);
    }
  };

  const handleUpdateAgent = async (values: AgentFormValues) => {
    if (!selectedAgent) {
      return;
    }

    const payload = parseConfigPayload(values);
    if (!payload) {
      return;
    }

    try {
      const response = await ApiService.updateAgent(selectedAgent.name, payload);
      if (response.success) {
        message.success('Agent 更新成功');
        setEditModalVisible(false);
        editForm.resetFields();
        fetchManagedAgents();
      } else {
        message.error(response.message || '更新 Agent 失败');
      }
    } catch (error) {
      message.error('更新 Agent 失败');
      console.error('Update agent error:', error);
    }
  };

  const showEditModal = (agent: ManagedAgent) => {
    setSelectedAgent(agent);
    editForm.setFieldsValue({
      display_name: agent.display_name,
      description: agent.description,
      status: agent.status,
      agent_type: agent.agent_type,
      config: agent.config ? JSON.stringify(agent.config, null, 2) : '',
    });
    setEditModalVisible(true);
  };

  const showDetailModal = (agent: ManagedAgent) => {
    setSelectedAgent(agent);
    setDetailModalVisible(true);
  };

  const managedAgentColumns = [
    {
      title: 'Agent 标识',
      dataIndex: 'name',
      key: 'name',
      width: 220,
      render: (text: string, record: ManagedAgent) => (
        <div className="agent-table-name">
          <code>{text}</code>
          <span>{record.display_name || '未命名 Agent'}</span>
        </div>
      ),
    },
    {
      title: '异构类别',
      dataIndex: 'agent_type',
      key: 'agent_type',
      width: 180,
      render: (type: string) => {
        const meta = getTypeMeta(type);
        return (
          <span className={`hetero-type-pill hetero-type-pill--${meta.tone}`}>
            {meta.label}
          </span>
        );
      },
    },
    {
      title: '运行状态',
      dataIndex: 'status',
      key: 'status',
      width: 140,
      render: (status: string) => (
        <span className={`status-pill status-pill--${getStatusTone(status)}`}>
          {STATUS_LABELS[(status || '').toLowerCase()] || status || '未知'}
        </span>
      ),
    },
    {
      title: '职责说明',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (text: string, record: ManagedAgent) => (
        <span className="agent-table-description">
          {text || getTypeMeta(record.agent_type).description}
        </span>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (timestamp: string) =>
        timestamp ? moment(timestamp).format('MM-DD HH:mm') : '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 150,
      render: (_: unknown, record: ManagedAgent) => (
        <Space>
          <Button
            type="link"
            icon={<EyeOutlined />}
            onClick={() => showDetailModal(record)}
            size="small"
          >
            详情
          </Button>
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => showEditModal(record)}
            size="small"
          >
            编辑
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <>
      <div className="dashboard-overview-grid mb-4">
        <div className="overview-stat-card">
          <span className="overview-stat-label">Agent 总数</span>
          <strong className="overview-stat-value">{metrics.total}</strong>
          <span className="overview-stat-foot">已登记的可调度节点</span>
        </div>
        <div className="overview-stat-card">
          <span className="overview-stat-label">活跃节点</span>
          <strong className="overview-stat-value">{metrics.active}</strong>
          <span className="overview-stat-foot">当前可直接参与协作</span>
        </div>
        <div className="overview-stat-card">
          <span className="overview-stat-label">异构类别</span>
          <strong className="overview-stat-value">{metrics.heterogeneousKinds}</strong>
          <span className="overview-stat-foot">规则、量化、统计与 LLM 并存</span>
        </div>
        <div className="overview-stat-card">
          <span className="overview-stat-label">维护中</span>
          <strong className="overview-stat-value">{metrics.maintenance}</strong>
          <span className="overview-stat-foot">用于排查或暂时停服的节点</span>
        </div>
      </div>

      <Card
        title={
          <Space>
            <SettingOutlined />
            <span>异构 Agent 控制中心</span>
            <Badge count={managedAgents.length} />
          </Space>
        }
        extra={
          <Space>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setCreateModalVisible(true)}
              size="small"
            >
              新建 Agent
            </Button>
            <Button
              icon={<ReloadOutlined />}
              onClick={fetchManagedAgents}
              loading={loading}
              size="small"
              className="secondary-button"
            >
              刷新
            </Button>
          </Space>
        }
        className="feature-card"
      >
        <div className="agents-toolbar">
          <div>
            <Text className="agents-toolbar-kicker">Heterogeneous Control Plane</Text>
            <Paragraph className="agents-toolbar-copy">
              指南要求这里能直观看到各类 Agent 的异构分布。当前页面会优先突出
              `agent_type`，便于后续联调时直接对照规则引擎、量化模型、统计模型与 LLM 节点。
            </Paragraph>
          </div>
          <div className="agents-type-legend">
            {['rule_engine', 'quantitative_model', 'statistical_model', 'llm_rag', 'hybrid_rule_llm', 'llm'].map(
              (type) => {
                const meta = getTypeMeta(type);
                return (
                  <span
                    key={type}
                    className={`hetero-type-pill hetero-type-pill--${meta.tone}`}
                  >
                    {meta.label}
                  </span>
                );
              },
            )}
          </div>
        </div>

        <Table
          dataSource={managedAgents}
          columns={managedAgentColumns}
          rowKey="id"
          loading={loading}
          pagination={{
            pageSize: 10,
            showSizeChanger: false,
            showQuickJumper: true,
          }}
        />
      </Card>

      <Modal
        title="创建新 Agent"
        open={createModalVisible}
        onCancel={() => {
          setCreateModalVisible(false);
          createForm.resetFields();
        }}
        footer={null}
        width={720}
      >
        <Form
          form={createForm}
          layout="vertical"
          onFinish={handleCreateAgent}
          initialValues={{ status: 'active', agent_type: 'rule_engine' }}
          className="modern-form"
        >
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="name"
                label="Agent 标识"
                rules={[
                  { required: true, message: '请输入 Agent 标识' },
                  {
                    pattern: /^[a-zA-Z_][a-zA-Z0-9_]*$/,
                    message: '标识只能包含字母、数字和下划线，且不能以数字开头',
                  },
                ]}
              >
                <Input placeholder="valuation_agent" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="display_name"
                label="显示名称"
                rules={[{ required: true, message: '请输入显示名称' }]}
              >
                <Input placeholder="DCF 估值 Agent" />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="agent_type"
                label="异构类别"
                rules={[{ required: true, message: '请选择 Agent 类型' }]}
              >
                <Select
                  options={AGENT_TYPE_OPTIONS}
                  placeholder="选择 Agent 类型"
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="status" label="状态">
                <Select
                  options={[
                    { value: 'active', label: '活跃' },
                    { value: 'inactive', label: '停用' },
                    { value: 'maintenance', label: '维护中' },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item name="description" label="职责描述">
            <TextArea
              rows={3}
              placeholder="说明这个 Agent 负责的分析任务、输入来源和主要输出。"
            />
          </Form.Item>

          <Form.Item name="config" label="配置 JSON（可选）">
            <TextArea
              rows={6}
              placeholder='例如：{"refresh_interval": "daily", "risk_limit": 0.2}'
            />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0 }}>
            <Space>
              <Button type="primary" htmlType="submit">
                创建
              </Button>
              <Button
                onClick={() => {
                  setCreateModalVisible(false);
                  createForm.resetFields();
                }}
              >
                取消
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`编辑 Agent · ${selectedAgent?.display_name || selectedAgent?.name || ''}`}
        open={editModalVisible}
        onCancel={() => {
          setEditModalVisible(false);
          editForm.resetFields();
        }}
        footer={null}
        width={720}
      >
        <Form
          form={editForm}
          layout="vertical"
          onFinish={handleUpdateAgent}
          className="modern-form"
        >
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="display_name" label="显示名称">
                <Input placeholder="Agent 显示名称" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="agent_type" label="异构类别">
                <Select
                  options={AGENT_TYPE_OPTIONS}
                  placeholder="选择 Agent 类型"
                />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="status" label="状态">
                <Select
                  options={[
                    { value: 'active', label: '活跃' },
                    { value: 'inactive', label: '停用' },
                    { value: 'maintenance', label: '维护中' },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item name="description" label="职责描述">
            <TextArea rows={3} placeholder="补充 Agent 的职责边界和用途。" />
          </Form.Item>

          <Form.Item name="config" label="配置 JSON">
            <TextArea rows={6} placeholder="请输入 JSON 格式配置" />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0 }}>
            <Space>
              <Button type="primary" htmlType="submit">
                保存修改
              </Button>
              <Button
                onClick={() => {
                  setEditModalVisible(false);
                  editForm.resetFields();
                }}
              >
                取消
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`Agent 详情 · ${selectedAgent?.display_name || selectedAgent?.name || ''}`}
        open={detailModalVisible}
        onCancel={() => setDetailModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setDetailModalVisible(false)}>
            关闭
          </Button>,
        ]}
        width={820}
      >
        {selectedAgent && (
          <>
            <div className="agent-detail-hero">
              <div>
                <Text className="agents-toolbar-kicker">Agent Profile</Text>
                <h3>{selectedAgent.display_name || selectedAgent.name}</h3>
                <p>{selectedAgent.description || getTypeMeta(selectedAgent.agent_type).description}</p>
              </div>
              <div className="agent-detail-badges">
                <span
                  className={`hetero-type-pill hetero-type-pill--${getTypeMeta(selectedAgent.agent_type).tone}`}
                >
                  {getTypeMeta(selectedAgent.agent_type).label}
                </span>
                <span className={`status-pill status-pill--${getStatusTone(selectedAgent.status)}`}>
                  {STATUS_LABELS[(selectedAgent.status || '').toLowerCase()] || selectedAgent.status}
                </span>
              </div>
            </div>

            <Descriptions bordered column={1}>
              <Descriptions.Item label="Agent 标识">
                <code>{selectedAgent.name}</code>
              </Descriptions.Item>
              <Descriptions.Item label="显示名称">
                {selectedAgent.display_name}
              </Descriptions.Item>
              <Descriptions.Item label="异构类别">
                {getTypeMeta(selectedAgent.agent_type).label}
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                {STATUS_LABELS[(selectedAgent.status || '').toLowerCase()] || selectedAgent.status}
              </Descriptions.Item>
              <Descriptions.Item label="创建时间">
                {selectedAgent.created_at
                  ? moment(selectedAgent.created_at).format('YYYY-MM-DD HH:mm:ss')
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="更新时间">
                {selectedAgent.updated_at
                  ? moment(selectedAgent.updated_at).format('YYYY-MM-DD HH:mm:ss')
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="配置内容">
                <pre className="config-viewer">
                  {selectedAgent.config
                    ? JSON.stringify(selectedAgent.config, null, 2)
                    : '暂无配置'}
                </pre>
              </Descriptions.Item>
            </Descriptions>
          </>
        )}
      </Modal>
    </>
  );
};

export default AgentDashboard;
