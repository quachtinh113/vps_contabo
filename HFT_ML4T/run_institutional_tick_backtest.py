"""
========================================================================================
HFT_ML4T — INSTITUTIONAL TICK-LEVEL HYBRID BACKTEST RUNNER
Executes the 4-Pillar Quantitative Backtest Engine:
1. Data Engineering (Level 1 Millisecond Ticks via Polars & Parquet)
2. Microstructure Realism (Empirical Latency Jitter & Adverse Slippage Penalty)
3. Hybrid Processing (Vectorized Optimization + Numba Event-Driven Validation + Lookahead Leak Audit)
4. Combinatorial Purged Cross-Validation (CPCV) & Deflated Sharpe Ratio (DSR)
========================================================================================
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone
import polars as pl
import pandas as pd

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engines.institutional_tick_backtester import (
    TickDataPipeline,
    MicrostructureExecutionModel,
    HybridBacktestEngine,
    CombinatorialPurgedCrossValidator
)


def run_institutional_backtest(symbol: str = "XAUUSDm", tick_count: int = 30000) -> None:
    print("=" * 82)
    print(f"  🏛️ HFT_ML4T — INSTITUTIONAL TICK-LEVEL HYBRID BACKTEST ENGINE")
    print(f"  Target Asset: {symbol} | Sample Size: {tick_count:,} Level 1 Ticks")
    print(f"  Pillars: Polars/Parquet -> Microstructure Realism -> Vectorized+Event -> CPCV/DSR")
    print("=" * 82 + "\n")

    # ----------------------------------------------------------------------------------
    # PILLAR 1: DATA ENGINEERING WITH POLARS & PARQUET
    # ----------------------------------------------------------------------------------
    print("─── [PILLAR 1: DATA ENGINEERING] ──────────────────────────────────────────")
    pipeline = TickDataPipeline()
    ticks_df = pipeline.fetch_or_load_ticks(symbol=symbol, count=tick_count, use_cache=True)
    print(f"✅ Level 1 Tick Ingestion complete: {len(ticks_df):,} ticks.")
    print(f"   Schema: {ticks_df.columns}")
    print(f"   Spread Mean: {ticks_df['spread_pts'].mean():.2f} pts | Micro-Vol Mean: {ticks_df['micro_vol'].mean():.6f}")
    print(f"   OFI Range: [{ticks_df['ofi'].min():.2f}, {ticks_df['ofi'].max():.2f}] | Mean: {ticks_df['ofi'].mean():.4f}\n")

    # ----------------------------------------------------------------------------------
    # PILLAR 2: MICROSTRUCTURE REALISM
    # ----------------------------------------------------------------------------------
    print("─── [PILLAR 2: MICROSTRUCTURE REALISM] ────────────────────────────────────")
    exec_model = MicrostructureExecutionModel()
    lat_ticks = exec_model.get_latency_delay_ticks(tick_interval_ms=50.0)
    adv_slip = exec_model.get_adverse_slippage_pts()
    print(f"✅ Ingested Telemetry Priors:")
    print(f"   Latency Model: ~{exec_model.empirical_latency_mean:.1f}ms -> {lat_ticks} tick queue delay")
    print(f"   Adverse Slippage: ~{adv_slip:.2f} pts penalty on market impact")
    print(f"   Adversarial Rule: No positive slippage; fills penalized on volatility jumps.\n")

    # ----------------------------------------------------------------------------------
    # PILLAR 3: HYBRID ENGINE (VECTORIZED GRID + EVENT-DRIVEN VALIDATION)
    # ----------------------------------------------------------------------------------
    print("─── [PILLAR 3: HYBRID PROCESSING & LOOKAHEAD AUDIT] ──────────────────────")
    hybrid = HybridBacktestEngine(data_pipeline=pipeline, execution_model=exec_model)
    
    # Grid search over 80 combinations
    grid_results = hybrid.run_vectorized_grid_search(
        symbol=symbol,
        ticks_df=ticks_df,
        gamma_grid=[0.02, 0.05, 0.1, 0.25],
        kappa_grid=[0.75, 1.25, 2.0, 3.0],
        ofi_grid=[0.15, 0.35, 0.60],
        max_inv_grid=[2.0, 3.0, 5.0]
    )

    print(f"✅ Completed Vectorized Grid Search ({len(grid_results)} trials).")
    print("   Stress-testing Top 5 candidates in Event-Driven Simulator...")
    
    validated = hybrid.validate_top_candidates_event_driven(
        symbol=symbol,
        ticks_df=ticks_df,
        top_candidates=grid_results,
        top_k=5,
        max_allowed_divergence_pct=0.05
    )

    print("\n   [HYBRID CONSISTENCY & FIDELITY AUDIT TABLE]")
    print(f"   {'Rank':<5} {'γ':<6} {'κ':<6} {'OFI':<6} {'Vec PnL':<12} {'Event PnL':<12} {'Divergence':<12} {'Status':<16}")
    print("   " + "-" * 75)
    for v in validated:
        status_txt = "🚨 LEAK REJECTED" if v["data_leakage_detected"] else "✅ FIDELITY OK"
        print(
            f"   #{v['rank']:<4} {v['gamma']:<6.2f} {v['kappa']:<6.2f} {v['ofi_sensitivity']:<6.2f} "
            f"${v['vectorized_pnl']:<11.2f} ${v['event_driven_pnl']:<11.2f} "
            f"{v['pnl_divergence_pct']:<11.1%} {status_txt:<16}"
        )
    print()

    # Pick the best validated candidate (divergence <= 5%)
    valid_candidates = [c for c in validated if not c["data_leakage_detected"]]
    if not valid_candidates:
        print("⚠️ All candidates showed lookahead bias (>5% divergence). Using best event-driven candidate for CPCV.")
        best_cand = validated[0]
    else:
        best_cand = valid_candidates[0]

    # ----------------------------------------------------------------------------------
    # PILLAR 4: CPCV & DEFLATED SHARPE RATIO (DSR)
    # ----------------------------------------------------------------------------------
    print("─── [PILLAR 4: COMBINATORIAL PURGED CROSS-VALIDATION] ─────────────────────")
    cpcv = CombinatorialPurgedCrossValidator(num_groups=6, test_groups=2, embargo_pct=0.01)
    cpcv_res = cpcv.evaluate_cpcv(
        symbol=symbol,
        ticks_df=ticks_df,
        gamma=best_cand["gamma"],
        kappa=best_cand["kappa"],
        ofi_sensitivity=best_cand["ofi_sensitivity"],
        max_inventory=best_cand["max_inventory"],
        num_total_trials=len(grid_results)
    )

    print(f"✅ CPCV Verification Complete:")
    print(f"   Combinatorial Paths Tested: {cpcv_res['cpcv_paths_count']} paths (Purged & Embargoed)")
    print(f"   Median Out-of-Sample Sharpe: {cpcv_res['median_oos_sharpe']:.2f} (Mean: {cpcv_res['mean_oos_sharpe']:.2f})")
    print(f"   Positive Paths Ratio: {cpcv_res['positive_paths_pct']:.1%}")
    print(f"   Deflated Sharpe Ratio (DSR): {cpcv_res['deflated_sharpe_ratio']:.3f} (Marcos López de Prado standard)")
    
    if cpcv_res["deflated_sharpe_ratio"] >= 0.95:
        print(f"   🎉 INSTITUTIONAL GRADE CONFIRMED: DSR >= 0.95 (Statistical False Discovery < 5%)")
    else:
        print(f"   ⚠️ WARNING: DSR < 0.95 (Strategy exhibits selection bias across {len(grid_results)} trials)")

    print("\n" + "=" * 82)
    print("  🏁 INSTITUTIONAL BACKTEST SUMMARY AUDIT COMPLETE")
    print("=" * 82 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Institutional Tick-Level Hybrid Backtest Runner")
    parser.add_argument("--symbol", type=str, default="XAUUSDm", help="Target trading symbol")
    parser.add_argument("--ticks", type=int, default=25000, help="Number of Level 1 ticks")
    args = parser.parse_args()

    run_institutional_backtest(symbol=args.symbol, tick_count=args.ticks)
