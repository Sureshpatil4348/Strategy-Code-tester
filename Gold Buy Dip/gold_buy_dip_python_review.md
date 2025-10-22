# Gold Buy Dip Python Strategy Review

This document summarizes the discrepancies I found between the Python implementation in `gold_buy_dip_strategy.py` and the reference MT4 Expert Advisor in `Gold Buy Dip.mq4`. Each point highlights where the behavior diverges and why it matters for faithfully replicating the MT4 logic before risking capital.

## 1. Percentage trigger lookback window
- **Python:** The trigger compares the latest close against the highest/lowest values inside `recent_candles = self.candles[-lookback_count:]`, which includes the same candle being evaluated.【F:Gold Buy Dip/gold_buy_dip_strategy.py†L39-L50】
- **MT4:** The EA uses `Close[1]` as the current price and only scans `Close[2]` and back for the high/low, explicitly requiring at least `LookbackCandles + 2` bars.【F:Gold Buy Dip/Gold Buy Dip.mq4†L139-L183】

**Impact:** Including the current candle in the high/low set suppresses triggers whenever that candle is the extreme (the percentage becomes zero). The MT4 version deliberately excludes the active candle so that a breakout on the latest bar can still trigger the setup. The Python version should either require one extra candle or explicitly drop the most recent close from the lookback window to match MT4.

## 2. Z-score waiting period length
- **Python:** Times out when `wait_candles_count >= self.config.zscore_wait_candles`, ending the setup as soon as the count reaches the configured limit.【F:Gold Buy Dip/gold_buy_dip_strategy.py†L287-L292】
- **MT4:** Uses `if(ConditionCandles > ZScoreWaitCandles)`; the EA waits the full number of candles and only times out on the *next* bar.【F:Gold Buy Dip/Gold Buy Dip.mq4†L189-L200】

**Impact:** The Python port cancels one candle earlier than MT4, so valid signals that arrive on the last allowed candle in MT4 will be rejected in Python.

## 3. Z-score threshold comparison
- **Python:** Confirms when `zscore >= threshold` for sells and `<= threshold` for buys.【F:Gold Buy Dip/gold_buy_dip_strategy.py†L61-L66】
- **MT4:** Requires strict inequality (`>` for sells, `<` for buys).【F:Gold Buy Dip/Gold Buy Dip.mq4†L207-L228】

**Impact:** Allowing equality introduces trades that MT4 would skip. Depending on data precision this can generate extra entries, breaking parity with the MT4 track record.

## 4. Grid trade counting and shutdown
- **Python:** Counts the initial position in `self.state.grid_trades` and stops adding new trades once `len(self.state.grid_trades) < self.config.max_grid_trades` is false. It also closes the grid as soon as `len(self.state.grid_trades) >= max_grid_trades`.【F:Gold Buy Dip/gold_buy_dip_strategy.py†L314-L352】【F:Gold Buy Dip/gold_buy_dip_strategy.py†L123-L143】
- **MT4:** `CurrentGridLevel` tracks only *additional* trades beyond the initial order; the EA permits opening the final grid level and then immediately forces a closure when `CurrentGridLevel >= MaxGridTrades`.【F:Gold Buy Dip/Gold Buy Dip.mq4†L424-L515】【F:Gold Buy Dip/Gold Buy Dip.mq4†L570-L597】

**Impact:** With `MaxGridTrades = 5`, MT4 can momentarily hold six positions (initial + five grid levels) before shutting down, while the Python code limits the total to five (initial + four extras). This changes exposure, averaging prices, and the point at which the emergency close happens.

## 5. Take-profit distance in points mode
- **Python:** Converts points with a hard-coded divisor of `100` for XAU symbols and `10000` for everything else.【F:Gold Buy Dip/gold_buy_dip_strategy.py†L110-L121】
- **MT4:** Multiplies by the symbol’s actual `Point` size, so a 5-digit forex pair uses 0.00001 and a 3-digit pair uses 0.001.【F:Gold Buy Dip/Gold Buy Dip.mq4†L541-L562】

**Impact:** Any instrument whose `Point` is not exactly 0.01 (XAU) or 0.0001 (4-digit FX) will have an incorrect target in Python. Even for 5-digit brokers the MT4 TP would be 0.002 while Python places it at 0.02, a tenfold difference.

## 6. Grid spacing floor
- **Python:** Imposes a minimum spacing of 0.50 for XAUUSD even when the configured percentage or ATR distance is smaller.【F:Gold Buy Dip/gold_buy_dip_strategy.py†L68-L82】
- **MT4:** Uses the configured percentage or ATR distance exactly as-is.【F:Gold Buy Dip/Gold Buy Dip.mq4†L424-L453】

**Impact:** The fixed floor widens grids compared with the MT4 behavior and can prevent additional orders that the EA would place, altering averaging and exit behavior.

## 7. Extra filters absent from MT4
The Python port adds several filters that do not exist in the EA:
- Minimum move since the last grid close before allowing a new setup.【F:Gold Buy Dip/gold_buy_dip_strategy.py†L216-L225】
- Same-direction throttle that blocks re-entry near the last exit price.【F:Gold Buy Dip/gold_buy_dip_strategy.py†L226-L242】

**Impact:** These filters reduce trading frequency compared with MT4. If the goal is a faithful replication, they should be optional or removed so the behavior matches the reference.

## 8. Execution price assumptions
- **Python:** Records the initial grid trade at `candle.close` and reuses `candle.close` for all subsequent grid orders.【F:Gold Buy Dip/gold_buy_dip_strategy.py†L267-L342】
- **MT4:** Uses the actual trade prices (`Ask` for buys, `Bid` for sells) at execution time.【F:Gold Buy Dip/Gold Buy Dip.mq4†L270-L327】【F:Gold Buy Dip/Gold Buy Dip.mq4†L466-L515】

**Impact:** Backtesting or live fills in Python will not match MT4 unless the framework injects precise bid/ask prices. Misalignments propagate to VWAP, TP, and spacing logic.

## 9. Drawdown enforcement scope
- **Python:** Computes equity as `initial_balance + realized PnL + floating PnL` maintained inside the strategy state.【F:Gold Buy Dip/gold_buy_dip_strategy.py†L197-L208】
- **MT4:** References the broker account’s `AccountEquity()` directly.【F:Gold Buy Dip/Gold Buy Dip.mq4†L638-L648】

**Impact:** Unless `BaseStrategy` keeps the running PnL perfectly synchronized with account equity (including commissions/swaps), the Python drawdown check may drift from MT4 and could miss (or falsely trigger) the emergency close.

## 10. External dependencies
The Python module depends on application components (`app.models`, `app.indicators`, `MT5MarginValidator`, etc.) that are not present in this repository.【F:Gold Buy Dip/gold_buy_dip_strategy.py†L1-L23】 Without confirming those implementations, we cannot assert parity for Z-score, ATR, order handling, or margin checks.

---

## Recommendation
Because of the discrepancies above, the current Python strategy will not reproduce the MT4 Expert Advisor’s trade timing, grid sizing, or exit behavior. I recommend addressing each mismatch—especially the lookback window, Z-score timing, grid limits, and point conversion—before deploying capital. Aligning these details will ensure the Python port mirrors the live-proven MT4 logic.
