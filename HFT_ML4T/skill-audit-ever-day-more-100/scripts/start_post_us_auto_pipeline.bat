@echo off
chcp 65001 >nul
cd /d "c:\Word_Quant\05_Quant"
echo ================================================================================
echo [SKILL AUDIT EVER DAY MORE 100$] Running Unified Audit and Launching Latest Bot...
echo ================================================================================
python ".agents\skills\skill-audit-ever-day-more-100\scripts\post_us_session_auto_pipeline.py" --live-mt5 --pretty

