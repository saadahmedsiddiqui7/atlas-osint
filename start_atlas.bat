@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo First-time setup: creating the private Python environment...
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3 -m venv .venv
    ) else (
        python -m venv .venv
    )
    if errorlevel 1 goto setup_failed
)

if not exist ".venv\Scripts\python.exe" goto setup_failed

echo Installing or checking required packages...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto setup_failed

echo.
echo ATLAS will open at http://127.0.0.1:8000
echo Keep this window open while using ATLAS. Press Ctrl+C to stop it.
".venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8000
exit /b %errorlevel%

:setup_failed
echo.
echo ATLAS could not start. Install Python 3.10 or newer, check your internet connection, and try again.
exit /b 1
