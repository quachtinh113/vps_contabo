@echo off
chcp 65001 >nul
cd /d "c:\Word_Quant\05_Quant"
echo ================================================================================
echo [POST-US-SESSION AUTO PIPELINE] Running Unified Audit and Launching Latest Bot...
echo ================================================================================
python ".agents\skills\daily-quant-audit-system\scripts\post_us_session_auto_pipeline.py" --live-mt5 --pretty

