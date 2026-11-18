"""
========================================================================================
HFT_ML4T — GATE 1 DECOUPLED MASTER PRODUCTION RUNNER (v2.0)
Architecture: Data Tier -> Strategy Tier -> Execution/Risk Tier
Timezone: zoneinfo (America/New_York, Europe/London, calibrated UTC)
Mutex: OS-level Exclusive File Lock (quant_bot.lock)
========================================================================================
"""

import os
import sys
import time
import signal
from pathlib import Path
from datetime import datetime, timezone, timedelta

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import yaml
import pandas as pd
from dotenv import load_dotenv

# Path setup
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.audit_logger import setup_logger, get_logger, log_trade_audit, flush_execution_audit
from core.mt5_bridge import MT5Bridge

from timezone_dst import ZoneinfoSessionManager, ZoneinfoNewsShield, get_calibrated_utc, format_real_utc_log
from data_layer import MarketDataIngestion
from strategy_layer import GoldAlphaEngine, OilAlphaEngine
from execution_risk_layer import DecoupledExecutionRiskManager

# Load environment & config
load_dotenv(_ROOT / ".env")
CONFIG_PATH = _ROOT / "config" / "hft_config.yaml"

if not CONFIG_PATH.exists():
    raise FileNotFoundError(f"Configuration file not found: {CONFIG_PATH}")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

system_cfg = config.get("system", {})
risk_cfg = config.get("risk_desk", {})

logger = setup_logger(
    log_dir=str(_ROOT / system_cfg.get("log_dir", "logs")),
    log_level=system_cfg.get("log_level", "INFO")
)

# OS-Level Process Mutex Lock (quant_bot.lock)
LOCK_FILE = _ROOT / "quant_bot.lock"
_lock_handle = None

def acquire_process_lock():
    global _lock_handle
    try:
        if sys.platform == "win32":
            import msvcrt
            _lock_handle = open(LOCK_FILE, "a+")
            msvcrt.locking(_lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            _lock_handle = open(LOCK_FILE, "a+")
            fcntl.flock(_lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        logger.info(f"🔒 [MUTEX] Acquired exclusive OS process lock: {LOCK_FILE.name}")
        return True
    except (IOError, OSError) as e:
        logger.critical(f"🛑 [MUTEX ERROR] Another bot instance is already running! Mutex lock failed: {e}")
        print(f"🛑 [FATAL] Another bot instance is already holding {LOCK_FILE.name}. Exiting.")
        sys.exit(1)

def release_process_lock():
    global _lock_handle
    if _lock_handle:
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(_lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(_lock_handle, fcntl.LOCK_UN)
            _lock_handle.close()
            if LOCK_FILE.exists():
                LOCK_FILE.unlink(missing_ok=True)
            logger.info("🔓 [MUTEX] Released OS process lock.")
        except Exception as e:
            logger.error(f"[MUTEX] Error releasing lock: {e}")

_running = True

def signal_handler(signum, frame):
    global _running
    logger.info("⚠️ Received shutdown signal. Initiating graceful shutdown...")
    _running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def main():
    global _running
    acquire_process_lock()

    logger.info("=" * 80)
    logger.info("🚀 [HFT_ML4T] INITIALIZING GATE 1 PRODUCTION ENGINE (v2.0 DECOUPLED)")
    logger.info("=" * 80)

    # Initialize MT5 Bridge
    mt5_bridge = MT5Bridge(
        terminal_path=os.getenv("MT5_PATH", ""),
        account=int(os.getenv("MT5_ACCOUNT", "0")),
        password=os.getenv("MT5_PASSWORD", ""),
        server=os.getenv("MT5_SERVER", "")
    )
    if not mt5_bridge.initialize():
        logger.critical("🛑 [HFT_ML4T] Failed to initialize MT5 Gateway. Aborting.")
        release_process_lock()
        sys.exit(1)

    # Log Timezone and NTP Skew Calibration
    real_utc = get_calibrated_utc()
    logger.info(f"⏱️ [TIME ENGINE] Real UTC Clock initialized: {format_real_utc_log(real_utc)}")
    session_mgr = ZoneinfoSessionManager()
    news_shield = ZoneinfoNewsShield()
    logger.info(f"🛡️ [NEWS SHIELD] Zoneinfo Macro News Shield: ACTIVE (EIA, CPI, NFP, FOMC auto-gated)")
    is_dst, dst_desc = session_mgr.is_dst_transition_week(real_utc)
    logger.info(f"🌐 [DST STATUS] {dst_desc}")

    # Initialize Decoupled Architecture Tiers
    data_ingestion = MarketDataIngestion()
    strategy_gold = GoldAlphaEngine()
    strategy_oil = OilAlphaEngine()
    execution_manager = DecoupledExecutionRiskManager(
        risk_per_trade_pct=risk_cfg.get("risk_per_trade_pct", 0.005),
        max_lot_caps={"XAUUSDm": 0.07, "USOILm": 0.05},
        max_daily_drawdown_usd=risk_cfg.get("max_daily_drawdown_usd", 100.0)
    )

    strategies = {
        "XAUUSDm": strategy_gold,
        "USOILm": strategy_oil
    }

    last_status_print = 0.0
    inflight_order_lock = {}
    DUPLICATE_GUARD_SEC = 5.0
    polling_interval = system_cfg.get("polling_interval_seconds", 2.0)

    logger.info("🎯 [HFT_ML4T] System live and entering event loop.")

    try:
        while _running:
            loop_start = time.time()
            now_calibrated_utc = get_calibrated_utc()

            acc = mt5_bridge.get_account_info()
            if not acc:
                logger.warning("[HFT_ML4T] Failed to retrieve account telemetry from MT5 bridge.")
                time.sleep(polling_interval)
                continue

            open_pos_all = mt5_bridge.get_open_positions()

            # -------------------------------------------------------------
            # 1. POSITION MANAGEMENT & IN-FLIGHT BARRIERS (Stage A & Stage B)
            # -------------------------------------------------------------
            for p in open_pos_all:
                sym_upper = p.symbol.upper()
                if sym_upper not in ("XAUUSDM", "USOILM"):
                    continue

                pos_age_min = (time.time() - p.time) / 60.0
                action = "BUY" if p.type == 0 else "SELL"

                # Get M15 ATR for dynamic barrier calculation
                m15_rates = mt5_bridge.get_rates_df(p.symbol, timeframe="M15", count=25)
                current_atr = 2.0 if "XAU" in sym_upper else 0.35
                if m15_rates is not None and len(m15_rates) >= 15:
                    hl = m15_rates["high"] - m15_rates["low"]
                    hc = (m15_rates["high"] - m15_rates["close"].shift(1)).abs()
                    lc = (m15_rates["low"] - m15_rates["close"].shift(1)).abs()
                    current_atr = float(pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean().iloc[-2])

                new_sl, barrier_reason = execution_manager.evaluate_in_flight_barriers(
                    symbol=p.symbol,
                    action=action,
                    entry_price=p.price_open,
                    current_price=p.price_current,
                    current_sl=p.sl,
                    initial_sl=p.sl,
                    holding_minutes=pos_age_min,
                    atr_14=current_atr
                )

                if new_sl is not None:
                    logger.info(
                        f"🛡️ [BARRIER ENGAGED] Ticket #{p.ticket} {p.symbol} {action} | "
                        f"Moving SL from {p.sl:.3f} to {new_sl:.3f} | Reason: {barrier_reason}"
                    )
                    mt5_bridge.modify_position_sl(p, new_sl)

            # -------------------------------------------------------------
            # 2. PERIODIC HEARTBEAT TELEMETRY (Every 60s)
            # -------------------------------------------------------------
            if loop_start - last_status_print >= 60.0:
                last_status_print = loop_start
                logger.info(
                    f"💓 [HEARTBEAT] Real UTC: {format_real_utc_log(now_calibrated_utc)} | "
                    f"Equity: ${acc['equity']:,.2f} | Margin Level: {acc.get('margin_level', 0):.1f}% | "
                    f"Open Positions: {len(open_pos_all)} | News Shield: ACTIVE | Mode: LIVE"
                )

            # -------------------------------------------------------------
            # 3. ALPHA GENERATION & DECOUPLED RISK EXECUTION
            # -------------------------------------------------------------
            for sym, strat_engine in strategies.items():
                if not _running:
                    break

                now_ts = time.time()
                # Anti-duplicate lock (< 5s)
                if now_ts < inflight_order_lock.get(sym, 0.0):
                    continue

                snapshot = mt5_bridge.get_market_snapshot(sym)
                if not snapshot:
                    continue

                # Max 1 concurrent position per symbol
                sym_positions = [p for p in open_pos_all if p.symbol == sym]
                if len(sym_positions) >= 1:
                    continue

                # Ingestion: Fetch closed M15 and H1 bars
                rates_m15 = mt5_bridge.get_rates_df(sym, timeframe="M15", count=105)
                rates_h1 = mt5_bridge.get_rates_df(sym, timeframe="H1", count=220)
                if rates_m15 is None or len(rates_m15) < 50 or rates_h1 is None or len(rates_h1) < 55:
                    continue

                clean_m15, m15_features = data_ingestion.prepare_closed_series(rates_m15)
                clean_h1, _ = data_ingestion.prepare_closed_series(rates_h1)

                # Tier 2: Pure Strategy Signal Generation
                if sym == "XAUUSDm":
                    ah, al, _ = data_ingestion.extract_asian_range(rates_m15)
                    signal = strat_engine.evaluate(
                        closed_m15_df=clean_m15,
                        features=m15_features,
                        asian_high=ah,
                        asian_low=al,
                        now_utc=now_calibrated_utc
                    )
                elif sym == "USOILm":
                    signal = strat_engine.evaluate(
                        closed_m15_df=clean_m15,
                        features=m15_features,
                        h1_df=clean_h1,
                        now_utc=now_calibrated_utc
                    )
                else:
                    signal = None

                if signal and signal.action:
                    # Tier 3: Decoupled Execution & Risk Desk Gating
                    sym_info = mt5_bridge.get_symbol_info(sym)
                    contract_size = sym_info.trade_contract_size if sym_info else 100.0

                    trade_instr, exec_reason = execution_manager.process_signal(
                        signal=signal,
                        account_equity=acc["equity"],
                        market_snapshot=snapshot,
                        features=m15_features,
                        contract_size=contract_size,
                        now_utc=now_calibrated_utc
                    )

                    if trade_instr:
                        inflight_order_lock[sym] = now_ts + DUPLICATE_GUARD_SEC
                        logger.info(
                            f"⚡ [EXEC_APPROVED] {sym} -> {trade_instr.action} {trade_instr.volume} lots | "
                            f"SL: {trade_instr.sl_price:.3f} | TP: {trade_instr.tp_price:.3f} | "
                            f"Risk: ${trade_instr.risk_usd:.2f} (1R) | Reason: {exec_reason}"
                        )
                        success, msg, ticket = mt5_bridge.send_order(
                            symbol=trade_instr.symbol,
                            order_type=trade_instr.action,
                            lot=trade_instr.volume,
                            sl_price=trade_instr.sl_price,
                            tp_price=trade_instr.tp_price,
                            magic=trade_instr.magic,
                            comment=trade_instr.comment,
                            expected_price=snapshot.get("mid", 0.0)
                        )
                        if success:
                            logger.info(f"✅ [ORDER_FILLED] Ticket #{ticket} {sym} {trade_instr.action} {trade_instr.volume} lots @ {snapshot.get('mid', 0.0)}")
                        else:
                            logger.error(f"❌ [ORDER_REJECTED] {sym} {trade_instr.action} Failed: {msg}")
                    else:
                        logger.debug(f"🛡️ [RISK_VETO] {sym} signal vetoed: {exec_reason}")

            elapsed = time.time() - loop_start
            sleep_time = max(0.1, polling_interval - elapsed)
            time.sleep(sleep_time)

    except Exception as e:
        logger.critical(f"🛑 [FATAL CRASH] Unhandled exception in main loop: {e}", exc_info=True)
    finally:
        mt5_bridge.shutdown()
        release_process_lock()
        logger.info("🏁 [HFT_ML4T] Process shutdown complete.")

if __name__ == "__main__":
    main()
