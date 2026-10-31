@echo off
chcp 65001 >nul
cd /d "C:\VPS CONTABO\HFT_ML4T"
echo ================================================================================
echo [SKILL AUDIT EVER DAY MORE 100$] Running Unified Audit and Launching Latest Bot...
echo ================================================================================
python "skill-audit-ever-day-more-100\scripts\post_us_session_auto_pipeline.py" --live-mt5 --pretty
