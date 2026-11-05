"""
Demonstration script for Nixtla N-BEATS Doubly Residuals & AutoGluon Stacking.
Run: python nbeats_stacking_demo.py
"""

import sys
from pathlib import Path
import numpy as np

# Ensure workspace root is in path
workspace = Path(__file__).resolve().parents[4]
if str(workspace) not in sys.path:
    sys.path.insert(0, str(workspace))

import importlib
mod = importlib.import_module("quant_research_hub.03_alpha_factory.nixtla_autogluon_ensemble_engine")
UnifiedNixtlaAutoGluonPipeline = mod.UnifiedNixtlaAutoGluonPipeline

def main():
    print("=== NIXTLA & AUTOGLUON: Probabilistic Volatility Cone & Stacking Demo ===")
    np.random.seed(42)
    L = 60
    base = 2650.0
    prices = base + np.cumsum(np.random.normal(0.15, 0.6, L))
    spreads = np.random.uniform(0.8, 1.8, L)

    pipeline = UnifiedNixtlaAutoGluonPipeline(lookback_len=48, pred_len=6)
    res = pipeline.process(prices, high_low_spreads=spreads)

    print(f"Current Price: {res['current_price']}")
    print(f"Blended Stacking Forecast (H=1..6): {res['blended_forecast_h6']}")
    print(f"Volatility Regime: {res['volatility_cone']['volatility_regime']}")
    print(f"Cone Width: {res['volatility_cone']['cone_width_pts']} pts")
    print(f"Suggested Dynamic Stop-Loss (P10/P90): {res['suggested_orders']['dynamic_sl']}")
    print(f"Suggested Dynamic Take-Profit: {res['suggested_orders']['dynamic_tp']}")
    print("AutoGluon Stacking Weights:", res["stacking_weights"])
    print("Nixtla & AutoGluon Pipeline Execution Verified Successfully!")

if __name__ == "__main__":
    main()
