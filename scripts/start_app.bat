@echo off
setlocal
cd /d "%~dp0.."
title The Stallion Bullets - %APP_MODE%

call "%~dp0ensure_python312.bat"
if errorlevel 1 (
    pause
    exit /b 1
)

%PYTHON_CMD% -c "import django; from ortools.sat.python import cp_model" >nul 2>&1
if errorlevel 1 (
    echo Benodigde onderdelen worden eenmalig geinstalleerd...
    %PYTHON_CMD% -m pip install -r config\requirements.txt
    if errorlevel 1 (
        echo Installeren is mislukt. Controleer uw internetverbinding en probeer opnieuw.
        pause
        exit /b 1
    )
)

echo De database voor %APP_MODE% wordt bijgewerkt...
%PYTHON_CMD% scripts\manage.py migrate --noinput
if errorlevel 1 (
    echo De database kon niet worden bijgewerkt. De applicatie wordt niet gestart.
    pause
    exit /b 1
)

echo %APP_MODE% start op http://127.0.0.1:8000
echo Laat dit venster open zolang u de applicatie gebruikt.
echo Sluit de applicatie met Ctrl+C en sluit daarna dit venster.
start "" powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8000'"
%PYTHON_CMD% scripts\manage.py runserver 127.0.0.1:8000
pause
