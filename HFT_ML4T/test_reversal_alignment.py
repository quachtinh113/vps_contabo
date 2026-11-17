import sys
from pathlib import Path
_ROOT = Path(r"C:\VPS CONTABO\HFT_ML4T")
sys.path.insert(0, str(_ROOT))

from run_sweep_rejection_falsification import DestructiveFalsificationEngine

engine = DestructiveFalsificationEngine(initial_capital=9907.83)
df_m15, df_h1 = engine.fetch_bars("XAUUSDm", m15_count=4800)

print(f"Data fetched: {len(df_m15)} M15 bars, {len(df_h1)} H1 bars")

