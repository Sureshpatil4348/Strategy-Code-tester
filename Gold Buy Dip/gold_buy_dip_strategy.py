from typing import List, Optional, Dict
from datetime import datetime
from decimal import Decimal
from sqlalchemy.orm import Session
from app.models.trading_models import MarketData, TradeSignal, TradeDirection, SetupState
from app.models.strategy_models import GoldBuyDipConfig, GoldBuyDipState
from app.indicators.zscore import calculate_zscore
from app.indicators.atr import calculate_atr
from app.utilities.forex_logger import forex_logger
from app.services.strategy_performance_tracker import StrategyPerformanceTracker
from app.services.base_strategy import BaseStrategy
from app.services.mt5_margin_validator import MT5MarginValidator

logger = forex_logger.get_logger(__name__)

class GoldBuyDipStrategy(BaseStrategy):
    def __init__(self, config: GoldBuyDipConfig, pair: str, timeframe: str = "15M", db: Session = None):
        super().__init__(pair, timeframe, "gold_buy_dip", db)
        self.config = config
        self.state = GoldBuyDipState()
        self.candles: List[MarketData] = []
        self.performance_tracker = StrategyPerformanceTracker(timeframe)
        self.margin_validator = MT5MarginValidator()
    
    def add_candle(self, candle: MarketData):
        self.candles.append(candle)
        max_needed = max(self.config.lookback_candles, self.config.zscore_period, self.config.atr_period) + 10
        if len(self.candles) > max_needed:
            self.candles = self.candles[-max_needed:]
    
    def check_percentage_trigger(self) -> Optional[TradeDirection]:
        # Fully dynamic: Use exactly what user configured
        if len(self.candles) < self.config.lookback_candles:
            return None
        
        # Use exact user-configured lookback period
        lookback_count = self.config.lookback_candles
        
        recent_candles = self.candles[-lookback_count:]
        highest_high = max(c.close for c in recent_candles)
        lowest_low = min(c.close for c in recent_candles)
        current_price = self.candles[-1].close
        
        pct_from_low = ((current_price - lowest_low) / lowest_low) * 100
        if pct_from_low >= self.config.percentage_threshold:
            return TradeDirection.SELL
        
        pct_from_high = ((highest_high - current_price) / highest_high) * 100
        if pct_from_high >= self.config.percentage_threshold:
            return TradeDirection.BUY
        
        return None
    
    def check_zscore_confirmation(self) -> bool:
        if len(self.candles) < self.config.zscore_period:
            return False
        
        closes = [c.close for c in self.candles]
        zscore = calculate_zscore(closes, self.config.zscore_period)
        
        if self.state.trigger_direction == TradeDirection.SELL:
            return zscore >= self.config.zscore_threshold_sell
        elif self.state.trigger_direction == TradeDirection.BUY:
            return zscore <= self.config.zscore_threshold_buy
        
        return False
    
    def calculate_grid_spacing(self) -> float:
        """Calculate grid spacing based on user configuration"""
        if self.config.use_grid_percent:
            # Use the last grid trade price as reference, not current market price
            if self.state.grid_trades:
                reference_price = self.state.grid_trades[-1]["price"]
            else:
                reference_price = self.candles[-1].close
            spacing = reference_price * (self.config.grid_percent / 100)
            # Ensure minimum spacing for XAUUSD (at least 0.50 points)
            min_spacing = 0.50 if "XAU" in self.pair else 0.0001
            return max(spacing, min_spacing)
        else:
            atr = calculate_atr(self.candles, self.config.atr_period)
            return atr * self.config.grid_atr_multiplier
    
    def calculate_grid_lot_size(self, grid_level: int) -> float:
        """Calculate lot size for grid trade based on user configuration"""
        if self.config.use_progressive_lots:
            return self.config.lot_size * (self.config.lot_progression_factor ** grid_level)
        else:
            return self.config.lot_size * self.config.grid_lot_multiplier
    
    def calculate_volume_weighted_take_profit(self) -> Optional[float]:
        """Calculate take profit based on volume-weighted average price of all grid trades"""
        if not self.state.grid_trades:
            return None
        
        total_lots = sum(trade["lot_size"] for trade in self.state.grid_trades)
        if total_lots == 0:
            return None
        
        # Volume-weighted average price calculation
        weighted_price = sum(trade["price"] * trade["lot_size"] for trade in self.state.grid_trades)
        vwap = weighted_price / total_lots
        
        first_trade = self.state.grid_trades[0]
        
        if first_trade["direction"] == "BUY":
            if self.config.use_take_profit_percent:
                return vwap * (1 + self.config.take_profit_percent / 100)
            else:
                # For XAUUSD: 200 points = 2.00 price points (divide by 100)
                # For forex pairs: 200 points = 0.0200 price points (divide by 10000)
                divisor = 100 if "XAU" in self.pair else 10000
                return vwap + (self.config.take_profit / divisor)
        else:
            if self.config.use_take_profit_percent:
                return vwap * (1 - self.config.take_profit_percent / 100)
            else:
                # For XAUUSD: 200 points = 2.00 price points (divide by 100)
                # For forex pairs: 200 points = 0.0200 price points (divide by 10000)
                divisor = 100 if "XAU" in self.pair else 10000
                return vwap - (self.config.take_profit / divisor)
    
    def check_grid_exit_conditions(self, current_price: float) -> bool:
        """Check if grid should be closed."""
        if not self.state.grid_trades:
            return False
        
        # Check volume-weighted take profit first (priority exit)
        avg_tp = self.calculate_volume_weighted_take_profit()
        if avg_tp is not None:
            first_trade = self.state.grid_trades[0]
            if first_trade["direction"] == "BUY" and current_price >= avg_tp:
                logger.info(f"BUY grid profit target reached: {current_price:.2f} >= {avg_tp:.2f}")
                return True
            elif first_trade["direction"] == "SELL" and current_price <= avg_tp:
                logger.info(f"SELL grid profit target reached: {current_price:.2f} <= {avg_tp:.2f}")
                return True
        
        # Only exit on max trades if we have reached the limit
        if len(self.state.grid_trades) >= self.config.max_grid_trades:
            logger.info(f"Grid exit: Max trades reached {len(self.state.grid_trades)}/{self.config.max_grid_trades}")
            return True
        

        
        return False
    
    def _check_strategy_drawdown(self, current_equity: float) -> bool:
        """Check if strategy-specific maximum drawdown is exceeded"""
        if self.state.initial_balance <= 0:
            logger.error("Initial balance not set - cannot check drawdown")
            return False
        
        drawdown_pct = ((self.state.initial_balance - current_equity) / self.state.initial_balance) * 100
        
        if drawdown_pct >= self.config.max_drawdown_percent:
            logger.critical(f"STRATEGY DRAWDOWN LIMIT EXCEEDED: {drawdown_pct:.2f}% >= {self.config.max_drawdown_percent}%")
            return True
        

        
        return False
    
    def _process_market_data(self, candle: MarketData) -> Optional[TradeSignal]:
        """Strategy-specific market data processing."""
        self.add_candle(candle)
        
        # Debug logging
        logger.info(f"Gold Buy Dip: Candles={len(self.candles)}, State={self.state.setup_state}, Price={candle.close:.2f}")
        
        # Calculate indicators for logging
        zscore = 0
        atr = 0
        price_movement_score = 0
        
        if len(self.candles) >= self.config.zscore_period:
            closes = [c.close for c in self.candles]
            zscore = calculate_zscore(closes, self.config.zscore_period)
        
        if len(self.candles) >= self.config.atr_period:
            atr = calculate_atr(self.candles, self.config.atr_period)
        
        # Use configured candles for price movement calculation
        if len(self.candles) >= self.config.lookback_candles:
            recent_candles = self.candles[-self.config.lookback_candles:]
            highest_high = max(c.close for c in recent_candles)
            lowest_low = min(c.close for c in recent_candles)
            price_range = highest_high - lowest_low
            if price_range > 0:
                price_movement_score = ((candle.close - lowest_low) / price_range) * 100
            
            # Debug percentage trigger calculation
            pct_from_low = ((candle.close - lowest_low) / lowest_low) * 100
            pct_from_high = ((highest_high - candle.close) / highest_high) * 100
            logger.info(f"Gold Buy Dip: PctFromLow={pct_from_low:.2f}%, PctFromHigh={pct_from_high:.2f}%, Threshold={self.config.percentage_threshold}%")
        
        # Check for maximum drawdown - requires current equity to be provided
        signal = None
        current_equity = self.state.initial_balance + float(self.current_realized_pnl) + float(self.current_floating_pnl)
        if self._check_strategy_drawdown(current_equity):
            self.state.setup_state = SetupState.WAITING_FOR_TRIGGER
            self.state.grid_trades.clear()
            signal = TradeSignal(
                action="CLOSE_ALL",
                lot_size=0,
                reason="Strategy maximum drawdown exceeded"
            )
        
        # Forex standard: Log only when signals are generated
        if signal is not None:
            self._log_market_data_with_signals(signal, zscore, atr, price_movement_score, 0)
        
        if signal:
            return signal
        
        if self.state.setup_state == SetupState.WAITING_FOR_TRIGGER:
            # Intelligent filtering: prevent immediate re-entry without significant price move
            if self.state.last_grid_close_price > 0:
                current_price = candle.close
                price_move_pct = abs(current_price - self.state.last_grid_close_price) / self.state.last_grid_close_price * 100
                
                if price_move_pct < self.state.min_price_move_for_new_grid:
                    logger.debug(f"Insufficient price move: {price_move_pct:.3f}% < {self.state.min_price_move_for_new_grid}%")
                    return None
                
            trigger = self.check_percentage_trigger()
            if trigger:
                # Additional filter: avoid same direction trades too close together
                if (self.state.last_grid_close_direction and 
                    trigger.value == self.state.last_grid_close_direction and
                    self.state.last_grid_close_price > 0):
                    
                    current_price = candle.close
                    if self.state.last_grid_close_direction == "BUY":
                        if current_price >= self.state.last_grid_close_price * (1 - self.state.min_price_move_for_new_grid / 100):
                            logger.debug(f"Same direction filter: BUY too close to last close")
                            return None
                    else:
                        if current_price <= self.state.last_grid_close_price * (1 + self.state.min_price_move_for_new_grid / 100):
                            logger.debug(f"Same direction filter: SELL too close to last close")
                            return None
                
                logger.info(f"Gold Buy Dip: Percentage trigger detected - {trigger}")
                self.state.setup_state = SetupState.WAITING_FOR_ZSCORE
                self.state.trigger_direction = trigger
                self.state.trigger_candle = len(self.candles) - 1
                self.state.wait_candles_count = 0
        
        elif self.state.setup_state == SetupState.WAITING_FOR_ZSCORE:
            self.state.wait_candles_count += 1
            logger.info(f"Gold Buy Dip: Waiting for Z-score confirmation, wait_count={self.state.wait_candles_count}, zscore={zscore:.2f}")
            
            if self.check_zscore_confirmation():
                logger.info(f"Gold Buy Dip: Z-score confirmation received - {zscore:.2f}")
                # Capital allocation disabled - trading with MT5 balance directly
                
                # Execute initial trade
                self.state.setup_state = SetupState.TRADE_EXECUTED
                
                # Use configured lot size directly - no calculations or fallbacks
                position_size = self.config.lot_size
                
                # Don't set individual take profit for initial trade
                # Let the grid system handle take profit via VWAP calculation
                take_profit = None
                
                self.state.grid_trades.append({
                    "price": candle.close,
                    "direction": self.state.trigger_direction.value,
                    "lot_size": self.config.lot_size,
                    "grid_level": 0
                })
                
                logger.info(f"Initial grid trade: Price: {candle.close:.2f}, Direction: {self.state.trigger_direction.value}, Lot: {position_size}")
                
                signal = TradeSignal(
                    action=self.state.trigger_direction.value,
                    lot_size=self.config.lot_size,
                    take_profit=take_profit,
                    reason=f"Initial trade - Z-score confirmed (Magic: {self.config.magic_number})"
                )
                
                # Log the signal before returning
                self._log_market_data_with_signals(signal, zscore, atr, price_movement_score, 0)
                return signal
            
            elif self.state.wait_candles_count >= self.config.zscore_wait_candles:
                # Z-score confirmation timeout - reset to waiting for trigger
                logger.info(f"Z-score confirmation timeout after {self.config.zscore_wait_candles} candles")
                self.state.setup_state = SetupState.WAITING_FOR_TRIGGER
                self.state.trigger_direction = None
        
        elif self.state.setup_state == SetupState.TRADE_EXECUTED:
            # Check grid exit conditions first
            if self.config.use_grid_trading and self.check_grid_exit_conditions(candle.close):
                # Store grid close info for intelligent filtering
                self.state.last_grid_close_price = candle.close
                self.state.last_grid_close_direction = self.state.grid_trades[0]["direction"] if self.state.grid_trades else None
                
                # Close all grid trades
                self.state.setup_state = SetupState.WAITING_FOR_TRIGGER
                total_trades = len(self.state.grid_trades)
                self.state.grid_trades.clear()
                
                logger.info(f"Grid closed at {candle.close:.2f}, direction: {self.state.last_grid_close_direction}")
                
                signal = TradeSignal(
                    action="CLOSE_ALL",
                    lot_size=0,
                    reason=f"Grid exit: {total_trades} trades closed"
                )
                return signal
            
            # Handle adding new grid trades - enforce max_grid_trades strictly
            if (self.config.use_grid_trading and 
                len(self.state.grid_trades) > 0 and 
                len(self.state.grid_trades) < self.config.max_grid_trades):
                
                last_trade = self.state.grid_trades[-1]
                grid_spacing = self.calculate_grid_spacing()
                
                # Check if price moved against position by grid spacing amount
                should_add_grid = False
                price_diff = 0
                
                if last_trade["direction"] == "BUY":
                    price_diff = last_trade["price"] - candle.close
                    should_add_grid = price_diff >= grid_spacing
                elif last_trade["direction"] == "SELL":
                    price_diff = candle.close - last_trade["price"]
                    should_add_grid = price_diff >= grid_spacing
                
                if should_add_grid:
                    grid_level = len(self.state.grid_trades)
                    lot_size = self.calculate_grid_lot_size(grid_level)
                    
                    self.state.grid_trades.append({
                        "price": candle.close,
                        "direction": last_trade["direction"],
                        "lot_size": lot_size,
                        "grid_level": grid_level
                    })
                    
                    logger.info(f"Grid trade added: Level {grid_level + 1}/{self.config.max_grid_trades}, Price: {candle.close:.2f}, Lot: {lot_size:.2f}, Spacing: {grid_spacing:.2f}, PriceDiff: {price_diff:.2f}")
                    
                    signal = TradeSignal(
                        action=last_trade["direction"],
                        lot_size=lot_size,
                        take_profit=self.calculate_volume_weighted_take_profit(),
                        reason=f"Grid trade level {grid_level + 1}/{self.config.max_grid_trades} (Magic: {self.config.magic_number})"
                    )
                    return signal
                else:
                    # Debug why grid trade wasn't added
                    logger.debug(f"Grid trade not added: PriceDiff={price_diff:.2f} < RequiredSpacing={grid_spacing:.2f}, Direction={last_trade['direction']}, LastPrice={last_trade['price']:.2f}, CurrentPrice={candle.close:.2f}")
        
        return None
    
    def get_grid_status(self) -> dict:
        """Get current grid trading status."""
        current_price = self.candles[-1].close if self.candles else 0
        price_move_since_close = 0
        
        if self.state.last_grid_close_price > 0 and current_price > 0:
            price_move_since_close = abs(current_price - self.state.last_grid_close_price) / self.state.last_grid_close_price * 100
        
        if not self.state.grid_trades:
            return {
                "active": False, 
                "trades": 0,
                "last_close_price": self.state.last_grid_close_price,
                "last_close_direction": self.state.last_grid_close_direction,
                "price_move_since_close": price_move_since_close,
                "min_move_required": self.state.min_price_move_for_new_grid
            }
        
        total_lots = sum(trade["lot_size"] for trade in self.state.grid_trades)
        avg_price = sum(trade["price"] * trade["lot_size"] for trade in self.state.grid_trades) / total_lots if total_lots > 0 else 0
        avg_tp = self.calculate_volume_weighted_take_profit()
        
        return {
            "active": True,
            "trades": len(self.state.grid_trades),
            "max_trades": self.config.max_grid_trades,
            "total_lots": total_lots,
            "average_price": avg_price,
            "volume_weighted_take_profit": avg_tp,
            "direction": self.state.grid_trades[0]["direction"] if self.state.grid_trades else None,
            "grid_levels": [trade["grid_level"] for trade in self.state.grid_trades],
            "grid_spacing_percent": self.config.grid_percent,
            "use_progressive_lots": self.config.use_progressive_lots,
            "last_close_price": self.state.last_grid_close_price,
            "last_close_direction": self.state.last_grid_close_direction,
            "price_move_since_close": price_move_since_close
        }
    
    def _log_market_data_with_signals(self, signal: Optional[TradeSignal], zscore: float, atr: float, 
                                    price_movement_score: float, drawdown_pct: float):
        """Log market data following forex standards - trade from available data."""
        # Forex standard: Use available candles (minimum 20 for Z-score)
        if len(self.candles) < self.config.zscore_period:
            return
            
        # Log 50 candles with signal (show all candles like before)
        recent_candles = self.candles[-50:] if len(self.candles) >= 50 else self.candles
        
        # Use simple CSV logger for signal logging
        candle_data = {
            'timestamp': recent_candles[-1].timestamp,
            'open': recent_candles[-1].open,
            'high': recent_candles[-1].high,
            'low': recent_candles[-1].low,
            'close': recent_candles[-1].close
        }
        
        indicators = {
            'zscore': zscore,
            'atr': atr,
            'price_movement_score': price_movement_score,
            'strategy_state': f"Grid:{len(self.state.grid_trades)} Drawdown:{drawdown_pct:.1f}%"
        }
        
        forex_logger.log_signal(self.timeframe, candle_data, signal, indicators)

    
    def set_initial_balance(self, balance: float):
        """Set initial balance for MaxDrawdownPercent calculation"""
        self.state.initial_balance = balance
        logger.info(f"Initial balance set: ${balance}")
    
    def get_magic_number(self) -> int:
        """Get magic number for trade identification"""
        return self.config.magic_number
    
    def reset_strategy(self):
        """Reset strategy state."""
        logger.info("Resetting strategy state")
        self.state = GoldBuyDipState()
        self.candles.clear()
        logger.info(f"Strategy reset with intelligent filtering (min move: {self.state.min_price_move_for_new_grid}%)")