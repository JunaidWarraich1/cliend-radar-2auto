@echo off
title Global Apply Hub - Job Application Workspace
cd /d "%~dp0"
echo Starting Global Apply Hub on http://127.0.0.1:8085 ...
start "" http://127.0.0.1:8085
python -m uvicorn app:app --host 127.0.0.1 --port 8085
pause
