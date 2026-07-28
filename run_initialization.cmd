@echo off
setlocal enabledelayedexpansion
title Bing Wallpaper Pipeline Setup Engine

echo =======================================================================
echo     BING WALLPAPER PIPELINE - AUTOMATED CORE DEPENDENCY LIFECYCLE
echo =======================================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] CRITICAL SYSTEM FAILURE: Python interpreter was not detected.
    echo [!] Please install Python 3.9+ and add it to your Windows Environment PATH.
    echo.
    pause
    exit /b 1
)

echo [*] Upgrading default system packet management layer (pip)...
python -m pip install --upgrade pip --quiet
if %errorlevel% neq 0 (
    echo [Warning] Non-fatal notification: Pipeline skipped pipeline manager upgrade package.
)

echo [*] Executing deployment framework bindings from requirements.txt...
python -m pip install -r requirements.txt --user
if %errorlevel% neq 0 (
    echo [!] CRITICAL DEPLOYMENT FAILURE: Subsystem packages rejected tracking installation.
    echo.
    pause
    exit /b 1
)

echo.
echo [+] Success! All prerequisite operational dependencies successfully deployed.
echo -----------------------------------------------------------------------
echo.
echo [*] Launching Multi-Threaded Concurrent Connection Background Engine...
echo.

python "2. grab_everything_multithreaded_with_deduplication_and_automatic-npanuhin.me-all.json_download.py"

echo.
echo =======================================================================
echo   Pipeline execution cycle terminated. Press any key to exit shell.
echo =======================================================================
pause >nul