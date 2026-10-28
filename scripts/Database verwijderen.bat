@echo off
setlocal
cd /d "%~dp0.."
title The Stallion Bullets - Database verwijderen

echo WAARSCHUWING: de gekozen database en alle competitiegegevens worden permanent verwijderd.
echo Stop eerst de applicatie voordat u doorgaat.
echo.
choice /c 12X /n /m "Kies 1 voor competitie, 2 voor sandbox, of X om te annuleren: "
if errorlevel 3 goto canceled
if errorlevel 2 goto sandbox
set "DATABASE_FILE=data\competitie.sqlite3"
goto selected

:sandbox
set "DATABASE_FILE=data\competitie-sandbox.sqlite3"

:selected
set "DATABASE_PATH=%CD%\%DATABASE_FILE%"
if not exist "%DATABASE_PATH%" (
    echo.
    echo Databasebestand niet gevonden: %DATABASE_FILE%
    goto end
)

echo.
echo Te verwijderen bestand: %DATABASE_PATH%
set /p "CONFIRM=Typ DELETE om dit databasebestand definitief te verwijderen: "
if /i not "%CONFIRM%"=="DELETE" goto canceled

del /f /q "%DATABASE_PATH%"
if exist "%DATABASE_PATH%" (
    echo.
    echo FOUT: het databasebestand kon niet worden verwijderd.
    echo Controleer of de applicatie is gestopt en probeer opnieuw.
    goto end
)

if exist "%DATABASE_PATH%-wal" del /f /q "%DATABASE_PATH%-wal"
if exist "%DATABASE_PATH%-shm" del /f /q "%DATABASE_PATH%-shm"
if exist "%DATABASE_PATH%-journal" del /f /q "%DATABASE_PATH%-journal"
echo.
echo Database verwijderd: %DATABASE_FILE%
goto end

:canceled
echo.
echo Verwijderen geannuleerd. Er zijn geen bestanden verwijderd.

:end
echo.
pause
