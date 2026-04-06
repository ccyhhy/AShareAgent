@echo off
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_fullstack.ps1" %*

endlocal
