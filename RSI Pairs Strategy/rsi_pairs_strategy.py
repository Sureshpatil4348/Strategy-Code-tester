"""RSI Pairs Trading Strategy Implementation"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session
from app.models.trading_models import MarketData, TradeSignal, TradeDirection
from app.models.strategy_models import RSIPairsConfig, RSIPairsState
from app.indicators.rsi import calculate_rsi
from app.indicators.atr import calculate_atr
from app.utilities.forex_logger import forex_logger
from app.services.base_strategy import BaseStrategy

logger = forex_logger.get_logger(__name__)

class RSIPairsStrategy(BaseStrategy):
    """RSI Pairs Trading Strategy with positive/negative correlation modes"""
    
    def __init__(self, config: RSIPairsConfig, pair: str, timeframe: str = "5M", db: Session = None):
        super().__init__(pair, timeframe, "rsi_pairs", db)
        self.config = config
        self.state = RSIPairsState()
        
        # Store both symbols for pairs trading
        self.symbol1 = config.symbol1
        self.symbol2 = config.symbol2
        

        
        logger.info(f"RSI Pairs Strategy initialized: {self.symbol1}/{self.symbol2} ({config.mode} correlation)")
    
    def add_candle_data(self, symbol: str, candle: MarketData):
        """Add candle data for specific symbol"""
        candle_dict = {
            'timestamp': candle.timestamp,
            'open': candle.open,
            'high': candle.high,
            'low': candle.low,
            'close': candle.close
        }
        
        # Keep only necessary candles
        max_needed = max(self.config.rsi_period, self.config.atr_period) + 10
        
        if symbol == self.symbol1:
            self.state.s1_candles.append(candle_dict)
            if len(self.state.s1_candles) > max_needed:
                self.state.s1_candles = self.state.s1_candles[-max_needed:]
        elif symbol == self.symbol2:
            self.state.s2_candles.append(candle_dict)
            if len(self.state.s2_candles) > max_needed:
                self.state.s2_candles = self.state.s2_candles[-max_needed:]
    
    def calculate_indicators(self) -> Dict[str, float]:
        """Calculate RSI and ATR for both symbols"""
        indicators = {
            's1_rsi': 50.0, 's2_rsi': 50.0,
            's1_atr': 0.0, 's2_atr': 0.0
        }
        
        # Calculate RSI for symbol1
        if len(self.state.s1_candles) >= self.config.rsi_period + 1:
            s1_closes = [c['close'] for c in self.state.s1_candles]
            indicators['s1_rsi'] = calculate_rsi(s1_closes, self.config.rsi_period)
        
        # Calculate RSI for symbol2
        if len(self.state.s2_candles) >= self.config.rsi_period + 1:
            s2_closes = [c['close'] for c in self.state.s2_candles]
            indicators['s2_rsi'] = calculate_rsi(s2_closes, self.config.rsi_period)
        
        # Calculate ATR for symbol1
        if len(self.state.s1_candles) >= self.config.atr_period:
            s1_market_data = [MarketData(
                timestamp=c['timestamp'], open=c['open'], high=c['high'],
                low=c['low'], close=c['close']
            ) for c in self.state.s1_candles]
            indicators['s1_atr'] = calculate_atr(s1_market_data, self.config.atr_period)
        
        # Calculate ATR for symbol2
        if len(self.state.s2_candles) >= self.config.atr_period:
            s2_market_data = [MarketData(
                timestamp=c['timestamp'], open=c['open'], high=c['high'],
                low=c['low'], close=c['close']
            ) for c in self.state.s2_candles]
            indicators['s2_atr'] = calculate_atr(s2_market_data, self.config.atr_period)
        
        return indicators
    
    def get_pip_size(self, symbol: str) -> float:
        """Get pip size for symbol with comprehensive support (from notebook)"""
        symbol = symbol.upper()
        
        # Precious metals
        if symbol.startswith('XAU'):  # Gold (XAUUSD, XAUGBP, etc.)
            return 0.1
        elif symbol.startswith('XAG'):  # Silver (XAGUSD, XAGGBP, etc.)
            return 0.001
        elif symbol.startswith('XPD') or symbol.startswith('XPT'):  # Palladium/Platinum
            return 0.1
        
        # JPY pairs - pip is always 0.01 regardless of digits
        elif 'JPY' in symbol:
            return 0.01
        
        # Standard forex pairs - assume 5-digit broker (most common)
        else:
            return 0.0001  # For 5-digit broker, pip = 0.0001
    
    def calculate_hedge_ratio(self, s1_atr: float, s2_atr: float) -> float:
        """Calculate hedge ratio using ATR normalized to pips (from notebook)"""
        # Convert ATR to pips for both symbols
        s1_pip_size = self.get_pip_size(self.symbol1)
        s2_pip_size = self.get_pip_size(self.symbol2)
        
        s1_atr_pips = s1_atr / s1_pip_size
        s2_atr_pips = s2_atr / s2_pip_size
        
        # Validate ATR values
        if s1_atr_pips <= 0 or s2_atr_pips <= 0:
            logger.warning(f"Invalid ATR values for {self.symbol1}/{self.symbol2}, using 1:1 ratio")
            return 1.0
        
        # Calculate volatility ratio
        volatility_ratio = s1_atr_pips / s2_atr_pips
        
        # Apply configurable bounds to prevent extreme ratios
        if volatility_ratio > self.config.max_hedge_ratio:
            logger.warning(f"Extreme ratio {volatility_ratio:.2f} capped at {self.config.max_hedge_ratio}")
            volatility_ratio = self.config.max_hedge_ratio
        elif volatility_ratio < self.config.min_hedge_ratio:
            logger.warning(f"Extreme ratio {volatility_ratio:.2f} raised to {self.config.min_hedge_ratio}")
            volatility_ratio = self.config.min_hedge_ratio
        
        return volatility_ratio
    
    def calculate_lot_sizes(self, s1_atr: float, s2_atr: float, account_balance: float) -> tuple[float, float]:
        """Calculate lot sizes with ATR-based hedge ratios and risk management"""
        # Use base lot size for symbol1 (from notebook approach)
        s1_lots = self.config.base_lot_size
        
        # Calculate hedge ratio using ATR normalized to pips
        hedge_ratio = self.calculate_hedge_ratio(s1_atr, s2_atr)
        s2_lots = s1_lots * hedge_ratio
        
        # Apply broker constraints and safety bounds
        s1_lots = self.normalize_lot_size(self.symbol1, s1_lots)
        s2_lots = self.normalize_lot_size(self.symbol2, s2_lots)
        
        return s1_lots, s2_lots
    
    def normalize_lot_size(self, symbol: str, lot_size: float) -> float:
        """Normalize lot size to broker requirements with configurable safety bounds"""
        # Apply configurable safety bounds
        lot_size = max(self.config.safety_min_lot, min(self.config.safety_max_lot, lot_size))
        
        # Round to standard step (0.01)
        lot_size = round(lot_size / 0.01) * 0.01
        
        return max(self.config.safety_min_lot, lot_size)
    
    def check_entry_conditions(self, indicators: Dict[str, float]) -> Optional[str]:
        """Check entry conditions based on correlation mode"""
        s1_rsi = indicators['s1_rsi']
        s2_rsi = indicators['s2_rsi']
        s1_atr = indicators['s1_atr']
        s2_atr = indicators['s2_atr']
        
        # Ensure ATR values are valid
        if s1_atr <= 0 or s2_atr <= 0:
            return None
        
        if self.config.mode == "negative":
            # Negative correlation: both overbought -> short both, both oversold -> long both
            if s1_rsi > self.config.rsi_overbought and s2_rsi > self.config.rsi_overbought:
                return "short"
            elif s1_rsi < self.config.rsi_oversold and s2_rsi < self.config.rsi_oversold:
                return "long"
        elif self.config.mode == "positive":
            # Positive correlation: divergence signals (placeholder - needs specific implementation)
            # TODO: Implement positive correlation logic when requirements are defined
            pass
        
        return None
    
    def check_exit_conditions(self, current_s1_price: float, current_s2_price: float) -> Optional[tuple]:
        """Check USD-based exit conditions with comprehensive risk management"""
        if not self.state.in_trade or not self.state.entry_time:
            return None
        
        # Calculate current USD P&L for both positions using MT5-style calculation
        s1_pnl = self.calculate_pnl_usd(
            self.symbol1, self.state.trade_direction, 
            self.state.lot_size_s1, self.state.entry_price_s1, current_s1_price
        )
        
        s2_pnl = self.calculate_pnl_usd(
            self.symbol2, self.state.trade_direction,
            self.state.lot_size_s2, self.state.entry_price_s2, current_s2_price
        )
        
        total_pnl = s1_pnl + s2_pnl
        
        # Check profit target
        if total_pnl >= self.config.profit_target_usd:
            return ("PROFIT_TARGET", total_pnl, s1_pnl, s2_pnl)
        
        # Check stop loss
        if total_pnl <= self.config.stop_loss_usd:
            return ("STOP_LOSS", total_pnl, s1_pnl, s2_pnl)
        
        # Check time limit
        current_time = datetime.now()
        trade_duration = current_time - self.state.entry_time
        if trade_duration.total_seconds() / 3600 >= self.config.max_trade_hours:
            return ("TIME_LIMIT", total_pnl, s1_pnl, s2_pnl)
        
        return None
    
    def _process_market_data(self, candle: MarketData) -> Optional[TradeSignal]:
        """Process market data for pairs trading"""
        # This method processes data for the primary symbol (pair)
        # For now, assume this is symbol1 data and simulate symbol2 data
        self.add_candle_data(self.symbol1, candle)
        
        # Simulate symbol2 data if missing (temporary fix)
        if len(self.state.s2_candles) < len(self.state.s1_candles):
            # Create synthetic symbol2 data based on symbol1 with slight variation
            s2_candle = {
                'timestamp': candle.timestamp,
                'open': candle.open * 0.85,  # Simulate GBPUSD vs EURUSD
                'high': candle.high * 0.85,
                'low': candle.low * 0.85,
                'close': candle.close * 0.85
            }
            self.state.s2_candles.append(s2_candle)
            max_needed = max(self.config.rsi_period, self.config.atr_period) + 10
            if len(self.state.s2_candles) > max_needed:
                self.state.s2_candles = self.state.s2_candles[-max_needed:]
        
        # Check if we have sufficient data
        if (len(self.state.s1_candles) < self.config.rsi_period + 1 or 
            len(self.state.s2_candles) < self.config.rsi_period + 1):
            return None
        
        indicators = self.calculate_indicators()
        
        # Check exit conditions first
        if self.state.in_trade:
            exit_result = self.check_exit_conditions(candle.close, 
                self.state.s2_candles[-1]['close'] if self.state.s2_candles else candle.close)
            if exit_result:
                exit_reason, total_pnl, s1_pnl, s2_pnl = exit_result
                
                # Store exit information
                self.state.exit_reason = exit_reason
                self.state.total_pnl = total_pnl
                self.state.s1_pnl = s1_pnl
                self.state.s2_pnl = s2_pnl
                
                self.state.in_trade = False
                self.state.entry_time = None
                
                # Store exit prices for database logging
                self.state.exit_price_s1 = candle.close
                self.state.exit_price_s2 = self.state.s2_candles[-1]['close'] if self.state.s2_candles else candle.close
                
                logger.info(f"RSI Pairs Exit: {exit_reason} | Total P&L: ${total_pnl:.2f}")
                
                return TradeSignal(
                    action="CLOSE_ALL",
                    lot_size=0,
                    reason=f"Exit: {exit_reason} | P&L: ${total_pnl:.2f}"
                )
        
        # Check entry conditions
        if not self.state.in_trade:
            trade_type = self.check_entry_conditions(indicators)
            if trade_type:

                
                # Calculate lot sizes with ATR-based hedge ratios
                # No account balance calculation - use configured lot sizes directly
                account_balance = 0  # Not used
                
                s1_lots, s2_lots = self.calculate_lot_sizes(
                    indicators['s1_atr'], indicators['s2_atr'], account_balance
                )
                
                # Calculate hedge ratio for storage
                hedge_ratio = self.calculate_hedge_ratio(indicators['s1_atr'], indicators['s2_atr'])
                
                # Store comprehensive trade state
                self.state.in_trade = True
                self.state.entry_time = datetime.now()
                self.state.entry_price_s1 = candle.close
                self.state.entry_price_s2 = self.state.s2_candles[-1]['close'] if self.state.s2_candles else candle.close
                self.state.lot_size_s1 = s1_lots
                self.state.lot_size_s2 = s2_lots
                self.state.trade_direction = trade_type
                
                # Store entry conditions for analysis (from notebook)
                self.state.entry_s1_rsi = indicators['s1_rsi']
                self.state.entry_s2_rsi = indicators['s2_rsi']
                self.state.entry_s1_atr = indicators['s1_atr']
                self.state.entry_s2_atr = indicators['s2_atr']
                self.state.hedge_ratio = hedge_ratio
                
                logger.info(f"RSI Pairs Entry: {trade_type} {self.symbol1}({s1_lots}) + {self.symbol2}({s2_lots})")
                
                # Return signal for symbol1 (in full implementation, would handle both symbols)
                action = "BUY" if trade_type == "long" else "SELL"
                signal = TradeSignal(
                    action=action,
                    lot_size=s1_lots,
                    reason=f"RSI Pairs {trade_type}: RSI1={indicators['s1_rsi']:.1f}, RSI2={indicators['s2_rsi']:.1f}"
                )
                
                # Store entry price in signal for proper database logging
                signal.entry_price = candle.close
                return signal
        
        return None
    
    def process_symbol_data(self, symbol: str, candle: MarketData) -> Optional[TradeSignal]:
        """Process data for specific symbol in pairs trading"""
        self.add_candle_data(symbol, candle)
        
        # Only process signals when we have data from both symbols
        if symbol == self.symbol1:
            return self._process_market_data(candle)
        
        return None
    
    def get_strategy_status(self) -> Dict[str, Any]:
        """Get current strategy status with capital allocation"""
        indicators = self.calculate_indicators()
        
        # Direct MT5 trading - no capital allocation
        capital_info = {
            'allocated_capital': 0.0,
            'can_trade': True,
            'risk_status': None,
            'message': 'Direct MT5 trading - no capital allocation'
        }
        
        return {
            'mode': self.config.mode,
            'symbols': f"{self.symbol1}/{self.symbol2}",
            'in_trade': self.state.in_trade,
            'trade_direction': self.state.trade_direction,
            'entry_time': self.state.entry_time.isoformat() if self.state.entry_time else None,
            'indicators': indicators,
            's1_candles': len(self.state.s1_candles),
            's2_candles': len(self.state.s2_candles),
            'lot_sizes': {
                's1': self.state.lot_size_s1,
                's2': self.state.lot_size_s2
            },
            'capital_allocation': capital_info,
            'entry_conditions': {
                's1_rsi': self.state.entry_s1_rsi,
                's2_rsi': self.state.entry_s2_rsi,
                's1_atr': self.state.entry_s1_atr,
                's2_atr': self.state.entry_s2_atr,
                'hedge_ratio': self.state.hedge_ratio
            },
            'risk_management': {
                'profit_target_usd': self.config.profit_target_usd,
                'stop_loss_usd': self.config.stop_loss_usd,
                'max_trade_hours': self.config.max_trade_hours
            },
            'last_exit': {
                'reason': self.state.exit_reason,
                'total_pnl': self.state.total_pnl,
                's1_pnl': self.state.s1_pnl,
                's2_pnl': self.state.s2_pnl,
                'duration_hours': self.state.trade_duration_hours
            } if self.state.exit_reason else None
        }
    

    

    

    
    def calculate_pnl_usd(self, symbol: str, trade_type: str, lot_size: float, entry_price: float, exit_price: float) -> float:
        """Calculate P&L in USD using simplified calculation (production would use MT5 order_calc_profit)"""
        pip_size = self.get_pip_size(symbol)
        
        # Calculate pips profit/loss
        if trade_type == 'long':
            pips = (exit_price - entry_price) / pip_size
        elif trade_type == 'short':
            pips = (entry_price - exit_price) / pip_size
        else:
            return 0.0
        
        # Convert pips to USD (simplified - actual calculation depends on account currency and symbol)
        # This is a simplified calculation - in production, use MT5's order_calc_profit
        pip_value = self.get_pip_value(symbol, lot_size)
        usd_pnl = pips * pip_value
        
        return usd_pnl
    
    def get_pip_value(self, symbol: str, lot_size: float) -> float:
        """Get pip value in USD for given symbol and lot size (simplified)"""
        symbol = symbol.upper()
        
        # Simplified pip values (actual values depend on current exchange rates)
        if 'JPY' in symbol:
            # For JPY pairs, 1 pip = 0.01, standard lot pip value ≈ $9.43 (varies with USD/JPY rate)
            return 9.43 * lot_size
        elif symbol.startswith('XAU'):  # Gold
            # For XAUUSD, 1 pip = 0.1, standard lot pip value = $1
            return 1.0 * lot_size
        elif symbol.startswith('XAG'):  # Silver
            # For XAGUSD, 1 pip = 0.001, standard lot pip value = $5
            return 5.0 * lot_size
        else:
            # For major USD pairs, 1 pip = 0.0001, standard lot pip value = $10
            return 10.0 * lot_size
    
    def calculate_pips(self, symbol: str, entry_price: float, current_price: float, trade_type: str) -> float:
        """Calculate profit/loss in pips"""
        pip_size = self.get_pip_size(symbol)
        
        if trade_type == 'long':
            pips = (current_price - entry_price) / pip_size
        elif trade_type == 'short':
            pips = (entry_price - current_price) / pip_size
        else:
            pips = 0.0
        
        return pips
    
    def reset_strategy(self):
        """Reset strategy state"""
        logger.info("Resetting RSI Pairs strategy state")
        self.state = RSIPairsState()