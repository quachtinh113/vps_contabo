"""
GATE 1 STAGING — DATA LAYER (MarketDataIngestion)
Strictly handles market data parsing, closed-bar isolation, and microstructure feature engineering.
Decoupled completely from Strategy and Execution layers.
"""

from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import zoneinfo

TZ_UTC = zoneinfo.ZoneInfo("UTC")

class MarketDataIngestion:
    """
    Ingests raw rates and order book snapshots from MT5Bridge.
    Ensures zero look-ahead bias by strictly isolating closed bars (iloc[:-1]).
    Computes technical and microstructure features:
      - Garman-Klass Volatility
      - Order Flow Imbalance (OFI) proxy
      - Average True Range (ATR 14)
      - Asian Range high/low cache
    """

    def __init__(self, ofi_window: int = 5, atr_window: int = 14, gk_window: int = 20):
        self.ofi_window = ofi_window
        self.atr_window = atr_window
        self.gk_window = gk_window

    def prepare_closed_series(self, raw_rates: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Takes raw rates dataframe from MT5, standardizes UTC timezone,
        drops uncompleted current candle (iloc[:-1]), and calculates feature metrics.
        """
        if raw_rates is None or len(raw_rates) < 25:
            return pd.DataFrame(), {}

        df = raw_rates.copy()
        if "time" in df.columns:
            if not pd.api.types.is_datetime64_any_dtype(df["time"]):
                df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
            elif df["time"].dt.tz is None:
                df["time"] = df["time"].dt.tz_localize("UTC")
            else:
                df["time"] = df["time"].dt.tz_convert("UTC")

        # STRICT ISOLATION: Drop currently ticking bar to prevent look-ahead bias
        closed_df = df.iloc[:-1].copy().reset_index(drop=True)

        features = {
            "atr_14": self.calculate_atr(closed_df, window=self.atr_window),
            "garman_klass_vol": self.calculate_garman_klass(closed_df, window=self.gk_window),
            "ofi": self.calculate_ofi(closed_df, window=self.ofi_window),
            "last_closed_time": closed_df["time"].iloc[-1] if len(closed_df) > 0 else None,
            "last_closed_price": float(closed_df["close"].iloc[-1]) if len(closed_df) > 0 else 0.0
        }
        return closed_df, features

    @staticmethod
    def calculate_atr(df: pd.DataFrame, window: int = 14) -> float:
        """Calculates Average True Range over closed bars."""
        if len(df) < window + 1:
            return 2.0
        h = df["high"]
        l = df["low"]
        c_prev = df["close"].shift(1)
        tr = pd.concat([
            h - l,
            (h - c_prev).abs(),
            (l - c_prev).abs()
        ], axis=1).max(axis=1)
        atr = float(tr.iloc[-window:].mean())
        return max(0.10, atr) if not np.isnan(atr) else 2.0

    @staticmethod
    def calculate_garman_klass(df: pd.DataFrame, window: int = 20) -> float:
        """Calculates Garman-Klass intraday volatility proxy."""
        if len(df) < window:
            return 0.001
        sub = df.iloc[-window:]
        log_hl = np.log(sub["high"] / sub["low"])
        log_co = np.log(sub["close"] / sub["open"])
        gk_per_bar = 0.5 * (log_hl ** 2) - (2.0 * np.log(2.0) - 1.0) * (log_co ** 2)
        var = float(np.mean(gk_per_bar))
        return float(np.sqrt(max(1e-8, var)))

    @staticmethod
    def calculate_ofi(df: pd.DataFrame, window: int = 5) -> float:
        """Calculates institutional Order Flow Imbalance proxy (ML4T Jansen Ch. 21)."""
        if len(df) < max(window, 3):
            return 0.0
        sub = df.iloc[-max(window, 3):]
        last_b = sub.iloc[-1]
        hl = max(1e-6, float(last_b["high"] - last_b["low"]))
        bar_skew = float((last_b["close"] - (last_b["high"] + last_b["low"]) / 2.0) / hl)
        vol = sub["tick_volume"].values.astype(float) if "tick_volume" in sub.columns else np.ones(len(sub))
        p_diff = sub["close"].diff().fillna(0.0).values
        vol_weights = vol / (np.sum(vol) + 1e-6)
        vw_delta = float(np.sum(np.sign(p_diff) * vol_weights))
        combined = (0.60 * bar_skew) + (0.40 * vw_delta)
        return float(np.clip(combined * 1.5, -1.0, 1.0))

    @staticmethod
    def extract_asian_range(df_m15: pd.DataFrame) -> Tuple[float, float, float]:
        """
        Calculates Asian High, Asian Low, and Amplitude from 00:00 - 07:00 UTC.
        Returns: (asian_high, asian_low, asian_amplitude)
        """
        if df_m15 is None or len(df_m15) < 4:
            return 0.0, 0.0, 0.0

        # Asian bars: hour < 7
        asian_bars = df_m15[df_m15["time"].dt.hour < 7]
        if len(asian_bars) >= 4:
            # Use last 28 bars of Asian session (7 hours * 4 M15 bars = 28 bars)
            recent_asia = asian_bars.iloc[-28:]
            ah = float(recent_asia["high"].max())
            al = float(recent_asia["low"].min())
            return ah, al, ah - al
        return 0.0, 0.0, 0.0
