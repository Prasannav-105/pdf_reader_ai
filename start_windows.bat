@echo off
title PDF Reader AI Tutor Launcher
echo ===================================================
echo Starting PDF Reader AI Tutor...
echo ===================================================

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not found in PATH!
    echo Please install Python 3.10+ and check 'Add Python to PATH'.
    pause
    exit /b 1
)

:: Create venv if not exists
if not exist "venv" (
    echo [INFO] Creating Python virtual environment...
    python -m venv venv
)

:: Activate venv
call venv\Scripts\activate.bat

:: Install requirements
echo [INFO] Checking dependencies...
pip install -r requirements.txt --quiet

:: Set CPU mode for Ollama stability
set OLLAMA_IGPU_ENABLE=0
set PYTHONUTF8=1

:: Launch Streamlit
echo [INFO] Launching Streamlit web interface...
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
pause
