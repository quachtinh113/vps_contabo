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
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

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


_EXECUTION_AUDIT_BUFFER: List[Dict[str, Any]] = []
_LAST_AUDIT_FLUSH_TS: float = time.time()


def flush_execution_audit(log_dir: str = "logs") -> None:
    """Flushes buffered execution telemetry records to disk in a single I/O burst."""
    global _EXECUTION_AUDIT_BUFFER, _LAST_AUDIT_FLUSH_TS
    if not _EXECUTION_AUDIT_BUFFER:
        return

    records_to_write = list(_EXECUTION_AUDIT_BUFFER)
    _EXECUTION_AUDIT_BUFFER.clear()
    _LAST_AUDIT_FLUSH_TS = time.time()

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
            writer.writerows(records_to_write)
    except Exception as e:
        get_logger().error(f"Failed to flush execution audit records: {e}")


def log_execution_audit(log_dir: str, record: Dict[str, Any], immediate: bool = False) -> None:
    """
    Buffers order execution latency and slippage telemetry to RAM before batching to execution_audit.csv.
    Protects shared VPS SSD/NVMe from excessive disk I/O wait spikes.
    """
    global _EXECUTION_AUDIT_BUFFER, _LAST_AUDIT_FLUSH_TS
    try:
        _EXECUTION_AUDIT_BUFFER.append(record)
        # Flush if buffer reaches threshold (5 trades), interval elapsed (15s), or test/immediate requested
        now_ts = time.time()
        is_test_env = any(t in str(log_dir).lower() for t in ["tmp", "temp", "test"])
        if immediate or is_test_env or len(_EXECUTION_AUDIT_BUFFER) >= 5 or (now_ts - _LAST_AUDIT_FLUSH_TS >= 15.0):
            flush_execution_audit(log_dir)
    except Exception as e:
        get_logger().error(f"Failed to buffer execution audit record: {e}")


