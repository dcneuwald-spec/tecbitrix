@echo off
REM ============================================================
REM  LOGIN MANUAL: abre o navegador para voce entrar no Bitrix24
REM  (nenhuma senha e digitada ou armazenada pelo script)
REM ============================================================
cd /d %~dp0
.venv\Scripts\python save_auth.py
pause
