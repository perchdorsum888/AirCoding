@echo off
cd /d "%~dp0"

set "PYTHONW=%~dp0.venv_run\Scripts\pythonw.exe"
set "PYTHON=%~dp0.venv_run\Scripts\python.exe"
set PYTHONDONTWRITEBYTECODE=1

if not exist "%PYTHONW%" (
    if not exist "%PYTHON%" (
        echo [ERROR] Python venv not found at .venv_run
        pause
        exit /b 1
    )
    set "PYTHONW=%PYTHON%"
)

start "" "%PYTHONW%" -B main.py
