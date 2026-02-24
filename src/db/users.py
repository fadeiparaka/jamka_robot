from .database import get_db


async def init_users_table():
    db = await get_db()
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            username TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, chat_id)
        )
        """
    )
    await db.commit()
    await db.close()


async def add_user_from_message(message):
    """
    Сохраняем пользователя и чат, если такой записи ещё нет.
    """
    db = await get_db()
    await db.execute(
        """
        INSERT OR IGNORE INTO users (user_id, chat_id, username)
        VALUES (?, ?, ?)
        """,
        (
            message.from_user.id,
            message.chat.id,
            message.from_user.username,
        ),
    )
    await db.commit()
    await db.close()


async def get_all_chat_ids():
    """
    Возвращает список chat_id всех пользователей бота.
    """
    db = await get_db()
    cursor = await db.execute("SELECT chat_id FROM users")
    rows = await cursor.fetchall()
    await db.close()
    return [row[0] for row in rows]

async def delete_user_by_chat_id(chat_id: int):
    db = await get_db()
    await db.execute("DELETE FROM users WHERE chat_id = ?", (chat_id,))
    await db.commit()
    await db.close()
