@echo off
chcp 65001 >nul
title 解惑议事厅启动器
echo ============================================
echo   解惑议事厅 · 一键启动（DeepSeek 后端）
echo ============================================
echo.
echo [1/2] 启动 WSL 服务（首次约 1-2 分钟，之后几秒）...
start "解惑议事厅服务" /min wsl -e bash -c "cd /mnt/e/Projects/idea/解惑议事厅/web && ./run.sh"
echo [2/2] 等待服务就绪并打开浏览器...
powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 60 -and -not $ok;$i++){ try { $r=Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8787/api/health' -TimeoutSec 1; if($r.StatusCode -eq 200){$ok=$true} } catch { Start-Sleep -Milliseconds 500 } }; if($ok){ Start-Process 'http://127.0.0.1:8787' } else { Write-Host '30 秒内未就绪，请检查 WSL，或手动打开 http://127.0.0.1:8787' }"
echo.
echo 服务已启动。浏览器若未自动打开，请手动访问 http://127.0.0.1:8787
echo 注意：最小化的「解惑议事厅服务」窗口请保留（关闭它会停止服务）。
echo.
pause
