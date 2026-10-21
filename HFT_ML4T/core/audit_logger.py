"""
HFT_ML4T — Audit & Real-Time Production Logger
Handles formatted logging to console, rotating file, and structured JSONL trade audits.
"""

import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import csv
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional

_LOGGER: Optional[logging.Logger] = None


def setup_logger(log_dir: str = "logs", log_level: str = "INFO") -> logging.Logger:
    global _LOGGER
    path = Path(log_dir)
    path.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("HFT_ML4T")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    logger.handlers.clear()

    # Formatter
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-5s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # Rotating / Date File handler
    from logging.handlers import TimedRotatingFileHandler
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    fh = TimedRotatingFileHandler(
        path / f"hft_live_{today_str}.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
        utc=True
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    _LOGGER = logger
    return logger


def get_logger() -> logging.Logger:
    global _LOGGER
    if _LOGGER is None:
        return setup_logger()
    return _LOGGER


def log_trade_audit(log_dir: str, record: Dict[str, Any]) -> None:
    """Appends an immutable JSONL audit record for institutional compliance."""
    try:
        path = Path(log_dir)
        path.mkdir(parents=True, exist_ok=True)
        audit_file = path / "trade_audit.jsonl"
        
        record_copy = dict(record)
        if "timestamp_utc" not in record_copy:
            record_copy["timestamp_utc"] = datetime.now(timezone.utc).isoformat()

        with open(audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record_copy, ensure_ascii=False) + "\n")
    except Exception as e:
        get_logger().error(f"Failed to log trade audit record: {e}")


def log_execution_audit(log_dir: str, record: Dict[str, Any]) -> None:
    """
    Appends order execution latency and slippage telemetry to execution_audit.csv.
    Enables statistical analysis and slippage distribution plotting.
    """
    try:
        path = Path(log_dir)
        path.mkdir(parents=True, exist_ok=True)
        csv_file = path / "execution_audit.csv"

        fieldnames = [
            "timestamp_utc",
            "ticket",
            "symbol",
            "order_type",
            "volume",
            "expected_price",
            "fill_price",
            "slippage_points",
            "slippage_usd",
            "latency_ms",
            "retcode",
            "comment"
        ]

        file_exists = csv_file.exists() and csv_file.stat().st_size > 0

        with open(csv_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            if not file_exists:
                writer.writeheader()
            writer.writerow(record)
    except Exception as e:
        get_logger().error(f"Failed to log execution audit record: {e}")

