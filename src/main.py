import asyncio
import logging
import sys

from bot.loader import bot, dp
from db.users import init_users_table
from db.tasks import init_tasks_table


async def main():
    # базовая настройка логов в stdout
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    await init_tasks_table()
    await init_users_table()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
