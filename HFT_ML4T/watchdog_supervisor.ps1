# =====================================================================
# HFT_ML4T — 24/7 Watchdog Supervisor
# Automatically monitors and self-heals MT5 Terminal and HFT Trading Bot.
# =====================================================================

$projectDir = "c:\VPS CONTABO\HFT_ML4T"
$mt5Exe = "C:\MT5_Exness\terminal64.exe"
$mt5Dir = "C:\MT5_Exness"
$logFile = Join-Path $projectDir "logs\watchdog.log"
$haltFile = Join-Path $projectDir "HALT_HFT"

# Ensure logs directory exists
$logDir = Join-Path $projectDir "logs"
if (!(Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

function Log-Message([string]$msg) {
    $timeStr = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $line = "[$timeStr] [WATCHDOG] $msg"
    Write-Output $line
    Add-Content -Path $logFile -Value $line -Encoding utf8
}

# 1. Check MT5 Terminal
$mt5Procs = Get-Process -Name "terminal64" -ErrorAction SilentlyContinue
if (!$mt5Procs) {
    Log-Message "⚠️ MT5 Terminal is NOT running. Auto-launching: $mt5Exe"
    if (Test-Path $mt5Exe) {
        Start-Process -FilePath $mt5Exe -WorkingDirectory $mt5Dir
        Start-Sleep -Seconds 15
        Log-Message "✅ MT5 Terminal launched. Waiting for broker connection."
    } else {
        Log-Message "❌ Error: MT5 executable not found at $mt5Exe"
    }
}

# 2. Check HFT Bot (run_hft_bot.py)
$botProcs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { 
    $_.CommandLine -match 'run_hft_bot' 
}

if ($botProcs) {
    # Bot is healthy
    Log-Message "💚 Health Check OK: MT5 (PID: $($mt5Procs[0].Id)) & Bot (PID: $($botProcs[0].ProcessId)) are active."
} else {
    # Check if manual kill-switch file HALT_HFT is present
    if (Test-Path $haltFile) {
        Log-Message "⏸️ Manual kill-switch ($haltFile) detected. Bot intentionally halted by user or risk limit. Skipping auto-restart."
    } else {
        Log-Message "⚠️ HFT Bot is NOT running and no HALT_HFT flag found. Auto-restarting bot via start_bot.bat..."
        Start-Process -FilePath "cmd.exe" -ArgumentList "/c start_bot.bat" -WorkingDirectory $projectDir
        Log-Message "✅ Bot restart command dispatched."
    }
}
