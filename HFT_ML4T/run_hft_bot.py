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
from dotenv import load_dotenv

# Path setup
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.audit_logger import setup_logger, get_logger, log_trade_audit
from core.central_risk_desk import CentralRiskDesk
from core.mt5_bridge import MT5Bridge
from strategies.gold_micro_scalper import GoldMicroScalperStrategy
from strategies.fx_micro_arbitrage import FXMicroArbitrageStrategy
from strategies.crypto_micro_scalper import CryptoMicroScalperStrategy
from strategies.commodity_oil_scalper import OilMicroScalperStrategy
from strategies.index_micro_scalper import IndexMicroScalperStrategy

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
        post_sl_cooldown_seconds=risk_cfg.get("post_sl_cooldown_seconds", 240.0)
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

    poll_interval = system_cfg.get("polling_interval_seconds", 2.0)
    enable_breakeven = risk_cfg.get("enable_breakeven_guard", True)
    breakeven_ratio = risk_cfg.get("breakeven_trigger_ratio", 0.50)
    tracked_positions = {}  # ticket -> (symbol, open_price, type, magic)
    last_status_print = 0.0

    logger.info("⚡ HFT_ML4T Engine running loop started. Press Ctrl+C to terminate.")

    # Main Trading Loop
    while _running:
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
                sym_closed, open_px, p_type, magic_closed = tracked_positions.pop(t)
                try:
                    import MetaTrader5 as mt5_raw
                    deal_history = mt5_raw.history_deals_get(position=t)
                    if deal_history:
                        exit_deal = [d for d in deal_history if d.entry == 1]
                        if exit_deal:
                            d_profit = exit_deal[0].profit + exit_deal[0].swap + exit_deal[0].commission
                            if d_profit < 0 or "[sl " in exit_deal[0].comment.lower():
                                risk_desk.trigger_cooldown(
                                    sym_closed,
                                    reason=f"Position #{t} closed at loss/SL: ${d_profit:+.2f} ({exit_deal[0].comment})"
                                )
                except Exception as e:
                    logger.debug(f"Error checking closed deal #{t}: {e}")

            # B. Apply Breakeven Guard on active open positions
            for p in open_pos_all:
                if p.ticket not in tracked_positions:
                    tracked_positions[p.ticket] = (p.symbol, p.price_open, p.type, p.magic)

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
                        buffer_pts = max(p_point * 25, 0.25)   # >= $0.25 buffer for Gold
                    elif "OIL" in sym_upper:
                        buffer_pts = max(p_point * 25, 0.05)   # >= $0.05 buffer for Crude Oil
                    else:
                        buffer_pts = p_point * 20              # 2.0 pips buffer for FX

                    tp_dist = abs(p.tp - p.price_open)
                    profit_dist = (p.price_current - p.price_open) if p.type == 0 else (p.price_open - p.price_current)
                    
                    # Nautilus Time-Barrier Exit (Alpha Decay after 4 hours / 16 bars M15)
                    pos_age_sec = time.time() - p.time
                    if pos_age_sec >= (16 * 15 * 60):
                        logger.info(f"⏳ [TIME-BARRIER] Closing Ticket #{p.ticket} {p.symbol} after {pos_age_sec/3600:.1f}h (Alpha Decay Horizon)")
                        mt5_bridge.close_position(p, comment="TIME_BARRIER")
                        continue

                    # Nautilus Two-Tier Profit Locking Ladder
                    if p.type == 0:  # BUY
                        if tp_dist > 0:
                            # Tier 2: Lock 50% TP when gain reaches 75% TP
                            if profit_dist >= tp_dist * 0.75:
                                target_sl = p.price_open + (tp_dist * 0.50)
                                if p.sl < target_sl:
                                    mt5_bridge.modify_position_sl(p, target_sl)
                            # Tier 1: Lock 25% TP when gain reaches 50% TP
                            elif profit_dist >= tp_dist * 0.50:
                                target_sl = p.price_open + (tp_dist * 0.25)
                                if p.sl < target_sl:
                                    mt5_bridge.modify_position_sl(p, target_sl)

                    elif p.type == 1:  # SELL
                        if tp_dist > 0:
                            # Tier 2: Lock 50% TP when gain reaches 75% TP
                            if profit_dist >= tp_dist * 0.75:
                                target_sl = p.price_open - (tp_dist * 0.50)
                                if p.sl > target_sl or p.sl == 0:
                                    mt5_bridge.modify_position_sl(p, target_sl)
                            # Tier 1: Lock 25% TP when gain reaches 50% TP
                            elif profit_dist >= tp_dist * 0.50:
                                target_sl = p.price_open - (tp_dist * 0.25)
                                if p.sl > target_sl or p.sl == 0:
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
                rates_df = mt5_bridge.get_rates_df(sym, timeframe=strat.config.get("timeframe", "M15"), count=100)
                if rates_df is None:
                    continue

                sym_info = mt5_bridge.get_symbol_info(sym)
                contract_size = sym_info.trade_contract_size if sym_info else 100.0
                min_lot = sym_info.volume_min if sym_info else 0.01
                lot_step = sym_info.volume_step if sym_info else 0.01

                # Evaluate strategy with Nautilus De-risking Multiplier
                risk_mult = risk_desk.get_risk_multiplier(acc["equity"])
                if risk_mult <= 0:
                    continue

                signal_res = strat.evaluate(
                    rates_df=rates_df,
                    market_snapshot=snapshot,
                    current_inventory=net_inventory,
                    account_equity=acc["equity"],
                    contract_size=contract_size,
                    min_lot=min_lot,
                    lot_step=lot_step,
                    risk_multiplier=risk_mult
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
                        # Real money order dispatch
                        success, msg, ticket = mt5_bridge.send_order(
                            symbol=sym,
                            order_type=action,
                            lot=lot,
                            sl_price=sl,
                            tp_price=tp,
                            magic=magic,
                            comment=comment
                        )
                        signal_res["execution_status"] = "FILLED" if success else "FAILED"
                        signal_res["order_ticket"] = ticket
                        signal_res["error_message"] = msg
                        if not success:
                            logger.warning(f"⚠️ [ORDER REJECTED BY BROKER/MT5] {sym}: {msg}")
                    else:
                        logger.info(f"🛡️ [PAPER TRADE ONLY] Order suppressed because LIVE_TRADING=false")
                        signal_res["execution_status"] = "PAPER_SIMULATED"
                        signal_res["order_ticket"] = None

                    # Audit Record Logging
                    log_trade_audit(str(_ROOT / "logs"), signal_res)

            elapsed = time.time() - loop_start
            sleep_time = max(0.1, poll_interval - elapsed)
            time.sleep(sleep_time)

        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            time.sleep(3.0)

    # Clean shutdown
    mt5_bridge.shutdown()
    logger.info("✅ HFT_ML4T shutdown completed.")


if __name__ == "__main__":
    main()
