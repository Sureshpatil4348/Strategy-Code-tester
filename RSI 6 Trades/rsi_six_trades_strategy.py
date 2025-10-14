"""
Python port of the MT4 expert advisor `RSI  6 Trades.mq4`.

This module mirrors the laddered RSI martingale behaviour in Python so it can
be executed against MetaTrader 5 (MT5) via the official `MetaTrader5` package.
The strategy manages independent buy and sell baskets, scales in using ATR
spacing, and exits when price retraces to the first entry or reaches an
ATR-derived target.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

try:
    import MetaTrader5 as mt5
except ImportError as exc:  # pragma: no cover - handled at runtime
    mt5 = None
    _import_error = exc
else:
    _import_error = None

# Lightweight fallback logger if project logger is unavailable
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


_TIMEFRAME_ALIASES: Dict[str, str] = {
    "M1": "TIMEFRAME_M1",
    "M2": "TIMEFRAME_M2",
    "M3": "TIMEFRAME_M3",
    "M4": "TIMEFRAME_M4",
    "M5": "TIMEFRAME_M5",
    "M6": "TIMEFRAME_M6",
    "M10": "TIMEFRAME_M10",
    "M12": "TIMEFRAME_M12",
    "M15": "TIMEFRAME_M15",
    "M20": "TIMEFRAME_M20",
    "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1",
    "H2": "TIMEFRAME_H2",
    "H3": "TIMEFRAME_H3",
    "H4": "TIMEFRAME_H4",
    "H6": "TIMEFRAME_H6",
    "H8": "TIMEFRAME_H8",
    "H12": "TIMEFRAME_H12",
    "D1": "TIMEFRAME_D1",
    "W1": "TIMEFRAME_W1",
    "MN1": "TIMEFRAME_MN1",
}


def _timeframe_to_str(tf_code: int) -> str:
    if mt5 is None:  # pragma: no cover - depends on runtime module
        return str(tf_code)
    for name, attr in _TIMEFRAME_ALIASES.items():
        if hasattr(mt5, attr) and getattr(mt5, attr) == tf_code:
            return name
    return str(tf_code)


def _resolve_timeframe(value: str | int) -> Tuple[int, str]:
    if isinstance(value, int):
        return value, _timeframe_to_str(value)

    tf = str(value).upper().strip()
    if tf.startswith("PERIOD_"):
        tf = tf.replace("PERIOD_", "")

    if mt5 is None:
        raise RuntimeError(
            "MetaTrader5 module is required to resolve textual timeframes."
        ) from _import_error

    attr_name = _TIMEFRAME_ALIASES.get(tf)
    if attr_name and hasattr(mt5, attr_name):
        return getattr(mt5, attr_name), tf

    raise ValueError(f"Unsupported timeframe literal: {value}")


def _compute_rsi(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0 and avg_gain == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    if avg_gain == 0:
        return 0.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def calculate_rsi_series(closes: List[float], period: int) -> List[Optional[float]]:
    length = len(closes)
    if length < period + 1:
        return []

    rsis: List[Optional[float]] = [None] * length
    gains = [0.0] * length
    losses = [0.0] * length

    for i in range(1, length):
        change = closes[i] - closes[i - 1]
        gains[i] = max(change, 0.0)
        losses[i] = max(-change, 0.0)

    avg_gain = sum(gains[1 : period + 1]) / period
    avg_loss = sum(losses[1 : period + 1]) / period
    rsis[period] = _compute_rsi(avg_gain, avg_loss)

    for i in range(period + 1, length):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period
        rsis[i] = _compute_rsi(avg_gain, avg_loss)

    return rsis


def calculate_atr_series(
    highs: List[float], lows: List[float], closes: List[float], period: int
) -> List[Optional[float]]:
    length = len(closes)
    if length < period + 1:
        return []

    atrs: List[Optional[float]] = [None] * length
    true_ranges = [0.0] * length

    for i in range(1, length):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        true_ranges[i] = max(hl, hc, lc)

    first_atr = sum(true_ranges[1 : period + 1]) / period
    atrs[period] = first_atr

    for i in range(period + 1, length):
        atrs[i] = ((atrs[i - 1] or 0.0) * (period - 1) + true_ranges[i]) / period

    return atrs


@dataclass
class RSI6TradesConfig:
    symbol: str
    rsi_timeframe: str | int = "M5"
    higher_timeframe: str | int = "H1"
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    wait_for_candle_close: bool = True
    initial_lot: float = 0.01
    martingale_multiplier: float = 2.0
    max_trades: int = 8
    allow_both_directions: bool = True
    magic_number: int = 123456
    order_comment: str = "RSI_Ladder_Martingale"
    atr_grid_timeframe: str | int = "H4"
    atr_grid_period: int = 14
    atr_tp_timeframe: str | int = "H1"
    atr_tp_period: int = 14
    slippage_points: int = 3
    login: Optional[int] = None
    password: Optional[str] = None
    server: Optional[str] = None
    terminal_path: Optional[str] = None
    min_lot_override: Optional[float] = None
    max_lot_override: Optional[float] = None
    lot_step_override: Optional[float] = None

    rsi_timeframe_code: int = field(init=False)
    rsi_timeframe_name: str = field(init=False)
    higher_timeframe_code: int = field(init=False)
    higher_timeframe_name: str = field(init=False)
    atr_grid_timeframe_code: int = field(init=False)
    atr_grid_timeframe_name: str = field(init=False)
    atr_tp_timeframe_code: int = field(init=False)
    atr_tp_timeframe_name: str = field(init=False)

    def __post_init__(self) -> None:
        self.rsi_timeframe_code, self.rsi_timeframe_name = _resolve_timeframe(
            self.rsi_timeframe
        )
        (
            self.higher_timeframe_code,
            self.higher_timeframe_name,
        ) = _resolve_timeframe(self.higher_timeframe)
        (
            self.atr_grid_timeframe_code,
            self.atr_grid_timeframe_name,
        ) = _resolve_timeframe(self.atr_grid_timeframe)
        (
            self.atr_tp_timeframe_code,
            self.atr_tp_timeframe_name,
        ) = _resolve_timeframe(self.atr_tp_timeframe)

        if self.max_trades < 1:
            raise ValueError("max_trades must be >= 1")
        if self.martingale_multiplier <= 0:
            raise ValueError("martingale_multiplier must be > 0")


@dataclass
class SideState:
    first_rsi: float = 0.0
    next_index: int = 1
    zone_used: bool = False
    first_price: float = 0.0
    atr_grid: float = 0.0
    atr_tp: float = 0.0


@dataclass
class RSI6TradesState:
    buy: SideState = field(default_factory=SideState)
    sell: SideState = field(default_factory=SideState)
    last_tick_time: Optional[datetime] = None


class RSI6TradesStrategy:
    """
    Python implementation of the RSI 6 Trades martingale EA.

    The class can manage trades directly through the MT5 Python API. Call
    `initialize_mt5` once, then periodically invoke `on_tick()` (ideally on each
    price update) to let the strategy evaluate entries, scaling, and exits.
    """

    def __init__(self, config: RSI6TradesConfig, auto_initialize: bool = False):
        if mt5 is None:  # pragma: no cover - runtime guard
            raise ImportError(
                "MetaTrader5 package is required. Install it with "
                "`pip install MetaTrader5`."
            ) from _import_error

        self.config = config
        self.state = RSI6TradesState()
        self._positions_cache: Optional[List] = None
        self._filling_type: Optional[int] = None
        self.symbol_info = None
        self.connected = False

        if auto_initialize:
            self.initialize_mt5()

    # --- Connection helpers -------------------------------------------------
    def initialize_mt5(self) -> None:
        if not self.connected:
            initialized = mt5.initialize(path=self.config.terminal_path)
            if not initialized:
                raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")

            if self.config.login is not None:
                logged_in = mt5.login(
                    self.config.login,
                    password=self.config.password,
                    server=self.config.server,
                )
                if not logged_in:
                    raise RuntimeError(f"MT5 login failed: {mt5.last_error()}")

            self.connected = True

        if not mt5.symbol_select(self.config.symbol, True):
            raise RuntimeError(f"Unable to select symbol {self.config.symbol}")

        self.symbol_info = mt5.symbol_info(self.config.symbol)
        if self.symbol_info is None:
            raise RuntimeError(f"Failed to read symbol info for {self.config.symbol}")

        self._filling_type = self._determine_filling_type()
        logger.info(
            "RSI6TradesStrategy initialized for %s (ltf=%s, htf=%s)",
            self.config.symbol,
            self.config.rsi_timeframe_name,
            self.config.higher_timeframe_name,
        )

    def shutdown(self) -> None:
        if self.connected:
            mt5.shutdown()
            self.connected = False

    # --- Indicator data collection ------------------------------------------
    def _fetch_rates(self, timeframe: int, count: int) -> Optional[Any]:
        data = mt5.copy_rates_from_pos(self.config.symbol, timeframe, 0, count)
        if data is None:
            logger.warning("Failed to fetch rates for timeframe %s", timeframe)
            return None
        return data

    def _collect_indicators(self) -> Optional[Dict[str, float]]:
        rsi_bars = self.config.rsi_period + 10
        ltf_rates = self._fetch_rates(self.config.rsi_timeframe_code, rsi_bars)
        htf_rates = self._fetch_rates(self.config.higher_timeframe_code, rsi_bars)
        if not ltf_rates or not htf_rates:
            return None

        ltf_closes = ltf_rates["close"].tolist()
        rsi_series_ltf = calculate_rsi_series(ltf_closes, self.config.rsi_period)
        if (
            len(rsi_series_ltf) < 2
            or rsi_series_ltf[-1] is None
            or rsi_series_ltf[-2] is None
        ):
            return None

        htf_closes = htf_rates["close"].tolist()
        rsi_series_htf = calculate_rsi_series(htf_closes, self.config.rsi_period)
        if (
            len(rsi_series_htf) < 2
            or rsi_series_htf[-1] is None
            or rsi_series_htf[-2] is None
        ):
            return None

        atr_grid_rates = self._fetch_rates(
            self.config.atr_grid_timeframe_code, self.config.atr_grid_period + 10
        )
        atr_tp_rates = self._fetch_rates(
            self.config.atr_tp_timeframe_code, self.config.atr_tp_period + 10
        )

        atr_grid = 0.0
        if atr_grid_rates:
            highs = atr_grid_rates["high"].tolist()
            lows = atr_grid_rates["low"].tolist()
            closes = atr_grid_rates["close"].tolist()
            atr_series = calculate_atr_series(
                highs, lows, closes, self.config.atr_grid_period
            )
            if len(atr_series) >= 2 and atr_series[-2] is not None:
                atr_grid = float(atr_series[-2])

        atr_tp = 0.0
        if atr_tp_rates:
            highs = atr_tp_rates["high"].tolist()
            lows = atr_tp_rates["low"].tolist()
            closes = atr_tp_rates["close"].tolist()
            atr_series = calculate_atr_series(
                highs, lows, closes, self.config.atr_tp_period
            )
            if len(atr_series) >= 2 and atr_series[-2] is not None:
                atr_tp = float(atr_series[-2])

        return {
            "rsi_closed_ltf": float(rsi_series_ltf[-2]),
            "rsi_current_ltf": float(rsi_series_ltf[-1]),
            "rsi_closed_htf": float(rsi_series_htf[-2]),
            "rsi_current_htf": float(rsi_series_htf[-1]),
            "atr_grid": atr_grid,
            "atr_tp": atr_tp,
        }

    # --- Position helpers ---------------------------------------------------
    def _is_ours(self, position) -> bool:
        if position.symbol != self.config.symbol:
            return False
        if position.magic != self.config.magic_number:
            return False
        if self.config.order_comment:
            comment = position.comment or ""
            if not comment.startswith(self.config.order_comment):
                return False
        return True

    def _get_positions(self, force_refresh: bool = False) -> List:
        if force_refresh or self._positions_cache is None:
            raw = mt5.positions_get(symbol=self.config.symbol)
            if raw is None:
                logger.debug("positions_get returned None for %s", self.config.symbol)
                self._positions_cache = []
            else:
                self._positions_cache = [pos for pos in raw if self._is_ours(pos)]
        return list(self._positions_cache)

    def _count_side_orders(self, positions: List, is_buy: bool) -> int:
        target_type = mt5.POSITION_TYPE_BUY if is_buy else mt5.POSITION_TYPE_SELL
        return sum(1 for pos in positions if pos.type == target_type)

    def _side_vwap(self, positions: List, is_buy: bool) -> Tuple[float, float]:
        target_type = mt5.POSITION_TYPE_BUY if is_buy else mt5.POSITION_TYPE_SELL
        total_volume = 0.0
        weighted_price = 0.0
        for pos in positions:
            if pos.type != target_type:
                continue
            vol = pos.volume
            total_volume += vol
            weighted_price += vol * pos.price_open
        if total_volume <= 0.0:
            return 0.0, 0.0
        return weighted_price / total_volume, total_volume

    def _get_first_trade_price(self, positions: List, is_buy: bool) -> float:
        target_type = mt5.POSITION_TYPE_BUY if is_buy else mt5.POSITION_TYPE_SELL
        first_time = None
        first_price = 0.0
        for pos in positions:
            if pos.type != target_type:
                continue
            if first_time is None or pos.time < first_time:
                first_time = pos.time
                first_price = pos.price_open
        return first_price

    def _get_latest_trade_price(self, positions: List, is_buy: bool) -> float:
        target_type = mt5.POSITION_TYPE_BUY if is_buy else mt5.POSITION_TYPE_SELL
        latest_time = None
        latest_price = 0.0
        for pos in positions:
            if pos.type != target_type:
                continue
            if latest_time is None or pos.time > latest_time:
                latest_time = pos.time
                latest_price = pos.price_open
        return latest_price

    def _get_last_volume(self, positions: List, is_buy: bool) -> float:
        target_type = mt5.POSITION_TYPE_BUY if is_buy else mt5.POSITION_TYPE_SELL
        latest_time = None
        last_volume = 0.0
        for pos in positions:
            if pos.type != target_type:
                continue
            if latest_time is None or pos.time_msc > latest_time:
                latest_time = pos.time_msc
                last_volume = pos.volume
        return last_volume

    def _reset_side_state(self, is_buy: bool) -> None:
        side = self.state.buy if is_buy else self.state.sell
        side.first_rsi = 0.0
        side.next_index = 1
        side.first_price = 0.0
        side.atr_grid = 0.0
        side.atr_tp = 0.0

    # --- Trading primitives -------------------------------------------------
    def _determine_filling_type(self) -> int:
        if self.symbol_info is None:
            return mt5.ORDER_FILLING_IOC
        mask = self.symbol_info.fillings_mask
        if mask & mt5.ORDER_FILLING_FOK:
            return mt5.ORDER_FILLING_FOK
        if mask & mt5.ORDER_FILLING_IOC:
            return mt5.ORDER_FILLING_IOC
        if mask & mt5.ORDER_FILLING_RETURN:
            return mt5.ORDER_FILLING_RETURN
        return mt5.ORDER_FILLING_IOC

    def _normalize_volume(self, volume: float) -> float:
        if self.symbol_info is None:
            return volume
        min_lot = (
            self.config.min_lot_override
            if self.config.min_lot_override is not None
            else self.symbol_info.volume_min
        )
        max_lot = (
            self.config.max_lot_override
            if self.config.max_lot_override is not None
            else self.symbol_info.volume_max
        )
        lot_step = (
            self.config.lot_step_override
            if self.config.lot_step_override is not None
            else self.symbol_info.volume_step
        )
        if lot_step <= 0.0:
            lot_step = 0.01

        volume = max(min_lot, min(volume, max_lot))
        steps = round(volume / lot_step)
        normalized = steps * lot_step
        normalized = max(min_lot, min(normalized, max_lot))
        return round(normalized, 8)

    def _has_margin(self, order_type: int, volume: float, price: float) -> bool:
        margin = mt5.order_calc_margin(order_type, self.config.symbol, volume, price)
        if margin is None:
            logger.warning("order_calc_margin failed: %s", mt5.last_error())
            return False
        account_info = mt5.account_info()
        if account_info is None:
            logger.warning("account_info unavailable: %s", mt5.last_error())
            return False
        return account_info.margin_free >= margin

    def _place_market_order(self, is_buy: bool, volume: float) -> bool:
        tick = mt5.symbol_info_tick(self.config.symbol)
        if tick is None:
            logger.warning("No market tick available for %s", self.config.symbol)
            return False

        order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
        price = tick.ask if is_buy else tick.bid
        if price <= 0:
            logger.warning("Invalid price for %s order", "buy" if is_buy else "sell")
            return False

        normalized_volume = self._normalize_volume(volume)
        if normalized_volume <= 0:
            logger.warning("Normalized volume is zero, skip trade")
            return False

        if not self._has_margin(order_type, normalized_volume, price):
            logger.warning("Insufficient margin for %s order", "buy" if is_buy else "sell")
            return False

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.config.symbol,
            "volume": normalized_volume,
            "type": order_type,
            "price": price,
            "deviation": self.config.slippage_points,
            "magic": self.config.magic_number,
            "comment": self.config.order_comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._filling_type,
        }

        check = mt5.order_check(request)
        if check is None or check.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(
                "order_check failed (retcode=%s, comment=%s)",
                None if check is None else check.retcode,
                None if check is None else check.comment,
            )
            return False

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error("order_send failed: %s", result)
            return False

        logger.info(
            "Opened %s order lot=%.2f price=%f ticket=%s",
            "BUY" if is_buy else "SELL",
            normalized_volume,
            price,
            result.order,
        )
        self._positions_cache = None
        return True

    def _close_position(self, position) -> bool:
        tick = mt5.symbol_info_tick(self.config.symbol)
        if tick is None:
            logger.warning("No tick available to close position %s", position.ticket)
            return False

        close_type = (
            mt5.ORDER_TYPE_SELL
            if position.type == mt5.POSITION_TYPE_BUY
            else mt5.ORDER_TYPE_BUY
        )
        price = tick.bid if position.type == mt5.POSITION_TYPE_BUY else tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.config.symbol,
            "volume": position.volume,
            "type": close_type,
            "position": position.ticket,
            "price": price,
            "deviation": self.config.slippage_points,
            "magic": self.config.magic_number,
            "comment": f"{self.config.order_comment}_close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._filling_type,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error("Failed to close position %s: %s", position.ticket, result)
            return False

        logger.info("Closed position %s (volume %.2f)", position.ticket, position.volume)
        return True

    def _close_all_side_orders(self, positions: List, is_buy: bool) -> bool:
        success = True
        target_type = mt5.POSITION_TYPE_BUY if is_buy else mt5.POSITION_TYPE_SELL
        for pos in positions:
            if pos.type != target_type:
                continue
            if not self._close_position(pos):
                success = False
        if success:
            self._positions_cache = None
        return success

    # --- Strategy core ------------------------------------------------------
    def _allowed_to_open(self, positions: List, is_buy: bool) -> bool:
        if self.config.allow_both_directions:
            return True
        other_count = self._count_side_orders(positions, not is_buy)
        return other_count == 0

    def _update_zone_permissions(self, rsi_closed: float, rsi_current: float) -> None:
        if self.config.wait_for_candle_close:
            in_sell_zone = rsi_closed >= self.config.rsi_overbought
            in_buy_zone = rsi_closed <= self.config.rsi_oversold
        else:
            in_sell_zone = rsi_current >= self.config.rsi_overbought
            in_buy_zone = rsi_current <= self.config.rsi_oversold

        if not in_sell_zone:
            self.state.sell.zone_used = False
        if not in_buy_zone:
            self.state.buy.zone_used = False

    def _try_open_first_entries(
        self, positions: List, indicators: Dict[str, float]
    ) -> List[str]:
        actions: List[str] = []

        sell_count = self._count_side_orders(positions, is_buy=False)
        if (
            sell_count == 0
            and not self.state.sell.zone_used
            and self._allowed_to_open(positions, is_buy=False)
        ):
            cond_ltf = (
                indicators["rsi_closed_ltf"] >= self.config.rsi_overbought
                if self.config.wait_for_candle_close
                else indicators["rsi_current_ltf"] >= self.config.rsi_overbought
            )
            cond_htf = (
                indicators["rsi_closed_htf"] >= self.config.rsi_overbought
                if self.config.wait_for_candle_close
                else indicators["rsi_current_htf"] >= self.config.rsi_overbought
            )
            if cond_ltf and cond_htf:
                if self._place_market_order(False, self.config.initial_lot):
                    positions = self._get_positions(force_refresh=True)
                    self.state.sell.first_rsi = (
                        indicators["rsi_closed_ltf"]
                        if self.config.wait_for_candle_close
                        else indicators["rsi_current_ltf"]
                    )
                    self.state.sell.next_index = 1
                    self.state.sell.zone_used = True
                    self.state.sell.first_price = self._get_first_trade_price(
                        positions, is_buy=False
                    )
                    self.state.sell.atr_grid = indicators["atr_grid"]
                    self.state.sell.atr_tp = indicators["atr_tp"]
                    actions.append("opened_first_sell")
                    logger.info(
                        "Opened first sell trade @ %.5f (ATR grid %.5f, ATR TP %.5f)",
                        self.state.sell.first_price,
                        self.state.sell.atr_grid,
                        self.state.sell.atr_tp,
                    )

        positions = self._get_positions(force_refresh=True)

        buy_count = self._count_side_orders(positions, is_buy=True)
        if (
            buy_count == 0
            and not self.state.buy.zone_used
            and self._allowed_to_open(positions, is_buy=True)
        ):
            cond_ltf = (
                indicators["rsi_closed_ltf"] <= self.config.rsi_oversold
                if self.config.wait_for_candle_close
                else indicators["rsi_current_ltf"] <= self.config.rsi_oversold
            )
            cond_htf = (
                indicators["rsi_closed_htf"] <= self.config.rsi_oversold
                if self.config.wait_for_candle_close
                else indicators["rsi_current_htf"] <= self.config.rsi_oversold
            )
            if cond_ltf and cond_htf:
                if self._place_market_order(True, self.config.initial_lot):
                    positions = self._get_positions(force_refresh=True)
                    self.state.buy.first_rsi = (
                        indicators["rsi_closed_ltf"]
                        if self.config.wait_for_candle_close
                        else indicators["rsi_current_ltf"]
                    )
                    self.state.buy.next_index = 1
                    self.state.buy.zone_used = True
                    self.state.buy.first_price = self._get_first_trade_price(
                        positions, is_buy=True
                    )
                    self.state.buy.atr_grid = indicators["atr_grid"]
                    self.state.buy.atr_tp = indicators["atr_tp"]
                    actions.append("opened_first_buy")
                    logger.info(
                        "Opened first buy trade @ %.5f (ATR grid %.5f, ATR TP %.5f)",
                        self.state.buy.first_price,
                        self.state.buy.atr_grid,
                        self.state.buy.atr_tp,
                    )

        return actions

    def _try_scale_entries(self, positions: List) -> List[str]:
        actions: List[str] = []
        tick = mt5.symbol_info_tick(self.config.symbol)
        if tick is None:
            return actions

        sell_count = self._count_side_orders(positions, is_buy=False)
        if (
            sell_count > 0
            and sell_count < self.config.max_trades
            and self.state.sell.first_price > 0.0
            and self.state.sell.atr_grid > 0.0
        ):
            latest_price = self._get_latest_trade_price(positions, is_buy=False)
            current_price = tick.ask
            target_price = (
                self.state.sell.first_price
                + self.state.sell.next_index * self.state.sell.atr_grid
            )
            while (
                current_price >= target_price
                and current_price > latest_price
                and sell_count < self.config.max_trades
            ):
                last_volume = self._get_last_volume(positions, is_buy=False)
                next_volume = (
                    last_volume if last_volume > 0 else self.config.initial_lot
                ) * self.config.martingale_multiplier
                if not self._place_market_order(False, next_volume):
                    break
                positions = self._get_positions(force_refresh=True)
                sell_count += 1
                self.state.sell.next_index += 1
                latest_price = self._get_latest_trade_price(positions, is_buy=False)
                target_price = (
                    self.state.sell.first_price
                    + self.state.sell.next_index * self.state.sell.atr_grid
                )
                current_price = mt5.symbol_info_tick(self.config.symbol).ask
                actions.append("scaled_sell")

        positions = self._get_positions(force_refresh=True)

        buy_count = self._count_side_orders(positions, is_buy=True)
        if (
            buy_count > 0
            and buy_count < self.config.max_trades
            and self.state.buy.first_price > 0.0
            and self.state.buy.atr_grid > 0.0
        ):
            latest_price = self._get_latest_trade_price(positions, is_buy=True)
            current_price = tick.bid
            target_price = (
                self.state.buy.first_price
                - self.state.buy.next_index * self.state.buy.atr_grid
            )
            while (
                current_price <= target_price
                and current_price < latest_price
                and buy_count < self.config.max_trades
            ):
                last_volume = self._get_last_volume(positions, is_buy=True)
                next_volume = (
                    last_volume if last_volume > 0 else self.config.initial_lot
                ) * self.config.martingale_multiplier
                if not self._place_market_order(True, next_volume):
                    break
                positions = self._get_positions(force_refresh=True)
                buy_count += 1
                self.state.buy.next_index += 1
                latest_price = self._get_latest_trade_price(positions, is_buy=True)
                target_price = (
                    self.state.buy.first_price
                    - self.state.buy.next_index * self.state.buy.atr_grid
                )
                current_price = mt5.symbol_info_tick(self.config.symbol).bid
                actions.append("scaled_buy")

        return actions

    def _try_close_by_targets(self, positions: List) -> List[str]:
        actions: List[str] = []
        tick = mt5.symbol_info_tick(self.config.symbol)
        if tick is None:
            return actions

        sell_count = self._count_side_orders(positions, is_buy=False)
        if sell_count > 0:
            if sell_count > 1:
                first_price = self._get_first_trade_price(positions, is_buy=False)
                if first_price > 0.0 and tick.ask <= first_price:
                    if self._close_all_side_orders(positions, is_buy=False):
                        self._reset_side_state(is_buy=False)
                        positions = self._get_positions(force_refresh=True)
                        actions.append("closed_sell_retrace")
                        sell_count = 0

            if (
                sell_count > 0
                and sell_count < self.config.max_trades
                and self.state.sell.atr_tp > 0.0
            ):
                vwap, total_volume = self._side_vwap(positions, is_buy=False)
                if total_volume > 0.0:
                    if (vwap - tick.ask) >= self.state.sell.atr_tp:
                        if self._close_all_side_orders(positions, is_buy=False):
                            self._reset_side_state(is_buy=False)
                            self._positions_cache = None
                            positions = self._get_positions(force_refresh=True)
                            actions.append("closed_sell_atr_tp")

        buy_count = self._count_side_orders(positions, is_buy=True)
        if buy_count > 0:
            if buy_count > 1:
                first_price = self._get_first_trade_price(positions, is_buy=True)
                if first_price > 0.0 and tick.bid >= first_price:
                    if self._close_all_side_orders(positions, is_buy=True):
                        self._reset_side_state(is_buy=True)
                        positions = self._get_positions(force_refresh=True)
                        actions.append("closed_buy_retrace")
                        buy_count = 0

            if (
                buy_count > 0
                and buy_count < self.config.max_trades
                and self.state.buy.atr_tp > 0.0
            ):
                vwap, total_volume = self._side_vwap(positions, is_buy=True)
                if total_volume > 0.0:
                    if (tick.bid - vwap) >= self.state.buy.atr_tp:
                        if self._close_all_side_orders(positions, is_buy=True):
                            self._reset_side_state(is_buy=True)
                            self._positions_cache = None
                            actions.append("closed_buy_atr_tp")

        return actions

    # --- Public interface ---------------------------------------------------
    def on_tick(self) -> Dict[str, object]:
        if not self.connected:
            self.initialize_mt5()

        indicators = self._collect_indicators()
        if not indicators:
            return {"status": "waiting_data"}

        self._update_zone_permissions(
            indicators["rsi_closed_ltf"], indicators["rsi_current_ltf"]
        )

        positions = self._get_positions(force_refresh=True)
        actions: List[str] = []

        actions.extend(self._try_close_by_targets(positions))
        positions = self._get_positions(force_refresh=True)

        actions.extend(self._try_open_first_entries(positions, indicators))
        positions = self._get_positions(force_refresh=True)

        actions.extend(self._try_scale_entries(positions))

        self.state.last_tick_time = datetime.now()
        return {
            "status": "ok",
            "actions": actions,
            "open_positions": len(self._get_positions(force_refresh=True)),
            "state": self.get_state_snapshot(),
        }

    def get_state_snapshot(self) -> Dict[str, object]:
        return {
            "buy": {
                "zone_used": self.state.buy.zone_used,
                "first_price": self.state.buy.first_price,
                "next_index": self.state.buy.next_index,
                "atr_grid": self.state.buy.atr_grid,
                "atr_tp": self.state.buy.atr_tp,
            },
            "sell": {
                "zone_used": self.state.sell.zone_used,
                "first_price": self.state.sell.first_price,
                "next_index": self.state.sell.next_index,
                "atr_grid": self.state.sell.atr_grid,
                "atr_tp": self.state.sell.atr_tp,
            },
            "last_tick_time": self.state.last_tick_time.isoformat()
            if self.state.last_tick_time
            else None,
        }


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    example_config = RSI6TradesConfig(symbol="EURUSD")
    strategy = RSI6TradesStrategy(example_config, auto_initialize=False)
    try:
        strategy.initialize_mt5()
        result = strategy.on_tick()
        print(result)
    finally:
        strategy.shutdown()
