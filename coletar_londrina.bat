@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Execute instalar_windows.bat primeiro.
  pause
  exit /b 1
)
.venv\Scripts\python.exe collect_batch.py --sources olx zap vivareal imovelweb santamerica human monaco yticon --max-pages 3 --output diagnostico_coleta.json
if errorlevel 1 echo Algumas fontes nao foram concluidas. Consulte diagnostico_coleta.json.
pause
