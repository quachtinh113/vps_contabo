import json
import numpy as np
import pandas as pd
from pathlib import Path

audit_file = Path(r"C:\VPS CONTABO\HFT_ML4T\logs\trade_audit.jsonl")
records = []
with open(audit_file, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            em = d.get("execution_metrics")
            if em:
                records.append({
                    "timestamp": em.get("timestamp_utc") or d.get("timestamp_utc"),
                    "symbol": em.get("symbol") or d.get("symbol"),
                    "order_type": em.get("order_type") or d.get("action"),
                    "volume": em.get("volume") or d.get("lot"),
                    "latency_ms": em.get("latency_ms"),
                    "slippage_points": em.get("slippage_points"),
                    "slippage_usd": em.get("slippage_usd"),
                    "retcode": em.get("retcode")
                })
        except Exception:
            pass

df_exec = pd.DataFrame(records)
print(f"Total execution records parsed: {len(df_exec)}")
if len(df_exec) > 0:
    for sym, g in df_exec.groupby("symbol"):
        print(f"\n=== Symbol: {sym} (N={len(g)}) ===")
        print(f"Latency ms: p50={g['latency_ms'].median():.1f}ms, p90={g['latency_ms'].quantile(0.90):.1f}ms, mean={g['latency_ms'].mean():.1f}ms")
        print(f"Slippage points: mean={g['slippage_points'].mean():.1f} pts, median={g['slippage_points'].median():.1f} pts")
        print(f"Slippage USD: mean=${g['slippage_usd'].mean():.2f}, median=${g['slippage_usd'].median():.2f}")
