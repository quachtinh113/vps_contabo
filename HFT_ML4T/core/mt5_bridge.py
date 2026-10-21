"""
HFT_ML4T — MetaTrader 5 Bridge
High-reliability singleton connection, market data streaming, and order execution gateway.
"""

import os
import time
import math
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    MT5_AVAILABLE = False

from core.audit_logger import get_logger, log_execution_audit

logger = get_logger()

TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1 if MT5_AVAILABLE else 1,
    "M5": mt5.TIMEFRAME_M5 if MT5_AVAILABLE else 5,
    "M15": mt5.TIMEFRAME_M15 if MT5_AVAILABLE else 15,
    "H1": mt5.TIMEFRAME_H1 if MT5_AVAILABLE else 16385,
    "H4": mt5.TIMEFRAME_H4 if MT5_AVAILABLE else 16388,
}

# MQL5 Symbol Filling Policy bitmask constants (not defined in MetaTrader5 Python package)
SYMBOL_FILLING_FOK = 1  # 0x01
SYMBOL_FILLING_IOC = 2  # 0x02
SYMBOL_FILLING_BOC = 4  # 0x04


class MT5Bridge:
    _instance: Optional["MT5Bridge"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(MT5Bridge, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        terminal_path: str = "",
        account: int = 0,
        password: str = "",
        server: str = "",
        mt5_path: str = ""
    ):
        if self._initialized:
            return

        self.terminal_path = terminal_path or mt5_path or os.getenv("MT5_PATH", "")
        self.mt5_path = self.terminal_path
        self.account = int(account or os.getenv("MT5_ACCOUNT", "0"))
        self.password = password or os.getenv("MT5_PASSWORD", "")
        self.server = server or os.getenv("MT5_SERVER", "")
        self.connected = False
        self._last_health_check = 0.0
        self._symbol_cache: Dict[str, Any] = {}
        self.last_execution_metrics: Optional[Dict[str, Any]] = None
        self.log_dir: str = "logs"
        self._initialized = True

    def kill_zombie_terminal(self) -> None:
        """Bắn hạ tiến trình MT5 bị treo (Zombie) trên Windows và giải phóng tài nguyên mạng."""
        logger.warning("🧟 [BRIDGE] Killing zombie MT5 terminal (terminal64.exe)...")
        try:
            import subprocess
            subprocess.run(["taskkill", "/F", "/IM", "terminal64.exe"], capture_output=True, check=False)
        except Exception as e:
            logger.error(f"[BRIDGE] Error executing taskkill via subprocess: {e}")
            os.system("taskkill /F /IM terminal64.exe >nul 2>&1")
        time.sleep(3)  # Đợi hệ điều hành giải phóng cổng mạng & sockets

    def connect_robust(self, max_retries: int = 3) -> bool:
        """Khởi động và ép buộc đăng nhập lại MT5, tự động diệt zombie nếu phát hiện treo hoặc mất kết nối."""
        if not MT5_AVAILABLE:
            logger.error("MetaTrader5 package is not available in current environment.")
            return False

        for attempt in range(1, max_retries + 1):
            logger.info(f"[BRIDGE] Connection attempt {attempt}/{max_retries}...")

            init_kwargs: Dict[str, Any] = {}
            term_path = self.terminal_path or self.mt5_path
            if term_path and os.path.exists(term_path):
                init_kwargs["path"] = term_path
            if self.account:
                init_kwargs["login"] = int(self.account)
            if self.password:
                init_kwargs["password"] = self.password
            if self.server:
                init_kwargs["server"] = self.server
            init_kwargs["timeout"] = 15000

            # Khởi tạo MT5 với chứng chỉ cứng (Hard-auth) để ép đăng nhập lại
            init_result = mt5.initialize(**init_kwargs)

            if not init_result:
                err = mt5.last_error()
                logger.error(f"[BRIDGE] Initialize failed: {err}. Terminal might be corrupt or missing.")
                self.kill_zombie_terminal()
                continue

            # Kiểm tra trạng thái kết nối thực sự tới Server
            terminal_info = mt5.terminal_info()
            if terminal_info is None or not terminal_info.connected:
                logger.warning("[BRIDGE] Terminal running but DISCONNECTED from broker (Holiday/Weekend effect).")
                try:
                    mt5.shutdown()
                except Exception:
                    pass
                self.kill_zombie_terminal()
                continue

            # Kiểm tra xem tài khoản có bị Read-only/Invalid password không
            if not terminal_info.trade_allowed:
                logger.warning("[BRIDGE] WARNING: Terminal connected but Trading is Disabled (Check Investor password / Algo trading).")

            # Đảm bảo account_info khớp với tài khoản yêu cầu
            acc = mt5.account_info()
            if acc is None or (self.account and acc.login != int(self.account)):
                if self.account and self.password and self.server:
                    login_ok = mt5.login(
                        login=int(self.account),
                        password=self.password,
                        server=self.server
                    )
                    if not login_ok:
                        err = mt5.last_error()
                        logger.error(f"[BRIDGE] MT5 login failed for account {self.account} on {self.server}: {err}")
                        self.kill_zombie_terminal()
                        continue
                acc = mt5.account_info()

            if acc is None:
                logger.error("[BRIDGE] Failed to retrieve MT5 account info after login.")
                self.kill_zombie_terminal()
                continue

            ping_val = getattr(terminal_info, "ping_last", 0)
            is_real = (acc.trade_mode == mt5.ACCOUNT_TRADE_MODE_REAL)
            mode_str = "🔴 REAL MONEY (Tiền Thật)" if is_real else "🟡 DEMO / TRIAL"

            logger.info(
                f"✅ [BRIDGE] Successfully connected to {self.server} | Ping: {ping_val} ms | "
                f"Account: #{acc.login} | Mode: {mode_str} | "
                f"Balance: ${acc.balance:,.2f} | Equity: ${acc.equity:,.2f} | Leverage: 1:{acc.leverage}"
            )
            self.connected = True
            return True

        logger.critical("[CRITICAL] Failed to connect to MT5 after multiple hard-resets.")
        self.connected = False
        return False

    def initialize(self) -> bool:
        """Connects to MT5 terminal and verifies account authentication (via connect_robust)."""
        return self.connect_robust(max_retries=3)

    def ensure_symbols_visible(self, symbols_list: List[str]) -> None:
        """Buộc MT5 hiển thị lại các cặp tài sản trong Market Watch (tránh bị ẩn sau bảo trì Exness)."""
        if not self.ensure_connected() or not MT5_AVAILABLE:
            return
        for sym in symbols_list:
            resolved = self.resolve_symbol(sym)
            if not mt5.symbol_select(resolved, True):
                err = mt5.last_error()
                logger.warning(f"[BRIDGE] Failed to add {resolved} (requested {sym}) to Market Watch: {err}")
            else:
                logger.debug(f"[BRIDGE] Symbol {resolved} selected and visible in Market Watch.")

    def cancel_all_pending_orders(self, magic: Optional[int] = None, symbol: Optional[str] = None) -> int:
        """Hủy các lệnh Pending chưa khớp khi shutdown bot để tránh kẹt lệnh."""
        if not self.ensure_connected() or not MT5_AVAILABLE:
            return 0

        orders = mt5.orders_get()
        if orders is None or len(orders) == 0:
            return 0

        cancelled_count = 0
        for o in orders:
            if magic is not None and o.magic != magic:
                continue
            if symbol is not None and o.symbol != symbol:
                continue

            req = {
                "action": mt5.TRADE_ACTION_REMOVE,
                "order": o.ticket,
            }
            res = mt5.order_send(req)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"🚫 [CANCELLED PENDING] Order #{o.ticket} {o.symbol} cancelled successfully.")
                cancelled_count += 1
            else:
                comment = res.comment if res else str(mt5.last_error())
                logger.warning(f"⚠️ Failed to cancel pending order #{o.ticket}: {comment}")

        return cancelled_count

    def get_account_info(self) -> Dict[str, Any]:
        """Returns normalized account status dictionary."""
        if not self.ensure_connected():
            return {}
        acc = mt5.account_info()
        if acc is None:
            return {}
        return {
            "login": acc.login,
            "server": acc.server,
            "balance": acc.balance,
            "equity": acc.equity,
            "margin": acc.margin,
            "free_margin": acc.margin_free,
            "margin_level": acc.margin_level,
            "currency": acc.currency,
            "is_real": (acc.trade_mode == mt5.ACCOUNT_TRADE_MODE_REAL),
        }

    def ensure_connected(self) -> bool:
        """Periodic heartbeat and auto-reconnect."""
        now = time.time()
        if now - self._last_health_check < 3.0:
            return self.connected

        self._last_health_check = now
        if not MT5_AVAILABLE:
            return False

        term = mt5.terminal_info()
        if term is None or not term.connected:
            logger.warning("[MT5] Heartbeat disconnected (Holiday/Maintenance/Zombie). Invoking robust reconnection...")
            self.connected = False
            return self.connect_robust(max_retries=2)

        self.connected = True
        return True

    def resolve_symbol(self, symbol: str) -> str:
        """Finds the actual broker symbol name (e.g. XAUUSDm vs XAUUSD)."""
        if not self.ensure_connected() or not MT5_AVAILABLE:
            return symbol
        if mt5.symbol_info(symbol) is not None:
            return symbol
        if symbol.endswith("m") and mt5.symbol_info(symbol[:-1]) is not None:
            return symbol[:-1]
        if not symbol.endswith("m") and mt5.symbol_info(symbol + "m") is not None:
            return symbol + "m"
        return symbol

    def get_symbol_info(self, symbol: str) -> Optional[Any]:
        """Retrieves and caches symbol specification with auto broker suffix resolution."""
        if not self.ensure_connected():
            return None
        sym = self.resolve_symbol(symbol)
        info = mt5.symbol_info(sym)
        if info is None or not getattr(info, "visible", True):
            mt5.symbol_select(sym, True)
            info = mt5.symbol_info(sym)
        return info

    def get_market_snapshot(self, symbol: str) -> Optional[Dict[str, float]]:
        """Returns live bid, ask, and spread in points."""
        if not self.ensure_connected():
            return None
        sym = self.resolve_symbol(symbol)
        info = self.get_symbol_info(sym)
        if info is None:
            return None
        tick = mt5.symbol_info_tick(sym)
        if tick is None:
            return None
        point = info.point if info else 0.00001
        spread_pts = (tick.ask - tick.bid) / point if point > 0 else 0.0
        return {
            "bid": tick.bid,
            "ask": tick.ask,
            "mid": (tick.bid + tick.ask) / 2.0,
            "spread_points": spread_pts,
            "volume": getattr(tick, "volume", 0),
            "time": tick.time
        }

    def get_rates_df(self, symbol: str, timeframe: str = "M15", count: int = 100) -> Optional[pd.DataFrame]:
        """Fetches OHLCV candlestick DataFrame with auto symbol resolution."""
        if not self.ensure_connected():
            return None
        sym = self.resolve_symbol(symbol)
        self.get_symbol_info(sym)  # Ensure selected in Market Watch
        tf = TIMEFRAME_MAP.get(timeframe, mt5.TIMEFRAME_M15)
        rates = mt5.copy_rates_from_pos(sym, tf, 0, count)
        if rates is None or len(rates) == 0:
            return None
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        return df

    def get_open_positions(self, magic: Optional[int] = None, symbol: Optional[str] = None) -> List[Any]:
        """Retrieves active positions filtered by magic or symbol."""
        if not self.ensure_connected():
            return []
        if symbol:
            pos = mt5.positions_get(symbol=symbol)
        else:
            pos = mt5.positions_get()
        if pos is None:
            return []
        if magic is not None:
            return [p for p in pos if p.magic == magic]
        return list(pos)

    def _resolve_filling_mode(self, info: Any) -> int:
        """Determines the optimal broker filling mode (IOC, FOK, RETURN) based on symbol policy."""
        if not MT5_AVAILABLE or info is None:
            return 1  # ORDER_FILLING_IOC
        fill_flags = getattr(info, "filling_mode", 0)
        # Check filling mode bitmask (IOC preferred for low-latency market execution)
        if fill_flags & SYMBOL_FILLING_IOC:
            return mt5.ORDER_FILLING_IOC
        elif fill_flags & SYMBOL_FILLING_FOK:
            return mt5.ORDER_FILLING_FOK
        return mt5.ORDER_FILLING_RETURN

    def get_last_execution_metrics(self) -> Optional[Dict[str, Any]]:
        """Returns the execution telemetry (latency, slippage) from the most recent order."""
        return self.last_execution_metrics

    def send_order(
        self,
        symbol: str,
        order_type: str,            # "BUY" or "SELL"
        lot: float,
        sl_price: float = 0.0,
        tp_price: float = 0.0,
        magic: int = 777001,
        comment: str = "HFT_ML4T",
        slippage_points: int = 20,
        expected_price: Optional[float] = None
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Executes a live market order with microsecond timestamp telemetry,
        precise slippage auditing, and ticket tracking.
        Returns (success: bool, message: str, ticket: Optional[int]).
        """
        if not self.ensure_connected():
            return False, "MT5 not connected", None

        info = self.get_symbol_info(symbol)
        if info is None or not info.visible:
            mt5.symbol_select(symbol, True)
            info = self.get_symbol_info(symbol)
            if info is None:
                return False, f"Symbol {symbol} unavailable", None

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return False, f"Could not get tick for {symbol}", None

        # Price setup
        is_buy = (order_type.upper() == "BUY")
        action_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
        market_quote_price = tick.ask if is_buy else tick.bid
        ref_expected_price = expected_price if (expected_price is not None and expected_price > 0) else market_quote_price

        # Round lot to broker steps
        lot_step = info.volume_step or 0.01
        lot_clean = math.floor(lot / lot_step) * lot_step
        lot_clean = max(info.volume_min, min(info.volume_max, round(lot_clean, 2)))

        optimal_fill = self._resolve_filling_mode(info)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(lot_clean),
            "type": action_type,
            "price": float(round(market_quote_price, info.digits)),
            "sl": float(round(sl_price, info.digits)) if sl_price > 0 else 0.0,
            "tp": float(round(tp_price, info.digits)) if tp_price > 0 else 0.0,
            "deviation": int(slippage_points),
            "magic": int(magic),
            "comment": comment[:31],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": optimal_fill,
        }

        # Timestamp at dispatch (precision: microsecond)
        t_dispatch = time.perf_counter()
        t_dispatch_utc = datetime.now(timezone.utc)

        # Try optimal filling mode with dynamic fallback ladder
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_INVALID_FILL:
            for fallback_fill in [mt5.ORDER_FILLING_RETURN, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK]:
                if fallback_fill != optimal_fill:
                    request["type_filling"] = fallback_fill
                    result = mt5.order_send(request)
                    if result and result.retcode != mt5.TRADE_RETCODE_INVALID_FILL:
                        break

        # Timestamp at response arrival
        t_fill = time.perf_counter()
        latency_ms = (t_fill - t_dispatch) * 1000.0

        if result is None:
            err = mt5.last_error()
            return False, f"order_send failed: {err}", None

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return False, f"Broker returned code {result.retcode}: {result.comment}", None

        # Actual execution price confirmed by Exness / Broker
        fill_price = float(result.price) if getattr(result, "price", 0) > 0 else market_quote_price
        point = info.point if (info and info.point > 0) else 0.00001
        contract_size = getattr(info, "trade_contract_size", 1.0) or 1.0

        # Directional Slippage:
        # Positive = adverse slippage (bought higher than expected or sold lower than expected)
        # Negative = favorable price improvement
        if is_buy:
            slippage_pts = (fill_price - ref_expected_price) / point
            slippage_usd = (fill_price - ref_expected_price) * lot_clean * contract_size
        else:
            slippage_pts = (ref_expected_price - fill_price) / point
            slippage_usd = (ref_expected_price - fill_price) * lot_clean * contract_size

        # Record execution metrics
        exec_record = {
            "timestamp_utc": t_dispatch_utc.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "ticket": result.order,
            "symbol": symbol,
            "order_type": order_type.upper(),
            "volume": lot_clean,
            "expected_price": round(ref_expected_price, info.digits),
            "fill_price": round(fill_price, info.digits),
            "slippage_points": round(slippage_pts, 2),
            "slippage_usd": round(slippage_usd, 2),
            "latency_ms": round(latency_ms, 2),
            "retcode": result.retcode,
            "comment": comment[:31]
        }
        self.last_execution_metrics = exec_record

        # Append to execution_audit.csv
        log_execution_audit(self.log_dir, exec_record)

        logger.info(
            f"🎯 [ORDER FILLED] Ticket #{result.order} | {order_type} {lot_clean} {symbol} @ {fill_price:.5f} | "
            f"Latency: {latency_ms:.1f}ms | Slippage: {slippage_pts:+.1f} pts (${slippage_usd:+.2f}) | "
            f"SL: {sl_price:.5f} | TP: {tp_price:.5f} | Magic: {magic}"
        )
        return True, "SUCCESS", result.order

    def close_position(self, position: Any, comment: str = "HFT_EXIT") -> Tuple[bool, str]:
        """Closes an open position by ticket."""
        if not self.ensure_connected():
            return False, "MT5 not connected"

        symbol = position.symbol
        info = self.get_symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if tick is None or info is None:
            return False, f"Failed tick data for close: {symbol}"

        is_buy = (position.type == mt5.ORDER_TYPE_BUY)
        close_action = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
        close_price = tick.bid if is_buy else tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": position.ticket,
            "symbol": symbol,
            "volume": position.volume,
            "type": close_action,
            "price": float(round(close_price, info.digits)),
            "deviation": 25,
            "magic": position.magic,
            "comment": comment[:31],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._resolve_filling_mode(info),
        }

        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_INVALID_FILL:
            for fallback_fill in [mt5.ORDER_FILLING_RETURN, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK]:
                if fallback_fill != request["type_filling"]:
                    request["type_filling"] = fallback_fill
                    result = mt5.order_send(request)
                    if result and result.retcode != mt5.TRADE_RETCODE_INVALID_FILL:
                        break

        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"🔒 [CLOSED] Ticket #{position.ticket} {symbol} Vol {position.volume} @ {close_price:.5f}")
            return True, "SUCCESS"

        err_msg = f"Retcode {result.retcode}: {result.comment}" if result else f"Error: {mt5.last_error()}"
        return False, err_msg

    def modify_position_sl(self, position: Any, new_sl: float) -> Tuple[bool, str]:
        """Modifies Stop-Loss of an open position for Breakeven Guard."""
        if not self.ensure_connected():
            return False, "MT5 not connected"

        symbol = position.symbol
        info = self.get_symbol_info(symbol)
        if info is None:
            return False, f"Symbol info unavailable: {symbol}"

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": position.ticket,
            "symbol": symbol,
            "sl": float(round(new_sl, info.digits)),
            "tp": float(round(position.tp, info.digits)),
        }
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"🛡️ [BREAKEVEN GUARD] Ticket #{position.ticket} {symbol} SL moved to {new_sl:.5f}")
            return True, "SUCCESS"
        else:
            msg = result.comment if result else str(mt5.last_error())
            return False, msg

    def shutdown(self) -> None:
        if MT5_AVAILABLE:
            mt5.shutdown()
            self.connected = False
            logger.info("[MT5] Gateway gracefully shut down.")
