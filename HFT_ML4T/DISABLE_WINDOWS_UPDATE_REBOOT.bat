@echo off
title Disable Windows Update Auto-Reboot
color 0A

echo ========================================================
echo  CONFIGURING WINDOWS UPDATE POLICY (24/7 VPS PROTECTION)
echo ========================================================
echo.

:: Check for administrative rights
net session >nul 2>&1
if %errorLevel% NEQ 0 (
    echo [ERROR] Must be executed as Administrator!
    echo Please right-click this file and select "Run as administrator".
    echo.
    pause
    exit /b 1
)

reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" /v NoAutoRebootWithLoggedOnUsers /t REG_DWORD /d 1 /f
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" /v AUOptions /t REG_DWORD /d 3 /f

echo.
echo ========================================================
echo [SUCCESS] Windows Update Auto-Reboot is now DISABLED!
echo Your VPS will NEVER restart automatically while logged on.
echo ========================================================
echo.
pause
