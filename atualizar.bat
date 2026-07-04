@echo off
REM ============================================================
REM  ATUALIZACAO: baixa a versao mais recente do GitHub e aplica
REM ============================================================
cd /d %~dp0

curl -L -o update.zip https://github.com/dcneuwald-spec/tecbitrix/archive/refs/heads/claude/bitrix24-data-extraction-9joh5e.zip
if errorlevel 1 (
    echo ERRO ao baixar a atualizacao. Verifique a internet e tente de novo.
    pause
    exit /b 1
)

tar -xf update.zip
xcopy /E /Y tecbitrix-claude-bitrix24-data-extraction-9joh5e\* . >nul
rmdir /S /Q tecbitrix-claude-bitrix24-data-extraction-9joh5e
del update.zip

echo.
echo ============================================================
echo  Atualizado com sucesso.
echo ============================================================
pause
