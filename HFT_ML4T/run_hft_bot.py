"""
========================================================================================
HFT_ML4T — MASTER PRODUCTION RUNNER
Institutional High-Frequency Trading & Market Microstructure System.
Supports Real-Money Live Trading with Central Risk Desk (CRO) Protection.
========================================================================================
"""

import os
import sys
import time
import signal
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from datetime import datetime, timezone
import yaml
import pandas as pd
from dotenv import load_dotenv

# Path setup
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.audit_logger import setup_logger, get_logger, log_trade_audit, flush_execution_audit
from core.central_risk_desk import CentralRiskDesk
from core.mt5_bridge import MT5Bridge
from strategies.gold_micro_scalper import GoldMicroScalperStrategy
from strategies.fx_micro_arbitrage import FXMicroArbitrageStrategy
from strategies.crypto_micro_scalper import CryptoMicroScalperStrategy
from strategies.commodity_oil_scalper import OilMicroScalperStrategy
from strategies.index_micro_scalper import IndexMicroScalperStrategy
from engines.ml4t_data_pipeline import ParquetFeatureCollector

# Load environment & config
load_dotenv(_ROOT / ".env")
CONFIG_PATH = _ROOT / "config" / "hft_config.yaml"

if not CONFIG_PATH.exists():
    raise FileNotFoundError(f"Configuration file not found: {CONFIG_PATH}")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

system_cfg = config.get("system", {})
risk_cfg = config.get("risk_desk", {})
symbols_cfg = config.get("symbols", [])

logger = setup_logger(
    log_dir=str(_ROOT / system_cfg.get("log_dir", "logs")),
    log_level=system_cfg.get("log_level", "INFO")
)

_running = True


def _handle_exit(sig, frame):
    global _running
    logger.info("🛑 Exit signal received. Safely stopping HFT_ML4T...")
    _running = False


signal.signal(signal.SIGINT, _handle_exit)
signal.signal(signal.SIGTERM, _handle_exit)


def main():
    global _running

    live_trading_env = os.getenv("LIVE_TRADING", "false").lower() in ("true", "1", "yes")

    print("\n" + "=" * 78)
    print("  🚀 HFT_ML4T — PRODUCTION TRADING SYSTEM")
    print("  Algorithm: Avellaneda-Stoikov Microstructure & OFI + ML4T Gatekeeper")
    if live_trading_env:
        print("  ⚠️  EXECUTION MODE: 🔴 LIVE TRADING (TIỀN THẬT / REAL MONEY)")
    else:
        print("  ℹ️  EXECUTION MODE: 🟡 PAPER / SHADOW DRY-RUN (An toàn không rủi ro)")
    print("=" * 78 + "\n")

    # 1. Initialize MT5 Bridge
    mt5_bridge = MT5Bridge(
        terminal_path=os.getenv("MT5_PATH", ""),
        account=int(os.getenv("MT5_ACCOUNT", "0")),
        password=os.getenv("MT5_PASSWORD", ""),
        server=os.getenv("MT5_SERVER", "")
    )

    if not mt5_bridge.initialize():
        logger.error("Failed to connect to MetaTrader 5. Please verify MT5 is installed and credentials in .env are correct.")
        sys.exit(1)

    acc = mt5_bridge.get_account_info()
    if not acc:
        logger.error("Could not fetch account information.")
        sys.exit(1)

    # Ensure symbols are visible in Market Watch (resilience against broker maintenance/holidays)
    enabled_symbols = [s.get("name") for s in symbols_cfg if s.get("enabled", False)]
    mt5_bridge.ensure_symbols_visible(enabled_symbols)

    # 2. Real Account Verification Warning
    is_real = acc.get("is_real", False)
    if is_real and live_trading_env:
        logger.critical(
            f"🚨 CONFIRMED LIVE REAL ACCOUNT (#{acc['login']} on {acc['server']}). "
            f"REAL FUNDS AT RISK: Balance ${acc['balance']:,.2f} | Equity ${acc['equity']:,.2f}"
        )
    elif live_trading_env and not is_real:
        logger.warning(
            f"ℹ️ LIVE_TRADING is true, but connected account #{acc['login']} is DEMO/TRIAL. Orders will be demo."
        )

    # 3. Initialize Central Risk Desk
    risk_desk = CentralRiskDesk(
        max_daily_drawdown_usd=risk_cfg.get("max_daily_drawdown_usd", 300.0),
        max_daily_drawdown_pct=risk_cfg.get("max_daily_drawdown_pct", 0.05),
        warning_drawdown_pct=risk_cfg.get("warning_drawdown_pct", 0.025),
        min_margin_level_percent=risk_cfg.get("min_margin_level_percent", 300.0),
        max_total_open_positions=risk_cfg.get("max_total_open_positions", 4),
        max_positions_per_symbol=risk_cfg.get("max_positions_per_symbol", 1),
        rollover_curfew_utc=tuple(risk_cfg.get("rollover_curfew_utc", ["21:45", "22:30"])),
        halt_file=str(_ROOT / "HALT_HFT"),
        post_sl_cooldown_seconds=risk_cfg.get("post_sl_cooldown_seconds", 300.0),
        max_daily_loss_per_symbol_usd=risk_cfg.get("max_daily_loss_per_symbol_usd", 80.0),
        consecutive_loss_cooldowns=tuple(risk_cfg.get("consecutive_loss_cooldowns", [300, 2700, -1])),
        max_trailing_drawdown_pct=risk_cfg.get("max_trailing_drawdown_pct", 0.08),
        max_positions_per_cluster=risk_cfg.get("max_positions_per_cluster", 2),
        auto_write_halt_file=risk_cfg.get("auto_write_halt_file", True)
    )
    risk_desk.update_account_state(acc)

    # 4. Instantiate Strategies
    strategies = {}
    for s_cfg in symbols_cfg:
        if not s_cfg.get("enabled", False):
            continue
        sym = s_cfg.get("name")
        stype = s_cfg.get("strategy_type", "fx")
        if stype == "gold":
            strategies[sym] = GoldMicroScalperStrategy(s_cfg)
        elif stype == "crypto":
            strategies[sym] = CryptoMicroScalperStrategy(s_cfg)
        elif stype == "oil":
            strategies[sym] = OilMicroScalperStrategy(s_cfg)
        elif stype == "index":
            strategies[sym] = IndexMicroScalperStrategy(s_cfg)
        else:
            strategies[sym] = FXMicroArbitrageStrategy(s_cfg)
        logger.info(f"Loaded Strategy [{stype.upper()}] for {sym} (Magic: {s_cfg.get('magic')})")

    # 4.5 Machine Learning Parquet Feature Collector
    feature_collector = ParquetFeatureCollector(
        output_dir=str(_ROOT / "data" / "features"),
        flush_threshold=100
    )

    poll_interval = system_cfg.get("polling_interval_seconds", 2.0)
    enable_breakeven = risk_cfg.get("enable_breakeven_guard", True)
    breakeven_ratio = risk_cfg.get("breakeven_trigger_ratio", 0.50)
    enable_profit_ladder = risk_cfg.get("enable_profit_ladder", True)
    global_ladder_cfg = risk_cfg.get("profit_ladder", {})
    last_close_attempts = {}  # ticket -> last_attempt_ts
    tracked_positions = {}  # ticket -> (symbol, open_price, type, magic)
    last_status_print = 0.0

    logger.info("⚡ HFT_ML4T Engine running loop started. Press Ctrl+C to terminate.")

    # Main Trading Loop
    while _running:
        # Check Zero-Downtime Graceful Hot-Reload Trigger (RESTART_NOW)
        restart_file = _ROOT / "RESTART_NOW"
        if restart_file.exists():
            logger.info("🔄 [HOT-RELOAD] Detected 'RESTART_NOW' signal file. Initiating zero-downtime graceful shutdown...")
            try:
                cancelled = mt5_bridge.cancel_all_pending_orders()
                logger.info(f"🚫 [HOT-RELOAD] Cleaned up {cancelled} pending order(s).")
            except Exception as e_pend:
                logger.error(f"[HOT-RELOAD] Error cancelling pending orders: {e_pend}")

            try:
                feature_collector.close()
                flush_execution_audit(system_cfg.get("log_dir", "logs"))
                logger.info("💾 [HOT-RELOAD] ML feature collector & execution audit flushed to disk.")
            except Exception as e_fl:
                logger.error(f"[HOT-RELOAD] Error flushing features: {e_fl}")

            try:
                mt5_bridge.shutdown()
                logger.info("🔒 [HOT-RELOAD] MT5 connection cleanly disconnected.")
            except Exception as e_shut:
                logger.error(f"[HOT-RELOAD] Error during MT5 shutdown: {e_shut}")

            try:
                if restart_file.exists():
                    restart_file.unlink()
                    logger.info("🗑️ [HOT-RELOAD] Removed 'RESTART_NOW' signal file.")
            except Exception as e_unl:
                logger.error(f"[HOT-RELOAD] Error removing RESTART_NOW file: {e_unl}")

            logger.info("🚀 [HOT-RELOAD] Shutdown complete. Handing over to Watchdog/Supervisor for instant restart.")
            sys.exit(42)

        try:
            loop_start = time.time()
            acc = mt5_bridge.get_account_info()
            if not acc:
                time.sleep(poll_interval)
                continue

            risk_desk.update_account_state(acc)

            # Get open positions once per loop
            open_pos_all = mt5_bridge.get_open_positions()
            current_tickets = {p.ticket: p for p in open_pos_all}

            # A. Detect closed tickets to trigger Cooldown on SL/loss (Whipsaw protection)
            closed_tickets = [t for t in list(tracked_positions.keys()) if t not in current_tickets]
            for t in closed_tickets:
                pos_data = tracked_positions.pop(t)
                if isinstance(pos_data, dict):
                    sym_closed = pos_data.get("symbol", "")
                    open_px = pos_data.get("open_price", 0.0)
                    p_type = pos_data.get("type", 0)
                    magic_closed = pos_data.get("magic", 0)
                else:
                    sym_closed, open_px, p_type, magic_closed = pos_data[:4]

                try:
                    import MetaTrader5 as mt5_raw
                    deal_history = mt5_raw.history_deals_get(position=t)
                    if deal_history:
                        exit_deal = [d for d in deal_history if d.entry == 1]
                        if exit_deal:
                            d_profit = exit_deal[0].profit + exit_deal[0].swap + exit_deal[0].commission
                            risk_desk.record_trade_result(
                                symbol=sym_closed,
                                profit=d_profit,
                                comment=exit_deal[0].comment
                            )
                except Exception as e:
                    logger.debug(f"Error checking closed deal #{t}: {e}")

            # B. Apply Breakeven Guard & Dynamic ATR Trailing Stop on active open positions
            for p in open_pos_all:
                if p.ticket not in tracked_positions:
                    tracked_positions[p.ticket] = {
                        "symbol": p.symbol,
                        "open_price": p.price_open,
                        "type": p.type,
                        "magic": p.magic,
                        "highest_high": p.price_current,
                        "lowest_low": p.price_current
                    }

                pos_meta = tracked_positions[p.ticket]
                if isinstance(pos_meta, tuple):  # compatibility
                    pos_meta = {
                        "symbol": pos_meta[0],
                        "open_price": pos_meta[1],
                        "type": pos_meta[2],
                        "magic": pos_meta[3],
                        "highest_high": p.price_current,
                        "lowest_low": p.price_current
                    }
                    tracked_positions[p.ticket] = pos_meta

                # Update extreme running price
                if p.type == 0:  # BUY
                    pos_meta["highest_high"] = max(pos_meta.get("highest_high", p.price_current), p.price_current)
                else:  # SELL
                    pos_meta["lowest_low"] = min(pos_meta.get("lowest_low", p.price_current), p.price_current)

                if enable_breakeven and p.magic in [s.magic for s in strategies.values()]:
                    s_info = mt5_bridge.get_symbol_info(p.symbol)
                    p_point = s_info.point if s_info else 0.00001
                    sym_upper = p.symbol.upper()
                    # Institutional Asset-Aware Breakeven Buffer (Prevents micro-spread stop-outs)
                    if "BTC" in sym_upper:
                        buffer_pts = max(p_point * 500, 5.0)   # >= $5.0 buffer for Bitcoin
                    elif "US30" in sym_upper:
                        buffer_pts = max(p_point * 50, 5.0)    # >= 5.0 index pts for Dow Jones
                    elif "XAU" in sym_upper:
                        buffer_pts = max(p_point * 65, 0.65)   # >= $0.65 buffer for Gold (widened from 0.25 to prevent noise stop-outs)
                    elif "OIL" in sym_upper:
                        buffer_pts = max(p_point * 25, 0.05)   # >= $0.05 buffer for Crude Oil
                    else:
                        buffer_pts = p_point * 20              # 2.0 pips buffer for FX

                    tp_dist = abs(p.tp - p.price_open)
                    profit_dist = (p.price_current - p.price_open) if p.type == 0 else (p.price_open - p.price_current)
                    
                    # Nautilus Time-Barrier Exit (Alpha Decay after 4 hours / 16 bars M15)
                    pos_age_sec = time.time() - p.time
                    if pos_age_sec >= (16 * 15 * 60):
                        now_ts = time.time()
                        if now_ts - last_close_attempts.get(p.ticket, 0) >= 300:  # retry every 5m if market closed
                            last_close_attempts[p.ticket] = now_ts
                            logger.info(f"⏳ [TIME-BARRIER] Closing Ticket #{p.ticket} {p.symbol} after {pos_age_sec/3600:.1f}h (Alpha Decay Horizon)")
                            closed_ok, close_msg = mt5_bridge.close_position(p, comment="TIME_BARRIER")
                            if not closed_ok and ("10018" in str(close_msg) or "closed" in str(close_msg).lower()):
                                logger.info(f"⏸️ [MARKET_CLOSED] Ticket #{p.ticket} {p.symbol} will auto-close when market opens.")
                        continue

                    # Tier 1: Dynamic ATR Trailing Stop with Guaranteed Breakeven Floor
                    trailing_cfg = risk_cfg.get("trailing_stop", {})
                    if trailing_cfg.get("enabled", True) and tp_dist > 0:
                        # Quick ATR calculation from recent bars
                        rates_recent = mt5_bridge.get_rates_df(p.symbol, timeframe="M15", count=20)
                        if rates_recent is not None and len(rates_recent) >= 14:
                            hl = rates_recent["high"] - rates_recent["low"]
                            hc = (rates_recent["high"] - rates_recent["close"].shift(1)).abs()
                            lc = (rates_recent["low"] - rates_recent["close"].shift(1)).abs()
                            current_atr = float(pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean().iloc[-1])
                        else:
                            current_atr = buffer_pts * 2.0

                        if "XAU" in sym_upper:
                            atr_mult = 2.2  # Broadened to 2.2x ATR to give Gold trend breathing room
                        else:
                            atr_mult = trailing_cfg.get("atr_multiplier", 1.5)
                        min_gain_ratio = trailing_cfg.get("min_gain_ratio", 0.60)

                        if p.type == 0:  # BUY
                            if profit_dist >= max(current_atr * 1.5, tp_dist * min_gain_ratio):
                                be_sl = p.price_open + buffer_pts
                                dyn_sl = pos_meta["highest_high"] - (atr_mult * current_atr)
                                target_sl = max(be_sl, dyn_sl)
                                if p.sl < target_sl:
                                    logger.info(f"🎯 [ATR TRAILING] Ticket #{p.ticket} {p.symbol} BUY: Moving SL from {p.sl:.5f} to {target_sl:.5f}")
                                    mt5_bridge.modify_position_sl(p, target_sl)

                        elif p.type == 1:  # SELL
                            if profit_dist >= max(current_atr * 1.5, tp_dist * min_gain_ratio):
                                be_sl = p.price_open - buffer_pts
                                dyn_sl = pos_meta["lowest_low"] + (atr_mult * current_atr)
                                target_sl = min(be_sl, dyn_sl)
                                if p.sl > target_sl or p.sl == 0:
                                    logger.info(f"🎯 [ATR TRAILING] Ticket #{p.ticket} {p.symbol} SELL: Moving SL from {p.sl:.5f} to {target_sl:.5f}")
                                    mt5_bridge.modify_position_sl(p, target_sl)

            # Periodic heartbeat telemetry print (every 60s)
            if loop_start - last_status_print >= 60.0:
                last_status_print = loop_start
                logger.info(
                    f"💓 [HEARTBEAT] Equity: ${acc['equity']:,.2f} | Margin Level: {acc.get('margin_level', 0):.1f}% | "
                    f"Open Positions: {len(open_pos_all)} | Mode: {'LIVE' if live_trading_env else 'PAPER'}"
                )

            # Evaluate each symbol
            for sym, strat in strategies.items():
                if not _running:
                    break

                snapshot = mt5_bridge.get_market_snapshot(sym)
                if not snapshot:
                    continue

                # Market freshness / Weekend check: Skip traditional assets if market is closed (ticks older than 180s)
                tick_age = loop_start - snapshot.get("time", 0)
                if tick_age > 180 and "BTC" not in sym.upper():
                    continue

                # Trading Session Gate for US30m (US Cash Session: 13:30 - 20:30 UTC)
                if "US30" in sym.upper():
                    now_utc_dt = datetime.now(timezone.utc)
                    hm_str = now_utc_dt.strftime("%H:%M")
                    if not ("13:30" <= hm_str <= "20:30"):
                        continue

                sym_positions = [p for p in open_pos_all if p.symbol == sym and p.magic == strat.magic]

                # Current net inventory
                net_inventory = 0.0
                for p in sym_positions:
                    net_inventory += p.volume if p.type == 0 else -p.volume

                # Pre-trade Risk Audit
                is_safe, risk_reason = risk_desk.check_pre_trade_safety(
                    symbol=sym,
                    current_spread_points=snapshot["spread_points"],
                    max_allowed_spread_points=strat.max_spread_points,
                    open_positions=open_pos_all,
                    account_info=acc
                )

                if not is_safe:
                    continue

                # Fetch candle history
                # Fetch candle history (M15 execution + H1 Macro Trend)
                rates_df = mt5_bridge.get_rates_df(sym, timeframe=strat.config.get("timeframe", "M15"), count=100)
                if rates_df is None:
                    continue
                rates_h1 = mt5_bridge.get_rates_df(sym, timeframe="H1", count=250)

                sym_info = mt5_bridge.get_symbol_info(sym)
                contract_size = sym_info.trade_contract_size if sym_info else 100.0
                min_lot = sym_info.volume_min if sym_info else 0.01
                lot_step = sym_info.volume_step if sym_info else 0.01

                # Evaluate strategy with Nautilus De-risking Multiplier & Tier 1 Pod Recovery Sizing
                risk_mult = risk_desk.get_risk_multiplier(acc["equity"])
                pod_mult = risk_desk.get_symbol_risk_multiplier(sym)
                effective_risk_mult = risk_mult * pod_mult
                if effective_risk_mult <= 0:
                    continue

                signal_res = strat.evaluate(
                    rates_df=rates_df,
                    market_snapshot=snapshot,
                    current_inventory=net_inventory,
                    account_equity=acc["equity"],
                    contract_size=contract_size,
                    min_lot=min_lot,
                    lot_step=lot_step,
                    risk_multiplier=effective_risk_mult,
                    h1_df=rates_h1
                )

                if signal_res:
                    action = signal_res["action"]
                    lot = signal_res["lot"]
                    sl = signal_res["sl_price"]
                    tp = signal_res["tp_price"]
                    magic = signal_res["magic"]
                    comment = signal_res["comment"]

                    logger.info(
                        f"⚡ [SIGNAL] {sym} -> {action} {lot} lots | SL: {sl:.5f} | TP: {tp:.5f} | "
                        f"OFI: {signal_res.get('ofi', 0):.2f} | Vol: {signal_res.get('volatility', 0):.4f}"
                    )

                    if live_trading_env:
                        # Real money order dispatch with expected reservation price telemetry
                        target_exp_price = signal_res.get("reservation_price") or snapshot.get("mid", 0.0)
                        success, msg, ticket = mt5_bridge.send_order(
                            symbol=sym,
                            order_type=action,
                            lot=lot,
                            sl_price=sl,
                            tp_price=tp,
                            magic=magic,
                            comment=comment,
                            expected_price=target_exp_price
                        )
                        signal_res["execution_status"] = "FILLED" if success else "FAILED"
                        signal_res["order_ticket"] = ticket
                        signal_res["error_message"] = msg

                        exec_metrics = mt5_bridge.get_last_execution_metrics()
                        if exec_metrics:
                            signal_res["execution_metrics"] = exec_metrics
                            risk_desk.record_execution_metric(
                                symbol=sym,
                                latency_ms=exec_metrics.get("latency_ms", 0.0),
                                slippage_points=exec_metrics.get("slippage_points", 0.0)
                            )

                        if success:
                            risk_desk.consume_recovery_trade(sym)
                        else:
                            logger.warning(f"⚠️ [ORDER REJECTED BY BROKER/MT5] {sym}: {msg}")
                    else:
                        logger.info(f"🛡️ [PAPER TRADE ONLY] Order suppressed because LIVE_TRADING=false")
                        signal_res["execution_status"] = "PAPER_SIMULATED"
                        signal_res["order_ticket"] = None

                    # Audit Record Logging
                    log_trade_audit(str(_ROOT / "logs"), signal_res)

                    # Machine Learning Parquet Feature Telemetry
                    exec_stats = risk_desk.get_execution_stats(sym)
                    feature_collector.record_feature(
                        symbol=sym,
                        mid_price=snapshot.get("mid", 0.0),
                        spread_points=snapshot.get("spread_points", 0.0),
                        ofi=signal_res.get("ofi", 0.0),
                        garman_klass_vol=signal_res.get("volatility", 0.0),
                        micro_vol=signal_res.get("micro_volatility", signal_res.get("volatility", 0.0)),
                        dynamic_kappa=signal_res.get("dynamic_kappa", 1.5),
                        reservation_price=signal_res.get("reservation_price", snapshot.get("mid", 0.0)),
                        skew_offset=signal_res.get("skew_offset", 0.0),
                        action=action,
                        macro_regime=signal_res.get("macro_regime", "UNKNOWN"),
                        slope_ema21_pct=signal_res.get("slope_ema21_pct", 0.0),
                        recent_slippage_pts=exec_stats.get("avg_slippage_points", 0.0),
                        recent_latency_ms=exec_stats.get("avg_latency_ms", 0.0)
                    )

            elapsed = time.time() - loop_start
            sleep_time = max(0.1, poll_interval - elapsed)
            time.sleep(sleep_time)

        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            time.sleep(3.0)

    # Clean shutdown
    feature_collector.flush()
    mt5_bridge.shutdown()
    logger.info("✅ HFT_ML4T shutdown completed.")


if __name__ == "__main__":
    main()
