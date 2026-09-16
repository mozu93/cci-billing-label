@echo off
cd /d "%~dp0"
rem Python Launcher(py.exe) があればそれを優先する。
rem 特定ユーザーのインストール先を直書きすると他の端末で起動できないため。
py -3.11 -c "" >nul 2>&1
if %errorlevel%==0 (
    start "" pyw -3.11 main.py
    exit /b
)
py -3 -c "" >nul 2>&1
if %errorlevel%==0 (
    start "" pyw -3 main.py
    exit /b
)
pythonw -c "" >nul 2>&1
if %errorlevel%==0 (
    start "" pythonw main.py
    exit /b
)
echo Python 3.11 not found. Please install from https://www.python.org/
pause
