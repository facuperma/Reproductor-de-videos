@echo off
chcp 65001 >nul
title Preparar la PC para compilar TVon
cd /d "%~dp0"

echo == 1/4  Instalando Python 3.12, Inno Setup y FFmpeg (tarda unos minutos)
winget install -e --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements
winget install -e --id JRSoftware.InnoSetup --accept-source-agreements --accept-package-agreements
winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements

set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY%" (
    echo.
    echo No se encontro Python en "%PY%". Mira si arriba hubo un error de winget.
    pause
    exit /b 1
)

echo.
echo == 2/4  Entorno de Python del proyecto (.venv)
if not exist ".venv\Scripts\python.exe" "%PY%" -m venv .venv

echo.
echo == 3/4  Dependencias de TVon y PyInstaller (baja unos 200 MB)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt pyinstaller

echo.
echo == 4/4  Subiendo los cambios a GitHub (si pide iniciar sesion, entra con tu cuenta)
git push origin main

echo.
echo == Listo. Cerra esta ventana, reinicia VS Code y avisale a Claude.
pause
