"""
BTC 4-Layer Paper Trade Bot — Simulated Mode
ไม่ต้องสมัคร exchange — ใช้ราคา Binance real-time ฟรี
รันทุกวัน 07:05 น. (ไทย) = 00:05 UTC หลัง Daily candle close

วิธีรัน:
  pip install -r requirements.txt
  python bot_sim.py
"""

import time
import schedule
import traceback
from datetime import datetime, timezone

from core.signal_engine import get_latest_signal
from core.data_fetcher   import fetch_all_data
from core.sim_executor   import (
    simulate_entry, check_exit,
    calculate_pnl, get_open_sim_trade
)
from core.trade_logger import (
    init_db, log_entry, log_exit, log_event, get_stats
)

INITIAL_EQUITY = 10_000.0  # USDT จำลอง


def get_current_equity() -> float:
    """คำนวณ equity ปัจจุบันจาก trade history"""
    import sqlite3
    from pathlib import Path
    db = Path("data/trades.db")
    if not db.exists():
        return INITIAL_EQUITY
    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT pnl_usdt FROM trades WHERE exit_time IS NOT NULL"
    ).fetchall()
    conn.close()
    total_pnl = sum(r[0] for r in rows if r[0] is not None)
    return INITIAL_EQUITY + total_pnl


def run_bot():
    """Main logic — รันทุกวันหลัง Daily candle close"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'='*60}")
    print(f"🤖 BTC Paper Trade Bot — {now}")
    print(f"{'='*60}")

    try:
        # 1. ดึงข้อมูลราคา (ฟรี ไม่ต้อง API key)
        print("\n📡 Fetching market data...")
        df_daily, df_weekly, df_perp = fetch_all_data()

        # 2. คำนวณ signal
        signal = get_latest_signal(df_daily, df_weekly, df_perp)

        print(f"\n📊 Signal Bar: {signal['bar_time']}")
        print(f"   Close  : ${signal['close']:>10,.2f}")
        print(f"   Cycle  : {signal['cycle']}")
        print(f"   ATR    : ${signal['atr']:>10,.2f}")
        print(f"   LONG   : {'✅' if signal['long_signal']  else '❌'}  (GP: {'✅' if signal['in_long_gp']  else '❌'})")
        print(f"   SHORT  : {'✅' if signal['short_signal'] else '❌'}  (GP: {'✅' if signal['in_short_gp'] else '❌'})")
        print(f"   Funding: {'🚫 BLOCKED' if signal['funding_blocked'] else '✅ OK'}")

        log_event("INFO", f"Signal computed: {signal['bar_time']} | Long={signal['long_signal']} | Short={signal['short_signal']}")

        equity = get_current_equity()
        print(f"\n💰 Simulated Equity: ${equity:,.2f} USDT")

        # 3. เช็ค open position — ดูว่า SL/TP hit ไหมจาก bar นี้
        open_trade = get_open_sim_trade()

        if open_trade:
            print(f"\n📌 Open position: {open_trade['direction']} @ ${open_trade['entry_price']:,.2f}")
            print(f"   SL: ${open_trade['sl_price']:,.2f}  TP: ${open_trade['tp_price']:,.2f}")

            # เช็ค exit จาก bar ล่าสุด
            bar = {
                "high":  df_daily["high"].iloc[-2],
                "low":   df_daily["low"].iloc[-2],
                "close": df_daily["close"].iloc[-2],
            }

            exit_result = check_exit(open_trade, bar)

            if exit_result:
                exit_price  = exit_result["exit_price"]
                exit_reason = exit_result["exit_reason"]
                pnl_usdt    = calculate_pnl(open_trade, exit_price)
                pnl_pct     = pnl_usdt / open_trade["equity_before"] * 100
                new_equity  = equity + pnl_usdt

                emoji = "✅" if pnl_usdt > 0 else "❌"
                print(f"\n{emoji} Position CLOSED by {exit_reason}")
                print(f"   Exit price : ${exit_price:,.2f}")
                print(f"   PnL        : ${pnl_usdt:+.2f} ({pnl_pct:+.2f}%)")
                print(f"   New equity : ${new_equity:,.2f}")

                log_exit(open_trade["id"], exit_price, exit_reason, new_equity)
                log_event("TRADE", f"EXIT {exit_reason}: PnL={pnl_pct:+.2f}%")
                open_trade = None
                equity = new_equity
            else:
                print("   → ยังไม่ hit SL/TP — holding")
                log_event("INFO", "Position holding — no exit triggered")

        # 4. เปิด position ใหม่ถ้าไม่มี open trade
        if not open_trade:
            if signal["long_signal"]:
                sig_label = signal["signal_type"]
                gp_label  = "+GP" if signal["in_long_gp"] else ""
                print(f"\n🟢 LONG signal! [{sig_label}{gp_label}] Cycle={signal['cycle']}")

                result = simulate_entry(signal, "LONG", equity)
                if result["success"]:
                    log_entry(signal, result, equity)
                    log_event("TRADE", f"LONG entry @ {result['entry_price']:.2f}")

            elif signal["short_signal"]:
                sig_label = signal["signal_type"]
                gp_label  = "+GP" if signal["in_short_gp"] else ""
                print(f"\n🔴 SHORT signal! [{sig_label}{gp_label}] Cycle={signal['cycle']}")

                result = simulate_entry(signal, "SHORT", equity)
                if result["success"]:
                    log_entry(signal, result, equity)
                    log_event("TRADE", f"SHORT entry @ {result['entry_price']:.2f}")

            else:
                print("\n⏳ No signal this bar — waiting")
                log_event("INFO", "No signal")

        # 5. แสดง stats เปรียบเทียบกับ backtest
        stats = get_stats()
        if "total_trades" in stats:
            print(f"\n{'─'*50}")
            print(f"📈 Paper Trade Performance vs Backtest")
            print(f"{'─'*50}")
            metrics = [
                ("Trades",       stats["total_trades"],         68),
                ("Win Rate",     f"{stats['win_rate']}%",       "39.71%"),
                ("Profit Factor",stats["profit_factor"],        1.445),
                ("PnL %",        f"{stats['total_pnl_pct']:+.2f}%", "+18.39%"),
                ("Max DD %",     f"{stats['max_dd_pct']:.2f}%", "6.91%"),
                ("Return/DD",    stats["return_dd"],            2.66),
            ]
            for name, paper, bt in metrics:
                print(f"   {name:<16}: Paper={str(paper):<12} Backtest={bt}")
        else:
            print("\n📊 No completed trades yet — waiting for first signal")

    except Exception as e:
        err = traceback.format_exc()
        print(f"\n❌ Error: {e}")
        print(err)
        log_event("ERROR", err)


def run_scheduler():
    """Schedule รันทุกวัน 00:05 UTC (07:05 น. ไทย)"""
    print("🚀 BTC Paper Trade Bot (Simulated) started!")
    print("📅 Will run daily at 00:05 UTC (07:05 ICT)")
    print("─" * 60)

    init_db()

    # รันครั้งแรกทันทีเพื่อ test
    print("\n🔄 Running initial check now...")
    run_bot()

    # Schedule วันละครั้ง
    schedule.every().day.at("00:05").do(run_bot)

    print("\n✅ Scheduler running — press Ctrl+C to stop")
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    run_scheduler()
