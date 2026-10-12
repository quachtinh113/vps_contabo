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

from core.audit_logger import get_logger

logger = get_logger()

TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1 if MT5_AVAILABLE else 1,
    "M5": mt5.TIMEFRAME_M5 if MT5_AVAILABLE else 5,
    "M15": mt5.TIMEFRAME_M15 if MT5_AVAILABLE else 15,
    "H1": mt5.TIMEFRAME_H1 if MT5_AVAILABLE else 16385,
    "H4": mt5.TIMEFRAME_H4 if MT5_AVAILABLE else 16388,
}


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
        server: str = ""
    ):
        if self._initialized:
            return

        self.terminal_path = terminal_path or os.getenv("MT5_PATH", "")
        self.account = account or int(os.getenv("MT5_ACCOUNT", "0"))
        self.password = password or os.getenv("MT5_PASSWORD", "")
        self.server = server or os.getenv("MT5_SERVER", "")
        self.connected = False
        self._last_health_check = 0.0
        self._symbol_cache: Dict[str, Any] = {}
        self._initialized = True

    def initialize(self) -> bool:
        """Connects to MT5 terminal and verifies account authentication."""
        if not MT5_AVAILABLE:
            logger.error("MetaTrader5 package is not available in current environment.")
            return False

        init_kwargs: Dict[str, Any] = {}
        if self.terminal_path and os.path.exists(self.terminal_path):
            init_kwargs["path"] = self.terminal_path
        if self.account:
            init_kwargs["login"] = self.account
        if self.password:
            init_kwargs["password"] = self.password
        if self.server:
            init_kwargs["server"] = self.server
        init_kwargs["timeout"] = 15000

        if not mt5.initialize(**init_kwargs):
            err = mt5.last_error()
            logger.error(f"MT5 initialize failed: {err}")
            return False

        # Login verification if credentials provided
        acc = mt5.account_info()
        if acc is None or (self.account and acc.login != self.account):
            if self.account and self.password and self.server:
                login_ok = mt5.login(
                    login=self.account,
                    password=self.password,
                    server=self.server
                )
                if not login_ok:
                    err = mt5.last_error()
                    logger.error(f"MT5 login failed for account {self.account} on {self.server}: {err}")
                    return False
            acc = mt5.account_info()

        if acc is None:
            logger.error("Failed to retrieve MT5 account info.")
            return False

        is_real = (acc.trade_mode == mt5.ACCOUNT_TRADE_MODE_REAL)
        mode_str = "🔴 REAL MONEY (Tiền Thật)" if is_real else "🟡 DEMO / TRIAL"

        logger.info(
            f"✅ MT5 Gateway Connected successfully! "
            f"Account: {acc.login} | Server: {acc.server} | Mode: {mode_str} | "
            f"Balance: ${acc.balance:,.2f} | Equity: ${acc.equity:,.2f} | Leverage: 1:{acc.leverage}"
        )
        self.connected = True
        return True

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
            logger.warning("[MT5] Heartbeat disconnected. Attempting auto-reconnect...")
            self.connected = False
            return self.initialize()

        self.connected = True
        return True

    def get_symbol_info(self, symbol: str) -> Optional[Any]:
        """Retrieves and caches symbol specification."""
        if not self.ensure_connected():
            return None
        info = mt5.symbol_info(symbol)
        if info is None or not getattr(info, "visible", True):
            mt5.symbol_select(symbol, True)
            info = mt5.symbol_info(symbol)
        return info

    def get_market_snapshot(self, symbol: str) -> Optional[Dict[str, float]]:
        """Returns live bid, ask, and spread in points."""
        if not self.ensure_connected():
            return None
        info = self.get_symbol_info(symbol)
        if info is None:
            return None
        tick = mt5.symbol_info_tick(symbol)
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
        """Fetches OHLCV candlestick DataFrame."""
        if not self.ensure_connected():
            return None
        tf = TIMEFRAME_MAP.get(timeframe, mt5.TIMEFRAME_M15)
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
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

    def send_order(
        self,
        symbol: str,
        order_type: str,            # "BUY" or "SELL"
        lot: float,
        sl_price: float = 0.0,
        tp_price: float = 0.0,
        magic: int = 777001,
        comment: str = "HFT_ML4T",
        slippage_points: int = 20
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Executes a live market order with slippage limits and ticket tracking.
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
        price = tick.ask if is_buy else tick.bid

        # Round lot to broker steps
        lot_step = info.volume_step or 0.01
        lot_clean = math.floor(lot / lot_step) * lot_step
        lot_clean = max(info.volume_min, min(info.volume_max, round(lot_clean, 2)))

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(lot_clean),
            "type": action_type,
            "price": float(round(price, info.digits)),
            "sl": float(round(sl_price, info.digits)) if sl_price > 0 else 0.0,
            "tp": float(round(tp_price, info.digits)) if tp_price > 0 else 0.0,
            "deviation": int(slippage_points),
            "magic": int(magic),
            "comment": comment[:31],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        # Try IOC first, fallback to RETURN or FOK if unsupported
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_INVALID_FILL:
            request["type_filling"] = mt5.ORDER_FILLING_RETURN
            result = mt5.order_send(request)

        if result is None:
            err = mt5.last_error()
            return False, f"order_send failed: {err}", None

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return False, f"Broker returned code {result.retcode}: {result.comment}", None

        logger.info(
            f"🎯 [ORDER FILLED] Ticket #{result.order} | {order_type} {lot_clean} {symbol} @ {price:.5f} | "
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
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_INVALID_FILL:
            request["type_filling"] = mt5.ORDER_FILLING_RETURN
            result = mt5.order_send(request)

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
