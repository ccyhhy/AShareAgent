import sys
import os

filepath = r'e:\codework\graduation design\frontend\src\App.tsx'
content = open(filepath, 'r', encoding='utf-8').read()

# 1. Imports
imp_search = "import { Avatar, Button, Dropdown, Input, Layout, Menu, Space, Typography } from 'antd';"
imp_replace = "import { Avatar, Button, Dropdown, Input, Layout, Menu, Space, Typography, ConfigProvider, theme } from 'antd';\nimport { motion, AnimatePresence } from 'framer-motion';"
content = content.replace(imp_search, imp_replace)

# Icons
icon_search = """  MonitorOutlined,
  QuestionCircleOutlined,
  ReloadOutlined,
  RobotOutlined,
  SearchOutlined,
  SettingOutlined,
  UserOutlined,
} from '@ant-design/icons';"""
icon_replace = """  MonitorOutlined,
  QuestionCircleOutlined,
  ReloadOutlined,
  RobotOutlined,
  SearchOutlined,
  SettingOutlined,
  UserOutlined,
  MoonOutlined,
  SunOutlined,
} from '@ant-design/icons';"""
content = content.replace(icon_search, icon_replace)

# 2. Add isDarkMode state
state_search = "  const [isAuthenticated, setIsAuthenticated] = useState(false);"
state_replace = """  const [isAuthenticated, setIsAuthenticated] = useState(false);
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

  const toggleDarkMode = () => setIsDarkMode(!isDarkMode);"""
content = content.replace(state_search, state_replace)

# 3. Add toggle button in header
header_btn_search = '<Button type="text" className="header-icon-button" icon={<BellOutlined />} />'
header_btn_replace = """<Button type="text" className="header-icon-button" icon={<BellOutlined />} />
            <Button
              type="text"
              className="header-icon-button"
              icon={isDarkMode ? <SunOutlined /> : <MoonOutlined />}
              onClick={toggleDarkMode}
            />"""
content = content.replace(header_btn_search, header_btn_replace)

# 4. Wrap with ConfigProvider
return_search = """  return (
    <Layout className="app-shell">"""
return_replace = """  return (
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
    <Layout className="app-shell">"""
content = content.replace(return_search, return_replace)

shell_end_search = """    </Layout>
  );
}"""
shell_end_replace = """    </Layout>
    </ConfigProvider>
  );
}"""
content = content.replace(shell_end_search, shell_end_replace)

# 5. Add framer-motion AnimatePresence to body
body_search = '<div className="app-content-body fade-in-up">{renderContent()}</div>'
body_replace = """<div className="app-content-body">
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
            </div>"""
content = content.replace(body_search, body_replace)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated App.tsx")
