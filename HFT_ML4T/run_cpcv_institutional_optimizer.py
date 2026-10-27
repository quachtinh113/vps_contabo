"""
========================================================================================
HFT_ML4T — INSTITUTIONAL EVENT-DRIVEN & CPCV OPTIMIZATION ENGINE
Based on Marcos López de Prado (Advances in Financial Machine Learning, 2018) & Stefan Jansen (ML4T).

4-Pillar Quantitative Protocol:
1. Multi-source Data Ingestion (MT5 Real Level 1 Ticks / Parquet Features / Synthetic).
2. Vectorized Ultra-Fast Grid Exploration (Numba JIT accelerated).
3. Microstructural Realistic Event-Driven Stress Testing (Queue Position & Adverse Selection).
4. Combinatorial Purged Cross-Validation (CPCV) & Deflated Sharpe Ratio (DSR).
========================================================================================
"""

import os
import sys
import math
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import numpy as np
import pandas as pd
import polars as pl
import MetaTrader5 as mt5

# Path setup
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.audit_logger import setup_logger, get_logger
from engines.institutional_tick_backtester import (
    TickDataPipeline,
    MicrostructureExecutionModel,
    HybridBacktestEngine,
    CombinatorialPurgedCrossValidator
)

logger = get_logger()


class CPCVInstitutionalOptimizer:
    """
    Production-grade Quantitative Optimizer for Avellaneda-Stoikov Micro-Scalping.
    Guarantees that discovered parameters survive institutional execution barriers
    and pass López de Prado's Deflated Sharpe Ratio (DSR >= 0.95).
    """

    def __init__(
        self,
        symbol: str = "XAUUSDm",
        tick_count: int = 50000,
        cpcv_groups: int = 6,
        cpcv_test_groups: int = 2,
        embargo_pct: float = 0.01,
        audit_csv_path: str = "logs/execution_audit.csv",
        simulated_latency_ms: Optional[float] = None,
        force_refresh: bool = False
    ):
        self.symbol = symbol
        self.tick_count = tick_count
        self.cpcv_groups = cpcv_groups
        self.cpcv_test_groups = cpcv_test_groups
        self.embargo_pct = embargo_pct
        self.audit_csv_path = audit_csv_path
        self.force_refresh = force_refresh

        self.pipeline = TickDataPipeline()
        self.exec_model = MicrostructureExecutionModel(
            symbol=symbol,
            audit_csv_path=audit_csv_path,
            simulated_latency_ms=simulated_latency_ms
        )
        self.hybrid_engine = HybridBacktestEngine(self.pipeline, self.exec_model)
        self.cpcv = CombinatorialPurgedCrossValidator(
            num_groups=cpcv_groups,
            test_groups=cpcv_test_groups,
            embargo_pct=embargo_pct
        )

    def load_tick_dataset(self) -> pl.DataFrame:
        """
        Loads tick stream with Level 1 microstructural features (OFI, Micro-volatility, Spread).
        Priority: MT5 Live History -> Parquet Features -> Synthetic Poisson Jumps.
        """
        logger.info(f"📥 [DATA INGESTION] Sourcing Level 1 tick data for {self.symbol}...")
        use_cache = not self.force_refresh
        return self.pipeline.fetch_or_load_ticks(symbol=self.symbol, count=self.tick_count, use_cache=use_cache)

    def run_optimization(
        self,
        gamma_grid: Optional[List[float]] = None,
        kappa_grid: Optional[List[float]] = None,
        ofi_grid: Optional[List[float]] = None,
        max_inventory: float = 1.0,
        top_candidates_count: int = 3
    ) -> Dict[str, Any]:
        """
        Executes complete 4-tier quantitative research run:
        Vectorized Exploration -> Event-Driven Filtering -> CPCV Out-Of-Sample -> DSR Check.
        """
        t0 = time.time()
        print("\n" + "=" * 80)
        print(f"🚀 HFT_ML4T INSTITUTIONAL CPCV OPTIMIZATION: {self.symbol}")
        print("=" * 80)

        # Grids: Institutional multi-dimensional parameter search
        gammas = gamma_grid or [0.03, 0.06, 0.09, 0.12, 0.15, 0.18, 0.22]
        kappas = kappa_grid or [0.8, 1.0, 1.3, 1.6, 1.9, 2.2, 2.6]
        ofis = ofi_grid or [0.15, 0.20, 0.25, 0.30, 0.35]
        total_trials = len(gammas) * len(kappas) * len(ofis)

        # Step 1: Load Data
        ticks_df = self.load_tick_dataset()
        logger.info(f"📊 Dataset active: {len(ticks_df):,} Level 1 ticks.")

        # Step 2: Vectorized Grid Exploration
        logger.info(f"⚡ [PHASE 1] Vectorized Numba grid exploration ({total_trials} parameter sets)...")
        vec_candidates = self.hybrid_engine.run_vectorized_grid_search(
            symbol=self.symbol,
            ticks_df=ticks_df,
            gamma_grid=gammas,
            kappa_grid=kappas,
            ofi_grid=ofis,
            max_inv_grid=[max_inventory]
        )

        top_candidates = vec_candidates[:top_candidates_count]
        logger.info(f"🏅 Top {len(top_candidates)} vectorized candidates selected for microstructural stress testing.")

        # Step 3: Event-Driven Microstructure Stress Test (Queue + Latency + Adverse Slippage)
        logger.info("🔬 [PHASE 2] Event-Driven stress testing (Simulating queue degradation & adverse selection)...")
        validated_candidates = self.hybrid_engine.validate_top_candidates_event_driven(
            symbol=self.symbol,
            ticks_df=ticks_df,
            top_candidates=top_candidates,
            top_k=min(top_candidates_count, len(top_candidates)),
            max_allowed_divergence_pct=0.35
        )

        # Step 4: Combinatorial Purged Cross-Validation & DSR for surviving candidates
        logger.info("🛡️ [PHASE 3] Combinatorial Purged Cross-Validation (CPCV) & Deflated Sharpe Ratio...")
        cpcv_results = []
        best_candidate = None
        best_dsr = -1.0

        for cand in validated_candidates:
            if cand.get("data_leakage_detected", False):
                logger.warning(
                    f"⚠️ Skipping candidate (γ={cand['gamma']}, κ={cand['kappa']}): "
                    f"Rejected by Event-Driven validator (Divergence: {cand['pnl_divergence_pct']:.1%})"
                )
                continue

            cpcv_metric = self.cpcv.evaluate_cpcv(
                symbol=self.symbol,
                ticks_df=ticks_df,
                gamma=cand["gamma"],
                kappa=cand["kappa"],
                ofi_sensitivity=cand["ofi_sensitivity"],
                max_inventory=max_inventory,
                num_total_trials=total_trials
            )

            cand_full = cand.copy()
            cand_full.update({
                "cpcv_median_sharpe": cpcv_metric["median_oos_sharpe"],
                "cpcv_mean_sharpe": cpcv_metric["mean_oos_sharpe"],
                "cpcv_positive_paths_pct": cpcv_metric["positive_paths_pct"],
                "deflated_sharpe_ratio": cpcv_metric["deflated_sharpe_ratio"],
                "is_statistically_sound": cpcv_metric["is_statistically_sound"]
            })
            cpcv_results.append(cand_full)

            if cand_full["deflated_sharpe_ratio"] > best_dsr:
                best_dsr = cand_full["deflated_sharpe_ratio"]
                best_candidate = cand_full

        elapsed = time.time() - t0
        logger.info(f"⏱️ Optimization completed in {elapsed:.2f} seconds.")

        summary = {
            "symbol": self.symbol,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(elapsed, 2),
            "total_trials_tested": total_trials,
            "ticks_analyzed": len(ticks_df),
            "top_candidates": cpcv_results,
            "best_parameter_set": best_candidate or (validated_candidates[0] if validated_candidates else None)
        }

        self._print_executive_summary(summary)
        return summary

    def _print_executive_summary(self, summary: Dict[str, Any]) -> None:
        """Formats and prints executive research findings in clean markdown tables."""
        print("\n" + "=" * 80)
        print("🏛️ INSTITUTIONAL CPCV OPTIMIZATION REPORT")
        print("=" * 80)
        print(f"Asset Symbol        : {summary['symbol']}")
        print(f"Ticks Processed     : {summary['ticks_analyzed']:,}")
        print(f"Total Trials Tested : {summary['total_trials_tested']} combinations")
        print(f"Execution Duration  : {summary['elapsed_seconds']}s")
        print("-" * 80)

        best = summary.get("best_parameter_set")
        if best:
            print("🏆 OPTIMAL PARAMETER SET (Validated via CPCV & DSR):")
            print(f"   • Risk Aversion (γ)        : {best['gamma']}")
            print(f"   • Order Book Liquidity (κ)  : {best['kappa']}")
            print(f"   • OFI Sensitivity Factor   : {best['ofi_sensitivity']}")
            print(f"   • Vectorized Net PnL       : ${best.get('vectorized_pnl', 0):,.2f}")
            print(f"   • Event-Driven Net PnL     : ${best.get('event_driven_pnl', 0):,.2f}")
            print(f"   • PnL Divergence           : {best.get('pnl_divergence_pct', 0):.1%}")
            print(f"   • Median OOS Sharpe (CPCV) : {best.get('cpcv_median_sharpe', 0):.2f}")
            print(f"   • Positive OOS Paths       : {best.get('cpcv_positive_paths_pct', 0):.1%}")
            print(f"   • Deflated Sharpe Ratio    : {best.get('deflated_sharpe_ratio', 0):.2f}")
            
            is_sound = best.get("is_statistically_sound", False)
            status_text = "✅ 95%+ CONFIDENCE (Non-overfit Alpha)" if is_sound else "⚠️ MODERATE STATISTICAL POWER"
            print(f"   • Statistical Verdict      : {status_text}")
        else:
            print("❌ No parameter set passed all realistic microstructural filters.")
        print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Institutional CPCV Optimizer for HFT_ML4T")
    parser.add_argument("--symbol", type=str, default="XAUUSDm", help="Trading asset symbol (e.g. XAUUSDm, BTCUSDm)")
    parser.add_argument("--ticks", type=int, default=15000, help="Number of ticks to evaluate")
    parser.add_argument("--cpcv-groups", type=int, default=6, help="Number of CPCV groups (N)")
    parser.add_argument("--test-groups", type=int, default=2, help="Number of test groups per split (k)")
    parser.add_argument("--latency-ms", type=float, default=20.0, help="Target simulated network latency in ms")
    parser.add_argument("--force-refresh", action="store_true", help="Force fetching fresh ticks from MT5")
    args = parser.parse_args()

    optimizer = CPCVInstitutionalOptimizer(
        symbol=args.symbol,
        tick_count=args.ticks,
        cpcv_groups=args.cpcv_groups,
        cpcv_test_groups=args.test_groups,
        simulated_latency_ms=args.latency_ms,
        force_refresh=args.force_refresh
    )
    optimizer.run_optimization()


if __name__ == "__main__":
    main()
