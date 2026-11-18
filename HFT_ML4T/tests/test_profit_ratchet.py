import sys
from pathlib import Path
from datetime import datetime, timezone

_ROOT = Path(r"C:\VPS CONTABO\HFT_ML4T")
sys.path.insert(0, str(_ROOT))

from core.central_risk_desk import CentralRiskDesk

def test_ratchet():
    desk = CentralRiskDesk(
        hard_daily_target_usd=200.0,
        max_daily_drawdown_usd=100.0,
        post_sl_cooldown_seconds=0.0,
        consecutive_loss_cooldowns=[],
        macro_news_window_utc=("23:58", "23:59"),
        rollover_curfew_utc=("23:58", "23:59")
    )
    acc = {"equity": 10000.0, "margin_level": 500.0}
    t_london = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)
    t_us = datetime(2026, 11, 17, 14, 0, tzinfo=timezone.utc)

    # Initial state
    assert desk.get_dynamic_daily_floor(t_london) == -100.0
    print("✅ Initial floor: -$100.00 PASSED")

    # Step 1: London banks +$110.00
    desk.record_trade_result("XAUUSDm", 110.0, comment="London Scalp Win")
    assert desk._peak_daily_realized_pnl == 110.0
    floor_rule1 = desk.get_dynamic_daily_floor(t_us)
    assert floor_rule1 == 55.0, f"Expected 55.0, got {floor_rule1}"
    print(f"✅ Rule 1 Floor (+${floor_rule1:.2f} locked on peak +$110.00) PASSED")

    # Step 2: US session open - trade with +$70 remaining (safe above $55)
    desk.record_trade_result("XAUUSDm", -40.0, comment="US Loss #1")
    desk._symbol_cooldowns.clear()
    # Realized PnL is now +$70.00
    approved, msg = desk.check_pre_trade_safety("XAUUSDm", 15.0, 35.0, [], acc, now_utc=t_us)
    assert approved, f"Expected approved at +$70, got: {msg}"
    print("✅ US session trade allowed above floor (+$70.00 > +$55.00) PASSED")

    # Step 3: US session takes another loss of -$25 -> PnL becomes +$45.00 (<= $55.00 floor)
    desk.record_trade_result("XAUUSDm", -25.0, comment="US Loss #2")
    desk._symbol_cooldowns.clear()
    # Realized PnL is now +$45.00
    approved, msg = desk.check_pre_trade_safety("XAUUSDm", 15.0, 35.0, [], acc, now_utc=t_us)
    assert not approved and "Inter-Session Profit Ratchet active" in msg, f"Expected Ratchet halt, got: {msg}"
    print(f"✅ Inter-Session Profit Ratchet blocked trade at +$45.00 <= +$55.00 floor ({msg}) PASSED")

    # Step 4: Rule 2 (Fat-Tail Runner Ratchet)
    desk2 = CentralRiskDesk(
        hard_daily_target_usd=200.0,
        max_daily_drawdown_usd=100.0,
        post_sl_cooldown_seconds=0.0,
        consecutive_loss_cooldowns=[],
        macro_news_window_utc=("23:58", "23:59"),
        rollover_curfew_utc=("23:58", "23:59")
    )
    desk2.record_trade_result("XAUUSDm", 240.0, comment="Fat-Tail Win")
    floor_rule2 = desk2.get_dynamic_daily_floor(t_us)
    assert floor_rule2 == 150.0, f"Expected 150.0 (75% of $200), got {floor_rule2}"
    print(f"✅ Rule 2 Floor (+${floor_rule2:.2f} locked on peak +$240.00) PASSED")

    desk2.record_trade_result("XAUUSDm", -100.0, comment="Pullback") # PnL is now +$140.00
    desk2._symbol_cooldowns.clear()
    approved, msg = desk2.check_pre_trade_safety("XAUUSDm", 15.0, 35.0, [], acc, signal_regime="FAT_TAIL", now_utc=t_us)
    assert not approved and "Inter-Session Profit Ratchet active" in msg, f"Expected Ratchet halt, got: {msg}"
    print(f"✅ Rule 2 Ratchet blocked pullback below $150.00 floor ({msg}) PASSED")

    print("\n🎉 ALL INTER-SESSION PROFIT RATCHET TESTS PASSED!")

if __name__ == "__main__":
    test_ratchet()
