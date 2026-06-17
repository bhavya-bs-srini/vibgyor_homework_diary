@echo off
title VIBGYOR Diary App - Gemini Edition
color 0A
cls

echo ============================================================
echo   VIBGYOR Diary - Reinforcement Extractor
echo   Auto Setup and Launch
echo ============================================================
echo.

:: ── Step 1: Check Python ─────────────────────────────────────────────────────
echo [1/4] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  Python not found. Attempting to install via winget...
    winget install Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo.
        echo  *** winget install failed. ***
        echo  Please install Python manually:
        echo  1. Go to https://www.python.org/downloads/
        echo  2. Download Python 3.11 or newer
        echo  3. During install, TICK "Add Python to PATH"
        echo  4. Re-run this file after installing.
        echo.
        pause
        exit /b 1
    )
    echo  Python installed. Refreshing environment...
    call refreshenv >nul 2>&1
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo  Found: %PYVER%
echo.

:: ── Step 2: Check pip ────────────────────────────────────────────────────────
echo [2/4] Checking pip...
python -m pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  pip not found. Installing pip...
    python -m ensurepip --upgrade
    if %errorlevel% neq 0 (
        echo  *** Could not install pip. ***
        echo  Try running: python -m ensurepip --upgrade
        pause
        exit /b 1
    )
)
echo  pip OK.
echo.

:: ── Step 3: Install packages ─────────────────────────────────────────────────
echo [3/4] Installing required packages (flask, openpyxl)...
echo  This may take a minute on first run...
echo.
python -m pip install flask openpyxl --quiet --upgrade
if %errorlevel% neq 0 (
    echo.
    echo  *** Package install failed. ***
    echo  Try running manually:
    echo      python -m pip install flask openpyxl pdfplumber
    echo  Then re-run this file.
    pause
    exit /b 1
)
echo  All packages installed.
echo.

:: ── Step 4: Check app.py exists ──────────────────────────────────────────────
echo [4/4] Checking app files...
if not exist "%~dp0app.py" (
    echo.
    echo  *** app.py not found in this folder! ***
    echo  Make sure app.py is in the same folder as this .bat file:
    echo  %~dp0
    echo.
    pause
    exit /b 1
)
if not exist "%~dp0templates\index.html" (
    echo.
    echo  *** templates\index.html not found! ***
    echo  Make sure the folder structure is:
    echo    diary-app\
    echo      app.py
    echo      run.bat          ^(this file^)
    echo      templates\
    echo        index.html
    echo.
    pause
    exit /b 1
)

:: Create required folders silently
if not exist "%~dp0uploads"  mkdir "%~dp0uploads"
if not exist "%~dp0outputs"  mkdir "%~dp0outputs"

echo  All files found.
echo.

:: ── Check if port 5000 is in use ────────────────────────────────────────────
netstat -ano | findstr ":5000 " >nul 2>&1
if %errorlevel% equ 0 (
    echo  Port 5000 is already in use. Switching to port 5001...
    set FLASK_PORT=5001
) else (
    set FLASK_PORT=5000
)

:: ── Launch ───────────────────────────────────────────────────────────────────
echo ============================================================
echo   Launching app on http://localhost:%FLASK_PORT%
echo   Opening browser in 3 seconds...
echo   Press Ctrl+C in this window to stop the app.
echo ============================================================
echo.

:: Open browser after 3-second delay (in background)
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:%FLASK_PORT%"

:: Run Flask on the detected port
cd /d "%~dp0"
python -c "
import app as a
import os
os.environ['FLASK_PORT'] = '%FLASK_PORT%'
a.app.run(debug=False, port=%FLASK_PORT%)
"

if %errorlevel% neq 0 (
    echo.
    echo  *** The app crashed or failed to start. ***
    echo  Common fixes:
    echo    - Make sure app.py has no errors
    echo    - Try a different port by editing this file
    echo    - Check the error message above
    echo.
    pause
)
