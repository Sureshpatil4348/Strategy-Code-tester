# RSI Pairs Strategy Python Review

This note captures the key gaps I found between `rsi_pairs_strategy.py` and the reference notebooks (`rsi_pairs_trading_strategy.ipynb` for the negative-correlation setup and its positive-correlation companion). Each item pinpoints where the Python service diverges so you can decide what needs to change before trading live capital.

## 1. Positive/negative mode selector is only half implemented
- **Notebook & spec:** The configuration explicitly exposes a `mode ∈ {"positive", "negative"}` switch, and every major logic block is supposed to branch on that setting. The design doc reiterates that both modes must be supported.【F:RSI Pairs Strategy/rsi_pairs_correlation_strategy.md†L1-L6】
- **Python:** `check_entry_conditions` handles the negative-correlation rules but the positive branch is just a TODO placeholder, so selecting `mode="positive"` never returns a signal.【F:RSI Pairs Strategy/rsi_pairs_strategy.py†L161-L184】

**Impact:** Any deployment that enables the positive-correlation workflow will sit idle, even though the notebooks provide dedicated scenarios for it. You will need the actual divergence/convergence rules implemented before live use.

## 2. Second-leg market data is fabricated instead of read from MT5
- **Notebook:** Each backtest pulls real candles for *both* symbols via `mt5.copy_rates_range`, merges them on the shared timestamp index, and drops any rows where either leg is missing so the indicators stay synchronized.【F:RSI Pairs Strategy/rsi_pairs_trading_strategy.ipynb†L1954-L1974】
- **Python:** `_process_market_data` only ingests the primary symbol’s candle. Whenever the secondary buffer is shorter it synthesizes a fake bar by multiplying symbol1’s OHLC values by 0.85 rather than consuming actual feeds.【F:RSI Pairs Strategy/rsi_pairs_strategy.py†L219-L238】

**Impact:** All RSI/ATR values for the hedge leg are disconnected from the real market. Divergences, volatility ratios, and USD P&L are therefore meaningless compared with the MT5 notebooks. You need genuine symbol2 ticks/bars wired in before expecting parity.

## 3. Trade execution only emits one leg
- **Notebook:** When a signal fires the backtest records both legs (lot sizes, entry prices) and evaluates P&L for each side in dollars.【F:RSI Pairs Strategy/rsi_pairs_trading_strategy.ipynb†L2059-L2088】
- **Python:** After storing its internal state the strategy returns a single `TradeSignal` for `symbol1` and never issues an order for `symbol2`; even the close instruction is a generic `CLOSE_ALL` without lot details for the hedge leg.【F:RSI Pairs Strategy/rsi_pairs_strategy.py†L289-L320】【F:RSI Pairs Strategy/rsi_pairs_strategy.py†L267-L273】

**Impact:** Unless the wider trading engine implicitly mirrors orders for `symbol2`, the current implementation will enter/exit only one side of the pair, breaking the hedged exposure that the notebooks assume.

## 4. Broker-specific pip/lot metadata is hard-coded
- **Notebook:** Helper functions read `mt5.symbol_info` so pip size, min/max volume, and lot step all come from the broker, then clamp with safety bounds before rounding.【F:RSI Pairs Strategy/rsi_pairs_trading_strategy.ipynb†L1688-L1759】
- **Python:** `get_pip_size` guesses pip size from string patterns and assumes a 5-digit broker, while `normalize_lot_size` relies solely on static safety limits from the config rather than broker constraints.【F:RSI Pairs Strategy/rsi_pairs_strategy.py†L89-L159】

**Impact:** For symbols whose contract specs differ from the assumptions (e.g., 4-digit FX, indices, brokers with custom lot steps) pip values, hedge ratios, and rounded lot sizes will deviate from the MT5 behavior. Aligning these helpers with `mt5.symbol_info` is necessary for apples-to-apples risk sizing.

## 5. USD P&L uses a simplified pip-value shortcut
- **Notebook:** Exit checks call `mt5.order_calc_profit` for each leg so USD profit reflects broker pricing, contract size, and cross-currency conversions.【F:RSI Pairs Strategy/rsi_pairs_trading_strategy.ipynb†L1810-L1884】
- **Python:** `calculate_pnl_usd` multiplies pip distance by a fixed pip value table (e.g., `$10` per pip for “major USD pairs”), ignoring live contract parameters or FX conversion.【F:RSI Pairs Strategy/rsi_pairs_strategy.py†L185-L405】

**Impact:** Profit targets and stop losses will trip at different times compared with the MT5 baseline, especially on metals, JPY, or non-USD-quoted pairs. To stay synchronized you need to port the `order_calc_profit`-based logic (or an exact equivalent) into the Python stack.

---

### Recommendation
The Python class captures the general structure (RSI/ATR calculation, hedge ratio skeleton), but the gaps above mean it will not replicate the MT5 notebooks without further work. Prioritize wiring real data for both symbols, implementing the missing positive-correlation rules, mirroring both trade legs, and matching broker-specific calculations before committing funds.
