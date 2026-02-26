from db.database import get_db


async def init_tasks_table() -> None:
    db = await get_db()
    await db.execute("""
        CREATE TABLE IF NOT EXISTS last_task (
            id      INTEGER PRIMARY KEY CHECK (id = 1),
            chat_id INTEGER NOT NULL,
            msg_id  INTEGER NOT NULL
        )
    """)
    await db.commit()
    await db.close()


async def save_last_task(chat_id: int, message_id: int) -> None:
    db = await get_db()
    await db.execute("""
        INSERT INTO last_task (id, chat_id, msg_id)
        VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            chat_id = excluded.chat_id,
            msg_id  = excluded.msg_id
    """, (chat_id, message_id))
    await db.commit()
    await db.close()


async def get_last_task() -> tuple[int, int] | None:
    db = await get_db()
    cursor = await db.execute(
        "SELECT chat_id, msg_id FROM last_task WHERE id = 1"
    )
    row = await cursor.fetchone()
    await db.close()
    return (row[0], row[1]) if row else None
