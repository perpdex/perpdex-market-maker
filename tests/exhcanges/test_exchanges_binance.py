import ccxt
from src.exchanges import binance
import pandas as pd


def test_binance_get_ohlcv_df():
    exchange = ccxt.binance()
    o = binance.BinanceRestOhlcv(
        ccxt_exchange=exchange,
        symbol="BTCUSDT",
        timeframe="1m",
    )
    df = o.get_ohlcv_df()
    assert type(df) is pd.DataFrame
    assert len(df) > 0
