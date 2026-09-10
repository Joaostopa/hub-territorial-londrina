@echo off
setlocal
cd /d "%~dp0"
python --version
if errorlevel 1 (
  echo Instale Python 3.11 ou 3.12 e marque Add Python to PATH.
  pause
  exit /b 1
)
python -c "import sys; assert (3,11) <= sys.version_info[:2] <= (3,12), 'Use Python 3.11 ou 3.12'"
if errorlevel 1 (
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe python -m venv .venv
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
  echo Instalacao falhou. Confira a conexao e a mensagem acima.
  pause
  exit /b 1
)
.venv\Scripts\python.exe preparar_projeto.py
if errorlevel 1 (
  pause
  exit /b 1
)
echo Instalacao concluida. Execute iniciar_windows.bat.
pause
