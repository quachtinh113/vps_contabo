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
from engines.avellaneda_stoikov import AvellanedaStoikovEngine
from engines.ml4t_meta_labeler import CUSUMEventFilter, calculate_garman_klass_volatility, calculate_triple_barriers, MLMetaGatekeeper
from engines.position_sizer import PositionSizer
from strategies.gold_micro_scalper import GoldMicroScalperStrategy
from strategies.fx_micro_arbitrage import FXMicroArbitrageStrategy
from strategies.crypto_micro_scalper import CryptoMicroScalperStrategy
from strategies.commodity_oil_scalper import OilMicroScalperStrategy
from strategies.index_micro_scalper import IndexMicroScalperStrategy


def test_avellaneda_stoikov():
    engine = AvellanedaStoikovEngine(gamma=0.1, kappa=1.5, ofi_sensitivity=0.25)
    quotes = engine.calculate_quotes(
        mid_price=2650.0,
        inventory_q=0.0,
        volatility_sigma=0.005,
        time_remaining_t=1.0,
        order_flow_imbalance=0.5
    )
    assert quotes["reservation_price"] > 2650.0, "Positive OFI should shift reservation price upwards"
    assert quotes["optimal_ask"] > quotes["optimal_bid"], "Ask must be higher than Bid"
    print("✅ test_avellaneda_stoikov PASSED")


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
    desk = CentralRiskDesk(max_daily_drawdown_usd=200.0, max_daily_drawdown_pct=0.05)
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
    test_strategy_instantiations()
    print("🎉 ALL 6 INTEGRATION TESTS PASSED SUCCESSFULLY!\n")

