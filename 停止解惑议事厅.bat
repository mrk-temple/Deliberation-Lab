@echo off
title Council Chamber Stopper
echo Stopping Council Chamber service...
wsl -e bash -c "pkill -f uvicorn || true"
echo Done. Start it again with the launcher anytime.
pause
