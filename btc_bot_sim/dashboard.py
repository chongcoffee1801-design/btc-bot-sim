"""
Paper Trade Dashboard
รัน: streamlit run dashboard.py
"""

import sqlite3
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "trades.db"

st.set_page_config(page_title="BTC Paper Trade", page_icon="🤖", layout="wide")

# Header
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.title("🤖 BTC 4-Layer — Paper Trade Dashboard")
    st.caption("Simulated execution | Real Binance prices | No exchange needed")
with col_h2:
    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()

BACKTEST = {
    "Trades": 68, "Win Rate": 39.71, "PF": 1.445,
    "PnL": 18.39, "DD": 6.91, "RDD": 2.66
}

# ============================================================
@st.cache_data(ttl=60)
def load_data():
    if not DB_PATH.exists():
        return pd.DataFrame(), pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    closed = pd.read_sql(
        "SELECT * FROM trades WHERE exit_time IS NOT NULL ORDER BY id", conn)
    open_t = pd.read_sql(
        "SELECT * FROM trades WHERE exit_time IS NULL ORDER BY id DESC LIMIT 1", conn)
    conn.close()
    return closed, open_t

closed, open_t = load_data()

# ============================================================
# METRICS
# ============================================================
st.subheader("📊 Performance vs Backtest")

if closed.empty:
    st.info("⏳ รอ signal แรก... Bot รันทุกวัน 07:05 น.")
    st.markdown("""
    **Bot กำลังทำงาน** — จะ trade อัตโนมัติเมื่อ:
    - BOS หรือ CHoCH signal เกิดขึ้น
    - ไม่มี open position อยู่แล้ว
    - Funding rate ไม่ blocking (สำหรับ Long)
    """)
else:
    total = len(closed)
    wins  = (closed["pnl_pct"] > 0).sum()
    wr    = wins / total * 100
    pnl   = closed["pnl_pct"].sum()
    gw    = closed[closed["pnl_usdt"] > 0]["pnl_usdt"].sum()
    gl    = abs(closed[closed["pnl_usdt"] < 0]["pnl_usdt"].sum())
    pf    = gw / gl if gl > 0 else 999

    # Drawdown
    eq = [10000.0]
    for p in closed["pnl_usdt"]:
        eq.append(eq[-1] + (p or 0))
    peak = eq[0]; max_dd = 0
    for e in eq:
        peak = max(peak, e)
        dd = (peak - e) / peak * 100
        max_dd = max(max_dd, dd)
    rdd = pnl / max_dd if max_dd > 0 else 0

    # Metric grid
    c1, c2, c3, c4, c5, c6 = st.columns(6)

    def delta_color(paper, bt, higher_is_better=True):
        diff = paper - bt
        return f"{'▲' if diff >= 0 else '▼'} {abs(diff):.2f} vs BT"

    c1.metric("Trades",        total,
              f"BT: {BACKTEST['Trades']}")
    c2.metric("Win Rate",      f"{wr:.1f}%",
              delta_color(wr, BACKTEST["Win Rate"]))
    c3.metric("Profit Factor", f"{pf:.3f}",
              delta_color(pf, BACKTEST["PF"]))
    c4.metric("PnL %",         f"{pnl:+.2f}%",
              delta_color(pnl, BACKTEST["PnL"]))
    c5.metric("Max DD %",      f"{max_dd:.2f}%",
              delta_color(max_dd, BACKTEST["DD"], higher_is_better=False))
    c6.metric("Return/DD",     f"{rdd:.3f}",
              delta_color(rdd, BACKTEST["RDD"]))

    # ============================================================
    # Equity Curve
    # ============================================================
    st.subheader("📈 Equity Curve")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        y=eq, x=list(range(len(eq))),
        mode="lines+markers", name="Paper Trade",
        line=dict(color="#00d4aa", width=2),
        fill="tozeroy", fillcolor="rgba(0,212,170,0.1)"
    ))
    fig.add_hline(y=10000, line_dash="dash",
                  line_color="gray", annotation_text="Start $10,000")
    fig.update_layout(
        xaxis_title="Trade #", yaxis_title="Equity (USDT)",
        height=300, template="plotly_dark",
        margin=dict(t=20, b=40)
    )
    st.plotly_chart(fig, use_container_width=True)

    # ============================================================
    # Trade Log
    # ============================================================
    st.subheader("📋 Trade Log")
    show = closed[[
        "entry_time", "exit_time", "direction", "signal_type",
        "cycle", "in_gp", "entry_price", "exit_price",
        "pnl_usdt", "pnl_pct", "exit_reason"
    ]].copy()
    show["pnl_pct"]   = show["pnl_pct"].apply(
        lambda x: f"{x:+.2f}%" if x is not None else "-")
    show["pnl_usdt"]  = show["pnl_usdt"].apply(
        lambda x: f"${x:+.2f}" if x is not None else "-")
    show["in_gp"]     = show["in_gp"].map({1: "✅ GP", 0: ""})
    show["entry_price"] = show["entry_price"].apply(
        lambda x: f"${x:,.2f}" if x else "-")
    show["exit_price"]  = show["exit_price"].apply(
        lambda x: f"${x:,.2f}" if x else "-")

    def highlight_pnl(row):
        if "+" in str(row.get("pnl_pct", "")):
            return ["background-color: rgba(0,200,100,0.15)"] * len(row)
        elif "-" in str(row.get("pnl_pct", "")):
            return ["background-color: rgba(255,60,60,0.15)"] * len(row)
        return [""] * len(row)

    st.dataframe(
        show.style.apply(highlight_pnl, axis=1),
        use_container_width=True, height=350
    )

# ============================================================
# Open Position
# ============================================================
st.subheader("📌 Open Position")
if open_t.empty:
    st.info("ไม่มี open position — รอ signal ถัดไป")
else:
    row = open_t.iloc[0]
    oc1, oc2, oc3, oc4, oc5 = st.columns(5)
    oc1.metric("Direction",   row["direction"])
    oc2.metric("Entry Price", f"${row['entry_price']:,.2f}")
    oc3.metric("Stop Loss",   f"${row['sl_price']:,.2f}")
    oc4.metric("Take Profit", f"${row['tp_price']:,.2f}")
    oc5.metric("Signal",      f"{row['signal_type']} {'GP' if row['in_gp'] else ''}")

# ============================================================
# Bot Log
# ============================================================
with st.expander("🔍 Bot Activity Log"):
    if DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH)
        logs = pd.read_sql(
            "SELECT timestamp, level, message FROM bot_log ORDER BY id DESC LIMIT 30",
            conn)
        conn.close()
        if not logs.empty:
            st.dataframe(logs, use_container_width=True, height=250)
        else:
            st.info("No logs yet")
    else:
        st.info("DB not created yet")

st.caption("🔄 Auto-refresh ทุก 60 วินาที | ราคาจาก Binance API | ไม่ใช้เงินจริง")
