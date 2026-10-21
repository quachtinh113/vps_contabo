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
call python run_hft_bot.py

:: Check exit code
set EXIT_CODE=%ERRORLEVEL%

if %EXIT_CODE% EQU 42 goto handle_hot_reload
if %EXIT_CODE% EQU 0 goto handle_clean_exit
goto handle_error_exit

:handle_hot_reload
echo.
echo =======================================================
echo  [HOT-RELOAD] Zero-downtime hot-reload triggered
echo  Restarting immediately with updated code and config
echo =======================================================
set /a RESTART_COUNT=0
ping -n 3 127.0.0.1 >nul
goto start_loop

:handle_clean_exit
echo.
echo =======================================================
echo  Bot stopped gracefully [exit code 0]. Not restarting.
echo =======================================================
exit /b 0

:handle_error_exit
echo.
echo =======================================================
echo  Bot exited with code %EXIT_CODE%.
echo  Restarting in %RESTART_DELAY% seconds...
echo =======================================================
ping -n %RESTART_DELAY% 127.0.0.1 >nul
goto start_loop
