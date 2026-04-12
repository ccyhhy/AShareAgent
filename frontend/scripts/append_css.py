import sys

filepath = r'e:\codework\graduation design\frontend\src\App.css'
content = open(filepath, 'r', encoding='utf-8').read()

dark_css = """

/* Dark Theme Overrides */
body.dark {
  --primary-soft: rgba(27, 77, 216, 0.2);
  --primary-muted: rgba(27, 77, 216, 0.15);

  --ink-900: #f8fafc;
  --ink-700: #cbd5e1;
  --ink-500: #8ba1ba;
  --ink-400: #64748b;

  --surface: rgba(15, 23, 42, 0.74);
  --surface-strong: rgba(15, 23, 42, 0.9);
  --surface-soft: rgba(30, 41, 59, 0.86);
  --surface-low: rgba(30, 41, 59, 0.5);

  --border-soft: rgba(148, 163, 184, 0.16);
  --border-ghost: rgba(148, 163, 184, 0.1);
  --shadow-soft: 0 16px 48px rgba(0, 0, 0, 0.5);
  --shadow-main: 0 28px 80px rgba(0, 0, 0, 0.6);

  background:
    radial-gradient(circle at top left, rgba(27, 77, 216, 0.18), transparent 28%),
    radial-gradient(circle at top right, rgba(56, 189, 248, 0.12), transparent 24%),
    linear-gradient(180deg, #020617 0%, #0f172a 54%, #1e293b 100%);
  
  color: var(--ink-900);
}

body.dark .app-sider.ant-layout-sider {
  background: var(--surface-soft) !important;
  box-shadow: var(--shadow-soft);
}

body.dark .app-header {
  background: var(--surface) !important;
  box-shadow: var(--shadow-soft);
}

body.dark .app-header-search .ant-input-affix-wrapper {
  background: rgba(30, 41, 59, 0.92) !important;
  box-shadow: inset 0 0 0 1px var(--border-ghost);
}

body.dark .market-pill,
body.dark .header-icon-button.ant-btn {
  background: rgba(30, 41, 59, 0.9);
  color: var(--ink-700);
  box-shadow: inset 0 0 0 1px var(--border-ghost);
}

body.dark .app-menu .ant-menu-item-selected {
  background: rgba(30, 41, 59, 0.95) !important;
  box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.12), 0 10px 24px rgba(0, 0, 0, 0.2);
}

body.dark .sider-status-card {
  background: linear-gradient(135deg, rgba(30, 41, 59, 0.82), rgba(15, 23, 42, 0.88));
}

body.dark .app-content-body .ant-card,
body.dark .analysis-stage-panel,
body.dark .decision-hero-card {
  background: var(--surface-strong) !important;
}

body.dark .run-chip {
  background: rgba(30, 41, 59, 0.92);
  color: var(--primary);
  box-shadow: inset 0 0 0 1px rgba(27, 77, 216, 0.22);
}
"""

if "body.dark" not in content:
    with open(filepath, 'a', encoding='utf-8') as f:
        f.write(dark_css)
    print("Dark theme appended.")
else:
    print("Dark theme already present.")
