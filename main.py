import asyncio
import sys
from logging import config, getLogger

import fire
import yaml
from dotenv import load_dotenv

from src import resolver

load_dotenv()

with open("main_logger_config.yml", encoding="UTF-8") as f:
    y = yaml.safe_load(f.read())
    config.dictConfig(y)


async def main(restart: bool):
    logger = getLogger(__name__)
    logger.info("start")

    while True:
        bot = resolver.create_market_maker_bot()
        bot.start()
        while bot.health_check():
            logger.debug("health check ok")
            await asyncio.sleep(10)
        await bot.stop()

        if not restart:
            break
        logger.warning("Restarting bot")

    logger.warning("exit")


class Cli:
    """market maker bot"""

    def run(self, restart: bool = True):
        """run arbitrage bot"""
        asyncio.run(main(restart))


if __name__ == "__main__":
    fire.Fire(Cli)
