@echo off
set "PYTHON_CMD="
set "PYTHON_VERSION="

call :try_py_launcher
if not errorlevel 1 goto resolved

call :try_python_command
if not errorlevel 1 goto resolved

echo Python 3.12 niet gevonden. Probeer automatisch te installeren...

where py >nul 2>&1
if not errorlevel 1 (
    py install 3.12 >nul 2>&1
    call :try_py_launcher
    if not errorlevel 1 goto resolved
)

where winget >nul 2>&1
if not errorlevel 1 (
    winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements >nul 2>&1
    call :try_py_launcher
    if not errorlevel 1 goto resolved
    call :try_python_command
    if not errorlevel 1 goto resolved
)

echo Kon Python 3.12 niet automatisch beschikbaar maken.
echo Installeer Python 3.12 handmatig en probeer opnieuw.
echo Download Python via https://www.python.org/downloads/
exit /b 1

:resolved
echo Python %PYTHON_VERSION% geselecteerd.
exit /b 0

:try_py_launcher
py -3.12 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>&1
if errorlevel 1 exit /b 1
set "PYTHON_CMD=py -3.12"
set "PYTHON_VERSION=3.12"
exit /b 0

:try_python_command
set "CANDIDATE_VERSION="
for /f "delims=" %%P in ('python -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" 2^>nul') do set "CANDIDATE_VERSION=%%P"
if not "%CANDIDATE_VERSION%"=="3.12" exit /b 1
set "PYTHON_CMD=python"
set "PYTHON_VERSION=3.12"
exit /b 0
