@echo off
title Nova AI - Hybrid Personal AI Assistant
echo ===================================================
echo              Starting Nova AI Assistant...
echo ===================================================
echo.

cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" (
    echo Activating Virtual Environment...
    call .venv\Scripts\activate.bat
) else (
    echo [WARNING] .venv not found. Running with system Python...
)

echo Starting main application...
python main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Nova AI exited with an error code %ERRORLEVEL%.
    pause
)
