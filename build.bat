@echo off
REM ============================================================
REM  TibiaAssist - build do executavel (rodar NO WINDOWS)
REM
REM    build.bat          -> build normal (sem console)
REM    build.bat debug    -> build com console, mostra tracebacks
REM ============================================================
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Criando ambiente virtual...
    python -m venv .venv || goto :erro
) else (
    echo [1/4] Ambiente virtual ja existe.
)

echo [2/4] Instalando dependencias...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :erro
".venv\Scripts\python.exe" -m pip install pyinstaller || goto :erro

if /i "%~1"=="debug" (
    echo [3/4] Modo DEBUG: o executavel abrira com janela de console.
    set TIBIAASSIST_CONSOLE=1
) else (
    echo [3/4] Modo normal: executavel sem console.
    set TIBIAASSIST_CONSOLE=
)

echo [4/4] Gerando o executavel...
".venv\Scripts\python.exe" -m PyInstaller TibiaAssist.spec --noconfirm --clean || goto :erro

echo.
echo ============================================================
echo  Pronto: dist\TibiaAssist.exe
echo.
echo  Antes de empacotar para outra maquina, lembre-se de que o
echo  Tesseract OCR e um programa separado e precisa estar
echo  instalado no computador que for rodar o RuneMaker.
echo ============================================================
goto :fim

:erro
echo.
echo *** A build falhou. Veja a mensagem de erro acima. ***
exit /b 1

:fim
endlocal
