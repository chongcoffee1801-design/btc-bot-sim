"""
Data Fetcher — pulls OHLCV from Binance (real prices, testnet trading)
Uses python-binance library
"""

import time
import pandas as pd
from binance.client import Client


def get_client(api_key: str = "", api_secret: str = "", testnet: bool = True) -> Client:
    client = Client(api_key, api_secret, testnet=testnet)
    return client


def fetch_ohlcv(
    client: Client,
    symbol: str,
    interval: str,
    limit: int = 600,
    use_futures: bool = False,
) -> pd.DataFrame:
    """
    Fetch OHLCV candles.
    interval: '1d', '1w', etc.
    For BTCUSDTPERP use use_futures=True
    """
    if use_futures:
        raw = client.futures_klines(symbol=symbol, interval=interval, limit=limit)
    else:
        raw = client.get_klines(symbol=symbol, interval=interval, limit=limit)

    df = pd.DataFrame(raw, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "qav", "num_trades", "taker_buy_base",
        "taker_buy_quote", "ignore"
    ])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df.set_index("open_time", inplace=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    return df[["open", "high", "low", "close", "volume"]]


def fetch_all_data(api_key: str = "", api_secret: str = "", testnet: bool = True):
    """
    Fetch all required dataframes for signal engine:
    - df_daily:  BTCUSDT 1D spot
    - df_weekly: BTCUSDT 1W spot (for 200W SMA needs 200+ weeks)
    - df_perp:   BTCUSDTPERP 1D futures (funding proxy)
    """
    # For real price data always use main Binance (not testnet)
    # Testnet only used for order execution
    price_client = Client("", "")  # public endpoint, no auth needed

    print("Fetching BTCUSDT Daily...")
    df_daily = fetch_ohlcv(price_client, "BTCUSDT", Client.KLINE_INTERVAL_1DAY, limit=600)

    print("Fetching BTCUSDT Weekly (200+ bars for 200W SMA)...")
    df_weekly = fetch_ohlcv(price_client, "BTCUSDT", Client.KLINE_INTERVAL_1WEEK, limit=250)

    print("Fetching BTCUSDTPERP Daily (funding proxy)...")
    df_perp = fetch_ohlcv(price_client, "BTCUSDT", Client.KLINE_INTERVAL_1DAY,
                          limit=600, use_futures=True)

    return df_daily, df_weekly, df_perp


def get_account_balance(client: Client) -> float:
    """Get USDT balance from testnet futures account"""
    try:
        balances = client.futures_account_balance()
        for b in balances:
            if b["asset"] == "USDT":
                return float(b["balance"])
    except Exception as e:
        print(f"Balance error: {e}")
    return 0.0


def get_current_price(symbol: str = "BTCUSDT") -> float:
    client = Client("", "")
    ticker = client.get_symbol_ticker(symbol=symbol)
    return float(ticker["price"])
