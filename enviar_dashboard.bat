@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "GIT=C:\Program Files\Git\cmd\git.exe"
set "REPO=%~dp0"
if "%REPO:~-1%"=="\" set "REPO=%REPO:~0,-1%"

cd /d "%REPO%" || exit /b 1
if not exist "%GIT%" (echo [ERRO] Git nao encontrado & pause & exit /b 1)

"%GIT%" status -s | findstr /R "." >nul || (echo Nenhuma alteracao. & pause & exit /b 0)

set "MSG="
set /p "MSG=Mensagem do commit (Enter = padrao): "
if "!MSG!"=="" set "MSG=Atualizacao dashboard"

"%GIT%" add .
"%GIT%" commit -m "!MSG!"
"%GIT%" push origin main
if errorlevel 1 (echo [ERRO] Push falhou. & pause & exit /b 1)
echo [OK] Enviado.
pause