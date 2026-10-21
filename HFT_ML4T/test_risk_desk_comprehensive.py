"""
========================================================================================
HFT_ML4T — COMPREHENSIVE INSTITUTIONAL CENTRAL RISK DESK TEST SUITE
Validates 9 Critical Safety Dimensions:
1. Spread Spike Barrier
2. Rollover Curfew Barrier
3. Post-SL Whipsaw Cooldown
4. Consecutive Loss Ladder & Pod Recovery (5m -> 45m -> 24h)
5. Margin Depletion Barrier (< 300% reject, < 150% emergency halt)
6. Daily Drawdown Breach & Auto Physical HALT_HFT Lockfile Generation
7. Asset Cluster Correlation Exposure Barrier (Metals, Crypto, etc.)
8. All-Time Trailing High-Water Mark (HWM) Drawdown Guard
9. Asymmetric Risk Recovery Hysteresis Ladder
========================================================================================
"""

import os
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

# Ensure project root is in path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.central_risk_desk import CentralRiskDesk


def test_1_spread_spike_barrier():
    desk = CentralRiskDesk()
    acc = {"equity": 10000.0, "margin_level": 500.0, "margin": 100.0}
    desk.update_account_state(acc)

    # Within limit: 25 <= 35
    safe, msg = desk.check_pre_trade_safety("XAUUSDm", 25.0, 35.0, [], acc)
    assert safe, f"Expected APPROVED, got {msg}"

    # Spread spike: 40 > 35
    safe, msg = desk.check_pre_trade_safety("XAUUSDm", 40.0, 35.0, [], acc)
    assert not safe, "Expected rejection due to spread spike"
    assert "exceeds maximum threshold" in msg
    print("✅ Test 1: Spread Spike Barrier PASSED")


def test_2_rollover_curfew_barrier():
    # Force curfew to match current time
    now_utc = datetime.now(timezone.utc)
    cur_time = now_utc.strftime("%H:%M")
    desk = CentralRiskDesk(rollover_curfew_utc=(cur_time, cur_time))
    acc = {"equity": 10000.0, "margin_level": 500.0, "margin": 100.0}
    desk.update_account_state(acc)

    safe, msg = desk.check_pre_trade_safety("EURUSDm", 10.0, 30.0, [], acc)
    assert not safe, "Expected rejection during active rollover curfew"
    assert "Rollover Curfew Active" in msg
    print("✅ Test 2: Rollover Curfew Barrier PASSED")


def test_3_post_sl_cooldown():
    desk = CentralRiskDesk(post_sl_cooldown_seconds=2.0)
    acc = {"equity": 10000.0, "margin_level": 500.0, "margin": 100.0}
    desk.update_account_state(acc)

    # Trigger cooldown for 1 second
    desk.trigger_cooldown("XAUUSDm", duration_sec=1.0, reason="Test SL")
    safe, msg = desk.check_pre_trade_safety("XAUUSDm", 20.0, 35.0, [], acc)
    assert not safe, "Expected cooldown rejection"
    assert "Post-SL Cooldown active" in msg

    # Wait for expiry
    time.sleep(1.1)
    safe, msg = desk.check_pre_trade_safety("XAUUSDm", 20.0, 35.0, [], acc)
    assert safe, f"Expected APPROVED after cooldown expiry, got {msg}"
    print("✅ Test 3: Post-SL Whipsaw Cooldown PASSED")


def test_4_consecutive_loss_ladder_and_pod_recovery():
    desk = CentralRiskDesk()
    acc = {"equity": 10000.0, "margin_level": 500.0, "margin": 100.0}
    desk.update_account_state(acc)

    # Trade 1 Lost (-$10) -> 300s cooldown
    desk.record_trade_result("BTCUSDm", -10.0, "Stop Loss #1")
    assert desk.get_symbol_risk_multiplier("BTCUSDm") == 1.0

    # Trade 2 Lost (-$10) -> 2700s cooldown
    desk.record_trade_result("BTCUSDm", -10.0, "Stop Loss #2")
    assert desk.get_symbol_risk_multiplier("BTCUSDm") == 1.0

    # Trade 3 Lost (-$10) -> Tier 1 Pod Drawdown (24h lockout & 5 recovery trades at 50% lot)
    desk.record_trade_result("BTCUSDm", -10.0, "Stop Loss #3")
    assert desk.get_symbol_risk_multiplier("BTCUSDm") == 0.50
    assert desk._symbol_recovery_trades["BTCUSDm"] == 5

    # Consume recovery trades
    for i in range(5):
        assert desk.get_symbol_risk_multiplier("BTCUSDm") == 0.50
        desk.consume_recovery_trade("BTCUSDm")

    # Should be back to normal 1.0 multiplier
    assert desk.get_symbol_risk_multiplier("BTCUSDm") == 1.0
    print("✅ Test 4: Consecutive Loss Ladder & Pod Recovery PASSED")


def test_5_margin_depletion_barrier():
    test_halt_file = _ROOT / "HALT_TEST_MARGIN"
    if test_halt_file.exists():
        test_halt_file.unlink()
    desk = CentralRiskDesk(min_margin_level_percent=300.0, halt_file=str(test_halt_file), auto_write_halt_file=True)
    acc = {"equity": 10000.0, "margin_level": 250.0, "margin": 200.0}
    desk.update_account_state(acc)

    # Case A: Margin level 250% (< 300% safe minimum) -> Pre-trade rejection, no emergency halt
    safe, msg = desk.check_pre_trade_safety("XAUUSDm", 20.0, 35.0, [], acc)
    assert not safe, f"Expected rejection when margin level < 300%, got safe={safe}, msg={msg}"
    assert "safe minimum" in msg
    assert not desk._is_halted

    # Case B: Margin level 120% (< 150% emergency barrier) -> Emergency Halt triggered & file generated
    acc_crit = {"equity": 9900.0, "margin_level": 120.0, "margin": 4000.0}
    safe, msg = desk.check_pre_trade_safety("XAUUSDm", 20.0, 35.0, [], acc_crit)
    assert not safe
    assert desk._is_halted
    assert "Emergency Margin Depletion" in msg
    assert test_halt_file.exists()

    desk.manual_unlock()
    assert not test_halt_file.exists()
    print("✅ Test 5: Margin Depletion Barrier (<300% & <150%) PASSED")


def test_6_daily_drawdown_auto_halt_generation():
    test_halt_file = _ROOT / "HALT_TEST_DD"
    if test_halt_file.exists():
        test_halt_file.unlink()
    desk = CentralRiskDesk(max_daily_drawdown_usd=200.0, max_daily_drawdown_pct=0.05, halt_file=str(test_halt_file), auto_write_halt_file=True)
    desk.update_account_state({"equity": 10000.0, "margin_level": 500.0, "margin": 100.0})

    # Breach DD: Equity drops to 9750 (-$250 > $200 limit)
    acc_breach = {"equity": 9750.0, "margin_level": 500.0, "margin": 100.0}
    safe, msg = desk.check_pre_trade_safety("XAUUSDm", 20.0, 35.0, [], acc_breach)
    assert not safe
    assert desk._is_halted
    assert "Daily Drawdown Hard Limit breached" in msg

    # Verify physical file existence and content
    assert test_halt_file.exists(), "Physical HALT file must be created on hard DD breach"
    content = test_halt_file.read_text(encoding="utf-8")
    assert "EMERGENCY_HALT_TRIGGERED_AT" in content
    assert "$9,750.00" in content

    # Cleanup
    desk.manual_unlock()
    assert not test_halt_file.exists()
    assert not desk._is_halted
    print("✅ Test 6: Daily Drawdown Auto HALT_HFT File Generation PASSED")


def test_7_asset_cluster_correlation_barrier():
    desk = CentralRiskDesk(max_positions_per_cluster=2)
    acc = {"equity": 10000.0, "margin_level": 500.0, "margin": 100.0}
    desk.update_account_state(acc)

    # Simulate 2 existing open positions in METALS cluster (XAUUSDm & XAGUSDm)
    open_pos = [
        {"symbol": "XAUUSDm", "volume": 0.05},
        {"symbol": "XAGUSDm", "volume": 0.10}
    ]

    # Attempt to open a 3rd position in METALS cluster -> Should REJECT
    safe, msg = desk.check_pre_trade_safety("XAUUSDm", 20.0, 35.0, open_pos, acc)
    assert not safe, "Expected rejection when cluster position limit is reached"
    assert "Asset Cluster Correlation Barrier" in msg
    assert "METALS" in msg

    # Attempt to open position in CRYPTO cluster (BTCUSDm) -> Should APPROVE (different cluster)
    safe, msg = desk.check_pre_trade_safety("BTCUSDm", 500.0, 1500.0, open_pos, acc)
    assert safe, f"Expected APPROVED for different cluster, got {msg}"
    print("✅ Test 7: Asset Cluster Correlation Barrier PASSED")


def test_8_all_time_trailing_hwm_drawdown():
    test_halt_file = _ROOT / "HALT_TEST_TRAILING"
    if test_halt_file.exists():
        test_halt_file.unlink()
    desk = CentralRiskDesk(
        max_daily_drawdown_usd=1000.0,
        max_daily_drawdown_pct=0.20,
        max_trailing_drawdown_pct=0.08,
        halt_file=str(test_halt_file),
        auto_write_halt_file=True
    )

    # Day 1: Account reaches peak $10,000
    desk.update_account_state({"equity": 10000.0, "margin_level": 500.0, "margin": 100.0})
    assert desk._all_time_peak_equity == 10000.0

    # Day 2: Resets daily peak to 9,500, but all-time HWM remains 10,000
    desk._current_date = "2026-01-01"  # simulate day roll
    desk.update_account_state({"equity": 9500.0, "margin_level": 500.0, "margin": 100.0})
    assert desk._daily_peak_equity == 9500.0
    assert desk._all_time_peak_equity == 10000.0

    # Day 3: Equity drops to 9,150 -> Trailing DD is (10000 - 9150) / 10000 = 8.5% (> 8.0% limit)
    # Even though daily DD from 9500 is only $350 (3.68% < 5%), all-time trailing DD triggers!
    acc_hwm_breach = {"equity": 9150.0, "margin_level": 500.0, "margin": 100.0}
    safe, msg = desk.check_pre_trade_safety("XAUUSDm", 20.0, 35.0, [], acc_hwm_breach)
    assert not safe
    assert desk._is_halted
    assert "All-Time Trailing Drawdown Hard Limit breached" in msg
    assert test_halt_file.exists()

    desk.manual_unlock()
    assert not test_halt_file.exists()
    print("✅ Test 8: All-Time Trailing HWM Drawdown Barrier PASSED")


def test_9_asymmetric_hysteresis_recovery_ladder():
    desk = CentralRiskDesk(warning_drawdown_pct=0.025, max_daily_drawdown_pct=0.05)
    desk.update_account_state({"equity": 10000.0})

    # DD = 0% -> Tier 1.00
    assert desk.get_risk_multiplier(10000.0) == 1.0

    # DD = 2.6% (Breached 2.5% warning) -> Immediate derisking to 0.75
    assert desk.get_risk_multiplier(9740.0) == 0.75

    # DD recovers slightly to 2.2% (Between 1.5% and 2.5%)
    # In naive system, it would jump back to 1.00.
    # In hysteresis system, it MUST STAY at 0.75 until DD < 1.5%!
    assert desk.get_risk_multiplier(9780.0) == 0.75, "Hysteresis must hold 0.75 until DD < 1.5%"

    # DD drops further to 4.2% -> Immediate derisking to 0.50 (Survival mode)
    assert desk.get_risk_multiplier(9580.0) == 0.50

    # DD recovers slightly to 3.5% (Between 3.0% and 4.0%)
    # Must STAY at 0.50 until DD < 3.0%!
    assert desk.get_risk_multiplier(9650.0) == 0.50, "Hysteresis must hold 0.50 until DD < 3.0%"

    # DD recovers to 2.8% (< 3.0%) -> Promoted to 0.75
    assert desk.get_risk_multiplier(9720.0) == 0.75

    # DD recovers to 1.2% (< 1.5%) -> Fully promoted back to 1.00
    assert desk.get_risk_multiplier(9880.0) == 1.00
    print("✅ Test 9: Asymmetric Risk Recovery Hysteresis Ladder PASSED")


def run_all_comprehensive_tests():
    print("=====================================================================")
    print(" RUNNING CENTRAL RISK DESK COMPREHENSIVE INSTITUTIONAL SUITE")
    print("=====================================================================")
    test_1_spread_spike_barrier()
    test_2_rollover_curfew_barrier()
    test_3_post_sl_cooldown()
    test_4_consecutive_loss_ladder_and_pod_recovery()
    test_5_margin_depletion_barrier()
    test_6_daily_drawdown_auto_halt_generation()
    test_7_asset_cluster_correlation_barrier()
    test_8_all_time_trailing_hwm_drawdown()
    test_9_asymmetric_hysteresis_recovery_ladder()
    print("=====================================================================")
    print("🎉 ALL 9 INSTITUTIONAL RISK DIMENSION TESTS PASSED PERFECTLY!")
    print("=====================================================================")


if __name__ == "__main__":
    run_all_comprehensive_tests()
