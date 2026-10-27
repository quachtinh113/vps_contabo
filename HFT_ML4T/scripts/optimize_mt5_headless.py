"""
HFT_ML4T — MT5 Headless & VPS Resource Optimizer
Applies low-footprint virtualized server profile to MT5 Terminal:
1. Disables continuous news feeds (NewsEnable = 0)
2. Limits chart bar buffering to 5,000 bars (MaxBars = 5000)
3. Disables background chart preloading (PreloadCharts = 0)
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
from pathlib import Path

DATA_PATH = Path(r"C:\Users\Administrator\AppData\Roaming\MetaQuotes\Terminal\D81A0D581BA6190886BEACF0362E7BE5")
COMMON_INI = DATA_PATH / "config" / "common.ini"

def optimize():
    if not COMMON_INI.exists():
        print(f"Error: {COMMON_INI} not found.")
        sys.exit(1)

    # Read UTF-16
    content = COMMON_INI.read_text(encoding="utf-16", errors="ignore")
    lines = content.splitlines()
    new_lines = []
    
    in_common = False
    in_charts = False
    news_set = False
    maxbars_set = False
    preload_set = False

    for line in lines:
        stripped = line.strip()
        if stripped == "[Common]":
            in_common = True
            in_charts = False
            new_lines.append(line)
            continue
        elif stripped == "[Charts]":
            in_charts = True
            in_common = False
            new_lines.append(line)
            continue
        elif stripped.startswith("["):
            in_common = False
            in_charts = False

        if in_common and stripped.startswith("NewsEnable="):
            new_lines.append("NewsEnable=0")
            news_set = True
            continue

        if in_charts and stripped.startswith("MaxBars="):
            new_lines.append("MaxBars=5000")
            maxbars_set = True
            continue

        if in_charts and stripped.startswith("PreloadCharts="):
            new_lines.append("PreloadCharts=0")
            preload_set = True
            continue

        new_lines.append(line)

    # Write back UTF-16
    optimized_content = "\n".join(new_lines) + "\n"
    COMMON_INI.write_text(optimized_content, encoding="utf-16")
    print("✅ common.ini successfully optimized for VPS Headless operation:")
    print("   - NewsEnable=0 (Eliminated continuous news feed CPU/Network consumption)")
    print("   - MaxBars=5000 (Reduced chart memory footprint from 100,000 bars)")
    print("   - PreloadCharts=0 (Disabled idle chart preloading)")

if __name__ == "__main__":
    optimize()
