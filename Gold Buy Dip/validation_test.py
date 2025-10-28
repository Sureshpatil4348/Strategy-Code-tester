"""
Validation Test Script for Gold Buy Dip Strategy
Tests critical differences between MT4 and Python implementation
"""

def test_percentage_calculation():
    """Test Issue #1 and #2: Percentage calculation logic"""
    
    print("=" * 80)
    print("TEST 1: Percentage Calculation Logic")
    print("=" * 80)
    
    # Simulated candle data (close prices)
    # Index in MT4: [0]=current, [1]=previous, [2]=older, [3]=oldest...
    # For lookback of 50, MT4 uses indices 2 to 51 (50 candles, excluding 0 and 1)
    
    candles = [2000, 2010, 2020, 2030, 2040, 2050, 2060, 2070, 2080, 2090, 2100]
    # Simulate: oldest to newest
    
    lookback = 5
    
    print(f"\nCandle prices (oldest to newest): {candles}")
    print(f"Lookback period: {lookback}")
    
    # MT4 Logic (CORRECT)
    print("\n--- MT4 Logic ---")
    current_close_mt4 = candles[-2]  # Close[1] - previous candle
    lookback_candles_mt4 = candles[-(lookback + 2):-2]  # Excludes indices 0 and 1
    highest_mt4 = max(lookback_candles_mt4)
    lowest_mt4 = min(lookback_candles_mt4)
    
    pct_from_high_mt4 = ((current_close_mt4 - highest_mt4) / highest_mt4) * 100
    pct_from_low_mt4 = ((current_close_mt4 - lowest_mt4) / lowest_mt4) * 100
    
    print(f"Current Close (Close[1]): {current_close_mt4}")
    print(f"Lookback candles: {lookback_candles_mt4}")
    print(f"Highest: {highest_mt4}, Lowest: {lowest_mt4}")
    print(f"% from High: {pct_from_high_mt4:.2f}%")
    print(f"% from Low: {pct_from_low_mt4:.2f}%")
    
    # Python Logic (CURRENT - WRONG)
    print("\n--- Python Logic (Current - WRONG) ---")
    current_price_py_wrong = candles[-1]
    recent_candles_py_wrong = candles[-lookback:]  # Includes current
    highest_py_wrong = max(recent_candles_py_wrong)
    lowest_py_wrong = min(recent_candles_py_wrong)
    
    pct_from_low_py_wrong = ((current_price_py_wrong - lowest_py_wrong) / lowest_py_wrong) * 100
    pct_from_high_py_wrong = ((highest_py_wrong - current_price_py_wrong) / highest_py_wrong) * 100
    
    print(f"Current Price: {current_price_py_wrong}")
    print(f"Recent candles: {recent_candles_py_wrong}")
    print(f"Highest: {highest_py_wrong}, Lowest: {lowest_py_wrong}")
    print(f"% from Low: {pct_from_low_py_wrong:.2f}%")
    print(f"% from High (wrong formula): {pct_from_high_py_wrong:.2f}%")
    
    # Python Logic (FIXED - CORRECT)
    print("\n--- Python Logic (Fixed - CORRECT) ---")
    current_price_py_fixed = candles[-1]
    recent_candles_py_fixed = candles[-(lookback + 1):-1]  # Excludes current
    highest_py_fixed = max(recent_candles_py_fixed)
    lowest_py_fixed = min(recent_candles_py_fixed)
    
    pct_from_high_py_fixed = ((current_price_py_fixed - highest_py_fixed) / highest_py_fixed) * 100
    pct_from_low_py_fixed = ((current_price_py_fixed - lowest_py_fixed) / lowest_py_fixed) * 100
    
    print(f"Current Price: {current_price_py_fixed}")
    print(f"Recent candles: {recent_candles_py_fixed}")
    print(f"Highest: {highest_py_fixed}, Lowest: {lowest_py_fixed}")
    print(f"% from High: {pct_from_high_py_fixed:.2f}%")
    print(f"% from Low: {pct_from_low_py_fixed:.2f}%")
    
    # Comparison
    print("\n--- COMPARISON ---")
    print(f"MT4 vs Python (Wrong):")
    print(f"  High/Low range match: {highest_mt4 == highest_py_wrong and lowest_mt4 == lowest_py_wrong}")
    print(f"  % from Low match: {abs(pct_from_low_mt4 - pct_from_low_py_wrong) < 0.01}")
    print(f"  % from High match: {abs(pct_from_high_mt4 - pct_from_high_py_wrong) < 0.01}")
    
    print(f"\nMT4 vs Python (Fixed):")
    print(f"  High/Low range match: {highest_mt4 == highest_py_fixed and lowest_mt4 == lowest_py_fixed}")
    print(f"  % from Low match: {abs(pct_from_low_mt4 - pct_from_low_py_fixed) < 0.01}")
    print(f"  % from High match: {abs(pct_from_high_mt4 - pct_from_high_py_fixed) < 0.01}")
    
    return {
        'mt4_pct_high': pct_from_high_mt4,
        'mt4_pct_low': pct_from_low_mt4,
        'py_wrong_pct_high': pct_from_high_py_wrong,
        'py_wrong_pct_low': pct_from_low_py_wrong,
        'py_fixed_pct_high': pct_from_high_py_fixed,
        'py_fixed_pct_low': pct_from_low_py_fixed
    }


def test_zscore_calculation():
    """Test Issue #5: Z-score calculation with proper candle exclusion"""
    
    print("\n" + "=" * 80)
    print("TEST 2: Z-Score Calculation")
    print("=" * 80)
    
    # Sample close prices
    closes = [2000, 2010, 2005, 2015, 2020, 2025, 2030, 2035, 2040, 2045, 2050]
    period = 5
    
    print(f"\nClose prices: {closes}")
    print(f"Z-Score period: {period}")
    
    # MT4 Logic - Uses Close[1] to Close[period], excludes Close[0]
    print("\n--- MT4 Z-Score Calculation ---")
    current_price_mt4 = closes[-1]  # Close[0] - current candle
    historical_closes_mt4 = closes[-(period + 1):-1]  # Close[1] to Close[period]
    
    mean_mt4 = sum(historical_closes_mt4) / len(historical_closes_mt4)
    variance_mt4 = sum((x - mean_mt4) ** 2 for x in historical_closes_mt4) / len(historical_closes_mt4)
    std_dev_mt4 = variance_mt4 ** 0.5
    zscore_mt4 = (current_price_mt4 - mean_mt4) / std_dev_mt4 if std_dev_mt4 != 0 else 0
    
    print(f"Current Price (Close[0]): {current_price_mt4}")
    print(f"Historical closes (Close[1] to Close[{period}]): {historical_closes_mt4}")
    print(f"Mean: {mean_mt4:.2f}")
    print(f"Std Dev: {std_dev_mt4:.2f}")
    print(f"Z-Score: {zscore_mt4:.4f}")
    
    # Python Logic (if including current candle - WRONG)
    print("\n--- Python Z-Score (if includes current - WRONG) ---")
    all_closes_py_wrong = closes[-period:]  # Includes current
    mean_py_wrong = sum(all_closes_py_wrong) / len(all_closes_py_wrong)
    variance_py_wrong = sum((x - mean_py_wrong) ** 2 for x in all_closes_py_wrong) / len(all_closes_py_wrong)
    std_dev_py_wrong = variance_py_wrong ** 0.5
    zscore_py_wrong = (closes[-1] - mean_py_wrong) / std_dev_py_wrong if std_dev_py_wrong != 0 else 0
    
    print(f"All closes (includes current): {all_closes_py_wrong}")
    print(f"Mean: {mean_py_wrong:.2f}")
    print(f"Std Dev: {std_dev_py_wrong:.2f}")
    print(f"Z-Score: {zscore_py_wrong:.4f}")
    
    # Comparison
    print("\n--- COMPARISON ---")
    print(f"Z-Score difference: {abs(zscore_mt4 - zscore_py_wrong):.4f}")
    print(f"Match: {abs(zscore_mt4 - zscore_py_wrong) < 0.01}")
    
    return {
        'mt4_zscore': zscore_mt4,
        'py_wrong_zscore': zscore_py_wrong,
        'difference': abs(zscore_mt4 - zscore_py_wrong)
    }


def test_grid_spacing():
    """Test Issue #3: Grid spacing reference price"""
    
    print("\n" + "=" * 80)
    print("TEST 3: Grid Spacing Calculation")
    print("=" * 80)
    
    # Simulate grid trades
    grid_trades = [
        {"price": 2050.00, "lot_size": 0.1, "grid_level": 0},
        {"price": 2045.00, "lot_size": 0.1, "grid_level": 1},
    ]
    
    current_market_price = 2040.00
    grid_percent = 0.5  # 0.5%
    
    print(f"\nGrid trades: {grid_trades}")
    print(f"Current market price: {current_market_price}")
    print(f"Grid spacing percent: {grid_percent}%")
    
    # MT4 Logic - Always uses LastGridPrice
    print("\n--- MT4 Grid Spacing ---")
    last_grid_price_mt4 = grid_trades[-1]["price"]
    grid_distance_mt4 = last_grid_price_mt4 * (grid_percent / 100)
    next_grid_price_mt4 = last_grid_price_mt4 - grid_distance_mt4  # For BUY grid
    
    print(f"Last grid price: {last_grid_price_mt4}")
    print(f"Grid distance: {grid_distance_mt4:.2f}")
    print(f"Next grid price: {next_grid_price_mt4:.2f}")
    
    # Python Logic (Current - with fallback)
    print("\n--- Python Grid Spacing (with market price fallback) ---")
    if grid_trades:
        reference_price_py = grid_trades[-1]["price"]
    else:
        reference_price_py = current_market_price  # This is the problem
    
    grid_distance_py = reference_price_py * (grid_percent / 100)
    next_grid_price_py = reference_price_py - grid_distance_py
    
    print(f"Reference price: {reference_price_py}")
    print(f"Grid distance: {grid_distance_py:.2f}")
    print(f"Next grid price: {next_grid_price_py:.2f}")
    
    # Test scenario where grid_trades is empty (edge case)
    print("\n--- Edge Case: Empty Grid Trades ---")
    print("MT4: Would never calculate spacing without LastGridPrice set")
    print("Python (current): Would use current market price (WRONG)")
    print("Python (fixed): Should not calculate spacing if no grid trades exist")
    
    return {
        'mt4_next_price': next_grid_price_mt4,
        'py_next_price': next_grid_price_py,
        'match': abs(next_grid_price_mt4 - next_grid_price_py) < 0.01
    }


def test_take_profit_calculation():
    """Test take profit calculation"""
    
    print("\n" + "=" * 80)
    print("TEST 4: Volume-Weighted Take Profit Calculation")
    print("=" * 80)
    
    # Simulate BUY grid trades
    grid_trades = [
        {"price": 2050.00, "lot_size": 0.10, "direction": "BUY"},
        {"price": 2045.00, "lot_size": 0.10, "direction": "BUY"},
        {"price": 2040.00, "lot_size": 0.15, "direction": "BUY"},  # Progressive lots
    ]
    
    take_profit_points = 200  # MT4 parameter
    take_profit_percent = 1.0  # Alternative percentage-based
    
    print(f"\nGrid trades:")
    for i, trade in enumerate(grid_trades):
        print(f"  Trade {i}: Price={trade['price']}, Lot={trade['lot_size']}")
    
    # Volume-weighted average price
    total_lots = sum(t["lot_size"] for t in grid_trades)
    vwap = sum(t["price"] * t["lot_size"] for t in grid_trades) / total_lots
    
    print(f"\nTotal lots: {total_lots}")
    print(f"VWAP: {vwap:.2f}")
    
    # MT4 Logic - Points based
    print("\n--- MT4 Take Profit (Points) ---")
    # For XAUUSD, Point = 0.01 typically
    point_value = 0.01
    tp_mt4_points = vwap + (take_profit_points * point_value)
    print(f"Point value: {point_value}")
    print(f"Take profit points: {take_profit_points}")
    print(f"Target price: {tp_mt4_points:.2f}")
    
    # Python Logic - Points based (with divisor)
    print("\n--- Python Take Profit (Points with divisor) ---")
    divisor = 100  # For XAUUSD
    tp_py_points = vwap + (take_profit_points / divisor)
    print(f"Divisor: {divisor}")
    print(f"Take profit points: {take_profit_points}")
    print(f"Target price: {tp_py_points:.2f}")
    
    # Percentage based
    print("\n--- Take Profit (Percentage) ---")
    tp_percent = vwap * (1 + take_profit_percent / 100)
    print(f"Take profit percent: {take_profit_percent}%")
    print(f"Target price: {tp_percent:.2f}")
    
    print("\n--- COMPARISON ---")
    print(f"MT4 points vs Python points match: {abs(tp_mt4_points - tp_py_points) < 0.01}")
    print(f"Difference: {abs(tp_mt4_points - tp_py_points):.4f}")
    
    return {
        'vwap': vwap,
        'mt4_tp': tp_mt4_points,
        'py_tp': tp_py_points,
        'percent_tp': tp_percent
    }


if __name__ == "__main__":
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 15 + "GOLD BUY DIP STRATEGY VALIDATION TESTS" + " " * 24 + "║")
    print("╚" + "=" * 78 + "╝")
    
    results = {}
    
    # Run all tests
    results['percentage'] = test_percentage_calculation()
    results['zscore'] = test_zscore_calculation()
    results['grid_spacing'] = test_grid_spacing()
    results['take_profit'] = test_take_profit_calculation()
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    print("\n✅ = PASS | ❌ = FAIL")
    print("\n1. Percentage Calculation:")
    pct_match = abs(results['percentage']['mt4_pct_low'] - results['percentage']['py_fixed_pct_low']) < 0.01
    print(f"   {'✅' if pct_match else '❌'} Fixed Python logic matches MT4")
    
    print("\n2. Z-Score Calculation:")
    zscore_diff = results['zscore']['difference']
    print(f"   ⚠️  Difference: {zscore_diff:.4f} (check indicator implementation)")
    
    print("\n3. Grid Spacing:")
    grid_match = results['grid_spacing']['match']
    print(f"   {'✅' if grid_match else '❌'} Grid spacing calculation {'matches' if grid_match else 'differs'}")
    
    print("\n4. Take Profit:")
    tp_diff = abs(results['take_profit']['mt4_tp'] - results['take_profit']['py_tp'])
    print(f"   {'✅' if tp_diff < 0.01 else '❌'} TP calculation difference: {tp_diff:.4f}")
    
    print("\n" + "=" * 80)
    print("CRITICAL RECOMMENDATIONS:")
    print("=" * 80)
    print("""
1. FIX IMMEDIATELY: Update check_percentage_trigger() method:
   - Change: recent_candles = self.candles[-lookback_count:]
   - To:     recent_candles = self.candles[-(lookback_count + 1):-1]

2. FIX IMMEDIATELY: Update percentage formula for high:
   - Change: pct_from_high = ((highest_high - current_price) / highest_high) * 100
   - To:     pct_from_high = ((current_price - highest_high) / highest_high) * 100
   - And:    Check against NEGATIVE threshold: pct_from_high <= -threshold

3. VERIFY: Check calculate_zscore() implementation excludes current candle

4. FIX: Remove market price fallback in calculate_grid_spacing()

5. ADD: Trade ticket/ID tracking to grid_trades dictionary

6. TEST: Run this validation script after fixes to verify corrections
    """)
    
    print("\n" + "=" * 80)
    print("END OF VALIDATION TESTS")
    print("=" * 80 + "\n")
