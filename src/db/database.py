import os
import aiosqlite

# Абсолютный путь до корня проекта
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(BASE_DIR, "bot.db")


async def get_db():
    """
    Открывает новое соединение с SQLite.
    Каждый вызов возвращает независимое соединение.
    """
    return await aiosqlite.connect(DB_PATH)
