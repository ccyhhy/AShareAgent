import { useEffect, useState } from 'react';
import { Avatar, Button, Dropdown, Input, Layout, Menu, Space, Typography, ConfigProvider, theme } from 'antd';
import { motion, AnimatePresence } from 'framer-motion';
import {
  BarChartOutlined,
  BellOutlined,
  BookOutlined,
  DashboardOutlined,
  ExperimentOutlined,
  FundOutlined,
  HistoryOutlined,
  LineChartOutlined,
  LogoutOutlined,
  MonitorOutlined,
  QuestionCircleOutlined,
  ReloadOutlined,
  RobotOutlined,
  SearchOutlined,
  SettingOutlined,
  UserOutlined,
  MoonOutlined,
  SunOutlined,
} from '@ant-design/icons';
import AnalysisForm from './components/AnalysisForm';
import AnalysisStatus from './components/AnalysisStatus';
import AgentDashboard from './components/AgentDashboard';
import BacktestForm from './components/BacktestForm';
import BacktestResult from './components/BacktestResult';
import BacktestStatus from './components/BacktestStatus';
import DcfWorkbenchPage from './components/DcfWorkbenchPage';
import HistoryDashboard from './components/HistoryDashboard';
import LoginForm from './components/LoginForm';
import PersonalStats from './components/PersonalStats';
import PortfolioManagement from './components/PortfolioManagement';
import SystemMonitor from './components/SystemMonitor';
import UserProfile from './components/UserProfile';
import ApiService, { type UserInfo } from './services/api';
import 'antd/dist/reset.css';
import './App.css';

const { Header, Content, Sider } = Layout;
const { Title, Paragraph } = Typography;

type MenuKey =
  | 'dashboard'
  | 'valuation'
  | 'backtest'
  | 'agents'
  | 'history'
  | 'portfolios'
  | 'monitor'
  | 'stats'
  | 'profile';

const PAGE_META: Record<MenuKey, { title: string; subtitle: string }> = {
  dashboard: {
    title: '股票分析与多智能体协作',
    subtitle: '以价值投资为主线，汇总多类 Agent 的分析路径、状态和最终联合决策。',
  },
  valuation: {
    title: 'DCF 估值工具页',
    subtitle: '把增长率、折现率和现金流假设显式展开，用交互方式展示估值对参数的敏感性。',
  },
  backtest: {
    title: '策略回测实验台',
    subtitle: '对比多智能体策略与基准表现，支持实验参数配置、指标复盘和收益曲线分析。',
  },
  agents: {
    title: 'Agent 控制中心',
    subtitle: '查看各 Agent 运行状态、类型、配置参数与系统协作关系。',
  },
  history: {
    title: '历史运行档案',
    subtitle: '统一浏览分析历史、回测记录、决策详情与图表结果。',
  },
  portfolios: {
    title: '投资组合管理',
    subtitle: '跟踪组合资产、持仓结构、交易记录和风险告警。',
  },
  monitor: {
    title: '系统运维与监控',
    subtitle: '查看平台运行健康度、接口状态和服务级监控数据。',
  },
  stats: {
    title: '个人统计看板',
    subtitle: '展示用户侧的使用概览、绩效指标和交互频率。',
  },
  profile: {
    title: '个人设置',
    subtitle: '管理账户信息、权限视图与个性化偏好。',
  },
};

function App() {
  const [selectedMenu, setSelectedMenu] = useState<MenuKey>('dashboard');
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [currentBacktestId, setCurrentBacktestId] = useState<string | null>(null);
  const [backtestResult, setBacktestResult] = useState<any>(null);
  const [latestAnalysisResult, setLatestAnalysisResult] = useState<any>(null);
  const [user, setUser] = useState<UserInfo | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isDarkMode, setIsDarkMode] = useState(() => {
    return localStorage.getItem('theme') === 'dark';
  });

  useEffect(() => {
    if (isDarkMode) {
      document.body.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    } else {
      document.body.classList.remove('dark');
      localStorage.setItem('theme', 'light');
    }
  }, [isDarkMode]);

  const toggleDarkMode = () => setIsDarkMode(!isDarkMode);

  useEffect(() => {
    const checkAuth = async () => {
      const token = localStorage.getItem('auth_token');
      if (!token) {
        return;
      }

      try {
        const response = await ApiService.getCurrentUser();
        if (response.success && response.data) {
          setUser(response.data);
          setIsAuthenticated(true);
        } else {
          localStorage.removeItem('auth_token');
          localStorage.removeItem('user_info');
        }
      } catch {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('user_info');
      }
    };

    checkAuth();
  }, []);

  const handleAnalysisStart = (runId: string) => {
    setCurrentRunId(runId);
  };

  const handleAnalysisComplete = (result: any) => {
    setLatestAnalysisResult(result);
  };

  const handleOpenDcfWorkbench = (result?: any) => {
    if (result) {
      setLatestAnalysisResult(result);
    }
    setSelectedMenu('valuation');
  };

  const handleBacktestStart = (runId: string) => {
    setCurrentBacktestId(runId);
    setBacktestResult(null);
  };

  const handleBacktestComplete = (result: any) => {
    setBacktestResult(result);
  };

  const handleLoginSuccess = (userInfo: UserInfo) => {
    setUser(userInfo);
    setIsAuthenticated(true);
  };

  const handleLogout = async () => {
    await ApiService.logout();
    setUser(null);
    setIsAuthenticated(false);
    setSelectedMenu('dashboard');
    setCurrentRunId(null);
    setCurrentBacktestId(null);
    setBacktestResult(null);
  };

  const hasPermission = (permission: string): boolean => {
    return (
      user?.permissions?.includes(permission) ||
      user?.roles?.includes('admin') ||
      false
    );
  };

  if (!isAuthenticated) {
    return <LoginForm onLoginSuccess={handleLoginSuccess} />;
  }

  const renderPermissionError = (title: string, description: string) => (
    <div className="permission-error">
      <Title level={3}>{title}</Title>
      <p>{description}</p>
    </div>
  );

  const renderContent = () => {
    switch (selectedMenu) {
      case 'dashboard':
        return (
          <Space direction="vertical" style={{ width: '100%' }} size="large">
            <AnalysisForm onAnalysisStart={handleAnalysisStart} />
            {currentRunId && (
                <AnalysisStatus
                  runId={currentRunId}
                  onComplete={handleAnalysisComplete}
                  onOpenDcfWorkbench={handleOpenDcfWorkbench}
                />
              )}
            </Space>
          );
      case 'valuation':
        return <DcfWorkbenchPage initialData={latestAnalysisResult} />;
      case 'backtest':
        return (
          <Space direction="vertical" style={{ width: '100%' }} size="large">
            {hasPermission('backtest:basic') ? (
              <>
                <BacktestForm onBacktestStart={handleBacktestStart} />
                {currentBacktestId && (
                  <BacktestStatus
                    runId={currentBacktestId}
                    onComplete={handleBacktestComplete}
                  />
                )}
                {backtestResult && <BacktestResult result={backtestResult} />}
              </>
            ) : (
              renderPermissionError('权限不足', '当前账户没有访问回测模块的权限。')
            )}
          </Space>
        );
      case 'agents':
        return hasPermission('system:monitor')
          ? <AgentDashboard />
          : renderPermissionError('权限不足', '当前账户没有访问 Agent 管理模块的权限。');
      case 'history':
        return <HistoryDashboard />;
      case 'portfolios':
        return hasPermission('portfolio:read')
          ? <PortfolioManagement />
          : renderPermissionError('权限不足', '当前账户没有访问投资组合模块的权限。');
      case 'monitor':
        return hasPermission('system:monitor')
          ? <SystemMonitor />
          : renderPermissionError('权限不足', '当前账户没有访问系统监控模块的权限。');
      case 'stats':
        return <PersonalStats />;
      case 'profile':
        return <UserProfile onUserUpdate={setUser} />;
      default:
        return <div>页面未找到。</div>;
    }
  };

  const menuItems = [
    { key: 'dashboard', icon: <DashboardOutlined />, label: '股票分析' },
    { key: 'valuation', icon: <FundOutlined />, label: 'DCF 工具页' },
    ...(hasPermission('backtest:basic')
      ? [{ key: 'backtest', icon: <ExperimentOutlined />, label: '策略回测' }]
      : []),
    ...(hasPermission('portfolio:read')
      ? [{ key: 'portfolios', icon: <FundOutlined />, label: '投资组合' }]
      : []),
    ...(hasPermission('system:monitor')
      ? [{ key: 'agents', icon: <RobotOutlined />, label: 'Agent 控制' }]
      : []),
    { key: 'history', icon: <HistoryOutlined />, label: '历史记录' },
    { key: 'stats', icon: <LineChartOutlined />, label: '个人统计' },
    ...(hasPermission('system:monitor')
      ? [{ key: 'monitor', icon: <MonitorOutlined />, label: '系统运维' }]
      : []),
    { key: 'profile', icon: <SettingOutlined />, label: '系统设置' },
  ];

  const userMenu = {
    items: [
      {
        key: 'logout',
        icon: <LogoutOutlined />,
        label: '退出登录',
        onClick: handleLogout,
      },
    ],
  };

  const activeTaskId =
    selectedMenu === 'backtest' && currentBacktestId ? currentBacktestId : currentRunId;

  return (
    <ConfigProvider
      theme={{
        algorithm: isDarkMode ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: {
          colorPrimary: '#1b4dd8',
          fontFamily: 'Inter, Segoe UI, sans-serif',
          borderRadius: 12,
        },
      }}
    >
    <Layout className="app-shell">
      <Sider width={248} className="app-sider" breakpoint="lg" collapsedWidth="0">
        <div className="sider-brand">
          <div className="logo">
            <BarChartOutlined className="logo-icon" />
            <div className="logo-copy">
              <span className="logo-text">A-Share Agent Desk</span>
              <span className="logo-subtitle">基于异构多智能体的 A 股价值投资分析系统</span>
            </div>
          </div>
          <div className="sider-status-card">
            <span className="sider-status-kicker">Intelligence Hub</span>
            <strong>{hasPermission('system:monitor') ? '6' : '4'} 个活跃节点</strong>
          </div>
        </div>

        <Menu
          mode="inline"
          selectedKeys={[selectedMenu]}
          items={menuItems}
          className="app-menu"
          onSelect={({ key }) => setSelectedMenu(key as MenuKey)}
        />

        <div className="sider-footer">
          <div className="sider-footer-item">
            <QuestionCircleOutlined />
            <span>帮助中心</span>
          </div>
          <div className="sider-footer-item">
            <BookOutlined />
            <span>文档说明</span>
          </div>
        </div>
      </Sider>

      <Layout className="app-main-layout">
        <Header className="app-header">
          <div className="app-header-search">
            <Input
              prefix={<SearchOutlined />}
              placeholder="搜索股票代码，例如 600519.SH"
              allowClear
            />
          </div>

          <div className="app-user-area">
            <div className="market-pill">
              <span className="market-dot" />
              市场状态 OPEN
            </div>
            <Button type="text" className="header-icon-button" icon={<ReloadOutlined />} />
            <Button type="text" className="header-icon-button" icon={<BellOutlined />} />
            <Button
              type="text"
              className="header-icon-button"
              icon={isDarkMode ? <SunOutlined /> : <MoonOutlined />}
              onClick={toggleDarkMode}
            />
            <Dropdown menu={userMenu} placement="bottomRight">
              <Button className="app-user-button" type="text">
                <Avatar size="small" icon={<UserOutlined />} />
              </Button>
            </Dropdown>
          </div>
        </Header>

        <Layout className="app-workspace">
          <Content className="app-content">
            <div className="app-content-header">
              <div className="app-content-header-main">
                <div className="app-content-kicker">A-Share Multi-Agent Workflow</div>
                <Title level={2} className="app-content-title">
                  {PAGE_META[selectedMenu].title}
                </Title>
                <Paragraph className="app-content-subtitle">
                  {PAGE_META[selectedMenu].subtitle}
                </Paragraph>
              </div>
              {activeTaskId && (
                <div className="run-chip">
                  当前任务 #{activeTaskId.slice(0, 8)}
                </div>
              )}
            </div>
            <div className="app-content-body">
              <AnimatePresence mode="wait">
                <motion.div
                  key={selectedMenu}
                  initial={{ opacity: 0, y: 15 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -15 }}
                  transition={{ duration: 0.25, ease: 'easeInOut' }}
                >
                  {renderContent()}
                </motion.div>
              </AnimatePresence>
            </div>
          </Content>
        </Layout>
      </Layout>
    </Layout>
    </ConfigProvider>
  );
}

export default App;
