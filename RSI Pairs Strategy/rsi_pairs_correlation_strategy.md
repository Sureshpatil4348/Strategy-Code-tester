## RSI Pairs Trading Strategy (Positive/Negative Correlation)

### Mode Selector
- Top-level configuration: `mode` ∈ {`positive`, `negative`}. All inputs and logic MUST branch on this selection.
- The provided notebooks implement only the "negative correlation" variant as written. TODO: Specify the exact logic differences for `mode = "positive"` (entries/exits, directionality, and any filters) from the source notebook(s) if/when available.

### Overview
- Implements an automated mean-reversion pairs strategy using RSI on two symbols with ATR-based hedge sizing and USD-based exits.
- Platform/data: MetaTrader 5 (MT5) via `mt5.copy_rates_range` with 5-minute timeframe, from 2020-01-01 to present.
- Indicators: RSI on close prices; ATR on high/low/close. Lot sizing uses ATR normalized to pips to form a hedge ratio with safety bounds. Exits are based on combined USD P&L and maximum duration.
- Notebook references: "Strategy Overview & Configuration", "Strategy Parameters", "Helper Functions", "The Enhanced Backtesting Engine", "Run the Backtest for All Pairs" in both notebooks.

### Inputs

#### Common Inputs

| name | type | default | range | description | source_ref |
|---|---|---|---|---|---|
| `TIMEFRAME` | MT5 timeframe enum | `mt5.TIMEFRAME_M5` | MT5-supported | Bar timeframe for data. | Pos/Neg notebooks: "Strategy Parameters" (`TIMEFRAME = mt5.TIMEFRAME_M5`). |
| `START_DATE` | datetime | `datetime(2020, 1, 1)` | date | Start date for historical data. | Pos/Neg notebooks: "Strategy Parameters". |
| `END_DATE` | datetime | `datetime.now()` | date | End date for historical data. | Pos/Neg notebooks: "Strategy Parameters". |
| `RSI_PERIOD` | int | `14` | >0 | RSI period (SMA-based gain/loss). | Pos/Neg notebooks: "Strategy Parameters" and `calculate_rsi`. |
| `ATR_PERIOD` | int | `5` | >0 | ATR period (rolling mean of true range). | Pos/Neg notebooks: "Strategy Parameters" and `calculate_atr`. |
| `RSI_OVERBOUGHT` | float | `75` | 0–100 | Overbought threshold for RSI. | Pos/Neg notebooks: "Strategy Parameters". |
| `RSI_OVERSOLD` | float | `25` | 0–100 | Oversold threshold for RSI. | Pos/Neg notebooks: "Strategy Parameters". |
| `PROFIT_TARGET_USD` | float | `500.0` | real | Exit when combined USD P&L ≥ target. | Pos/Neg notebooks: "USD-Based Risk Management Parameters"; used in `check_exit_conditions`. |
| `STOP_LOSS_USD` | float | `-15000.0` | real | Exit when combined USD P&L ≤ stop. | Pos/Neg notebooks: "USD-Based Risk Management Parameters"; used in `check_exit_conditions`. |
| `MAX_TRADE_HOURS` | float | `2400` | ≥0 | Exit when trade duration ≥ hours. | Pos/Neg notebooks: "USD-Based Risk Management Parameters"; used in `check_exit_conditions`. |
| `BASE_LOT_SIZE` | float | `1.0` | per broker constraints | Base lot for symbol1 in simple sizing. | Pos/Neg notebooks: "USD-Based Risk Management Parameters" and `calculate_simple_lots`. |

#### Positive Correlation Only

| name | type | default | range | description | source_ref |
|---|---|---|---|---|---|
| TODO | - | - | - | The notebooks do not specify positive-correlation-only parameters. Identify from a positive-correlation notebook if available. | TODO: Provide cell/section reference. |

#### Negative Correlation Only

| name | type | default | range | description | source_ref |
|---|---|---|---|---|---|
| `PAIRS_TO_TEST` | list[tuple[str, str, float]] | 69 tuples (examples below) | symbols present in MT5 | Static list of symbol pairs with a third element labeled as correlation. | Pos/Neg notebooks: "List of Pairs to Test" (e.g., `('USDJPY','AUDUSD',-0.2529543842)`, `('EURUSD','GBPUSD',-0.3)`, `('XAUUSD','XAGUSD',-0.25)`). |

### Data Preparation
- Symbols/pairs: From static list `PAIRS_TO_TEST` defined in the notebooks (e.g., `('USDJPY','AUDUSD',-0.2529)`, `('EURUSD','GBPUSD',-0.3)`, `('XAUUSD','XAGUSD',-0.25)`). Notebook prints indicate 69 total pairs loaded.
- Timeframes: `TIMEFRAME = mt5.TIMEFRAME_M5`.
- Data source: MT5 via `mt5.copy_rates_range(symbol, timeframe, start, end)`. Columns include `time`, `open`, `high`, `low`, `close`.
- Merge: Create a union index of both symbols’ bars; assemble `s1_close`, `s2_close`; compute indicators; then `dropna()` to retain timestamps where both symbols have data.
- Rolling windows: `RSI_PERIOD` for RSI, `ATR_PERIOD` for ATR; no other rolling windows defined.
- Data cleaning/NaNs: After indicator computation, `dropna()` enforced prior to simulation.

### Indicator Calculation
- RSI: `calculate_rsi(prices, period=14)` uses price differences; gains/losses averaged by simple moving average (rolling mean), not Wilder’s smoothing. Source: `calculate_rsi` function in both notebooks.
- ATR: `calculate_atr(high, low, close, period=5)` true range via max of three ranges; ATR is a simple rolling mean. Source: `calculate_atr`.
- Correlation: No rolling correlation is computed in the strategy logic. The `PAIRS_TO_TEST` list includes a static third value labeled as correlation for each pair; no method/threshold is computed in-code. TODO: Document correlation computation method, lookback, and selection threshold if required by implementation.
- Spread/ratio/normalization: No spread/ratio or z-score normalization used for signals. Lot sizing uses ATR-based hedge ratio normalized to pips with safety bounds (min 0.2, max 5.0). Source: `calculate_hedge_ratio`, `get_pip_size`, `normalize_lot_size`.

### Strategy Logic

#### Positive Correlation Logic
- TODO: Not defined in the provided notebooks. Specify entry/exit rules, directionality, and filters for positively correlated pairs, including any divergence/convergence criteria and thresholds. Provide source reference to the positive-correlation notebook cell/section.

#### Negative Correlation Logic
- Entry (bar close):
  - Short both pairs when both `s1_rsi > RSI_OVERBOUGHT` AND `s2_rsi > RSI_OVERBOUGHT`.
  - Long both pairs when both `s1_rsi < RSI_OVERSOLD` AND `s2_rsi < RSI_OVERSOLD`.
  - Preconditions: both `s1_atr` and `s2_atr` > 0; flat (no open trade).
  - Source: Main simulation loop in `run_backtest` (both notebooks).
- Exit (checked every bar via `check_exit_conditions`):
  - `PROFIT_TARGET` when combined USD P&L ≥ `PROFIT_TARGET_USD`.
  - `STOP_LOSS` when combined USD P&L ≤ `STOP_LOSS_USD`.
  - `TIME_LIMIT` when `(current_time - entry_time).hours ≥ MAX_TRADE_HOURS`.
  - P&L per leg via `mt5.order_calc_profit`. Source: `check_exit_conditions`.
- Position sizing:
  - Simple sizing: `calculate_simple_lots` uses `BASE_LOT_SIZE` for symbol1 and `hedge_ratio = ATR1_pips / ATR2_pips` for symbol2; both normalized to broker constraints and safety bounds via `normalize_lot_size`.
  - Safety bounds in hedge ratio: capped to [0.2, 5.0]. Source: `calculate_hedge_ratio`.
  - Note: Some notebook cells reference a risk-based sizing function and `RISK_PER_TRADE_PCT`, but the final `run_backtest` uses `calculate_simple_lots`. TODO: Confirm if risk-based sizing is intended and provide `RISK_PER_TRADE_PCT` definition if used.
- Filters/notes:
  - No additional filters (e.g., session, spread, correlation threshold) are enforced in code.
  - Execution is single-position-at-a-time per pair (`in_trade` flag).

#### Unified Pseudocode
```python
# mode: "positive" or "negative"

def run_strategy(mode, symbol1, symbol2, params):
    # Required params: TIMEFRAME, START_DATE, END_DATE, RSI_PERIOD, ATR_PERIOD,
    # RSI_OVERBOUGHT, RSI_OVERSOLD, PROFIT_TARGET_USD, STOP_LOSS_USD, MAX_TRADE_HOURS,
    # BASE_LOT_SIZE

    df1 = get_historical_data(symbol1, params.TIMEFRAME, params.START_DATE, params.END_DATE)
    df2 = get_historical_data(symbol2, params.TIMEFRAME, params.START_DATE, params.END_DATE)
    if df1.empty or df2.empty:
        return []

    df = union_index_merge(df1, df2)  # s1_close, s2_close
    df["s1_rsi"] = calculate_rsi(df["s1_close"], params.RSI_PERIOD)
    df["s2_rsi"] = calculate_rsi(df["s2_close"], params.RSI_PERIOD)
    df["s1_atr"] = calculate_atr(df1["high"], df1["low"], df1["close"], params.ATR_PERIOD)
    df["s2_atr"] = calculate_atr(df2["high"], df2["low"], df2["close"], params.ATR_PERIOD)
    df = df.dropna()

    in_trade = False
    trades = []

    for t in df.index:
        if in_trade:
            maybe_exit = check_exit_conditions(current_trade, symbol1, symbol2, t,
                                               df.loc[t, "s1_close"], df.loc[t, "s2_close"])
            if maybe_exit is not None:
                record_and_close(trades, current_trade, maybe_exit, t, df)
                in_trade = False
                continue

        if not in_trade:
            s1_rsi = df.loc[t, "s1_rsi"]
            s2_rsi = df.loc[t, "s2_rsi"]
            s1_atr = df.loc[t, "s1_atr"]
            s2_atr = df.loc[t, "s2_atr"]
            if s1_atr <= 0 or s2_atr <= 0:
                continue

            trade_type = None
            if mode == "negative":
                if s1_rsi > params.RSI_OVERBOUGHT and s2_rsi > params.RSI_OVERBOUGHT:
                    trade_type = "short"
                elif s1_rsi < params.RSI_OVERSOLD and s2_rsi < params.RSI_OVERSOLD:
                    trade_type = "long"
            elif mode == "positive":
                # TODO: Define positive-correlation entry/exit rules from source notebook(s)
                pass

            if trade_type is None:
                continue

            s1_lots, s2_lots = calculate_simple_lots(symbol1, symbol2, s1_atr, s2_atr)
            open_trade(current_trade, trade_type, t, df, s1_lots, s2_lots)
            in_trade = True

    return trades
```

### Parameter Map

| code variable | spec parameter | default | applies to mode |
|---|---|---|---|
| `TIMEFRAME` | `TIMEFRAME` | `mt5.TIMEFRAME_M5` | positive, negative |
| `START_DATE` | `START_DATE` | `datetime(2020, 1, 1)` | positive, negative |
| `END_DATE` | `END_DATE` | `datetime.now()` | positive, negative |
| `RSI_PERIOD` | `RSI_PERIOD` | `14` | positive, negative |
| `ATR_PERIOD` | `ATR_PERIOD` | `5` | positive, negative |
| `RSI_OVERBOUGHT` | `RSI_OVERBOUGHT` | `75` | positive, negative |
| `RSI_OVERSOLD` | `RSI_OVERSOLD` | `25` | positive, negative |
| `PROFIT_TARGET_USD` | `PROFIT_TARGET_USD` | `500.0` | positive, negative |
| `STOP_LOSS_USD` | `STOP_LOSS_USD` | `-15000.0` | positive, negative |
| `MAX_TRADE_HOURS` | `MAX_TRADE_HOURS` | `2400` | positive, negative |
| `BASE_LOT_SIZE` | `BASE_LOT_SIZE` | `1.0` | positive, negative |
| `PAIRS_TO_TEST` | `PAIRS_TO_TEST` | static list (69) | negative (as provided) |

### Edge Cases and Assumptions
- Execution price: entries/exits simulated at bar close; order type not explicitly modeled (assume market at close in backtest). Source: `run_backtest` loop uses `close`.
- Slippage/fees/spread: Not modeled explicitly; P&L uses `mt5.order_calc_profit`. TODO: Specify commission/spread/slippage assumptions if required.
- Correlation selection: Static `PAIRS_TO_TEST` list; no in-code rolling correlation filter. TODO: If dynamic selection is required, define correlation method (e.g., Pearson), lookback, and thresholds.
- Lot constraints: `normalize_lot_size` enforces broker min/max/step and safety clamp to [0.01, 10.0] lots. Source: `normalize_lot_size` in notebooks.
- Pip sizes: Determined per symbol, including metals and JPY-specific handling. Source: `get_pip_size`.
- Single open position per pair at a time (`in_trade` state). No pyramiding or partial exits.
- Multiple alternative cells exist that reference risk-based lot sizing and `RISK_PER_TRADE_PCT`, but final `run_backtest` uses simple sizing. TODO: Confirm final sizing approach and provide the missing `RISK_PER_TRADE_PCT` definition if risk-based sizing is adopted.

> TODO: The notebooks contain conflicting descriptions vs. parameter values: overview bullets mention `$300` target, `$150` stop, and `24` hours max; parameter cells set `PROFIT_TARGET_USD = 500.0`, `STOP_LOSS_USD = -15000.0`, `MAX_TRADE_HOURS = 2400`. Confirm the intended final values from the authoritative notebook cell/section and update accordingly.

### Appendix: Source References
- Files: `rsi_pairs_trading_strategy Pos Corelation.ipynb`, `rsi_pairs_trading_strategy - Neg Corelation.ipynb`.
- Key search anchors within notebooks:
  - "Strategy Overview & Configuration" (RSI/ATR, USD-based targets, timeframe)
  - "Strategy Parameters" (TIMEFRAME, START_DATE, END_DATE, RSI/ATR params, thresholds, USD targets)
  - "List of Pairs to Test" (`PAIRS_TO_TEST` with example tuples and printed count of 69)
  - "Helper Functions" (`calculate_rsi`, `calculate_atr`, `get_pip_size`, `normalize_lot_size`, `calculate_hedge_ratio`, `calculate_pnl_usd`, `check_exit_conditions`)
  - "The Enhanced Backtesting Engine" (`run_backtest` entry/exit logic and simple lot sizing)
- Example parameter lines and functions cited:
  - `RSI_PERIOD = 14`, `ATR_PERIOD = 5`, `RSI_OVERBOUGHT = 75`, `RSI_OVERSOLD = 25`.
  - `PROFIT_TARGET_USD = 500.0`, `STOP_LOSS_USD = -15000.0`, `MAX_TRADE_HOURS = 2400`, `BASE_LOT_SIZE = 1.0`.
  - Entries: RSI conditions in `run_backtest` loop. Exits: `check_exit_conditions` combining USD P&L and duration.
