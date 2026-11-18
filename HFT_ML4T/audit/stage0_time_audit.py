import sys
import io
import re
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
_ROOT = Path(r"C:\VPS CONTABO\HFT_ML4T")

files_to_check = [
    _ROOT / "run_hft_bot.py",
    _ROOT / "core" / "central_risk_desk.py",
    _ROOT / "core" / "mt5_bridge.py",
    _ROOT / "strategies" / "gold_micro_scalper.py",
    _ROOT / "strategies" / "oil_micro_scalper.py",
    _ROOT / "strategies" / "crypto_micro_scalper.py",
    _ROOT / "strategies" / "fx_micro_arbitrage.py",
    _ROOT / "config" / "hft_config.yaml"
]

time_patterns = [
    r"datetime\.now\([^)]*\)",
    r"strftime\([^)]*\)",
    r"trading_session",
    r"asian_range",
    r"macro_news",
    r"friday_hard",
    r"rollover_curfew",
    r"\.hour",
    r"utc"
]

print("=== GIAI ĐOẠN 0: RÀ SOÁT TẤT CẢ ĐIỂM KIỂM TRA THỜI GIAN TRONG CODE ===")
for f in files_to_check:
    if not f.exists(): continue
    lines = f.read_text(encoding='utf-8', errors='ignore').splitlines()
    found = []
    for idx, line in enumerate(lines, 1):
        for p in time_patterns:
            if re.search(p, line, re.IGNORECASE):
                found.append((idx, line.strip()))
                break
    print(f"\nFile: {f.relative_to(_ROOT)} (Tìm thấy {len(found)} dòng liên quan thời gian)")
    for lno, ltext in found[:15]:
        print(f"  L{lno:4d}: {ltext}")
    if len(found) > 15:
        print(f"  ... và {len(found)-15} dòng khác.")
