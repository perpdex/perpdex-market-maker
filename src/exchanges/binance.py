# %%
import ccxt
import pandas as pd


class BinanceRestOhlcv:
    def __init__(self, ccxt_exchange: ccxt.binance, symbol: str, timeframe: str):
        self._exchange = ccxt_exchange
        self._symbol = symbol
        self._timeframe = timeframe

    def get_ohlcv_df(self):
        # [
        #   [1663172280000, 20203.95, 20214.19, 20190.56, 20193.88, 304.94341]
        # ]
        data = self._exchange.fetch_ohlcv(self._symbol, self._timeframe)
        df = pd.DataFrame(
            data,
            columns=[
                "timestamp",
                "op",
                "hi",
                "lo",
                "cl",
                "volume",
            ],
        )
        return df
