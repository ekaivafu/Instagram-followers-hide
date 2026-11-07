@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
    .venv\Scripts\python -m pip install --disable-pip-version-check -r requirements.txt
)
.venv\Scripts\python bot.py
pause
