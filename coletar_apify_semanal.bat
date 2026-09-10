@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Execute instalar_windows.bat primeiro.
  exit /b 1
)
".venv\Scripts\python.exe" apify_cli.py weekly --business SALE --max-items 100
exit /b %errorlevel%
