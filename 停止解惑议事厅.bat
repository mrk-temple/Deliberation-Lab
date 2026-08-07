@echo off
chcp 65001 >nul
title 解惑议事厅停止器
echo 正在停止解惑议事厅服务...
wsl -e bash -c "pkill -f uvicorn || true"
echo 已停止。可以重新打开「启动解惑议事厅.bat」再次启动。
pause
