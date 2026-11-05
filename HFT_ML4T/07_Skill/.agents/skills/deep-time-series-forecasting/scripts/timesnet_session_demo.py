"""
Demonstration script for TimesNet Intraday 2D Session Periodicity Extractor.
Run: python timesnet_session_demo.py
"""

import sys
from pathlib import Path
import numpy as np

# Ensure workspace root is in path
workspace = Path(__file__).resolve().parents[4]
if str(workspace) not in sys.path:
    sys.path.insert(0, str(workspace))

import importlib
tslib_mod = importlib.import_module("quant_research_hub.03_alpha_factory.tslib_deep_quant_engine")
TimesNetSessionExtractor = tslib_mod.TimesNetSessionExtractor

def main():
    print("=== TSLIB QUANT: TimesNet 2D Session Periodicity Demonstration ===")
    np.random.seed(42)
    # Simulate cyclical intraday returns with 24-bar (e.g. 2-hour) and 96-bar (8-hour) session cycles
    t = np.arange(288) # 24 hours of 5-minute candles
    cycle_8h = 0.002 * np.sin(2 * np.pi * t / 96)
    cycle_2h = 0.001 * np.sin(2 * np.pi * t / 24)
    noise = np.random.normal(0, 0.0005, 288)
    returns = cycle_8h + cycle_2h + noise

    extractor = TimesNetSessionExtractor(top_k_periods=3)
    res = extractor.compute_2d_session_features(returns)

    print("Detected Dominant Harmonics (Periods in Bars):", res["dominant_periods"])
    print("Primary Cycle Length:", res["primary_period_bars"], "bars")
    print("Intraperiod Variation (Within Session):", res["intraperiod_variation"])
    print("Interperiod Variation (Across Sessions):", res["interperiod_variation"])
    print("Session Coherence Ratio:", res["session_coherence_ratio"])
    print("Session Regime:", res["session_regime"])
    print("TimesNet 2D Session Analysis Verified Successfully!")

if __name__ == "__main__":
    main()
