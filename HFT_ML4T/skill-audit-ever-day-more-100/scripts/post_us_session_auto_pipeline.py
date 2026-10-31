#!/usr/bin/env python3
"""Skill Audit Ever Day More 100$ (`skill-audit-ever-day-more-100`) — Post-US-Session Auto-Audit & Process Relauncher.

Combines `daily-quant-audit-system` + `daily-tri-block-audit` into 1 master pipeline (`skill audit ever day more 100$`) that:
1. Triggers automatically right after the US Session closes (21:05 UTC / 23:45 Broker Server Time / 04:05 GMT+7),
   or runs immediately.
2. Enforces the 23:45 Server Time EOD Flat check on Live MT5.
3. Runs the Unified Master Audit (Status Tiers, Ticket Attribution, 3A Tri-Block Alpha/ML/Emergency Forensics,
   3B Keep-vs-Fix Matrix, >$100/day Reconciliation, and Section 4 Counterfactual No-Regression Gate).
4. Saves the timestamped JSON + Markdown report to `05_ALL_Bot/logs/daily_audit_reports/`.
5. Verifies the 5 Institutional Commandments (Drawdown Ladder > -7.5%) and AUTOMATICALLY LAUNCHES / RESTARTS
   the latest bot process (`run_unified_bot.py`, `pipeline_live.py`, `live_trade.py`, or custom `--process-cmd`)
   immediately after the audit finishes!
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import subprocess
import sys
import time
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
ALL_BOT_DIR = WORKSPACE_ROOT
REPORT_ARCHIVE_DIR = WORKSPACE_ROOT / "logs" / "daily_audit_reports"
UNIVERSAL_AUDIT_SCRIPT = (
    WORKSPACE_ROOT
    / "07_Skill"
    / "Quant_Audit"
    / "scripts"
    / "audit_any_bot.py"
)

CANDIDATE_BOT_ENTRYPOINTS: List[Tuple[str, Path]] = [
    ("HFT_ML4T", WORKSPACE_ROOT / "run_hft_bot.py"),
]


def load_audit_module():
    spec = importlib.util.spec_from_file_location("audit_any_bot", str(UNIVERSAL_AUDIT_SCRIPT))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {UNIVERSAL_AUDIT_SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def discover_latest_bot_entrypoint(target_bot_dir: Optional[Path] = None) -> Tuple[str, Path]:
    """Find the most recently updated bot runner script in `--bot-dir` or across `05_ALL_Bot`."""
    if target_bot_dir and target_bot_dir.exists():
        target_bot_dir = target_bot_dir.resolve()
        for pat in ("run_unified_bot.py", "pipeline_live.py", "live_trade.py", "*orchestrator*.py", "main.py", "run*.py"):
            matches = sorted(target_bot_dir.glob(pat), key=lambda p: p.stat().st_mtime, reverse=True)
            if matches:
                return target_bot_dir.name, matches[0].resolve()

    existing: List[Tuple[str, Path, float]] = []
    for name, path in CANDIDATE_BOT_ENTRYPOINTS:
        if path.exists():
            existing.append((name, path.resolve(), path.stat().st_mtime))
    if not existing:
        raise FileNotFoundError("No bot entrypoint script found in 05_ALL_Bot.")
    existing.sort(key=lambda x: x[2], reverse=True)
    return existing[0][0], existing[0][1]


def check_and_launch_latest_bot_process(
    bot_name: str,
    entrypoint_path: Path,
    audit_payload: Dict[str, Any],
    custom_cmd: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Verify Risk Gate after audit and automatically launch/restart the latest bot process."""
    entrypoint_path = entrypoint_path.resolve()
    rec = audit_payload.get("3_daily_100usd_reconciliation", {})
    nrg = audit_payload.get("counterfactual_no_regression_gate", {})

    tiers = audit_payload.get("1_status_tiers", [])
    is_halted = any("TIER_3_HALTED" in str(t.get("detail", "")) for t in tiers)
    if is_halted:
        return {
            "relaunch_status": "BLOCKED_BY_TIER_3_HALT",
            "bot_name": bot_name,
            "entrypoint": str(entrypoint_path),
            "reason": "Tài khoản chạm ngưỡng ngắt mạch khẩn cấp TIER_3_HALTED (-7.5% DD). Đóng băng mở tiến trình mới theo Điều Răn #1.",
        }

    cmd_list = custom_cmd.split() if custom_cmd else [sys.executable, str(entrypoint_path)]
    log_dir = REPORT_ARCHIVE_DIR / "process_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    proc_log_file = log_dir / f"{bot_name.replace(' ', '_')}_{ts_tag}.log"

    if dry_run:
        return {
            "relaunch_status": "READY_VERIFIED (DRY-RUN)",
            "bot_name": bot_name,
            "entrypoint": str(entrypoint_path),
            "last_modified": datetime.fromtimestamp(entrypoint_path.stat().st_mtime).isoformat(),
            "command": " ".join(cmd_list),
            "process_log": str(proc_log_file),
            "no_regression_gate": nrg.get("verdict", "PASS"),
            "potential_daily_pnl_usd": rec.get("clean_no_bad_loss_avg_daily_pnl_usd", 0.0),
        }

    # Check if run_hft_bot.py is already running under start_bot.bat / Watchdog
    if os.name == "nt" and entrypoint_path.name == "run_hft_bot.py":
        ps_check = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'run_hft_bot\\.py' -and $_.Name -match 'python' } | Select-Object -First 1 -ExpandProperty ProcessId",
            ],
            capture_output=True,
            text=True,
        )
        existing_pid_str = ps_check.stdout.strip()
        if existing_pid_str.isdigit():
            return {
                "relaunch_status": "RUNNING_ACTIVE (SUPERVISED_BY_WATCHDOG)",
                "pid": int(existing_pid_str),
                "bot_name": bot_name,
                "entrypoint": str(entrypoint_path),
                "last_modified": datetime.fromtimestamp(entrypoint_path.stat().st_mtime).isoformat(),
                "command": " ".join(cmd_list),
                "working_dir": str(entrypoint_path.parent),
                "process_log": str(WORKSPACE_ROOT / "logs" / f"hft_live_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.log"),
                "no_regression_gate": nrg.get("verdict", "PASS"),
            }

    creation_flags = 0
    if os.name == "nt":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    with proc_log_file.open("a", encoding="utf-8") as lf:
        lf.write(f"=== [{datetime.now(timezone.utc).isoformat()}] AUTO-LAUNCHED BY SKILL AUDIT EVER DAY MORE 100$ ===\n")
        lf.flush()
        proc = subprocess.Popen(
            cmd_list,
            cwd=str(entrypoint_path.parent),
            stdout=lf,
            stderr=subprocess.STDOUT,
            creationflags=creation_flags,
        )

    time.sleep(0.8)
    poll_code = proc.poll()
    is_running = poll_code is None

    return {
        "relaunch_status": "RUNNING_ACTIVE" if is_running else f"EXITED_EARLY (code={poll_code})",
        "pid": proc.pid,
        "bot_name": bot_name,
        "entrypoint": str(entrypoint_path),
        "last_modified": datetime.fromtimestamp(entrypoint_path.stat().st_mtime).isoformat(),
        "command": " ".join(cmd_list),
        "working_dir": str(entrypoint_path.parent),
        "process_log": str(proc_log_file),
        "no_regression_gate": nrg.get("verdict", "PASS"),
    }


def execute_post_us_session_pipeline(
    bot_dir: Optional[Path] = None,
    use_live_mt5: bool = False,
    custom_process_cmd: Optional[str] = None,
    dry_run_relaunch: bool = False,
    pretty: bool = True,
) -> Dict[str, Any]:
    """Run the full Post-US-Session Audit -> Save Report -> Launch Latest Bot Process pipeline."""
    mod = load_audit_module()
    bot_name, latest_entrypoint = discover_latest_bot_entrypoint(bot_dir)
    effective_bot_dir = bot_dir.resolve() if bot_dir else latest_entrypoint.parent

    payload = mod.run_universal_bot_audit(
        bot_dir=effective_bot_dir,
        use_live_mt5=use_live_mt5,
        daily_target_usd=100.0,
        lookback_hours=168,
    )
    payload["skill_name"] = "skill audit ever day more 100$ (skill-audit-ever-day-more-100)"

    buf = io.StringIO()
    with redirect_stdout(buf):
        mod.print_pretty_report(payload)
    pretty_text = buf.getvalue()

    REPORT_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    date_tag = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    safe_bot = bot_name.replace(" ", "_")
    json_report_path = REPORT_ARCHIVE_DIR / f"audit_100usd_{safe_bot}_{date_tag}.json"
    md_report_path = REPORT_ARCHIVE_DIR / f"audit_100usd_{safe_bot}_{date_tag}.md"

    relaunch_info = check_and_launch_latest_bot_process(
        bot_name=bot_name,
        entrypoint_path=latest_entrypoint,
        audit_payload=payload,
        custom_cmd=custom_process_cmd,
        dry_run=dry_run_relaunch,
    )
    payload["5_post_audit_auto_runner"] = relaunch_info

    json_report_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    md_report_path.write_text(
        "🏆 [SKILL: skill audit ever day more 100$ (skill-audit-ever-day-more-100)]\n"
        + pretty_text
        + "\n### 5. TRẠNG THÁI TỰ ĐỘNG KHỞI CHẠY TIẾN TRÌNH MỚI NHẤT SAU AUDIT (POST-AUDIT AUTO-RUNNER)\n"
        + "-" * 104
        + f"\n  • Trạng thái tiến trình : {relaunch_info['relaunch_status']}"
        + (f" (PID: {relaunch_info['pid']})" if "pid" in relaunch_info else "")
        + f"\n  • Tiến trình mới nhất   : {relaunch_info['entrypoint']} (Cập nhật lúc: {relaunch_info.get('last_modified', 'N/A')})"
        + f"\n  • Lệnh khởi chạy        : {relaunch_info.get('command', 'N/A')}"
        + f"\n  • File Log Tiến Trình   : {relaunch_info.get('process_log', 'N/A')}"
        + f"\n  • Bản lưu Báo cáo Audit : {md_report_path}\n"
        + "=" * 104
        + "\n",
        encoding="utf-8",
    )

    if pretty:
        print(md_report_path.read_text(encoding="utf-8"))
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=False))

    return payload


def register_windows_scheduled_task(daily_time_local: str = "04:05") -> str:
    """Register Windows Task Scheduler job to run automatically after US Session close (04:05 GMT+7 = 21:05 UTC = 23:45 Server Time)."""
    task_name = "Skill_Audit_Ever_Day_More_100USD"
    bat_path = Path(__file__).resolve().parent / "start_post_us_auto_pipeline.bat"
    cmd = [
        "schtasks",
        "/Create",
        "/F",
        "/SC",
        "DAILY",
        "/TN",
        task_name,
        "/TR",
        f'"{bat_path}"',
        "/ST",
        daily_time_local,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        return f"SUCCESS: Đã đăng ký Windows Scheduled Task '{task_name}' (skill audit ever day more 100$) tự động chạy lúc {daily_time_local} mỗi ngày (ngay sau khi đóng phiên Mỹ)."
    return f"WARNING: Không thể tạo schtasks tự động ({res.stderr.strip()}). Bạn có thể chạy bằng chế độ --daemon."


def run_us_session_close_daemon(
    bot_dir: Optional[Path],
    close_utc_hour: int = 21,
    close_utc_minute: int = 5,
    dry_run_relaunch: bool = False,
) -> None:
    """Background daemon that waits for US Session close (21:05 UTC / 23:45 Broker Server Time) and triggers Audit + Relaunch."""
    print(
        f"[SKILL AUDIT EVER DAY MORE 100$ — DAEMON] Đang trực chiến chờ kết thúc Phiên Mỹ ({close_utc_hour:02d}:{close_utc_minute:02d} UTC / 23:45 Server Time / 04:05 GMT+7)..."
    )
    last_triggered_date: Optional[str] = None
    while True:
        now_utc = datetime.now(timezone.utc)
        today_str = now_utc.strftime("%Y-%m-%d")
        if (
            now_utc.weekday() in (0, 1, 2, 3, 4)
            and now_utc.hour == close_utc_hour
            and now_utc.minute >= close_utc_minute
            and last_triggered_date != today_str
        ):
            print(f"\n⚡ [{now_utc.isoformat()}] PHIÊN MỸ ĐÃ ĐÓNG! Chạy 'skill audit ever day more 100$' & Khởi động tiến trình mới nhất...")
            execute_post_us_session_pipeline(
                bot_dir=bot_dir,
                use_live_mt5=True,
                dry_run_relaunch=dry_run_relaunch,
                pretty=True,
            )
            last_triggered_date = today_str
        time.sleep(30)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="skill audit ever day more 100$ — Post-US-Session Auto-Audit & Latest Bot Relauncher")
    parser.add_argument("--bot-dir", default=None, help="Target bot directory (auto-detects latest modified bot if omitted)")
    parser.add_argument("--live-mt5", action="store_true", help="Include Live MT5 deal & position inspection")
    parser.add_argument("--process-cmd", default=None, help="Custom command to launch after audit finishes")
    parser.add_argument("--dry-run-relaunch", action="store_true", help="Verify latest bot entrypoint without spawning a duplicate process")
    parser.add_argument("--daemon", action="store_true", help="Run continuous background daemon that triggers after every US Session close (21:05 UTC)")
    parser.add_argument("--install-windows-task", action="store_true", help="Register Windows Task Scheduler job at 04:05 GMT+7 (post US Session close)")
    parser.add_argument("--pretty", action="store_true", default=True, help="Print formatted report")
    args = parser.parse_args()

    if args.install_windows_task:
        print(register_windows_scheduled_task("04:05"))

    bot_dir = Path(args.bot_dir) if args.bot_dir else None

    if args.daemon:
        run_us_session_close_daemon(bot_dir=bot_dir, dry_run_relaunch=args.dry_run_relaunch)
    else:
        execute_post_us_session_pipeline(
            bot_dir=bot_dir,
            use_live_mt5=args.live_mt5,
            custom_process_cmd=args.process_cmd,
            dry_run_relaunch=args.dry_run_relaunch,
            pretty=args.pretty,
        )


if __name__ == "__main__":
    main()

