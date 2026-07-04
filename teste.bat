@echo off
REM ============================================================
REM  RODADA DE TESTE: 10 tarefas, navegador visivel, com debug
REM  Saidas: relatorios\  e  relatorios\debug\ (coleta.png, links.txt)
REM ============================================================
cd /d %~dp0
.venv\Scripts\python gerar_relatorio.py --headed --max-tasks 10 --debug
pause
