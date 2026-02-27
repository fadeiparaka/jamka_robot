import asyncio
import logging
import sys

from bot.loader import bot, dp
from db.users import init_users_table
from db.tasks import init_tasks_table
from db.archive import init_archive_tables
from bot.routers.forarchive import router as archive_router


async def main():
    # базовая настройка логов в stdout
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    await init_archive_tables()  
    await init_tasks_table()
    await init_users_table()
    dp.include_router(archive_router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
