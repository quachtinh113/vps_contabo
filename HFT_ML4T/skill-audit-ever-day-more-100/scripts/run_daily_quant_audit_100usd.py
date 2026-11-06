#!/usr/bin/env python3
"""Skill Audit Ever Day More 100$ (`skill-audit-ever-day-more-100`) — Universal Bot Engine."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

UNIVERSAL_ENGINE_PATH = (
    Path(__file__).resolve().parents[2]
    / "07_Skill"
    / "Quant_Audit"
    / "scripts"
    / "audit_any_bot.py"
)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    spec = importlib.util.spec_from_file_location("audit_any_bot", str(UNIVERSAL_ENGINE_PATH))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load universal engine at {UNIVERSAL_ENGINE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()


if __name__ == "__main__":
    main()

