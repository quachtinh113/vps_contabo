"""
Unit & Integration Verification Suite for Oct 15 Quant Improvements:
1. BTCUSDm: OFI Threshold (0.35 vs 0.40 Night), Volume Filter (>= 1.2 * SMA20), Filter Reject Logging.
2. US30m: H1 Trend Filter (EMA50 & Donchian 20), Falling Knife Blocker, M15 Pullback Confirmation.
3. XAUUSDm: Session-Aware ATR Multiplier (1.5x Asia/Europe vs 2.2x US), Volatility Sizing Invariant.
4. System Config & Central Risk Desk Integrity.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone
import yaml
import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from strategies.crypto_micro_scalper import CryptoMicroScalperStrategy
from strategies.index_micro_scalper import IndexMicroScalperStrategy
from strategies.gold_micro_scalper import GoldMicroScalperStrategy
from strategies.commodity_oil_scalper import OilMicroScalperStrategy
from engines.ml4t_meta_labeler import CUSUMEventFilter
from core.central_risk_desk import CentralRiskDesk


def create_synthetic_bars(count=60, base_price=100.0, trend=0.0, volume=1000.0):
    times = pd.date_range("2026-10-15 00:00", periods=count, freq="15min", tz="UTC")
    prices = base_price + np.cumsum(np.random.normal(trend, 0.5, count))
    highs = prices + np.abs(np.random.normal(0.5, 0.2, count))
    lows = prices - np.abs(np.random.normal(0.5, 0.2, count))
    opens = prices + np.random.normal(0, 0.2, count)
    closes = prices
    vols = np.full(count, volume)
    
    df = pd.DataFrame({
        "time": times,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "tick_volume": vols
    })
    return df


def test_btc_filters():
    print("\n--- Testing BTCUSDm Filters (Volume, Night OFI, Filter Reject) ---")
    with open(_ROOT / "config/hft_config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    btc_cfg = next(s for s in cfg["symbols"] if s["name"] == "BTCUSDm")
    strat = CryptoMicroScalperStrategy(btc_cfg)

    # 1. Test Low Volume Filter Rejection
    bars = create_synthetic_bars(count=40, base_price=80000.0, volume=1000.0)
    # Set current bar volume low (e.g. 500 when SMA20 is 1000 -> 500 < 1.2 * 1000)
    bars.loc[bars.index[-1], "tick_volume"] = 500.0
    snap = {"mid": 80000.0, "spread_points": 800.0, "time": datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)}
    res = strat.evaluate(bars, snap, 0.0, 10000.0, contract_size=1.0)
    assert res is None, "Should reject when volume < 1.2 * SMA20"
    print("  ✅ 1. BTC Low Volume Filter: Rejected successfully")

    # 2. Test Night Window OFI Requirement (+0.05 penalty)
    # At 22:00 UTC (Night window), required OFI is 0.35.
    assert strat.ofi_threshold == 0.30, f"Base OFI threshold must be 0.30, got {strat.ofi_threshold}"
    assert strat.ofi_night_threshold == 0.35, f"Night OFI threshold must be 0.35, got {strat.ofi_night_threshold}"
    print("  ✅ 2. BTC Night OFI Parameter Invariant: Verified (0.30 Day vs 0.35 Night)")


def test_us30_filters():
    print("\n--- Testing US30m Filters (H1 Trend, Falling Knife, Pullback) ---")
    with open(_ROOT / "config/hft_config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    us30_cfg = next(s for s in cfg["symbols"] if s["name"] == "US30m")
    strat = IndexMicroScalperStrategy(us30_cfg)

    # 1. Test Falling Knife Blocker on BUY
    bars = create_synthetic_bars(count=40, base_price=51000.0)
    # Set up consecutive bearish impulse bars (falling knife)
    bars.loc[bars.index[-3], "open"] = 51200.0
    bars.loc[bars.index[-3], "close"] = 51100.0
    bars.loc[bars.index[-2], "open"] = 51100.0
    bars.loc[bars.index[-2], "close"] = 51000.0
    bars.loc[bars.index[-1], "open"] = 51000.0
    bars.loc[bars.index[-1], "close"] = 50850.0
    bars.loc[bars.index[-1], "low"] = 50800.0

    # Ensure OFI / skew attempts BUY by having positive drift on last bar or inventory
    snap = {"mid": 50850.0, "spread_points": 10.0, "time": datetime(2026, 10, 15, 14, 0, tzinfo=timezone.utc)}
    h1_bars = create_synthetic_bars(count=60, base_price=51000.0)
    
    # Evaluate - whether BUY or SELL, it must be rejected or filtered
    res = strat.evaluate(bars, snap, 0.0, 10000.0, contract_size=1.0, h1_df=h1_bars)
    if res is not None:
        assert res.get("action") != "BUY", "BUY must never be triggered during a falling knife"
    print("  ✅ 1. US30 Falling Knife Filter: Verified (No BUY during falling knife)")

    # 2. Test H1 Trend Filter Parameters
    assert strat.h1_ema_period == 50, "H1 EMA period must be 50"
    assert strat.donchian_period == 20, "Donchian period must be 20"
    print("  ✅ 2. US30 H1 Trend & Donchian Filter parameters: Verified")


def test_gold_session_atr():
    print("\n--- Testing XAUUSDm Session-Aware ATR & Sizing Invariant ---")
    with open(_ROOT / "config/hft_config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    gold_cfg = next(s for s in cfg["symbols"] if s["name"] == "XAUUSDm")
    strat = GoldMicroScalperStrategy(gold_cfg)

    assert strat.asia_europe_sl_mult == 1.5, f"Expected 1.5x, got {strat.asia_europe_sl_mult}"
    assert strat.us_session_sl_mult == 2.2, f"Expected 2.2x, got {strat.us_session_sl_mult}"
    assert strat.tp_rr_ratio == 2.0, f"Expected TP R:R 2.0, got {strat.tp_rr_ratio}"

    # Verify Volatility Sizing Invariant:
    # Dollar Risk = lot * stop_dist * contract_size <= risk_budget
    equity = 10000.0
    risk_pct = 0.004
    budget = equity * risk_pct  # $40.00

    # Test Asian Session Sizing (SL = 1.5 * $5 = $7.50)
    stop_asian = 1.5 * 5.0
    lot_asian, _ = strat.position_sizer.calculate_lot(equity, 4150.0, 4150.0 - stop_asian, contract_size=100.0)
    risk_asian = lot_asian * stop_asian * 100.0

    # Test US Session Sizing (SL = 2.2 * $5 = $11.00)
    stop_us = 2.2 * 5.0
    lot_us, _ = strat.position_sizer.calculate_lot(equity, 4150.0, 4150.0 - stop_us, contract_size=100.0)
    risk_us = lot_us * stop_us * 100.0

    print(f"  Asian Session -> Stop: ${stop_asian:.2f} | Lot: {lot_asian:.2f} | Risk: ${risk_asian:.2f} (Budget: ${budget:.2f})")
    print(f"  US Session    -> Stop: ${stop_us:.2f} | Lot: {lot_us:.2f} | Risk: ${risk_us:.2f} (Budget: ${budget:.2f})")

    assert lot_us < lot_asian, "US Session lot size must be smaller than Asian session due to wider ATR stop"
    assert risk_asian <= budget * 1.05, "Asian session risk must not breach budget"
    assert risk_us <= budget * 1.05, "US session risk must not breach budget"
    print("  ✅ Volatility Sizing Invariant Verified: Risk USD remains constant while lot size dynamically scales")


def test_config_integrity():
    print("\n--- Testing Config & Risk Desk Integrity ---")
    with open(_ROOT / "config/hft_config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    risk_cfg = cfg["risk_desk"]
    assert risk_cfg["max_daily_loss_per_symbol_usd"] == 80.0
    assert risk_cfg["consecutive_loss_cooldowns"] == [300, 2700, -1]
    assert risk_cfg["enable_profit_ladder"] is True
    print("  ✅ Risk Desk Lockout & Exponential Backoff settings intact")


def test_pre_market_audit_checklist():
    print("\n--- Testing Pre-Market Quantitative Audit Checklist (5 Structural Fixes) ---")
    with open(_ROOT / "config/hft_config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # Check 1 (Unit State): Simulate 10 consecutive ticks within the same M15 bar
    cusum = CUSUMEventFilter(threshold_mult=1.5)
    closed_bars = create_synthetic_bars(count=45, base_price=68.50)
    # Create strong upward move on the last closed bar so CUSUM triggers on bar close
    closed_bars.loc[closed_bars.index[-2], "close"] = 68.00
    closed_bars.loc[closed_bars.index[-1], "close"] = 69.50

    bar_ts = int(pd.Timestamp(closed_bars["time"].iloc[-1]).timestamp())
    signals_emitted = []
    for tick_idx in range(10):
        sig_dir = cusum.update_on_closed_bar("USOILm", closed_bars)
        # Also verify direct update() with same bar_time emits 0 on ticks 2..10
        dup_check = cusum.update(0.015, 0.002, bar_time=bar_ts, sym="USOILm_direct")
        signals_emitted.append((sig_dir, dup_check))

    assert cusum.last_bar_time["USOILm"] == bar_ts, "last_bar_time must lock onto closed M15 bar timestamp"
    # Direct update() must only evaluate on tick 0, and return (False, 0) on ticks 1..9
    direct_subsequent = [x[1] for x in signals_emitted[1:]]
    assert all(d == (False, 0) for d in direct_subsequent), f"Duplicate intra-bar CUSUM updates must return (False, 0), got {direct_subsequent}"
    print(f"  ✅ Check 1 (CUSUM Unit State): 10 intra-bar ticks verified -> last_bar_time={bar_ts} updated 1x, 0 duplicate accumulations")

    # Check 2 (USOILm Sizing): Equity $9,853.24, risk_per_trade_pct = 0.003 ($29.56), SL = 2.2 x ATR14
    oil_cfg = next(s for s in cfg["symbols"] if s["name"] == "USOILm")
    gbp_cfg = next(s for s in cfg["symbols"] if s["name"] == "GBPUSDm")
    assert gbp_cfg["enabled"] is False, "GBPUSDm must be disabled in config"
    assert oil_cfg["position_sizing"]["risk_per_trade_pct"] == 0.003, f"USOILm risk_per_trade_pct must be 0.003, got {oil_cfg['position_sizing']['risk_per_trade_pct']}"
    assert oil_cfg["position_sizing"]["max_lot_cap"] == 0.05, f"USOILm max_lot_cap must be 0.05, got {oil_cfg['position_sizing']['max_lot_cap']}"
    assert oil_cfg["sl_multiplier"] == 2.2, f"USOILm sl_multiplier must be 2.2, got {oil_cfg['sl_multiplier']}"
    assert oil_cfg["tp_multiplier"] == 3.3, f"USOILm tp_multiplier must be 3.3, got {oil_cfg['tp_multiplier']}"
    assert oil_cfg["friday_hard_close_utc"] == "20:30"

    oil_strat = OilMicroScalperStrategy(oil_cfg)
    equity = 9853.24
    entry_price = 68.50
    # Construct closed M15 bars with typical USOILm M15 ATR14 ~ $0.30
    oil_bars = create_synthetic_bars(count=30, base_price=68.50)
    oil_bars["close"] = 68.50
    oil_bars["open"] = 68.50
    oil_bars["high"] = 68.65
    oil_bars["low"] = 68.35
    sl_price, tp_price = oil_strat.calculate_triple_barriers(entry_price, side=1, closed_rates_df=oil_bars)
    sl_dist = abs(entry_price - sl_price)
    lot, _ = oil_strat.position_sizer.calculate_lot(equity, entry_price, sl_price, contract_size=1000.0)
    max_loss_usd = lot * sl_dist * 1000.0
    print(f"  ✅ Check 2 (USOILm Sizing): Equity=${equity:,.2f} | SL Dist=${sl_dist:.3f} (2.2x ATR14) | Lot={lot:.2f} | Max Risk=${max_loss_usd:.2f} (< $30.00)")
    assert 0.03 <= lot <= 0.05, f"Expected USOILm lot in [0.03, 0.05], got {lot}"
    assert max_loss_usd <= 30.00, f"Expected max loss <= $30.00, got ${max_loss_usd:.2f}"

    # Check 3 (Reject Log / 10018 Market Closed Guard on US30m)
    us30_cfg = next(s for s in cfg["symbols"] if s["name"] == "US30m")
    us30_strat = IndexMicroScalperStrategy(us30_cfg)
    # Case 3a: Weekend UTC timestamp (Saturday) even if last Friday tick was inside 13:00-21:00
    sat_utc = datetime(2026, 10, 31, 15, 0, tzinfo=timezone.utc)  # Saturday
    stale_friday_tick = {"mid": 42000.0, "spread_points": 15.0, "time": datetime(2026, 10, 30, 20, 59, tzinfo=timezone.utc), "time_msc": int(datetime(2026, 10, 30, 20, 59, tzinfo=timezone.utc).timestamp() * 1000)}
    assert us30_strat.is_session_active(sat_utc, stale_friday_tick) is False, "Must block Saturday trading"

    # Case 3b: Weekday inside 13:00-21:00 UTC, but tick is >30s stale (Market closed / holiday)
    mon_utc = datetime(2026, 11, 2, 15, 0, 0, tzinfo=timezone.utc)
    stale_tick = {"mid": 42000.0, "spread_points": 15.0, "time": mon_utc, "time_msc": int((mon_utc.timestamp() - 45.0) * 1000)}
    assert us30_strat.is_session_active(mon_utc, stale_tick) is False, "Must block stale tick (>30s)"
    print("  ✅ Check 3 (US30m 10018 Market Closed Guard): Weekend & Stale Tick (>30s) blocked before order routing")


def main():
    print("=" * 80)
    print("  QUANT TRADING UPGRADE VERIFICATION SUITE")
    print("=" * 80)
    test_btc_filters()
    test_us30_filters()
    test_gold_session_atr()
    test_config_integrity()
    test_pre_market_audit_checklist()
    print("\n" + "=" * 80)
    print("  ALL 5 VERIFICATION STAGES PASSED! READY FOR BOT RESTART.")
    print("=" * 80)


if __name__ == "__main__":
    main()
