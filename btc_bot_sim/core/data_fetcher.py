"""
Data Fetcher — ใช้ ccxt (ไม่ถูก block จาก US server)
"""
import ccxt
import pandas as pd

def fetch_ohlcv_ccxt(symbol: str, timeframe: str, limit: int = 600) -> pd.DataFrame:
    exchange = ccxt.binance({
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    })
    raw = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp","open","high","low","close","volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)
    return df

def fetch_all_data():
    print("Fetching BTCUSDT Daily...")
    df_daily = fetch_ohlcv_ccxt("BTC/USDT", "1d", limit=600)

    print("Fetching BTCUSDT Weekly...")
    df_weekly = fetch_ohlcv_ccxt("BTC/USDT", "1w", limit=250)

    print("Fetching BTCUSDTPERP Daily (funding proxy)...")
    exchange_futures = ccxt.binance({
        "enableRateLimit": True,
        "options": {"defaultType": "future"},
    })
    raw = exchange_futures.fetch_ohlcv("BTC/USDT:USDT", "1d", limit=600)
    df_perp = pd.DataFrame(raw, columns=["timestamp","open","high","low","close","volume"])
    df_perp["timestamp"] = pd.to_datetime(df_perp["timestamp"], unit="ms")
    df_perp.set_index("timestamp", inplace=True)

    return df_daily, df_weekly, df_perp
