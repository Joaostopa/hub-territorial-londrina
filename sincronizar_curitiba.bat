@echo off
cd /d "%~dp0"
set "HUB_PYTHON=python"
if exist ".venv\Scripts\python.exe" set "HUB_PYTHON=.venv\Scripts\python.exe"
"%HUB_PYTHON%" curitiba_pipeline.py sync
if errorlevel 1 goto fim
"%HUB_PYTHON%" curitiba_pipeline.py public
echo Recarregue a pagina local. O site GitHub Pages so muda apos enviar os JSON atualizados.
:fim
pause
