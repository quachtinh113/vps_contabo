import sys
import io
import pandas as pd
import numpy as np
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
_ROOT = Path(r"C:\VPS CONTABO\HFT_ML4T")
sys.path.insert(0, str(_ROOT))

from core.mt5_bridge import MT5Bridge
import MetaTrader5 as mt5
from strategies.commodity_oil_scalper import OilMicroScalperStrategy

def test_oil_exact():
    bridge = MT5Bridge()
    bridge.initialize()
    r_oil_m15 = mt5.copy_rates_from_pos("USOILm", mt5.TIMEFRAME_M15, 0, 4950)
    r_oil_h1 = mt5.copy_rates_from_pos("USOILm", mt5.TIMEFRAME_H1, 0, 1000)
    bridge.shutdown()

    df_m15 = pd.DataFrame(r_oil_m15)
    df_m15["time"] = pd.to_datetime(df_m15["time"], unit="s", utc=True)
    df_h1 = pd.DataFrame(r_oil_h1)
    df_h1["time"] = pd.to_datetime(df_h1["time"], unit="s", utc=True)

    cfg = {
        "name": "USOILm",
        "magic": 777005,
        "max_spread_points": 35.0,
        "trading_session_utc": ["07:00", "20:00"],
        "sl_multiplier": 2.2,
        "tp_multiplier": 3.3,
        "digits": 3,
        "avellaneda_stoikov": {"gamma": 0.12, "kappa": 1.8, "ofi_sensitivity": 0.25},
        "position_sizing": {"risk_per_trade_pct": 0.003, "max_lot_cap": 0.05}
    }
    strat = OilMicroScalperStrategy(cfg)

    signals = []
    for i in range(100, len(df_m15)-16):
        sub_m15 = df_m15.iloc[:i+1]
        t_cur = sub_m15["time"].iloc[-1]
        sub_h1 = df_h1[df_h1["time"] <= t_cur]
        if len(sub_h1) < 20: continue

        snap = {
            "mid": float(sub_m15["close"].iloc[-1]),
            "spread_points": 18.0
        }
        res = strat.evaluate(
            rates_df=sub_m15,
            market_snapshot=snap,
            current_inventory=0.0,
            account_equity=10000.0,
            h1_df=sub_h1,
            closed_rates_df=sub_m15.iloc[:-1],
            closed_h1_df=sub_h1.iloc[:-1],
            now_utc=t_cur.to_pydatetime()
        )
        if res:
            signals.append((i, t_cur, res["action"], res["sl_price"], res["tp_price"], res["ofi"], res.get("comment", "N/A")))

    print(f"Total Oil signals generated using exact strategy: {len(signals)}")
    if signals:
        df_sig = pd.DataFrame(signals, columns=["idx", "time", "action", "sl", "tp", "ofi", "reason"])
        print(df_sig.to_string())

        # Evaluate PnL in R
        pnls = []
        c = df_m15["close"].values
        h = df_m15["high"].values
        l = df_m15["low"].values
        for idx, t, action, sl, tp, ofi, reason in signals:
            entry = c[idx]
            sl_dist = abs(entry - sl)
            tp_dist = abs(tp - entry)
            trade_r = 0.0
            for f in range(idx+1, min(idx+17, len(df_m15))):
                if action == "BUY":
                    if l[f] <= sl: trade_r = -1.0; break
                    elif h[f] >= tp: trade_r = tp_dist / sl_dist; break
                else:
                    if h[f] >= sl: trade_r = -1.0; break
                    elif l[f] <= tp: trade_r = tp_dist / sl_dist; break
            if trade_r == 0.0:
                diff = (c[min(idx+16, len(df_m15)-1)] - entry) if action == "BUY" else (entry - c[min(idx+16, len(df_m15)-1)])
                trade_r = diff / sl_dist
            friction_r = 0.043 / sl_dist
            pnls.append(trade_r - friction_r)

        arr = np.array(pnls)
        print(f"Oil Strategy Performance (N={len(arr)} trades):")
        print(f"  Win Rate: {np.mean(arr > 0)*100:.1f}%")
        print(f"  Net E[R]: {np.mean(arr):+.3f}R")
        boot = [np.mean(np.random.choice(arr, size=len(arr), replace=True)) for _ in range(1000)]
        print(f"  95% CI  : [{np.percentile(boot, 2.5):+.3f}R, {np.percentile(boot, 97.5):+.3f}R]")

if __name__ == "__main__":
    test_oil_exact()
