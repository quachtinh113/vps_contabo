@echo off
title HFT_ML4T - Production HFT Trading Bot
color 0A

echo =======================================================
echo          HFT_ML4T - INITIALIZING HFT BOT...
echo =======================================================
echo.

:: Ensure we are in the correct directory
cd /d "%~dp0"

:: Set utf-8 encoding for proper emoji display
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1

:: Auto-restart loop (max 50 restarts to prevent infinite crash loops)
set /a RESTART_COUNT=0
set MAX_RESTARTS=50
set RESTART_DELAY=15

:start_loop
set /a RESTART_COUNT+=1

if %RESTART_COUNT% GTR %MAX_RESTARTS% (
    echo.
    echo =======================================================
    echo  ERROR: Max restarts reached [%MAX_RESTARTS%]. Bot will NOT restart.
    echo  Please check logs and fix the issue manually.
    echo =======================================================
    pause
    exit /b 1
)

echo.
echo [%date% %time%] Starting HFT bot (attempt %RESTART_COUNT%/%MAX_RESTARTS%)...
echo.

:: Run the bot
python run_hft_bot.py

:: Check exit code
set EXIT_CODE=%ERRORLEVEL%

if %EXIT_CODE% EQU 0 (
    echo.
    echo =======================================================
    echo  Bot stopped gracefully [exit code 0]. Not restarting.
    echo =======================================================
    exit /b 0
)

echo.
echo =======================================================
echo  Bot exited with code %EXIT_CODE%.
echo  Restarting in %RESTART_DELAY% seconds...
echo =======================================================

:: Wait before restart (using ping for reliable sleep in all environments)
ping -n %RESTART_DELAY% 127.0.0.1 >nul

goto start_loop
