#!/usr/bin/env python3
"""Triple Barrier Labeling Method with Dynamic Volatility.

Based on Marcos López de Prado, 'Advances in Financial Machine Learning' (Chapter 3).
Overcomes fixed-horizon labeling by setting 3 dynamic barriers:
1. Upper horizontal barrier: Take-Profit based on dynamic volatility σ_t
2. Lower horizontal barrier: Stop-Loss based on dynamic volatility σ_t
3. Vertical barrier: Expiration horizon (holding window limit)
"""

from __future__ import annotations

import argparse
from typing import Optional, Union

import numpy as np
import pandas as pd


def get_daily_volatility(close: pd.Series, span: int = 100) -> pd.Series:
    """Calculate rolling daily volatility (exponentially weighted standard deviation of log returns)."""
    df0 = close.index.searchsorted(close.index - pd.Timedelta(days=1))
    df0 = df0[df0 > 0]
    df0 = pd.Series(close.index[df0 - 1], index=close.index[close.index.shape[0] - df0.shape[0] :])
    
    # Calculate returns over 1-day step
    try:
        df0 = close.loc[df0.index] / close.loc[df0.values].values - 1.0
    except Exception:
        # Fallback to simple percentage change
        df0 = close.pct_change()
        
    return df0.ewm(span=span).std().dropna()


def apply_triple_barrier(
    close: pd.Series,
    events: pd.DataFrame,
    pt_mult: float = 1.0,
    sl_mult: float = 1.0,
    min_ret: float = 0.001,
) -> pd.DataFrame:
    """Apply the Triple Barrier Method to a series of events.

    Parameters
    ----------
    close : pd.Series
        Time series of close prices.
    events : pd.DataFrame
        DataFrame with index = event timestamp, containing:
        - 't1': Timestamp of vertical barrier (expiration).
        - 'trgt': Target volatility σ_t used to scale barriers.
        - 'side' (optional): 1 for long, -1 for short (default: 1).

    Returns
    -------
    pd.DataFrame
        DataFrame with columns:
        - 'touch_time': Timestamp when the first barrier was touched.
        - 'ret': Return realized at touch_time.
        - 'label': -1 (SL hit), 1 (TP hit), 0 (Vertical barrier / expired).
    """
    out = pd.DataFrame(index=events.index, columns=["touch_time", "ret", "label"])

    for t0, row in events.iterrows():
        t1 = row["t1"]
        trgt = max(float(row["trgt"]), min_ret)
        side = float(row.get("side", 1.0))

        # Price path between event and vertical barrier
        path = close.loc[t0:t1]
        if len(path) < 2:
            continue

        base_price = path.iloc[0]
        # Return path adjusted for side
        returns = (path / base_price - 1.0) * side

        # Barrier thresholds
        upper_barrier = pt_mult * trgt if pt_mult > 0 else np.inf
        lower_barrier = -sl_mult * trgt if sl_mult > 0 else -np.inf

        # Find earliest hit
        touch_tp = returns[returns >= upper_barrier].index.min()
        touch_sl = returns[returns <= lower_barrier].index.min()

        # Compare hits
        candidates = [t for t in [touch_tp, touch_sl, t1] if pd.notna(t)]
        first_touch = min(candidates)

        actual_ret = returns.loc[first_touch]
        if first_touch == touch_tp:
            label = 1
        elif first_touch == touch_sl:
            label = -1
        else:
            label = 0

        out.loc[t0, "touch_time"] = first_touch
        out.loc[t0, "ret"] = actual_ret
        out.loc[t0, "label"] = label

    return out.dropna(subset=["touch_time"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Triple Barrier Method")
    parser.add_argument("--test", action="store_true", help="Run automated test with synthetic price series")
    args = parser.parse_args()

    if args.test:
        np.random.seed(42)
        dates = pd.date_range("2026-01-01", periods=500, freq="1h")
        returns = np.random.normal(0, 0.005, len(dates))
        close = pd.Series(100.0 * np.exp(np.cumsum(returns)), index=dates, name="Close")

        vol = close.pct_change().ewm(span=20).std().fillna(0.005)

        # Generate sample events every 10 bars with 24-bar vertical horizon
        sample_idx = dates[100::20][:-2]
        events = pd.DataFrame(index=sample_idx)
        events["t1"] = [dates[min(dates.get_loc(t) + 24, len(dates) - 1)] for t in sample_idx]
        events["trgt"] = vol.loc[sample_idx]
        events["side"] = 1.0  # Long signals

        labeled = apply_triple_barrier(close, events, pt_mult=1.5, sl_mult=1.0)
        print(f"[*] Generated {len(labeled)} labeled events using Triple Barrier Method:")
        print("\nLabel Distribution:")
        print(labeled["label"].value_counts().to_string())
        print("\nSample Output:")
        print(labeled.head().to_string())


if __name__ == "__main__":
    main()
