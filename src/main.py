import asyncio
import logging
import sys

from bot.loader import bot, dp
from db.users import init_users_table


async def main():
    # базовая настройка логов в stdout
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    await init_users_table()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
    