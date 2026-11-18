import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from datetime import datetime, timezone
from core.central_risk_desk import CentralRiskDesk

print("--- Testing Dual-Mode Asymmetric Controller ---")

desk = CentralRiskDesk(
    hard_daily_target_usd=200.0,
    max_daily_drawdown_usd=100.0,
    fat_tail_override_enabled=True,
    macro_news_window_utc=("23:58", "23:59"),
    rollover_curfew_utc=("23:58", "23:59")
)

acc = {"equity": 10000.0, "margin_level": 500.0, "margin": 100.0}

# 1. Normal state: Realized PnL = $0 -> APPROVED
safe, msg = desk.check_pre_trade_safety("XAUUSDm", 15.0, 35.0, [], acc, signal_regime="BASELINE")
assert safe, f"Expected APPROVED, got: {msg}"
print("✅ Test 1: Baseline Approval PASSED")

# 2. Daily target reached: Realized PnL = +$220.00
desk.record_trade_result("XAUUSDm", 220.0, comment="TP Hit")
# A: Standard BASELINE signal -> REJECT (Hard Lock)
safe_base, msg_base = desk.check_pre_trade_safety("XAUUSDm", 15.0, 35.0, [], acc, signal_regime="BASELINE")
assert not safe_base and "Daily Profit Target Reached" in msg_base, f"Expected Target Lock, got: {msg_base}"
print("✅ Test 2A: Baseline Hard Daily Lock (+ $200) PASSED")

# B: FAT_TAIL Conviction signal during US Session (14:00 UTC) -> OVERRIDE (Approved)
t_us = datetime(2026, 11, 17, 14, 0, tzinfo=timezone.utc)
safe_ft, msg_ft = desk.check_pre_trade_safety("XAUUSDm", 15.0, 35.0, [], acc, signal_regime="FAT_TAIL", now_utc=t_us)
assert safe_ft, f"Expected Fat-Tail Override, got: {msg_ft}"
print("✅ Test 2B: Fat-Tail Conviction Override during US Session PASSED")

# 3. Hard Daily Stop: Realized PnL = -$120.00
if Path("HALT_TEST_LOSS").exists():
    Path("HALT_TEST_LOSS").unlink()

desk_loss = CentralRiskDesk(
    hard_daily_target_usd=200.0,
    max_daily_drawdown_usd=100.0,
    max_daily_loss_per_symbol_usd=200.0,
    halt_file="HALT_TEST_LOSS",
    macro_news_window_utc=("23:58", "23:59"),
    rollover_curfew_utc=("23:58", "23:59")
)
desk_loss.record_trade_result("XAUUSDm", -120.0, comment="SL Hit")
safe_loss, msg_loss = desk_loss.check_pre_trade_safety("XAUUSDm", 15.0, 35.0, [], acc, signal_regime="FAT_TAIL", now_utc=t_us)
assert not safe_loss and ("Daily Loss Hard Stop" in msg_loss or "Kill-switch" in msg_loss), f"Expected Hard Loss Stop, got: {msg_loss}"
if Path("HALT_TEST_LOSS").exists():
    Path("HALT_TEST_LOSS").unlink()
print("✅ Test 3: Hard Daily Drawdown Stop (-$100) PASSED")

print("\n🎉 ALL DUAL-MODE CONTROLLER TESTS PASSED PERFECTLY!")
