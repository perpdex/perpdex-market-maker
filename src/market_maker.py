from dataclasses import dataclass
from logging import getLogger

import pandas as pd
import talib


class IPositionGetter:
    def current_position(self) -> float:
        ...


class IMaker:
    def post_limit_order(
        self, symbol: str, side_int: int, size: float, price: float
    ) -> str:
        ...

    def cancel_limit_order(self, symbol: str, order_id: str):
        ...

    def cancel_all_orders(self, symbol: str):
        ...


class IOhlcvGetter:
    def get_ohlcv_df(self, min_len: int) -> pd.DataFrame:
        ...


@dataclass
class ATRMarketMakerConfig:
    ATR_len: int
    symbol: str
    unit_lot_size: float
    min_lot_size: float


class ATRMarketMaker:
    def __init__(
        self,
        position_getter: IPositionGetter,
        ohlcv_getter: IOhlcvGetter,
        maker: IMaker,
        config: ATRMarketMakerConfig,
    ):
        self._position_getter = position_getter
        self._ohlcv_getter = ohlcv_getter
        self._maker = maker
        self._config = config

        self._logger = getLogger(__class__.__name__)

        self._current_order_id: str = None

    async def execute(self):
        # price
        ohlcv_df = self._ohlcv_getter.get_ohlcv_df(min_len=self._config.ATR_len)

        ATRs = talib.ATR(
            ohlcv_df["hi"],
            ohlcv_df["lo"],
            ohlcv_df["cl"],
            timeperiod=self._config.ATR_len,
        )
        ATR = ATRs[-1]
        ask_price = ATR * (1 + self._config.ask_price_diff_ratio)
        bid_price = ATR * (1 - self._config.bid_price_diff_ratio)

        # cancel order
        # TODO: use replace instead of cancel
        self._maker.cancel_all_orders(symbol=self._config.symbol)

        pos = self._position_getter.current_position()
        # ask size
        if pos < 0:
            # short position
            ask_size = max(0, self._config.unit_lot_size - abs(pos))
        else:
            # no position or long position
            ask_size = pos + self._config.unit_lot_size

        # bid size
        if pos > 0:
            # long position
            bid_size = max(0, self._config.unit_lot_size - pos)
        else:
            # no position or short position
            bid_size = abs(pos) + self._config.unit_lot_size

        # ask order
        self._maker.post_limit_order(
            symbol=self._config.symbol, side_int=-1, size=ask_size, price=ask_price
        )

        # bid order
        self._maker.post_limit_order(
            symbol=self._config.symbol, side_int=1, size=bid_size, price=bid_price
        )
