@echo off
REM Master batch script to:
REM 1. Delete database
REM 2. Start Django development server
REM 3. Run import_both_seasons.bat after server starts
REM Usage: Run from scripts directory

echo.
echo ========================================
echo Stallion Bullets - Setup & Import
echo ========================================
echo.

REM Check if manage.py exists
if not exist "manage.py" (
    echo Error: manage.py not found. Please run this script from the scripts directory.
    pause
    exit /b 1
)

REM Delete existing database
echo [1/3] Clearing database...
echo ========================================
if exist "..\data\competitie.sqlite3" (
    del "..\data\competitie.sqlite3"
    echo Database cleared.
) else (
    echo No existing database found.
)
echo.

REM Run database migrations
echo [2/3] Applying migrations...
echo ========================================
python manage.py migrate
if errorlevel 1 (
    echo.
    echo Error: Failed to apply migrations.
    pause
    exit /b 1
)
echo.
echo [3/3] Starting server...
echo ========================================
echo Starting Django development server...
echo Please wait for the server to be ready (watch for "Starting development server")
echo.

REM Start server in a new window so it keeps running
start "Stallion Bullets Server" cmd /k python manage.py runserver 0.0.0.0:8000

REM Wait for server to start (give it 5 seconds)
timeout /t 5 /nobreak

REM Run import script
echo.
echo [4/4] Running import for both seasons...
echo ========================================
call import_both_seasons.bat

if errorlevel 1 (
    echo.
    echo Error during import. The server will keep running for debugging.
    pause
) else (
    echo.
    echo ========================================
    echo Setup complete! Server is running at:
    echo http://localhost:8000
    echo ========================================
    echo.
    pause
)
