from logging import getLogger
import time
from dataclasses import dataclass, field
from typing import Optional
from ..contracts.utils import get_contract_from_abi_json

import web3

Q96: int = 0x1000000000000000000000000  # same as 1 << 96
MAX_UINT: int = int(web3.constants.MAX_INT, base=16)
DECIMALS: int = 18


@dataclass
class PerpdexContractTickerConfig:
    market_contract_abi_json_filepath: str
    update_limit_sec: float = 0.5
    inverse: bool = False


class PerpdexContractTicker:
    def __init__(self, w3, config: PerpdexContractTickerConfig):
        self._w3 = w3
        self._config = config

        self._market_contract = get_contract_from_abi_json(
            w3,
            config.market_contract_abi_json_filepath,
        )

        self._mark_price = 0.0
        self._last_ts = 0.0

    def bid_price(self):
        return self._get_mark_price()

    def ask_price(self):
        return self._get_mark_price()

    def last_price(self):
        return self._get_mark_price()

    def _get_mark_price(self) -> float:
        if time.time() - self._last_ts >= self._config.update_limit_sec:
            price_x96 = self._market_contract.functions.getMarkPriceX96().call()
            self._mark_price = price_x96 / Q96
        if self._config.inverse:
            return 1 / self._mark_price
        return self._mark_price


@dataclass
class PerpdexOrdererConfig:
    market_contract_abi_json_filepaths: list
    exchange_contract_abi_json_filepath: str
    inverse: bool
    tx_options: dict = field(default_factory=dict)


class PerpdexOrderer:
    def __init__(self, w3, config: PerpdexOrdererConfig):
        self._w3 = w3
        self._config = config
        self._logger = getLogger(__name__)

        self._exchange_contract = get_contract_from_abi_json(
            w3,
            config.exchange_contract_abi_json_filepath,
        )

        self._symbol_to_market_contract: dict = {}
        for filepath in config.market_contract_abi_json_filepaths:
            contract = get_contract_from_abi_json(w3, filepath)
            symbol = contract.functions.symbol().call()
            self._symbol_to_market_contract[symbol] = contract

    def cancel_all_orders(self, symbol: str):
        self.cancel_all_ask_orders(symbol=symbol)
        self.cancel_all_bid_orders(symbol=symbol)

    def cancel_all_bid_orders(self, symbol: str):
        market_contract = self._symbol_to_market_contract[symbol]
        order_ids = self._exchange_contract.functions.getLimitOrderIds(
            self._w3.eth.default_account,  # trader
            market_contract.address,  # market
            True,  # isBid
        ).call()
        self._logger.debug(f"Bid orderIds {order_ids}")
        for order_id in order_ids:
            self.cancel_limit_order(symbol=symbol, side_int=1, order_id=order_id)

    def cancel_all_ask_orders(self, symbol: str):
        market_contract = self._symbol_to_market_contract[symbol]
        order_ids = self._exchange_contract.functions.getLimitOrderIds(
            self._w3.eth.default_account,  # trader
            market_contract.address,  # market
            False,  # isBid
        ).call()
        self._logger.debug(f"Ask orderIds {order_ids}")
        for order_id in order_ids:
            self.cancel_limit_order(symbol=symbol, side_int=-1, order_id=order_id)

    def cancel_limit_order(self, symbol: str, side_int: int, order_id: str):
        self._logger.debug(
            f"cancel_limit_order start {symbol=}, {side_int=}, {order_id=}"
        )
        market_contract = self._symbol_to_market_contract[symbol]

        method_call = self._exchange_contract.functions.cancelLimitOrder(
            dict(
                market=market_contract.address,
                isBid=side_int < 0 if self._config.inverse else side_int > 0,
                orderId=order_id,
                deadline=_get_deadline(),
            )
        )

        try:
            self._transact_with_retry(method_call, 3, "will retry cancel_limit_order")
            self._logger.debug("cancel_limit_order finish")
        except web3.exceptions.ContractLogicError as e:
            if "OBL_CO: already fully executed" in str(e):
                self._logger.info(f"{order_id=} is already fully filled")
                self._logger.debug("cancel_limit_order skip")
            elif "MOBL_CLO: enough mm" in str(e):
                self._logger.info(f"{order_id=} is not my order")
                self._logger.debug("cancel_limit_order skip")
            elif "RBTL_R: key not exist" in str(e):
                self._logger.info(f"{order_id=} does not exist")
                self._logger.debug("cancel_limit_order skip")
            else:
                raise e

    def post_limit_order(self, symbol: str, side_int: int, size: float, price: float):
        self._logger.info(
            "post_limit_order symbol {} side_int {} size {} price {} isBid {}".format(
                symbol, side_int, size, price, side_int > 0
            )
        )
        if size == 0:
            self._logger.debug(f"{size=} is zero. will skip")

        assert side_int != 0

        if symbol not in self._symbol_to_market_contract:
            raise ValueError(f"market address not initialized: {symbol=}")

        # get market address from symbol string
        market_contract = self._symbol_to_market_contract[symbol]

        # calculate amount with decimals from size
        amount = int(size * (10**DECIMALS))
        price = 1 / price if self._config.inverse else price
        priceX96 = int(price * Q96)

        method_call = self._exchange_contract.functions.createLimitOrder(
            dict(
                market=market_contract.address,
                isBid=side_int < 0 if self._config.inverse else side_int > 0,
                base=amount,
                priceX96=priceX96,
                deadline=_get_deadline(),
                limitOrderType=0,  # PostOnly
            )
        )

        self._transact_with_retry(method_call, 3, "will retry post_limit_order")
        self._logger.debug("post_limit_order finish")

    def post_market_order(self, symbol: str, side_int: int, size: float):
        self._logger.info(
            "post_market_order symbol {} side_int {} size {}".format(
                symbol, side_int, size
            )
        )

        assert side_int != 0

        if symbol not in self._symbol_to_market_contract:
            raise ValueError(f"market address not initialized: {symbol=}")

        # get market address from symbol string
        market_contract = self._symbol_to_market_contract[symbol]
        share_price = market_contract.functions.getShareMarkPriceX96().call() / Q96
        self._logger.debug("share_price {}".format(share_price))

        # calculate amount with decimals from size
        amount = int(size * (10**DECIMALS))

        retry_count = 32
        for i in range(retry_count):
            if self._config.max_slippage is None:
                opposite_amount_bound = 0 if (side_int < 0) else MAX_UINT
            else:
                opposite_amount_bound = int(
                    _calc_opposite_amount_bound(
                        side_int > 0, amount, share_price, self._config.max_slippage
                    )
                )

            self._logger.debug(
                "amount {} opposite_amount_bound {}".format(
                    amount, opposite_amount_bound
                )
            )

            method_call = self._exchange_contract.functions.trade(
                dict(
                    trader=self._w3.eth.default_account,
                    market=market_contract.address,
                    isBaseToQuote=(side_int < 0),
                    isExactInput=(side_int < 0),  # same as isBaseToQuote
                    amount=amount,
                    oppositeAmountBound=opposite_amount_bound,
                    deadline=_get_deadline(),
                )
            )

            try:
                method_call.estimateGas()
            except Exception as e:
                if i == retry_count - 1:
                    raise
                amount = int(amount / 2)
                self._logger.debug(f"estimateGas raises {e=} retrying")
                continue

            tx_hash = method_call.transact(self._config.tx_options)
            self._w3.eth.wait_for_transaction_receipt(tx_hash)
            break

    def _transact_with_retry(
        self, method_call, retry_num: int, retry_message: str = ""
    ):
        while retry_num > 0:
            try:
                tx_hash = method_call.transact(self._config.tx_options)
                self._w3.eth.wait_for_transaction_receipt(tx_hash)
                break
            except ValueError as e:
                # nonce too low
                if "nonce too low" in str(e):
                    self._logger.error(e)
                    retry_num -= 1
                    if retry_num == 0:
                        raise e
                    self._logger.info(f"{retry_num=}. {retry_message}")
                else:
                    raise e


@dataclass
class PerpdexPositionGetterConfig:
    market_contract_abi_json_filepath: str
    exchange_contract_abi_json_filepath: str
    inverse: bool


class PerpdexPositionGetter:
    def __init__(self, w3, config: PerpdexPositionGetterConfig):
        self._w3 = w3
        self._config = config

        self._market_contract = get_contract_from_abi_json(
            w3,
            config.market_contract_abi_json_filepath,
        )
        self._exchange_contract = get_contract_from_abi_json(
            w3,
            config.exchange_contract_abi_json_filepath,
        )

    def current_position(self) -> float:
        base_share = self._exchange_contract.functions.getPositionShare(
            self._w3.eth.default_account,
            self._market_contract.address,
        ).call()
        pos = base_share / (10**DECIMALS)
        if self._config.inverse:
            return -pos
        return pos

    def unit_leverage_lot(self) -> float:
        account_value = self._exchange_contract.functions.getTotalAccountValue(
            self._w3.eth.default_account,
        ).call() / (10**DECIMALS)
        share_price = (
            self._market_contract.functions.getShareMarkPriceX96().call() / Q96
        )
        return account_value / share_price


def _get_deadline():
    return int(time.time()) + 2 * 60


def _calc_opposite_amount_bound(is_long, share, share_price, slippage):
    opposite_amount_center = share * share_price
    if is_long:
        return opposite_amount_center * (1 + slippage)
    else:
        return opposite_amount_center * (1 - slippage)
