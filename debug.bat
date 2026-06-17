@echo off
title VIBGYOR Diary - Debug Mode
color 0E
cls

echo ============================================================
echo   DEBUG MODE - Reading errors...
echo ============================================================
echo.

cd /d "%~dp0"

echo Current folder: %~dp0
echo.
echo Files found:
dir /b
echo.
echo ── Checking Python ──
python --version
echo.
echo ── Checking packages ──
python -m pip show flask
echo.
python -m pip show openpyxl
echo.
python -m pip show pdfplumber
echo.
echo ── Starting app (errors will show below) ──
echo.
python app.py

echo.
echo ============================================================
echo   App stopped. Read the errors above.
echo ============================================================
pause
