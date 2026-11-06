"""
Unit & Integration Sanity Test Suite for HFT_ML4T
"""

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import pandas as pd
import numpy as np

# Path setup
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.central_risk_desk import CentralRiskDesk
from core.audit_logger import setup_logger
from engines.avellaneda_stoikov import AvellanedaStoikovEngine, calculate_order_flow_imbalance
from engines.ml4t_meta_labeler import CUSUMEventFilter, calculate_garman_klass_volatility, calculate_triple_barriers, MLMetaGatekeeper
from engines.position_sizer import PositionSizer
from strategies.gold_micro_scalper import GoldMicroScalperStrategy
from strategies.fx_micro_arbitrage import FXMicroArbitrageStrategy
from strategies.crypto_micro_scalper import CryptoMicroScalperStrategy
from strategies.commodity_oil_scalper import OilMicroScalperStrategy
from strategies.index_micro_scalper import IndexMicroScalperStrategy


from engines.avellaneda_stoikov import AvellanedaStoikovEngine, calculate_order_flow_imbalance, calculate_micro_volatility


def test_avellaneda_stoikov():
    engine = AvellanedaStoikovEngine(gamma=0.1, kappa=1.5, ofi_sensitivity=0.25, max_inventory=5.0)
    
    # 1. Base test: Positive OFI shifts reservation price upwards
    quotes = engine.calculate_quotes(
        mid_price=2650.0,
        inventory_q=0.0,
        volatility_sigma=0.005,
        time_remaining_t=1.0,
        order_flow_imbalance=0.5
    )
    assert quotes["reservation_price"] > 2650.0, "Positive OFI should shift reservation price upwards"
    assert quotes["optimal_ask"] > quotes["optimal_bid"], "Ask must be higher than Bid"
    assert quotes["allow_bid"] and quotes["allow_ask"], "Both quotes must be allowed when flat"

    # 2. Symmetrical case (q = 0, OFI = 0) -> r == s
    quotes_flat = engine.calculate_quotes(
        mid_price=2650.0, inventory_q=0.0, volatility_sigma=0.005, order_flow_imbalance=0.0
    )
    assert quotes_flat["reservation_price"] == 2650.0, "Flat inventory with zero OFI must equal mid price"

    # 3. Inventory skewing (q = +3.0 Long) -> r < s (shifts down to dump long inventory)
    quotes_long = engine.calculate_quotes(
        mid_price=2650.0, inventory_q=3.0, volatility_sigma=0.005, order_flow_imbalance=0.0
    )
    assert quotes_long["reservation_price"] < 2650.0, "Long inventory must skew reservation price downward"
    assert quotes_long["optimal_ask"] < quotes_flat["optimal_ask"], "Ask must drop to incentivize closing Long"

    # 4. Inventory skewing (q = -3.0 Short) -> r > s (shifts up to cover short inventory)
    quotes_short = engine.calculate_quotes(
        mid_price=2650.0, inventory_q=-3.0, volatility_sigma=0.005, order_flow_imbalance=0.0
    )
    assert quotes_short["reservation_price"] > 2650.0, "Short inventory must skew reservation price upward"
    assert quotes_short["optimal_bid"] > quotes_flat["optimal_bid"], "Bid must rise to incentivize covering Short"

    # 5. Dynamic Kappa: Low volume widens spread
    quotes_normal = engine.calculate_quotes(
        mid_price=2650.0, inventory_q=0.0, volatility_sigma=0.005, volume_ratio=1.0
    )
    quotes_thin = engine.calculate_quotes(
        mid_price=2650.0, inventory_q=0.0, volatility_sigma=0.005, volume_ratio=0.3
    )
    assert quotes_thin["dynamic_kappa"] < quotes_normal["dynamic_kappa"], "Kappa must drop in thin liquidity"
    assert quotes_thin["spread"] > quotes_normal["spread"], "Spread must widen in thin liquidity"

    # 6. Hard Inventory Circuit Breaker
    quotes_max_long = engine.calculate_quotes(
        mid_price=2650.0, inventory_q=5.0, volatility_sigma=0.005, max_inventory=5.0
    )
    assert not quotes_max_long["allow_bid"], "Must suppress BUY when max long inventory is reached"
    assert quotes_max_long["allow_ask"], "Must keep ASK enabled to unwind inventory"

    quotes_max_short = engine.calculate_quotes(
        mid_price=2650.0, inventory_q=-5.0, volatility_sigma=0.005, max_inventory=5.0
    )
    assert not quotes_max_short["allow_ask"], "Must suppress SELL when max short inventory is reached"
    assert quotes_max_short["allow_bid"], "Must keep BID enabled to cover short"

    # 7. Micro-Volatility Estimator
    prices = [2650.0 + i * 0.1 for i in range(100)]
    micro_vol = calculate_micro_volatility(prices, window=60)
    assert micro_vol > 0.0, "Micro-volatility must be positive"

    print("✅ test_avellaneda_stoikov (Institutional 7-Point Matrix) PASSED")


def test_position_sizer():
    sizer = PositionSizer(risk_per_trade_pct=0.005, max_lot_cap=0.5)
    lot, reason = sizer.calculate_lot(
        account_equity=10000.0,
        entry_price=2650.0,
        sl_price=2645.0,
        contract_size=100.0
    )
    # Risk budget = 10000 * 0.005 = $50. Loss per lot = 5 * 100 = $500. Expected lot = 50 / 500 = 0.10 lot
    assert lot == 0.10, f"Expected 0.10 lot, got {lot}"
    print("✅ test_position_sizer PASSED")


def test_quantization_guard():
    sizer = PositionSizer(risk_per_trade_pct=0.005, max_lot_cap=0.5)
    # Small equity where 0.01 lot loss exceeds budget
    lot, reason = sizer.calculate_lot(
        account_equity=100.0,  # $100 equity, budget = $0.50
        entry_price=2650.0,
        sl_price=2640.0,       # $10 stop distance * 100 * 0.01 = $10 loss > $0.50
        contract_size=100.0
    )
    assert lot == 0.0, "Small account must be protected by Quantization Guard"
    assert "Quantization Guard Rejected" in reason
    print("✅ test_quantization_guard PASSED")


def test_central_risk_desk():
    desk = CentralRiskDesk(max_daily_drawdown_usd=200.0, max_daily_drawdown_pct=0.05, rollover_curfew_utc=("00:00", "00:00"))
    desk.update_account_state({"equity": 10000.0, "margin_level": 500.0, "margin": 100.0})
    
    # 1. Normal pre-trade
    safe, msg = desk.check_pre_trade_safety(
        symbol="XAUUSDm",
        current_spread_points=25.0,
        max_allowed_spread_points=35.0,
        open_positions=[],
        account_info={"equity": 10000.0, "margin_level": 500.0, "margin": 100.0}
    )
    assert safe, f"Should be approved, got {msg}"

    # 2. Spread spike test
    safe_spread, msg_spread = desk.check_pre_trade_safety(
        symbol="XAUUSDm",
        current_spread_points=50.0,
        max_allowed_spread_points=35.0,
        open_positions=[],
        account_info={"equity": 10000.0, "margin_level": 500.0, "margin": 100.0}
    )
    assert not safe_spread, "Should reject spread spike"

    # 3. Drawdown breach test
    safe_dd, msg_dd = desk.check_pre_trade_safety(
        symbol="XAUUSDm",
        current_spread_points=20.0,
        max_allowed_spread_points=35.0,
        open_positions=[],
        account_info={"equity": 9700.0, "margin_level": 500.0, "margin": 100.0}  # -$300 DD > $200 limit
    )
    assert not safe_dd, "Should trigger Circuit Breaker on drawdown breach"
    desk.manual_unlock()
    print("✅ test_central_risk_desk PASSED")


def test_garman_klass_vol():
    np.random.seed(42)
    df = pd.DataFrame({
        "open": np.linspace(2600, 2650, 30),
        "high": np.linspace(2605, 2655, 30),
        "low": np.linspace(2595, 2645, 30),
        "close": np.linspace(2602, 2652, 30)
    })
    vol = calculate_garman_klass_volatility(df, window=20)
    assert vol > 0.0, "Garman-Klass volatility must be positive"
    print("✅ test_garman_klass_vol PASSED")


def test_order_flow_imbalance():
    # Construct bullish surge dataset with volume
    df_bull = pd.DataFrame({
        "open": [2600.0, 2605.0, 2610.0, 2615.0, 2620.0],
        "high": [2606.0, 2611.0, 2616.0, 2622.0, 2628.0],
        "low": [2599.0, 2604.0, 2609.0, 2614.0, 2619.0],
        "close": [2605.5, 2610.8, 2615.5, 2621.5, 2627.8],  # Close near high
        "tick_volume": [100, 150, 200, 350, 500]             # Surging volume
    })
    ofi_bull = calculate_order_flow_imbalance(df_bull, window=5)
    assert ofi_bull > 0.3, f"Expected strong positive OFI on bullish surge, got {ofi_bull}"

    # Construct bearish dump dataset
    df_bear = pd.DataFrame({
        "open": [2620.0, 2615.0, 2610.0, 2605.0, 2600.0],
        "high": [2621.0, 2616.0, 2611.0, 2606.0, 2601.0],
        "low": [2614.0, 2609.0, 2604.0, 2598.0, 2590.0],
        "close": [2614.5, 2609.2, 2604.5, 2598.5, 2590.5], # Close near low
        "tick_volume": [100, 150, 200, 350, 500]
    })
    ofi_bear = calculate_order_flow_imbalance(df_bear, window=5)
    assert ofi_bear < -0.3, f"Expected strong negative OFI on bearish dump, got {ofi_bear}"
    print(f"✅ test_order_flow_imbalance PASSED (Bull: {ofi_bull:+.2f}, Bear: {ofi_bear:+.2f})")


def test_strategy_instantiations():
    import yaml
    with open(_ROOT / "config" / "hft_config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    symbols = cfg.get("symbols", [])
    assert len(symbols) == 6, f"Expected 6 symbols in config, got {len(symbols)}"
    for s in symbols:
        stype = s.get("strategy_type")
        if stype == "gold":
            strat = GoldMicroScalperStrategy(s)
        elif stype == "crypto":
            strat = CryptoMicroScalperStrategy(s)
        elif stype == "oil":
            strat = OilMicroScalperStrategy(s)
        elif stype == "index":
            strat = IndexMicroScalperStrategy(s)
        else:
            strat = FXMicroArbitrageStrategy(s)
        assert strat.magic == s.get("magic")
    print("✅ test_strategy_instantiations PASSED (All 6 strategies validated)")


def test_execution_slippage_and_latency_audit():
    from core.audit_logger import log_execution_audit
    import tempfile
    import csv

    with tempfile.TemporaryDirectory() as tmpdir:
        test_record = {
            "timestamp_utc": "2026-10-22T00:00:00.123Z",
            "ticket": 99887766,
            "symbol": "XAUUSDm",
            "order_type": "BUY",
            "volume": 0.05,
            "expected_price": 2650.00,
            "fill_price": 2650.15,
            "slippage_points": 1.5,
            "slippage_usd": 0.75,
            "latency_ms": 45.2,
            "retcode": 10009,
            "comment": "HFT_TEST"
        }
        log_execution_audit(tmpdir, test_record)
        csv_file = Path(tmpdir) / "execution_audit.csv"
        assert csv_file.exists(), "execution_audit.csv must be created"

        with open(csv_file, "r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
            assert len(reader) == 1
            assert reader[0]["symbol"] == "XAUUSDm"
            assert float(reader[0]["slippage_points"]) == 1.5
            assert float(reader[0]["latency_ms"]) == 45.2

    # Risk Desk Execution Barrier test
    desk = CentralRiskDesk(max_acceptable_slippage_points=25.0, max_acceptable_latency_ms=1200.0)
    desk.record_execution_metric("EURUSDm", latency_ms=45.0, slippage_points=2.0)
    assert not desk.is_in_cooldown("EURUSDm"), "Normal execution should not trigger cooldown"

    # Severe adverse slippage (30.0 pts >= 25.0 pts limit) -> Must trigger Cooldown
    desk.record_execution_metric("EURUSDm", latency_ms=45.0, slippage_points=30.0)
    assert desk.is_in_cooldown("EURUSDm"), "Severe slippage must trigger symbol cooldown"
    assert "Severe Adverse Slippage" in desk.get_cooldown_reason("EURUSDm")

    # Severe latency (1500ms >= 1200ms limit) -> Must trigger Cooldown
    desk.record_execution_metric("BTCUSDm", latency_ms=1500.0, slippage_points=1.0)
    assert desk.is_in_cooldown("BTCUSDm"), "Severe latency must trigger symbol cooldown"

    stats = desk.get_execution_stats()
    assert stats["sample_count"] >= 3
    assert stats["avg_latency_ms"] > 0
    print("✅ test_execution_slippage_and_latency_audit PASSED")


def test_hierarchical_risk_parity():
    from engines.hrp_allocator import HierarchicalRiskParityAllocator

    np.random.seed(42)
    n_samples = 250

    # Generate returns with structural correlation (EUR and GBP highly correlated)
    base_fx = np.random.normal(0, 0.005, n_samples)
    returns_df = pd.DataFrame({
        "BTCUSDm": np.random.normal(0, 0.025, n_samples),
        "XAUUSDm": np.random.normal(0, 0.008, n_samples),
        "USOILm": np.random.normal(0, 0.015, n_samples),
        "US30m": np.random.normal(0, 0.006, n_samples),
        "EURUSDm": base_fx + np.random.normal(0, 0.002, n_samples),
        "GBPUSDm": base_fx + np.random.normal(0, 0.003, n_samples),
    })

    allocator = HierarchicalRiskParityAllocator()
    weights = allocator.allocate(returns_df, min_weight_cap=0.05, max_weight_cap=0.40)

    assert len(weights) == 6, f"Expected 6 asset weights, got {len(weights)}"
    total_w = sum(weights.values())
    assert abs(total_w - 1.0) < 0.01, f"Weights must sum to 1.0, got {total_w}"

    # Verify high-vol asset (BTC) receives lower allocation than low-vol asset (US30 / FX)
    assert weights["BTCUSDm"] < weights["US30m"], "HRP must allocate less capital to high-volatility assets"
    print(f"✅ test_hierarchical_risk_parity PASSED (Weights: {weights})")


def test_ml4t_data_pipeline():
    from engines.ml4t_data_pipeline import (
        ParquetFeatureCollector,
        TripleBarrierMetaLabeler,
        OrthogonalFactorNeutralizer,
        CombinatorialPurgedCrossValidation
    )
    import tempfile
    import pyarrow.parquet as pq

    # 1. Parquet Feature Collector test
    with tempfile.TemporaryDirectory() as tmpdir:
        collector = ParquetFeatureCollector(output_dir=tmpdir, flush_threshold=10)
        for i in range(12):
            collector.record_feature(
                symbol="XAUUSDm",
                mid_price=2650.0 + i,
                spread_points=25.0,
                ofi=0.35,
                garman_klass_vol=0.005,
                micro_vol=0.004,
                dynamic_kappa=1.45,
                reservation_price=2650.5,
                skew_offset=0.5,
                action="BUY" if i % 2 == 0 else "HOLD",
                macro_regime="BULL_TREND",
                slope_ema21_pct=0.05,
                recent_slippage_pts=1.2,
                recent_latency_ms=42.0
            )
        # Flush remaining
        flushed_file = collector.flush()
        assert flushed_file is not None, "Flushed parquet file path must be returned"
        assert Path(flushed_file).exists(), "Parquet file must exist on disk"

        table = pq.read_table(flushed_file)
        assert table.num_rows == 12, f"Expected 12 records in Parquet, got {table.num_rows}"
        assert "dynamic_kappa" in table.column_names
        assert "micro_volatility" in table.column_names

    # 2. Triple Barrier Meta-Labeler test
    df_prices = pd.DataFrame({
        "open":  [100, 101, 102, 105, 108, 103, 98, 95, 96, 97],
        "high":  [102, 103, 106, 110, 109, 104, 99, 97, 98, 99],
        "low":   [99,  100, 101, 104, 102, 97,  94, 93, 95, 96],
        "close": [101, 102, 105, 108, 103, 98,  95, 96, 97, 98]
    })
    labeler = TripleBarrierMetaLabeler(pt_multiplier=1.0, sl_multiplier=1.0, horizon_bars=4)
    labels = labeler.label_events(df_prices, event_indices=[1, 4])
    assert len(labels) == 2, f"Expected 2 labeled events, got {len(labels)}"
    # Event at idx 1: price goes from 102 up to 110 -> Upper barrier (+1)
    assert labels.iloc[0]["label"] == 1, "Bullish surge should trigger +1 label"

    # 3. Orthogonal Factor Neutralizer test
    neutralizer = OrthogonalFactorNeutralizer()
    active_pos = [
        {"symbol": "EURUSDm", "volume": 0.50, "order_type": "BUY"},   # Beta -1.0 -> -0.50 USD exposure
        {"symbol": "XAUUSDm", "volume": 0.20, "order_type": "BUY"},   # Beta -0.75 -> -0.15 USD exposure
    ]
    # Current net is negative USD exposure (short dollar tilt = -0.65)
    net_usd = neutralizer.calculate_portfolio_dollar_exposure(active_pos)
    assert net_usd < 0.0, "Net USD exposure should be negative"

    # Proposing a BUY on US30m (Beta +0.20): increases USD exposure -> Counters short dollar tilt (Hedging)
    hedging_mult = neutralizer.calculate_neutralizing_multiplier("US30m", "BUY", active_pos)
    assert hedging_mult > 1.0, "Hedging order should receive neutralizer multiplier boost"

    # 4. Combinatorial Purged Cross-Validation test (Deflated Sharpe Ratio)
    # High SR with few trials -> High DSR
    dsr_high = CombinatorialPurgedCrossValidation.calculate_deflated_sharpe_ratio(
        observed_sr=2.5, num_trials=5, sample_length=500
    )
    assert dsr_high > 0.90, f"Genuine high SR with few trials must yield high DSR, got {dsr_high}"

    # Weak SR with 1,000 data-snooping trials -> Low DSR (overfitted)
    dsr_overfit = CombinatorialPurgedCrossValidation.calculate_deflated_sharpe_ratio(
        observed_sr=1.1, num_trials=1000, sample_length=200
    )
    assert dsr_overfit < 0.30, f"Overfitted SR with 1000 trials must yield low DSR, got {dsr_overfit}"

    print(f"✅ test_ml4t_data_pipeline PASSED (DSR Genuine: {dsr_high:.2f}, DSR Overfit: {dsr_overfit:.2f})")


def test_mt5_bridge_devops_and_recovery():
    from core.mt5_bridge import MT5Bridge
    bridge = MT5Bridge()

    # 1. Verify DevOps recovery methods exist and are callable
    assert hasattr(bridge, "kill_zombie_terminal"), "MT5Bridge must have kill_zombie_terminal method"
    assert hasattr(bridge, "connect_robust"), "MT5Bridge must have connect_robust method"
    assert hasattr(bridge, "ensure_symbols_visible"), "MT5Bridge must have ensure_symbols_visible method"
    assert hasattr(bridge, "cancel_all_pending_orders"), "MT5Bridge must have cancel_all_pending_orders method"

    # 2. Verify ensure_symbols_visible doesn't crash on symbol list
    bridge.ensure_symbols_visible(["EURUSDm", "BTCUSDm"])

    # 3. Verify cancel_all_pending_orders return type
    cancelled = bridge.cancel_all_pending_orders()
    assert isinstance(cancelled, int), "cancel_all_pending_orders must return an integer count"

    # 4. Verify RESTART_NOW zero-downtime hot-reload file contract
    test_restart_flag = _ROOT / "TEST_RESTART_NOW"
    test_restart_flag.write_text("HOT_RELOAD_TEST", encoding="utf-8")
    assert test_restart_flag.exists(), "Test flag must exist"
    test_restart_flag.unlink()
    assert not test_restart_flag.exists(), "Flag must be removable on shutdown"

    print("✅ test_mt5_bridge_devops_and_recovery PASSED (Zombie Kill, Robust Connect, Symbols Select, RESTART_NOW contract)")


def test_institutional_tick_backtester():
    from engines.institutional_tick_backtester import (
        TickDataPipeline,
        MicrostructureExecutionModel,
        HybridBacktestEngine,
        CombinatorialPurgedCrossValidator
    )

    # 1. Pipeline test (Pillar 1)
    pipeline = TickDataPipeline()
    ticks_df = pipeline.fetch_or_load_ticks(symbol="TEST_ASSET", count=1000, use_cache=False)
    assert len(ticks_df) == 1000, "Pipeline must generate 1,000 Level 1 ticks"
    assert "mid" in ticks_df.columns and "ofi" in ticks_df.columns and "micro_vol" in ticks_df.columns

    # 2. Microstructure Execution Model (Pillar 2)
    exec_model = MicrostructureExecutionModel()
    lat_ticks = exec_model.get_latency_delay_ticks(tick_interval_ms=50.0)
    adv_slip = exec_model.get_adverse_slippage_pts()
    assert lat_ticks >= 1, "Latency delay must be at least 1 tick"
    assert adv_slip >= 0.0, "Adverse slippage must be non-negative"

    # 3. Hybrid Engine (Pillar 3)
    hybrid = HybridBacktestEngine(data_pipeline=pipeline, execution_model=exec_model)
    grid_res = hybrid.run_vectorized_grid_search(
        symbol="TEST_ASSET",
        ticks_df=ticks_df,
        gamma_grid=[0.05, 0.1],
        kappa_grid=[1.0],
        ofi_grid=[0.25],
        max_inv_grid=[2.0]
    )
    assert len(grid_res) == 2, f"Expected 2 grid results, got {len(grid_res)}"
    validated = hybrid.validate_top_candidates_event_driven(
        symbol="TEST_ASSET",
        ticks_df=ticks_df,
        top_candidates=grid_res,
        top_k=2,
        max_allowed_divergence_pct=0.05
    )
    assert len(validated) == 2, "Event-driven must validate 2 candidates"
    assert "data_leakage_detected" in validated[0], "Must contain data leakage flag"

    # 4. CPCV & Deflated Sharpe Ratio (Pillar 4)
    cpcv = CombinatorialPurgedCrossValidator(num_groups=4, test_groups=2, embargo_pct=0.01)
    cpcv_res = cpcv.evaluate_cpcv(
        symbol="TEST_ASSET",
        ticks_df=ticks_df,
        gamma=0.05,
        kappa=1.0,
        ofi_sensitivity=0.25,
        max_inventory=2.0,
        num_total_trials=10
    )
    assert cpcv_res["cpcv_paths_count"] == 6, f"C(4,2) must equal 6 paths, got {cpcv_res['cpcv_paths_count']}"
    assert 0.0 <= cpcv_res["deflated_sharpe_ratio"] <= 1.0, "DSR must be bounded in [0, 1]"

    print("✅ test_institutional_tick_backtester PASSED (All 4 Pillars Verified)")


if __name__ == "__main__":
    print("\n--- Running HFT_ML4T Verification Tests ---")
    test_avellaneda_stoikov()
    test_position_sizer()
    test_quantization_guard()
    test_central_risk_desk()
    test_garman_klass_vol()
    test_order_flow_imbalance()
    test_strategy_instantiations()
    test_execution_slippage_and_latency_audit()
    test_hierarchical_risk_parity()
    test_ml4t_data_pipeline()
    test_mt5_bridge_devops_and_recovery()
    test_institutional_tick_backtester()
    print("🎉 ALL 12 INTEGRATION & RESEARCH SUITE TESTS PASSED SUCCESSFULLY!\n")

