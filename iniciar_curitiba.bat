@echo off
cd /d "%~dp0"
set "HUB_PYTHON=python"
if exist ".venv\Scripts\python.exe" set "HUB_PYTHON=.venv\Scripts\python.exe"
"%HUB_PYTHON%" -c "import sys; assert sys.version_info >= (3,11), 'Use Python 3.11 ou superior'"
if errorlevel 1 goto erro
start "" "http://127.0.0.1:8503/curitiba/"
"%HUB_PYTHON%" -m http.server 8503 --bind 127.0.0.1 --directory docs
exit /b
:erro
pause
