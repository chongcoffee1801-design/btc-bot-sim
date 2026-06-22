"""
Trade Logger — SQLite database for paper trade recording
Auto-calculates PnL, Win Rate, Return/DD for comparison with backtest
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "trades.db"


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_time    TEXT,
            exit_time     TEXT,
            direction     TEXT,
            signal_type   TEXT,
            cycle         TEXT,
            in_gp         INTEGER,
            entry_price   REAL,
            exit_price    REAL,
            qty           REAL,
            sl_price      REAL,
            tp_price      REAL,
            pnl_usdt      REAL,
            pnl_pct       REAL,
            exit_reason   TEXT,
            equity_before REAL,
            equity_after  REAL,
            atr           REAL,
            raw_signal    TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS bot_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            level     TEXT,
            message   TEXT
        )
    """)

    conn.commit()
    conn.close()
    print(f"DB initialized at {DB_PATH}")


def log_entry(signal: dict, order_result: dict, equity: float):
    """Record trade entry"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    direction = order_result.get("direction", "")
    in_gp = 1 if (
        (direction == "LONG"  and signal.get("in_long_gp"))  or
        (direction == "SHORT" and signal.get("in_short_gp"))
    ) else 0

    c.execute("""
        INSERT INTO trades
        (entry_time, direction, signal_type, cycle, in_gp,
         entry_price, qty, sl_price, tp_price, equity_before, atr, raw_signal)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        signal["bar_time"],
        direction,
        signal["signal_type"],
        signal["cycle"],
        in_gp,
        order_result.get("entry_price", signal["close"]),
        order_result.get("qty", 0),
        order_result.get("sl_price", 0),
        order_result.get("tp_price", 0),
        equity,
        signal["atr"],
        json.dumps(signal),
    ))

    trade_id = c.lastrowid
    conn.commit()
    conn.close()
    print(f"📝 Trade entry logged: ID={trade_id} {direction} @ {signal['close']:.2f}")
    return trade_id


def log_exit(trade_id: int, exit_price: float, exit_reason: str, equity_after: float):
    """Record trade exit and calculate PnL"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Fetch entry data
    row = c.execute(
        "SELECT entry_price, qty, direction, equity_before FROM trades WHERE id=?",
        (trade_id,)
    ).fetchone()

    if not row:
        conn.close()
        return

    entry_price, qty, direction, equity_before = row

    if direction == "LONG":
        pnl_usdt = (exit_price - entry_price) * qty
    else:
        pnl_usdt = (entry_price - exit_price) * qty

    pnl_pct = (pnl_usdt / equity_before * 100) if equity_before > 0 else 0

    c.execute("""
        UPDATE trades
        SET exit_time=?, exit_price=?, pnl_usdt=?, pnl_pct=?, exit_reason=?, equity_after=?
        WHERE id=?
    """, (
        datetime.utcnow().isoformat(),
        exit_price,
        pnl_usdt,
        pnl_pct,
        exit_reason,
        equity_after,
        trade_id,
    ))

    conn.commit()
    conn.close()
    print(f"📝 Trade exit logged: ID={trade_id} PnL={pnl_pct:.2f}%")


def log_event(level: str, message: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO bot_log (timestamp, level, message) VALUES (?, ?, ?)",
        (datetime.utcnow().isoformat(), level, message)
    )
    conn.commit()
    conn.close()


def get_stats() -> dict:
    """Calculate paper trade performance stats"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    rows = c.execute("""
        SELECT pnl_pct, pnl_usdt, equity_before, equity_after,
               direction, in_gp, cycle, signal_type, exit_reason
        FROM trades
        WHERE exit_time IS NOT NULL
    """).fetchall()

    conn.close()

    if not rows:
        return {"message": "No completed trades yet"}

    total     = len(rows)
    wins      = sum(1 for r in rows if r[0] > 0)
    pnl_pcts  = [r[0] for r in rows]
    pnl_usdts = [r[1] for r in rows]

    # Equity curve for drawdown
    equity_curve = []
    eq = rows[0][2] if rows else 10000
    for r in rows:
        eq += r[1]
        equity_curve.append(eq)

    peak = equity_curve[0]
    max_dd = 0
    for e in equity_curve:
        if e > peak:
            peak = e
        dd = (peak - e) / peak * 100
        if dd > max_dd:
            max_dd = dd

    total_pnl_pct = sum(pnl_pcts)
    return_dd = (total_pnl_pct / max_dd) if max_dd > 0 else 0

    # Profit Factor
    gross_win  = sum(p for p in pnl_usdts if p > 0)
    gross_loss = abs(sum(p for p in pnl_usdts if p < 0))
    pf = (gross_win / gross_loss) if gross_loss > 0 else float("inf")

    return {
        "total_trades":  total,
        "win_rate":      round(wins / total * 100, 2),
        "profit_factor": round(pf, 3),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "max_dd_pct":    round(max_dd, 2),
        "return_dd":     round(return_dd, 3),
        # Backtest reference
        "backtest_pf":      1.445,
        "backtest_wr":      39.71,
        "backtest_return_dd": 2.66,
    }


def get_open_trade_id() -> int | None:
    """Return ID of the trade without exit_time (open position)"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    row = c.execute(
        "SELECT id FROM trades WHERE exit_time IS NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row[0] if row else None
