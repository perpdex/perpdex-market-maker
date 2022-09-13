import asyncio
import sys
import time
from dataclasses import dataclass
from logging import getLogger


class IMarketMaker:
    def execute(self):
        ...


class IInfoLogger:
    def log(self):
        ...


@dataclass
class BotConfig:
    trade_loop_sec: int
    balance_loop_sec: int


class Bot:
    def __init__(
        self,
        config: BotConfig,
        market_maker: IMarketMaker,
        info_logger: IInfoLogger,
    ):
        self._config = config
        self._market_maker = market_maker
        self._info_logger = info_logger

        self._logger = getLogger(__name__)

        self._task: asyncio.Task = None

    def health_check(self) -> bool:
        return not self._task.done() and not self._task_b.done()

    def start(self):
        self._logger.debug("start")
        self._task = asyncio.create_task(self._trade())
        self._task_b = asyncio.create_task(self._log_info())

    async def stop(self):
        self._logger.debug("force stop running tasks")
        for task in [self._task, self._task_b]:
            if task is None:
                continue

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            self._logger.debug(f"force stopped {task=}")

    async def _trade(self):
        self._logger.debug("start _trade")
        try:
            while True:
                start = time.time()

                # make
                await self._market_maker.execute()

                passed = time.time() - start
                await asyncio.sleep(max(0, self._config.trade_loop_sec - passed))

        except BaseException:
            self._logger.error(sys.exc_info(), exc_info=True)

    async def _log_info(self):
        self._logger.debug("start _log_info")
        while True:
            self._info_logger.log()
            self._logger.debug("bot info logged")
            await asyncio.sleep(self._config.balance_loop_sec)
