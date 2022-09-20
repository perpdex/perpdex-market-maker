from dataclasses import dataclass
from logging import getLogger

import pandas as pd
import talib


class IOhlcvGetter:
    def get_ohlcv_df(self) -> pd.DataFrame:
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
        ohlcv_df = self._ohlcv_getter.get_ohlcv_df()
        u = ohlcv_df["cl"].rolling(self._config.timeperiod).mean()
        s = ohlcv_df["cl"].rolling(self._config.timeperiod).std()
        diff = s * self._config.diff_k
        ask_price = u + diff
        bid_price = u - diff
        return ask_price.values[-1], bid_price.values[-1]


class IPriceGetter:
    def bid_price(self) -> float:
        ...

    def ask_price(self) -> float:
        ...

    def last_price(self) -> float:
        ...


@dataclass
class SimpleMakePriceCalculatorConfig:
    diff: int


class SimpleMakePriceCalculator:
    def __init__(
        self,
        ticker: IPriceGetter,
        config: NormMakePriceCalculatorConfig,
    ):
        self._ticker = ticker
        self._config = config

        self._logger = getLogger(__class__.__name__)

    def ask_bid_prices(self) -> dict:
        ltp = self._ticker.last_price()
        ask_price = ltp + self._config.diff
        bid_price = ltp - self._config.diff
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

    def ask_bid_prices(self) -> tuple:
        ohlcv_df = self._ohlcv_getter.get_ohlcv_df()
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


@dataclass
class SimpleMakeSizeCalculatorConfig:
    unit_lot_size: float


class SimpleMakeSizeCalculator:
    def __init__(
        self,
        position_getter: IPositionGetter,
        config: SimpleMakeSizeCalculatorConfig,
    ):
        self._position_getter = position_getter
        self._config = config

        self._logger = getLogger(__class__.__name__)

    def ask_bid_sizes(self) -> tuple:
        pos = self._position_getter.current_position()
        self._logger.debug(f"{pos=:.8f}")
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
        return ask_size, bid_size


class IMakePriceCalculator:
    def ask_bid_prices(self) -> tuple:
        ...


class IMakeSizeCalculator:
    def ask_bid_sizes(self) -> tuple:
        ...


class IMaker:
    def post_limit_order(
        self, symbol: str, side_int: int, size: float, price: float
    ) -> str:
        ...

    def cancel_all_orders(self, symbol: str):
        ...


@dataclass
class MarketMakerConfig:
    symbol: str
    inverse: bool


class MarketMaker:
    def __init__(
        self,
        make_price_calculator: IMakePriceCalculator,
        make_size_calculator: IMakeSizeCalculator,
        maker: IMaker,
        price_getter: IPriceGetter,
        config: MarketMakerConfig,
    ):
        self._make_price_calculator = make_price_calculator
        self._make_size_calculator = make_size_calculator
        self._maker = maker
        self._ticker = price_getter
        self._config = config

        self._logger = getLogger(__class__.__name__)

    async def execute(self):
        ask_price, bid_price = self._make_price_calculator.ask_bid_prices()
        ask_size, bid_size = self._make_size_calculator.ask_bid_sizes()

        ltp = self._ticker.last_price()
        self._logger.debug(f"{ltp=}")
        self._logger.debug(f"(ask_price, ask_size) = ({ask_price}, {ask_size})")
        self._logger.debug(f"(bid_price, bid_size) = ({bid_price}, {bid_size})")

        ask_price = max(ltp + 1, ask_price)
        bid_price = min(ltp - 1, bid_price)
        self._logger.debug("best priced")
        self._logger.debug(f"(ask_price, ask_size) = ({ask_price}, {ask_size})")
        self._logger.debug(f"(bid_price, bid_size) = ({bid_price}, {bid_size})")

        # cancel order
        self._maker.cancel_all_orders(symbol=self._config.symbol)

        if self._config.inverse:
            ask_price = 1 / ask_price
            bid_price = 1 / bid_price
            # bid(short) order
            self._maker.post_limit_order(
                symbol=self._config.symbol,
                side_int=1,  # inversed
                size=ask_size,
                price=ask_price,
            )

            # ask(long) order
            self._maker.post_limit_order(
                symbol=self._config.symbol,
                side_int=-1,  # inversed
                size=bid_size,
                price=bid_price,
            )
        else:
            raise NotImplementedError
