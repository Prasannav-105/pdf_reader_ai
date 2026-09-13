#!/usr/bin/env bash
set -e

echo "==================================================="
echo "Starting PDF Reader AI Tutor (Linux/WSL/macOS)..."
echo "==================================================="

# Check Python3
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 could not be found. Please install Python 3.10+."
    exit 1
fi

# Create venv if not exists
if [ ! -d "venv" ]; then
    echo "[INFO] Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install requirements
echo "[INFO] Checking dependencies..."
pip install -r requirements.txt --quiet

# Launch Streamlit bound to all interfaces
echo "[INFO] Launching Streamlit web interface on port 8501..."
export PYTHONUTF8=1
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
