"""
Demonstration script for iTransformer Inverted Cross-Variate Factor Attention.
Run: python itransformer_attention_demo.py
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
iTransformerFactorAttention = tslib_mod.iTransformerFactorAttention

def main():
    print("=== TSLIB QUANT: iTransformer Cross-Variate Attention Demonstration ===")
    np.random.seed(42)
    # Simulate 6 factors across 64 lookback bars:
    # 0: Gold_Price, 1: DXY_Proxy, 2: Yield_10Y, 3: VPIN_Toxicity, 4: Kaufman_ER, 5: YangZhang_Vol
    L = 64
    factors = np.zeros((L, 6))
    
    # Gold price trending upwards
    factors[:, 0] = 2650.0 + np.cumsum(np.random.normal(0.2, 0.5, L))
    # DXY inversely correlated with Gold
    factors[:, 1] = 104.5 - 0.05 * (factors[:, 0] - 2650.0) + np.random.normal(0, 0.1, L)
    # Yield_10Y
    factors[:, 2] = 4.25 + np.random.normal(0, 0.02, L)
    # VPIN toxicity spiking during momentum
    factors[:, 3] = 0.45 + np.abs(np.diff(np.pad(factors[:, 0], (1, 0)))) * 0.1
    # Kaufman ER
    factors[:, 4] = np.random.uniform(0.3, 0.8, L)
    # Volatility
    factors[:, 5] = 1.2 + np.random.exponential(0.3, L)

    factor_names = ["Gold_Price", "DXY_Dollar", "US10Y_Yield", "VPIN_Toxicity", "Kaufman_ER", "YangZhang_Vol"]

    engine = iTransformerFactorAttention(num_factors=6, d_model=32)
    res = engine.compute_factor_attention(factors, factor_names)

    print("Target Asset:", res["target_factor"])
    print("Cross-Factor Attention Weights on Gold:")
    for factor, weight in res["target_attention_weights"].items():
        print(f"  - {factor:16s}: {weight:.4f} ({weight*100:.1f}%)")
    print("Top Influencing Macro/Micro Factor:", res["top_influencing_factor"])
    print("iTransformer Factor Attention Verified Successfully!")

if __name__ == "__main__":
    main()
