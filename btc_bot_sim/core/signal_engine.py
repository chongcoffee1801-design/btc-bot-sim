"""
BTC 4-Layer Signal Engine
Replicates btc_strategy_FINAL.pine logic in Python
"""

import pandas as pd
import numpy as np


# ============================================================
# VALIDATED PARAMETERS (locked — same as Pine Script)
# ============================================================
PARAMS = {
    "pivot_left":        5,
    "pivot_right":       5,
    "ob_lookback":       3,
    "ob_active_window":  20,
    "atr_len":           14,
    "atr_stop_mult":     1.5,
    "atr_target_mult":   3.0,
    "gp_long_mult":      3.0,
    "gp_short_mult":     3.0,
    "gp_lower":          0.618,
    "gp_upper":          0.65,
    "funding_threshold": 0.10,
    "funding_lookback":  5,
    "ath_dd_thresh":     0.60,
    "bear_size_pct":     0.50,
    "base_position_pct": 0.20,
}


# ============================================================
# LAYER 1 — MACRO CYCLE
# ============================================================
def compute_macro_cycle(df_daily: pd.DataFrame, df_weekly: pd.DataFrame) -> pd.Series:
    """
    Returns cycle label per bar: 'Bull', 'Bear', 'Accum'
    Uses 200W SMA + Pi Cycle Top + ATH Drawdown
    """
    # 200W SMA — map weekly value to daily index
    sma200w_weekly = df_weekly["close"].rolling(200).mean()
    sma200w = sma200w_weekly.reindex(df_daily.index, method="ffill")

    # Pi Cycle: 111D SMA and 2×350D SMA
    sma111d  = df_daily["close"].rolling(111).mean()
    sma350d2 = df_daily["close"].rolling(350).mean() * 2.0
    pi_top   = (sma111d.shift(1) < sma350d2.shift(1)) & (sma111d >= sma350d2)

    # Bars since Pi Top (rolling min of distance)
    bars_since_pi = pd.Series(index=df_daily.index, dtype=float)
    last_pi = None
    for i, (idx, is_top) in enumerate(pi_top.items()):
        if is_top:
            last_pi = i
        bars_since_pi[idx] = (i - last_pi) if last_pi is not None else np.nan
    near_pi_top = bars_since_pi <= 14

    # ATH drawdown
    ath = df_daily["high"].cummax()
    dd  = (ath - df_daily["close"]) / ath

    # Cycle classification
    bull  = (df_daily["close"] > sma200w) & (~near_pi_top)
    accum = (df_daily["close"] < sma200w) & (dd >= PARAMS["ath_dd_thresh"])
    bear  = (df_daily["close"] < sma200w) & (dd < PARAMS["ath_dd_thresh"])

    cycle = pd.Series("Bear", index=df_daily.index)
    cycle[bull]  = "Bull"
    cycle[accum] = "Accum"
    return cycle


def cycle_size_mult(cycle_label: str) -> float:
    return {"Bull": 1.0, "Accum": 0.75, "Bear": PARAMS["bear_size_pct"]}.get(cycle_label, 0.5)


# ============================================================
# LAYER 2 — FUNDING RATE BLOCKER
# ============================================================
def compute_funding_block(df_spot: pd.DataFrame, df_perp: pd.DataFrame) -> pd.Series:
    """
    Returns True when funding blocks long entries
    proxy = (perp_close - spot_close) / spot_close * 100
    """
    proxy  = (df_perp["close"] - df_spot["close"]) / df_spot["close"] * 100
    smooth = proxy.rolling(PARAMS["funding_lookback"]).mean()
    return smooth >= PARAMS["funding_threshold"]


# ============================================================
# HELPERS — Pivot High/Low detection
# ============================================================
def pivot_high(series: pd.Series, left: int, right: int) -> pd.Series:
    """Returns pivot high value at confirmation bar (bar + right)"""
    result = pd.Series(np.nan, index=series.index)
    arr = series.values
    for i in range(left, len(arr) - right):
        window = arr[i - left: i + right + 1]
        if arr[i] == max(window):
            result.iloc[i] = arr[i]
    return result


def pivot_low(series: pd.Series, left: int, right: int) -> pd.Series:
    result = pd.Series(np.nan, index=series.index)
    arr = series.values
    for i in range(left, len(arr) - right):
        window = arr[i - left: i + right + 1]
        if arr[i] == min(window):
            result.iloc[i] = arr[i]
    return result


# ============================================================
# LAYER 3 — MARKET STRUCTURE (BOS / CHoCH + Order Block)
# ============================================================
def compute_structure_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Returns DataFrame with columns:
      bull_bos, bear_bos, bull_choch, bear_choch,
      struct_long, struct_short,
      bull_ob_high, bull_ob_low, bull_ob_bar,
      bear_ob_high, bear_ob_low, bear_ob_bar
    """
    L = PARAMS["pivot_left"]
    R = PARAMS["pivot_right"]
    OB_LB = PARAMS["ob_lookback"]
    OB_WIN = PARAMS["ob_active_window"]

    ph = pivot_high(df["high"], L, R)
    pl = pivot_low(df["low"],  L, R)

    n = len(df)
    last_sh = last_sl = prev_sh = prev_sl = np.nan
    last_sh_bar = last_sl_bar = -1
    struct_bull = struct_bear = False

    bull_ob_high = bull_ob_low = bull_ob_bar_val = np.nan
    bear_ob_high = bear_ob_low = bear_ob_bar_val = np.nan

    results = []

    for i in range(n):
        row = df.iloc[i]
        close  = row["close"]
        close1 = df["close"].iloc[i-1] if i > 0 else close

        # Update pivots
        if not np.isnan(ph.iloc[i]):
            prev_sh = last_sh
            last_sh = ph.iloc[i]
            last_sh_bar = i
            if not np.isnan(prev_sh) and last_sh > prev_sh:
                struct_bull = True
                struct_bear = False

        if not np.isnan(pl.iloc[i]):
            prev_sl = last_sl
            last_sl = pl.iloc[i]
            last_sl_bar = i
            if not np.isnan(prev_sl) and last_sl < prev_sl:
                struct_bear = True
                struct_bull = False

        # BOS detection (confirmed = not last bar, use close cross)
        bull_bos = (not np.isnan(last_sh)) and (close > last_sh) and (close1 <= last_sh)
        bear_bos = (not np.isnan(last_sl)) and (close < last_sl) and (close1 >= last_sl)

        bull_choch = bull_bos and struct_bear
        bear_choch = bear_bos and struct_bull

        # Update Order Blocks on BOS
        if bull_bos:
            for k in range(1, OB_LB + 1):
                if i - k >= 0:
                    ob_c = df["close"].iloc[i - k]
                    ob_o = df["open"].iloc[i - k]
                    if ob_c < ob_o:   # bearish candle before bull BOS
                        bull_ob_high    = ob_o
                        bull_ob_low     = ob_c
                        bull_ob_bar_val = i - k
                        break

        if bear_bos:
            for k in range(1, OB_LB + 1):
                if i - k >= 0:
                    ob_c = df["close"].iloc[i - k]
                    ob_o = df["open"].iloc[i - k]
                    if ob_c > ob_o:   # bullish candle before bear BOS
                        bear_ob_high    = ob_c
                        bear_ob_low     = ob_o
                        bear_ob_bar_val = i - k
                        break

        # Price inside active OB
        bull_ob_active = (not np.isnan(bull_ob_bar_val)) and ((i - bull_ob_bar_val) <= OB_WIN)
        bear_ob_active = (not np.isnan(bear_ob_bar_val)) and ((i - bear_ob_bar_val) <= OB_WIN)

        in_bull_ob = bull_ob_active and (row["low"] <= bull_ob_high) and (row["high"] >= bull_ob_low)
        in_bear_ob = bear_ob_active and (row["high"] >= bear_ob_low) and (row["low"] <= bear_ob_high)

        struct_long  = bull_choch or (bull_bos and in_bull_ob)
        struct_short = bear_choch or (bear_bos and in_bear_ob)

        results.append({
            "bull_bos":    bull_bos,
            "bear_bos":    bear_bos,
            "bull_choch":  bull_choch,
            "bear_choch":  bear_choch,
            "struct_long": struct_long,
            "struct_short":struct_short,
            "in_bull_ob":  in_bull_ob,
            "in_bear_ob":  in_bear_ob,
            "last_sh":     last_sh,
            "last_sl":     last_sl,
        })

    return pd.DataFrame(results, index=df.index)


# ============================================================
# GOLDEN POCKET ZONE
# ============================================================
def compute_golden_pocket(struct_df: pd.DataFrame) -> pd.DataFrame:
    """Returns inLongGP, inShortGP columns"""
    gp_lower = PARAMS["gp_lower"]
    gp_upper = PARAMS["gp_upper"]

    swing_range = (struct_df["last_sh"] - struct_df["last_sl"]).abs()

    long_gp_high = struct_df["last_sh"] - gp_lower * swing_range
    long_gp_low  = struct_df["last_sh"] - gp_upper * swing_range
    short_gp_low  = struct_df["last_sl"] + gp_lower * swing_range
    short_gp_high = struct_df["last_sl"] + gp_upper * swing_range

    return pd.DataFrame({
        "long_gp_high":  long_gp_high,
        "long_gp_low":   long_gp_low,
        "short_gp_high": short_gp_high,
        "short_gp_low":  short_gp_low,
    }, index=struct_df.index)


# ============================================================
# ATR
# ============================================================
def compute_atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(length).mean()


# ============================================================
# MAIN: Generate Signal for Latest Bar
# ============================================================
def get_latest_signal(
    df_daily:  pd.DataFrame,
    df_weekly: pd.DataFrame,
    df_perp:   pd.DataFrame,
) -> dict:
    """
    Run full signal engine on latest closed daily bar.
    Returns signal dict for bot to act on.
    """
    struct   = compute_structure_signals(df_daily)
    gp       = compute_golden_pocket(struct)
    cycle    = compute_macro_cycle(df_daily, df_weekly)
    funding_block = compute_funding_block(df_daily, df_perp)
    atr      = compute_atr(df_daily, PARAMS["atr_len"])

    # Latest confirmed bar (index -1 = current forming, -2 = last closed)
    idx = -2

    bar_close   = df_daily["close"].iloc[idx]
    bar_high    = df_daily["high"].iloc[idx]
    bar_low     = df_daily["low"].iloc[idx]
    bar_time    = df_daily.index[idx]
    bar_atr     = atr.iloc[idx]
    bar_cycle   = cycle.iloc[idx]
    bar_funding = funding_block.iloc[idx]

    s_long  = struct["struct_long"].iloc[idx]
    s_short = struct["struct_short"].iloc[idx]

    # Golden Pocket check
    gp_long_high  = gp["long_gp_high"].iloc[idx]
    gp_long_low   = gp["long_gp_low"].iloc[idx]
    gp_short_high = gp["short_gp_high"].iloc[idx]
    gp_short_low  = gp["short_gp_low"].iloc[idx]

    in_long_gp  = (bar_low <= gp_long_high) and (bar_high >= gp_long_low)
    in_short_gp = (bar_high >= gp_short_low) and (bar_low <= gp_short_high)

    # Signal type label
    sig_type = "CHoCH" if struct["bull_choch"].iloc[idx] else "BOS"

    long_condition  = s_long  and not bar_funding
    short_condition = s_short

    # Position sizing
    c_mult = cycle_size_mult(bar_cycle)
    gp_mult_long  = PARAMS["gp_long_mult"]  if in_long_gp  else 1.0
    gp_mult_short = PARAMS["gp_short_mult"] if in_short_gp else 1.0

    long_stop   = bar_close - PARAMS["atr_stop_mult"]   * bar_atr
    long_target = bar_close + PARAMS["atr_target_mult"] * bar_atr
    short_stop  = bar_close + PARAMS["atr_stop_mult"]   * bar_atr
    short_target= bar_close - PARAMS["atr_target_mult"] * bar_atr

    return {
        "bar_time":       str(bar_time),
        "close":          bar_close,
        "atr":            bar_atr,
        "cycle":          bar_cycle,
        "funding_blocked":bar_funding,
        "long_signal":    long_condition,
        "short_signal":   short_condition,
        "in_long_gp":     in_long_gp,
        "in_short_gp":    in_short_gp,
        "signal_type":    sig_type,
        "cycle_mult":     c_mult,
        "gp_mult_long":   gp_mult_long,
        "gp_mult_short":  gp_mult_short,
        "long_stop":      long_stop,
        "long_target":    long_target,
        "short_stop":     short_stop,
        "short_target":   short_target,
        "base_pos_pct":   PARAMS["base_position_pct"],
    }
