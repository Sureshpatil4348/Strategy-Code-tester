from typing import List
from app.models.trading_models import MarketData
from app.utilities.forex_logger import forex_logger

logger = forex_logger.get_logger(__name__)

def calculate_true_range(current: MarketData, previous: MarketData) -> float:
    """Calculate True Range for a single candle."""
    tr1 = current.high - current.low
    tr2 = abs(current.high - previous.close)
    tr3 = abs(current.low - previous.close)
    return max(tr1, tr2, tr3)

def calculate_atr(candles: List[MarketData], period: int) -> float:
    """Calculate Average True Range."""
    if len(candles) < period + 1:
        logger.debug(f"Insufficient candles for ATR: {len(candles)}/{period + 1}")
        # Fix #3: Return minimum safety value instead of 0
        return 0.001
    
    true_ranges = [calculate_true_range(candles[i], candles[i-1]) for i in range(1, len(candles))]
    
    if len(true_ranges) < period:
        logger.debug(f"Insufficient true ranges for ATR: {len(true_ranges)}/{period}")
        # Fix #3: Return minimum safety value instead of 0
        return 0.001
    
    atr = sum(true_ranges[-period:]) / period
    logger.debug(f"ATR calculated: {atr:.4f} over {period} periods")
    return atr