@echo off
REM Batch script to import both 2025-2026 and 2026-2027 darts seasons
REM Usage: Run this script from the scripts directory

echo.
echo ========================================
echo Stallion Bullets - Legacy Data Importer
echo ========================================
echo.

REM Check if manage.py exists
if not exist "manage.py" (
    echo Error: manage.py not found. Please run this script from the scripts directory.
    pause
    exit /b 1
)

call "%~dp0ensure_python312.bat"
if errorlevel 1 (
    pause
    exit /b 1
)

REM Delete existing database to start fresh
echo [0/4] Clearing database...
echo ========================================
if exist "..\data\competitie.sqlite3" (
    del "..\data\competitie.sqlite3"
    echo Database cleared.
) else (
    echo No existing database found.
)
echo.

REM Run database migrations
echo [1/4] Setting up database...
echo ========================================
%PYTHON_CMD% manage.py migrate
if errorlevel 1 (
    echo.
    echo Error: Failed to initialize database.
    pause
    exit /b 1
)
echo.
echo [✓] Database initialized successfully.
echo.

REM Import 2025-2026 season
echo [2/4] Importing 2025-2026 season...
echo ========================================
%PYTHON_CMD% manage.py import_legacy_data --season 2025-2026
if errorlevel 1 (
    echo.
    echo Error: Failed to import 2025-2026 season.
    pause
    exit /b 1
)
echo.
echo [✓] 2025-2026 season imported successfully.
echo.

REM Import 2026-2027 season
echo [3/4] Importing 2026-2027 season...
echo ========================================
%PYTHON_CMD% manage.py import_legacy_data --season 2026-2027
if errorlevel 1 (
    echo.
    echo Error: Failed to import 2026-2027 season.
    pause
    exit /b 1
)
echo.
echo [✓] 2026-2027 season imported successfully.
echo.

echo ========================================
echo All seasons imported successfully!
echo ========================================
echo.
pause
