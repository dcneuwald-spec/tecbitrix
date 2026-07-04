@echo off
REM ============================================================
REM  RELATORIO COMPLETO do cliente TEC SYSTEM (somente leitura)
REM  Saida: relatorios\relatorio_AAAA-MM-DD.md e .csv
REM ============================================================
cd /d %~dp0
.venv\Scripts\python gerar_relatorio.py %*
pause
