from dataclasses import dataclass
from logging import getLogger

import pandas as pd
import talib


class IOhlcvGetter:
    def get_ohlcv_df(self, min_len: int) -> pd.DataFrame:
        ...


@dataclass
class NormMakePriceCalculatorConfig:
    timeperiod: int
    diff_k: float


class NormMakePriceCalculator:
    def __init__(
        self,
        ohlcv_getter: IOhlcvGetter,
        config: NormMakePriceCalculatorConfig,
    ):
        self._ohlcv_getter = ohlcv_getter
        self._config = config

        self._logger = getLogger(__class__.__name__)

    def ask_bid_prices(self) -> dict:
        ohlcv_df = self._ohlcv_getter.get_ohlcv_df(min_len=self._config.timeperiod)
        u = ohlcv_df["cl"].rolling(self._config.timeperiod).mean()
        s = ohlcv_df["cl"].rolling(self._config.timeperiod).std()
        diff = s * self._config.diff_k
        ask_price = u + diff
        bid_price = u - diff
        return ask_price, bid_price


@dataclass
class ATRMakePriceCalculatorConfig:
    timeperiod: int
    diff_k: float


class ATRMakePriceCalculator:
    def __init__(
        self,
        ohlcv_getter: IOhlcvGetter,
        config: ATRMakePriceCalculatorConfig,
    ):
        self._ohlcv_getter = ohlcv_getter
        self._config = config

        self._logger = getLogger(__class__.__name__)

    def ask_bid_prices(self):
        ohlcv_df = self._ohlcv_getter.get_ohlcv_df(min_len=self._config.timeperiod)
        ATRs = talib.ATR(
            ohlcv_df["hi"],
            ohlcv_df["lo"],
            ohlcv_df["cl"],
            timeperiod=self._config.timeperiod,
        )
        ATR = ATRs[-1]
        diff = ATR * self._config.diff_k
        ask_price = ATR + diff
        bid_price = ATR - diff
        return ask_price, bid_price


class IPositionGetter:
    def current_position(self) -> float:
        ...


class IMakePriceCalculator:
    def ask_bid_prices(self) -> tuple:
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


@dataclass
class MarketMakerConfig:
    symbol: str
    unit_lot_size: float


class MarketMaker:
    def __init__(
        self,
        position_getter: IPositionGetter,
        make_price_calculator: IMakePriceCalculator,
        maker: IMaker,
        config: MarketMakerConfig,
    ):
        self._position_getter = position_getter
        self._make_price_calculator = make_price_calculator
        self._maker = maker
        self._config = config

        self._logger = getLogger(__class__.__name__)

    async def execute(self):
        ask_price, bid_price = self._make_price_calculator.ask_bid_prices()

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
