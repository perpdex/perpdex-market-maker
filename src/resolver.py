import os

from . import market_maker as mm
from .bot import Bot, BotConfig
from .contracts.utils import get_tx_options, get_w3
from .exchanges import binance, perpdex


def create_market_maker_bot() -> Bot:
    # setup perpdex contract infos
    web3_network_name = os.environ["WEB3_NETWORK_NAME"]
    _w3 = get_w3(
        network_name=web3_network_name,
        web3_provider_uri=os.environ["WEB3_PROVIDER_URI"],
        user_private_key=os.environ["USER_PRIVATE_KEY"],
    )
    perpdex_market_name = os.getenv("PERPDEX_MARKET", "ETH")
    perpdex_is_inverse = bool(os.getenv("PERPDEX_MARKET_INVERSE", 0))
    abi_json_dirpath = os.getenv(
        "PERPDEX_CONTRACT_ABI_JSON_DIRPATH",
        "/app/deps/perpdex-contract/deployments/" + web3_network_name,
    )
    _market_contract_filepath = os.path.join(
        abi_json_dirpath, "PerpdexMarket{}.json".format(perpdex_market_name)
    )
    _exchange_contract_filepath = os.path.join(abi_json_dirpath, "PerpdexExchange.json")
    tx_options = get_tx_options(web3_network_name)

    # init dependencies
    perpdex_pos_getter = perpdex.PerpdexPositionGetter(
        w3=_w3,
        config=perpdex.PerpdexPositionGetterConfig(
            market_contract_abi_json_filepath=_market_contract_filepath,
            exchange_contract_abi_json_filepath=_exchange_contract_filepath,
            inverse=perpdex_is_inverse,
        ),
    )
    # binance_exchange = ccxt.binance({"options": {"defaultType": "spot"}})
    # binance_ohlcv_getter = binance.BinanceRestOhlcv(
    #     ccxt_exchange=binance_exchange,
    #     symbol=os.getenv("BINANCE_SPOT_SYMBOL", "ETH/USDT"),
    #     timeframe="1m",
    # )
    perpdex_maker = perpdex.PerpdexOrderer(
        w3=_w3,
        config=perpdex.PerpdexOrdererConfig(
            market_contract_abi_json_filepaths=[_market_contract_filepath],
            exchange_contract_abi_json_filepath=_exchange_contract_filepath,
            inverse=perpdex_is_inverse,
            tx_options=tx_options,
        ),
    )

    perpdex_ticker = perpdex.PerpdexContractTicker(
        w3=_w3,
        config=perpdex.PerpdexContractTickerConfig(
            market_contract_abi_json_filepath=_market_contract_filepath,
            update_limit_sec=0.5,
            inverse=perpdex_is_inverse,
        ),
    )

    # init mm
    market_maker = mm.MarketMaker(
        # make_price_calculator=mm.NormMakePriceCalculator(
        #     ohlcv_getter=binance_ohlcv_getter,
        #     config=mm.NormMakePriceCalculatorConfig(
        #         timeperiod=int(os.getenv("PRICE_BAR_NUM", "200")),
        #         diff_k=float(os.getenv("PRICE_BAR_DIFF_K", "0.2")),
        #     ),
        # ),
        make_price_calculator=mm.SimpleMakePriceCalculator(
            ticker=perpdex_ticker,
            config=mm.SimpleMakePriceCalculatorConfig(
                diff=1,
            ),
        ),
        make_size_calculator=mm.SimpleMakeSizeCalculator(
            position_getter=perpdex_pos_getter,
            config=mm.SimpleMakeSizeCalculatorConfig(
                unit_lot_size=float(os.getenv("UNIT_LOT_SIZE", "0.01")),
            ),
        ),
        maker=perpdex_maker,
        price_getter=perpdex_ticker,
        config=mm.MarketMakerConfig(
            symbol=perpdex_market_name,
            inverse=perpdex_is_inverse,
        ),
    )
    return Bot(
        market_maker=market_maker,
        config=BotConfig(
            trade_loop_sec=60,
            balance_loop_sec=60.0,
        ),
    )
