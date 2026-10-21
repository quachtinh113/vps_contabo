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


if __name__ == "__main__":
    print("\n--- Running HFT_ML4T Verification Tests ---")
    test_avellaneda_stoikov()
    test_position_sizer()
    test_quantization_guard()
    test_central_risk_desk()
    test_garman_klass_vol()
    test_order_flow_imbalance()
    test_strategy_instantiations()
    print("🎉 ALL 7 INTEGRATION TESTS PASSED SUCCESSFULLY!\n")

