@echo off
setlocal
set PORT=8000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%PORT% ^| findstr LISTENING') do (
    taskkill /PID %%a /F
    echo 已停止 PID %%a（端口 %PORT%）
    set FOUND=1
)
if not defined FOUND (
    echo 未找到正在监听端口 %PORT% 的进程
)
endlocal
pause
