@echo off
setlocal
title Council Chamber Launcher

rem Locate project dir from this script's own location (works anywhere)
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"

echo ============================================
echo   Council Chamber - one-click launcher
echo ============================================
echo.

rem Probe if service is already up (bypass system proxy for localhost)
powershell -NoProfile -Command "$p=[System.Net.WebRequest]::DefaultWebProxy; [System.Net.WebRequest]::DefaultWebProxy=$null; try { $r=Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8787/api/health' -TimeoutSec 2; if($r.StatusCode -eq 200){exit 0} } catch {} ; exit 1"
if %errorlevel%==0 goto already_running

echo [1/2] Starting WSL service (first run takes 1-2 min)...
start "Council service" /min wsl --cd "%HERE%\web" -e bash ./run.sh
echo [2/2] Waiting for service to be ready...
powershell -NoProfile -Command "$p=[System.Net.WebRequest]::DefaultWebProxy; [System.Net.WebRequest]::DefaultWebProxy=$null; $ok=$false; for($i=0;$i -lt 60 -and -not $ok;$i++){ try { $r=Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8787/api/health' -TimeoutSec 1; if($r.StatusCode -eq 200){$ok=$true} } catch { Start-Sleep -Milliseconds 500 } }; [System.Net.WebRequest]::DefaultWebProxy=$p; if($ok){ Start-Process 'http://127.0.0.1:8787'; Write-Host 'Browser opened.' } else { Write-Host 'Not ready in 30s - open http://127.0.0.1:8787 manually.' }"
goto done

:already_running
echo Service already running. Opening browser...
start "" http://127.0.0.1:8787

:done
echo.
echo Keep the minimized "Council service" window open (closing it stops the service).
pause
