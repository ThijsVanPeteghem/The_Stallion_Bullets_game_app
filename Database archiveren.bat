@echo off
setlocal
cd /d "%~dp0"
title The Stallion Bullets - Database archiveren

echo Kies welke database een tijdstempel-snapshot moet krijgen.
echo De app mag blijven draaien; SQLite maakt een consistente kopie.
echo.
choice /c 12X /n /m "Kies 1 voor competitie, 2 voor sandbox, of X om te annuleren: "
if errorlevel 3 goto canceled
if errorlevel 2 goto sandbox
set "APP_MODE=Competitie"
set "DATABASE_NAME=data\competitie.sqlite3"
goto selected

:sandbox
set "APP_MODE=Sandbox"
set "DATABASE_NAME=data\competitie-sandbox.sqlite3"

:selected
where py >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=py -3"
) else (
    set "PYTHON=python"
)

%PYTHON% --version >nul 2>&1
if errorlevel 1 (
    echo Python 3 is niet gevonden. Installeer Python en probeer opnieuw.
    goto end
)

echo.
echo Snapshot maken van %APP_MODE%...
%PYTHON% scripts\manage.py snapshot_database --output-dir "%~dp0database_snapshots"
if errorlevel 1 (
    echo.
    echo Het database snapshot kon niet worden gemaakt.
    goto end
)
goto end

:canceled
echo.
echo Geannuleerd. Er is geen snapshot gemaakt.

:end
echo.
pause
