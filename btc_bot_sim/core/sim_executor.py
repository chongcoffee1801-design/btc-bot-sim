"""
Simulated Order Executor
ไม่ต้องต่อ exchange — ใช้ราคา real ในการจำลอง fill
จำลอง SL/TP hit โดยเช็คทุกวันว่า high/low แตะ level ไหมบ้าง
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent.parent / "data" / "trades.db"

# Slippage จำลอง (0.05% ต่อ trade — ใกล้เคียงความเป็นจริง)
SLIPPAGE_PCT = 0.0005
COMMISSION_PCT = 0.001  # 0.1% per trade (Binance taker fee)


def simulate_entry(signal: dict, direction: str, equity: float) -> dict:
    """
    จำลอง entry order
    fill ที่ close ของ bar + slippage
    """
    entry_price = signal["close"]

    # จำลอง slippage
    if direction == "LONG":
        fill_price = entry_price * (1 + SLIPPAGE_PCT)
        sl_price   = signal["long_stop"]
        tp_price   = signal["long_target"]
    else:
        fill_price = entry_price * (1 - SLIPPAGE_PCT)
        sl_price   = signal["short_stop"]
        tp_price   = signal["short_target"]

    # คำนวณ position size
    c_mult   = signal["cycle_mult"]
    gp_mult  = signal["gp_mult_long"] if direction == "LONG" else signal["gp_mult_short"]
    notional = equity * signal["base_pos_pct"] * c_mult * gp_mult
    qty      = notional / fill_price

    # Commission
    commission = notional * COMMISSION_PCT

    print(f"  📋 Simulated {direction} entry:")
    print(f"     Fill price : ${fill_price:,.2f}")
    print(f"     Qty        : {qty:.6f} BTC")
    print(f"     Notional   : ${notional:,.2f}")
    print(f"     SL         : ${sl_price:,.2f}")
    print(f"     TP         : ${tp_price:,.2f}")
    print(f"     Commission : ${commission:.4f}")

    return {
        "success":     True,
        "direction":   direction,
        "entry_price": fill_price,
        "qty":         qty,
        "sl_price":    sl_price,
        "tp_price":    tp_price,
        "notional":    notional,
        "commission":  commission,
        "simulated":   True,
    }


def check_exit(trade_row: dict, bar: dict) -> dict | None:
    """
    เช็คว่า bar นี้ hit SL หรือ TP ไหม
    ใช้ high/low ของ bar ในการตรวจสอบ
    bar = {"high": float, "low": float, "close": float}

    Returns exit dict หรือ None ถ้ายังไม่ออก
    """
    direction = trade_row["direction"]
    sl_price  = trade_row["sl_price"]
    tp_price  = trade_row["tp_price"]
    bar_high  = bar["high"]
    bar_low   = bar["low"]

    if direction == "LONG":
        # SL hit ถ้า low แตะ sl_price
        if bar_low <= sl_price:
            exit_price = sl_price * (1 - SLIPPAGE_PCT)  # slippage ที่ SL
            return {"exit_price": exit_price, "exit_reason": "SL"}
        # TP hit ถ้า high แตะ tp_price
        if bar_high >= tp_price:
            exit_price = tp_price * (1 - SLIPPAGE_PCT)
            return {"exit_price": exit_price, "exit_reason": "TP"}

    elif direction == "SHORT":
        # SL hit ถ้า high แตะ sl_price
        if bar_high >= sl_price:
            exit_price = sl_price * (1 + SLIPPAGE_PCT)
            return {"exit_price": exit_price, "exit_reason": "SL"}
        # TP hit ถ้า low แตะ tp_price
        if bar_low <= tp_price:
            exit_price = tp_price * (1 + SLIPPAGE_PCT)
            return {"exit_price": exit_price, "exit_reason": "TP"}

    return None


def calculate_pnl(trade_row: dict, exit_price: float) -> float:
    """คำนวณ PnL หักค่า commission"""
    direction   = trade_row["direction"]
    entry_price = trade_row["entry_price"]
    qty         = trade_row["qty"]
    commission  = trade_row.get("commission", 0)

    if direction == "LONG":
        gross_pnl = (exit_price - entry_price) * qty
    else:
        gross_pnl = (entry_price - exit_price) * qty

    # หัก commission ทั้ง entry และ exit
    net_pnl = gross_pnl - (commission * 2)
    return net_pnl


def get_open_sim_trade() -> dict | None:
    """ดึง open trade จาก DB"""
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM trades WHERE exit_time IS NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(row) if row else None
