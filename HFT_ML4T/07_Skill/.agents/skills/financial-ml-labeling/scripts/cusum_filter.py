#!/usr/bin/env python3
"""Symmetric CUSUM Filter for Event-Driven Sampling.

Based on Marcos López de Prado, 'Advances in Financial Machine Learning' (Chapter 2.5.2).
Samples observations only when cumulative price changes exceed a volatility threshold h.
Avoids sampling redundant noise during low-volatility chop while capturing structural shifts.
"""

from __future__ import annotations

import argparse
from typing import List

import numpy as np
import pandas as pd


def get_cusum_events(
    close: pd.Series,
    threshold: Union[float, pd.Series],
) -> pd.DatetimeIndex:
    """Run Symmetric CUSUM Filter to detect volatility breakthrough events.

    Parameters
    ----------
    close : pd.Series
        Time-series of prices indexed by DatetimeIndex.
    threshold : float or pd.Series
        Hurdle threshold h (fixed scalar or dynamic volatility series).

    Returns
    -------
    pd.DatetimeIndex
        Timestamps of CUSUM events.
    """
    events = []
    s_pos = 0.0
    s_neg = 0.0

    diff = close.pct_change().dropna()
    is_series_h = isinstance(threshold, pd.Series)

    for t, ret in diff.items():
        h = float(threshold.loc[t]) if is_series_h else float(threshold)
        s_pos = max(0.0, s_pos + ret)
        s_neg = min(0.0, s_neg + ret)

        if s_neg < -h:
            s_neg = 0.0
            events.append(t)
        elif s_pos > h:
            s_pos = 0.0
            events.append(t)

    return pd.DatetimeIndex(events)


def main() -> None:
    parser = argparse.ArgumentParser(description="Symmetric CUSUM Filter")
    parser.add_argument("--test", action="store_true", help="Run automated test")
    args = parser.parse_args()

    if args.test:
        np.random.seed(42)
        dates = pd.date_range("2026-01-01", periods=1000, freq="15min")
        returns = np.random.normal(0, 0.002, len(dates))
        close = pd.Series(100.0 * np.exp(np.cumsum(returns)), index=dates)

        vol = close.pct_change().ewm(span=50).std().fillna(0.002)
        events = get_cusum_events(close, threshold=vol * 2.0)

        print(f"[*] Total Raw Bars: {len(close)}")
        print(f"[+] Selected CUSUM Events: {len(events)} ({len(events)/len(close)*100:.1f}% sampling rate)")
        print(f"    First 5 event timestamps: {list(events[:5])}")


if __name__ == "__main__":
    main()
