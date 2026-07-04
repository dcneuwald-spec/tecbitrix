@echo off
REM ============================================================
REM  RODADA DE TESTE: 10 tarefas, busca manual no navegador, debug
REM  Voce navega/pesquisa no Chrome; pressione ENTER no terminal
REM  quando a lista de tarefas do cliente estiver na tela.
REM  Saidas: relatorios\  e  relatorios\debug\ (coleta.png, links.txt)
REM ============================================================
cd /d %~dp0
.venv\Scripts\python gerar_relatorio.py --max-tasks 10 --debug
pause
