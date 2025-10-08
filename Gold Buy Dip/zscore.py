import statistics
from typing import List
from app.utilities.forex_logger import forex_logger

logger = forex_logger.get_logger(__name__)

def calculate_zscore(prices: List[float], period: int) -> float:
    """Calculate Z-score for the latest price -  compatible."""
    if len(prices) < period + 1:
        logger.error(f"Insufficient data for Z-score: {len(prices)}/{period + 1}")
        raise ValueError(f"Insufficient data for Z-score calculation: {len(prices)}/{period + 1}")
    
    # Fix #5: Exclude current candle from mean/stddev calculation 
    current_price = prices[-1]
    historical_prices = prices[-(period + 1):-1]  # Exclude current candle
    
    if len(historical_prices) < 2:
        logger.warning("Insufficient historical data for standard deviation")
        return 0.0
    
    mean_price = statistics.mean(historical_prices)
    # Use population standard deviation (divide by N) to match MT5
    stdev_price = statistics.pstdev(historical_prices)
    
    if stdev_price == 0:
        logger.warning("Standard deviation is 0, returning Z-score of 0")
        return 0.0
    
    zscore = (current_price - mean_price) / stdev_price
    logger.debug(f"Z-score calculated: {zscore:.3f} (price: ${current_price}, mean: ${mean_price:.2f}, stdev: {stdev_price:.2f})")
    return zscore