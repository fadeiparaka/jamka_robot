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
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS users_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            event      TEXT NOT NULL CHECK(event IN ('joined', 'left')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    await db.commit()
    await db.close()


async def add_user_from_message(message):
    db = await get_db()
    cursor = await db.execute(
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
    inserted = cursor.rowcount
    if inserted:
        await db.execute("INSERT INTO users_log (event) VALUES ('joined')")
    await db.commit()
    await db.close()


async def get_all_chat_ids():
    db = await get_db()
    cursor = await db.execute("SELECT chat_id FROM users")
    rows = await cursor.fetchall()
    await db.close()
    return [row[0] for row in rows]


async def delete_user_by_chat_id(chat_id: int):
    db = await get_db()
    cursor = await db.execute("DELETE FROM users WHERE chat_id = ?", (chat_id,))
    deleted = cursor.rowcount
    if deleted:
        await db.execute("INSERT INTO users_log (event) VALUES ('left')")
    await db.commit()
    await db.close()


async def get_users_count() -> int:
    db = await get_db()
    cursor = await db.execute("SELECT COUNT(*) FROM users")
    row = await cursor.fetchone()
    await db.close()
    return row[0]


async def get_stats() -> dict:
    db = await get_db()

    cursor = await db.execute("SELECT COUNT(*) FROM users")
    total = (await cursor.fetchone())[0]

    periods = {"day": 1, "week": 7, "month": 30}
    result = {"total": total}

    for name, days in periods.items():
        cursor = await db.execute(
            "SELECT COUNT(*) FROM users_log WHERE event='joined' AND created_at >= datetime('now', ?)",
            (f"-{days} days",),
        )
        joined = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT COUNT(*) FROM users_log WHERE event='left' AND created_at >= datetime('now', ?)",
            (f"-{days} days",),
        )
        left = (await cursor.fetchone())[0]

        result[name] = {"joined": joined, "left": left}

    await db.close()
    return result

async def get_last_update_time() -> str | None:
    db = await get_db()
    cursor = await db.execute(
        "SELECT created_at FROM users_log WHERE event='left' ORDER BY created_at DESC LIMIT 1"
    )
    row = await cursor.fetchone()
    await db.close()
    return row[0] if row else None
