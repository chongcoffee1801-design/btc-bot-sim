# BTC 4-Layer Paper Trade Bot (Simulated) 🤖

ไม่ต้องสมัคร exchange — ดึงราคาจาก Binance API ฟรี แล้วจำลอง execution เอง

---

## วิธีรันบนเครื่อง Windows

### ต้องการ
- Python 3.10+ (ดาวน์โหลดที่ python.org)

### รันครั้งแรก
```
1. แตก ZIP ไปวางในโฟลเดอร์ที่ต้องการ
2. ดับเบิ้ลคลิก start_bot.bat
   → ติดตั้ง package อัตโนมัติ
   → รัน bot ทันที
```

### เปิด Dashboard (window แยก)
```
ดับเบิ้ลคลิก start_dashboard.bat
→ เปิด browser ที่ http://localhost:8501
```

---

## Bot ทำงานอะไร

ทุกวัน 07:05 น. (ไทย) หลัง Daily candle close:

1. ดึงราคา BTCUSDT จาก Binance (ฟรี)
2. คำนวณ signal (L1+L2+L3+GP เหมือน Pine Script)
3. ถ้ามี signal → บันทึก entry จำลอง
4. เช็คว่า SL หรือ TP hit จาก bar ก่อนหน้า
5. คำนวณ PnL หัก slippage 0.05% + commission 0.1%
6. บันทึกลง trades.db

---

## Files
```
btc_bot_sim/
├── bot_sim.py          ← Main bot (รันอันนี้)
├── dashboard.py        ← Dashboard (streamlit)
├── start_bot.bat       ← ดับเบิ้ลคลิกรัน bot (Windows)
├── start_dashboard.bat ← ดับเบิ้ลคลิกเปิด dashboard
├── requirements.txt
├── core/
│   ├── signal_engine.py  ← Pine Script → Python
│   ├── data_fetcher.py   ← Binance OHLCV
│   ├── sim_executor.py   ← จำลอง order fill + SL/TP
│   └── trade_logger.py   ← SQLite + stats
└── data/
    └── trades.db         ← สร้างอัตโนมัติ
```

---

## เปรียบเทียบกับ Backtest

| Metric | Backtest | Paper Trade |
|--------|----------|-------------|
| Trades | 68 | realtime |
| Win Rate | 39.71% | realtime |
| Profit Factor | 1.445 | realtime |
| PnL % | +18.39% | realtime |
| Max DD % | 6.91% | realtime |
| Return/DD | 2.66 | realtime |

---

## ความแม่นยำของ Simulation

- ราคา entry/exit: ราคา Binance จริง + slippage 0.05%
- Commission: 0.1% per trade (เทียบเท่า Binance taker)
- SL/TP: เช็คจาก high/low ของแต่ละ bar
- ความต่างจาก live trading: ไม่มี partial fill, liquidation

---

## หมายเหตุ

ถ้าต้องการรัน 24/7 โดยไม่ต้องเปิดเครื่อง ให้ deploy บน:
- Railway.app (ฟรี)
- Render.com (ฟรี)
- Start command: `python bot_sim.py`
