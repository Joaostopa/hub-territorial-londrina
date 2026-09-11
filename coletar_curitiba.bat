@echo off
cd /d "%~dp0"
set "HUB_PYTHON=python"
if exist ".venv\Scripts\python.exe" set "HUB_PYTHON=.venv\Scripts\python.exe"
echo Curitiba: duas execucoes de ate 1500 apartamentos, venda e aluguel.
echo Reserva maxima de US$4 por execucao, compartilhada com o teto local de US$10.
echo Quantidade de anuncios nao e garantida. Confira seu saldo e token no .env.
"%HUB_PYTHON%" curitiba_pipeline.py collect
if errorlevel 1 goto fim
echo Quando as coletas terminarem na Apify, execute sincronizar_curitiba.bat.
:fim
pause
