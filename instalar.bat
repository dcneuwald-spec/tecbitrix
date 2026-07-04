@echo off
REM ============================================================
REM  INSTALACAO (rodar 1 vez): cria o ambiente e instala tudo
REM ============================================================
cd /d %~dp0

if not exist .venv (
    echo Criando ambiente Python...
    python -m venv .venv
)

echo Instalando dependencias...
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\playwright install chromium

echo.
echo ============================================================
echo  Instalacao concluida.
echo  Proximo passo:  login.bat  (login manual no Bitrix24)
echo ============================================================
pause
