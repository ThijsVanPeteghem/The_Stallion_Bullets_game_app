@echo off
setlocal
cd /d "%~dp0.."
title The Stallion Bullets - %APP_MODE%

where py >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=py -3"
) else (
    set "PYTHON=python"
)

%PYTHON% --version >nul 2>&1
if errorlevel 1 (
    echo Python is niet gevonden. Installeer Python 3 en probeer het opnieuw.
    echo Download Python via https://www.python.org/downloads/
    pause
    exit /b 1
)

%PYTHON% -c "import django" >nul 2>&1
if errorlevel 1 (
    echo Benodigde onderdelen worden eenmalig geinstalleerd...
    %PYTHON% -m pip install -r config\requirements.txt
    if errorlevel 1 (
        echo Installeren is mislukt. Controleer uw internetverbinding en probeer opnieuw.
        pause
        exit /b 1
    )
)

echo De database voor %APP_MODE% wordt bijgewerkt...
%PYTHON% scripts\manage.py migrate --noinput
if errorlevel 1 (
    echo De database kon niet worden bijgewerkt. De applicatie wordt niet gestart.
    pause
    exit /b 1
)

echo %APP_MODE% start op http://127.0.0.1:8000
echo Laat dit venster open zolang u de applicatie gebruikt.
echo Sluit de applicatie met Ctrl+C en sluit daarna dit venster.
start "" powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8000'"
%PYTHON% scripts\manage.py runserver 127.0.0.1:8000
pause
