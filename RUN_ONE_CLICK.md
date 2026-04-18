# 一键启动说明（Windows）

双击项目根目录下的 [一键启动.cmd](/E:/codework/graduation%20design/一键启动.cmd) 即可启动前后端。

默认行为：
- 自动检测 `.venv` / `venv` / 系统 `python`
- 自动安装缺失后端依赖（`requirements.txt`）
- 自动安装缺失前端依赖（`frontend/node_modules` 不存在时）
- 自动处理端口冲突（默认端口被占用时自动换临近端口）
- 自动打开浏览器访问前端页面

默认地址：
- 前端：`http://127.0.0.1:5173`（若冲突会自动改端口）
- 后端：`http://127.0.0.1:8000/docs`（若冲突会自动改端口）

停止服务：
- 在启动窗口按 `Ctrl + C`

可选参数示例（命令行）：
```powershell
.\一键启动.cmd -ForceFreePorts
.\一键启动.cmd -BackendPort 18000 -FrontendPort 15173
.\一键启动.cmd -AutoStopSeconds 120
.\一键启动.cmd -NoOpenBrowser
.\一键启动.cmd -NoBootstrapDeps
```
