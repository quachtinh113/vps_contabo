"""
HFT_ML4T — High-Frequency Machine Learning Data Pipeline & Quantitative Research Suite
Based on Marcos López de Prado (Advances in Financial Machine Learning) & Stefan Jansen (ML4T).

Core Components:
1. ParquetFeatureCollector: High-throughput in-memory feature buffer & streaming Parquet archiver (PyArrow Snappy).
2. TripleBarrierMetaLabeler: Directional/Alpha Meta-labeling (+1, 0, -1) using dynamic triple barriers.
3. OrthogonalFactorNeutralizer: Dollar-Neutral Beta-weighting to neutralize macro shocks (DXY / Yields).
4. CombinatorialPurgedCV: Combinatorial Purged Cross-Validation (CPCV) with purging, embargoing, and Deflated Sharpe Ratio (DSR).
"""

import os
import math
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any, Union
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


class ParquetFeatureCollector:
    """
    High-throughput streaming feature collector:
    Buffers real-time microstructural features (OFI, Volatility, AS Skew, Dynamic Kappa, Telemetry)
    and flushes to compressed Parquet files (.parquet) using Apache Arrow.
    """

    def __init__(
        self,
        output_dir: str = "data/features",
        flush_threshold: int = 200,
        flush_interval_seconds: float = 20.0,
        compression: str = "snappy"
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.flush_threshold = flush_threshold
        self.flush_interval_seconds = flush_interval_seconds
        self.compression = compression
        self._buffer: List[Dict[str, Any]] = []
        self._last_flush_time = time.time()

    def record_feature(
        self,
        symbol: str,
        mid_price: float,
        spread_points: float,
        ofi: float,
        garman_klass_vol: float,
        micro_vol: float,
        dynamic_kappa: float,
        reservation_price: float,
        skew_offset: float,
        action: Optional[str] = None,
        macro_regime: str = "UNKNOWN",
        slope_ema21_pct: float = 0.0,
        recent_slippage_pts: float = 0.0,
        recent_latency_ms: float = 0.0
    ) -> None:
        """Buffers a microstructural feature record with UTC millisecond timestamp."""
        now_utc = datetime.now(timezone.utc)
        record = {
            "timestamp_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "epoch_ms": int(now_utc.timestamp() * 1000),
            "symbol": symbol,
            "mid_price": float(mid_price),
            "spread_points": float(spread_points),
            "ofi": float(round(ofi, 4)),
            "gk_volatility": float(round(garman_klass_vol, 6)),
            "micro_volatility": float(round(micro_vol, 6)),
            "dynamic_kappa": float(round(dynamic_kappa, 4)),
            "reservation_price": float(round(reservation_price, 5)),
            "skew_offset": float(round(skew_offset, 5)),
            "signal_action": action or "HOLD",
            "macro_regime": macro_regime,
            "slope_ema21_pct": float(round(slope_ema21_pct, 4)),
            "recent_slippage_pts": float(round(recent_slippage_pts, 2)),
            "recent_latency_ms": float(round(recent_latency_ms, 2))
        }
        self._buffer.append(record)

        # Dual trigger: Flush if count threshold reached OR time window (10-30s) elapsed
        now_ts = time.time()
        if len(self._buffer) >= self.flush_threshold or (now_ts - self._last_flush_time >= self.flush_interval_seconds and len(self._buffer) >= 20):
            self.flush()

    def flush(self) -> Optional[str]:
        """Flushes buffered records to an hourly-partitioned Parquet file."""
        if not self._buffer:
            return None

        records_to_write = list(self._buffer)
        self._buffer.clear()
        self._last_flush_time = time.time()

        df = pd.DataFrame(records_to_write)
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        hour_str = datetime.now(timezone.utc).strftime("%H")
        
        target_dir = self.output_dir / date_str
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / f"features_{date_str}_{hour_str}.parquet"

        table = pa.Table.from_pandas(df, preserve_index=False)
        if file_path.exists():
            try:
                existing_table = pq.read_table(file_path)
                combined_table = pa.concat_tables([existing_table, table])
                pq.write_table(combined_table, file_path, compression=self.compression)
            except Exception:
                pq.write_table(table, file_path, compression=self.compression)
        else:
            pq.write_table(table, file_path, compression=self.compression)

        return str(file_path)

    def close(self) -> None:
        """Flushes remaining records upon shutdown."""
        self.flush()

    def get_buffer_size(self) -> int:
        return len(self._buffer)


class TripleBarrierMetaLabeler:
    """
    Marcos López de Prado Triple Barrier Meta-Labeling Engine:
    Assigns institutional machine learning ground-truth labels (+1, 0, -1) to trade events.
      +1: Upper barrier touched first (Profit target / Continuation)
      -1: Lower barrier touched first (Stop-loss hit / Adverse Reversal)
       0: Vertical barrier reached first (Time expired without touching horizontal barriers)
    """

    def __init__(
        self,
        pt_multiplier: float = 1.5,
        sl_multiplier: float = 1.5,
        horizon_bars: int = 15
    ):
        self.pt_multiplier = pt_multiplier
        self.sl_multiplier = sl_multiplier
        self.horizon_bars = horizon_bars

    def label_events(
        self,
        rates_df: pd.DataFrame,
        event_indices: List[int],
        action_directions: Optional[List[int]] = None
    ) -> pd.DataFrame:
        """
        Labels given events across price history.
        :param rates_df: OHLCV DataFrame with 'close', 'high', 'low'
        :param event_indices: List of row indices where events/signals occurred
        :param action_directions: List of directions (+1 for BUY, -1 for SELL). Defaults to +1 (Long).
        :return: DataFrame of labeled events with columns ['event_idx', 'label', 'ret', 'barrier_type']
        """
        if rates_df is None or len(rates_df) < 5 or not event_indices:
            return pd.DataFrame()

        directions = action_directions or [1] * len(event_indices)
        results = []

        closes = rates_df["close"].values
        highs = rates_df["high"].values
        lows = rates_df["low"].values
        n = len(closes)

        # Estimate daily/sub-bar rolling standard deviation
        log_rets = np.diff(np.log(np.maximum(closes, 1e-8)))
        sigma_est = max(0.001, float(np.std(log_rets[-50:], ddof=1))) if len(log_rets) >= 2 else 0.005

        for idx, direction in zip(event_indices, directions):
            if idx >= n - 1:
                continue

            entry_price = closes[idx]
            pt_dist = entry_price * sigma_est * self.pt_multiplier
            sl_dist = entry_price * sigma_est * self.sl_multiplier

            upper_barrier = entry_price + pt_dist if direction > 0 else entry_price + sl_dist
            lower_barrier = entry_price - sl_dist if direction > 0 else entry_price - pt_dist

            end_idx = min(n - 1, idx + self.horizon_bars)
            label = 0
            barrier_type = "VERTICAL"
            realized_ret = 0.0

            for f_idx in range(idx + 1, end_idx + 1):
                cur_high = highs[f_idx]
                cur_low = lows[f_idx]
                cur_close = closes[f_idx]

                if direction > 0:
                    # Long trade
                    if cur_high >= upper_barrier:
                        label = 1
                        barrier_type = "UPPER"
                        realized_ret = (upper_barrier - entry_price) / entry_price
                        break
                    elif cur_low <= lower_barrier:
                        label = -1
                        barrier_type = "LOWER"
                        realized_ret = (lower_barrier - entry_price) / entry_price
                        break
                else:
                    # Short trade
                    if cur_low <= lower_barrier:
                        label = 1
                        barrier_type = "UPPER"  # Profit barrier hit for short
                        realized_ret = (entry_price - lower_barrier) / entry_price
                        break
                    elif cur_high >= upper_barrier:
                        label = -1
                        barrier_type = "LOWER"  # Stop barrier hit for short
                        realized_ret = (entry_price - upper_barrier) / entry_price
                        break

            if label == 0:
                final_close = closes[end_idx]
                realized_ret = ((final_close - entry_price) / entry_price) * direction

            results.append({
                "event_idx": idx,
                "direction": direction,
                "entry_price": entry_price,
                "label": label,
                "barrier_type": barrier_type,
                "realized_return": float(round(realized_ret, 6))
            })

        return pd.DataFrame(results)


class OrthogonalFactorNeutralizer:
    """
    Dollar & Macro Factor Neutralization:
    Computes asset sensitivity (Beta) to global macro factors (DXY / USD Index).
    Adjusts position sizing to enforce net Dollar-Neutral exposure across the 6 assets.
    """

    # Baseline theoretical empirical USD sensitivity (dAsset / dUSD)
    DEFAULT_USD_BETAS: Dict[str, float] = {
        "EURUSDm": -1.00,  # Pure inverted USD exposure
        "GBPUSDm": -0.85,  # Strong negative USD correlation
        "XAUUSDm": -0.75,  # Gold negative USD sensitivity
        "USOILm":  -0.45,  # Crude oil inverse USD correlation
        "BTCUSDm": -0.30,  # Crypto partial negative macro liquidity sensitivity
        "US30m":    0.20   # US Equity partial positive domestic USD beta
    }

    def __init__(self, custom_betas: Optional[Dict[str, float]] = None):
        self.betas = custom_betas or self.DEFAULT_USD_BETAS

    def calculate_portfolio_dollar_exposure(self, active_positions: List[Dict[str, Any]]) -> float:
        """
        Computes net USD factor exposure:
          Net_Exposure = sum( Position_Volume * Direction * Beta_i )
        """
        net_exposure = 0.0
        for pos in active_positions:
            sym = pos.get("symbol", "")
            vol = float(pos.get("volume", 0.0))
            is_buy = (pos.get("order_type", "").upper() == "BUY" or pos.get("type", 0) == 0)
            direction = 1.0 if is_buy else -1.0
            beta = self.betas.get(sym, 0.0)
            net_exposure += vol * direction * beta
        return round(net_exposure, 4)

    def calculate_neutralizing_multiplier(
        self,
        candidate_symbol: str,
        action: str,
        active_positions: List[Dict[str, Any]],
        max_tilt_cap: float = 1.50
    ) -> float:
        """
        Calculates a scale multiplier [0.5, 1.5] for the candidate order to maintain Dollar Neutrality.
        - If the candidate order REDUCES portfolio dollar imbalance -> Boost size (reward hedging).
        - If the candidate order INCREASES portfolio dollar imbalance -> Scale down size (penalize concentration).
        """
        current_net = self.calculate_portfolio_dollar_exposure(active_positions)
        sym_beta = self.betas.get(candidate_symbol, 0.0)
        direction = 1.0 if action.upper() == "BUY" else -1.0
        projected_delta = direction * sym_beta

        if abs(current_net) < 0.05:
            return 1.0  # Balanced portfolio

        # Check if projected trade counters existing tilt
        if current_net * projected_delta < 0:
            # Hedging trade: promotes dollar neutrality
            mult = 1.0 + min(0.30, abs(current_net) * 0.5)
        else:
            # Aggravating trade: exacerbates dollar tilt
            mult = max(0.50, 1.0 - abs(current_net) * 0.5)

        return float(round(np.clip(mult, 0.50, max_tilt_cap), 2))


class CombinatorialPurgedCrossValidation:
    """
    Combinatorial Purged Cross-Validation (CPCV) & Deflated Sharpe Ratio Engine:
    Marcos López de Prado (2018) methodology for leak-free, non-overfitted backtest evaluation.
    """

    def __init__(self, num_splits: int = 5, test_splits: int = 2, embargo_pct: float = 0.01):
        self.num_splits = num_splits
        self.test_splits = test_splits
        self.embargo_pct = embargo_pct

    @staticmethod
    def calculate_deflated_sharpe_ratio(
        observed_sr: float,
        num_trials: int,
        sample_length: int,
        skewness: float = 0.0,
        kurtosis: float = 3.0
    ) -> float:
        """
        Computes Deflated Sharpe Ratio (DSR):
        Probability that observed Sharpe Ratio is genuine and not a false discovery
        resulting from multiple backtest trials (data snooping bias).
        """
        if sample_length <= 1 or num_trials <= 0:
            return 0.50

        # Euler-Mascheroni constant
        gamma = 0.5772156649
        # Expected maximum SR across N independent Gaussian trials
        expected_max_sr = (1.0 - gamma) * math.sqrt(2.0 * math.log(num_trials)) + (
            gamma / math.sqrt(2.0 * math.log(num_trials))
        ) if num_trials > 1 else 0.0

        # Variance of Sharpe Ratio with non-normality adjustments
        sr_var = (1.0 - skewness * observed_sr + ((kurtosis - 1.0) / 4.0) * (observed_sr ** 2)) / sample_length
        if sr_var <= 0:
            return 1.0

        sr_std = math.sqrt(sr_var)
        z_stat = (observed_sr - expected_max_sr) / sr_std

        # Standard normal CDF
        dsr = 0.5 * (1.0 + math.erf(z_stat / math.sqrt(2.0)))
        return float(np.clip(dsr, 0.0, 1.0))
