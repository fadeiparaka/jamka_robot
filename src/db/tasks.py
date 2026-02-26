import json

from db.database import get_db


async def init_tasks_table() -> None:
    db = await get_db()

    # Создаём таблицу если её ещё нет (новая схема)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS last_task (
            id       INTEGER PRIMARY KEY CHECK (id = 1),
            chat_id  INTEGER NOT NULL,
            msg_ids  TEXT    NOT NULL
        )
    """)

    # Миграция: если есть старая колонка msg_id — переносим данные и пересоздаём таблицу
    cursor = await db.execute("PRAGMA table_info(last_task)")
    columns = [row[1] for row in await cursor.fetchall()]

    if "msg_id" in columns and "msg_ids" not in columns:
        # Читаем старые данные
        cursor = await db.execute("SELECT chat_id, msg_id FROM last_task WHERE id = 1")
        row = await cursor.fetchone()

        # Пересоздаём таблицу с новой схемой
        await db.execute("DROP TABLE last_task")
        await db.execute("""
            CREATE TABLE last_task (
                id       INTEGER PRIMARY KEY CHECK (id = 1),
                chat_id  INTEGER NOT NULL,
                msg_ids  TEXT    NOT NULL
            )
        """)

        # Переносим старые данные если были
        if row:
            import json
            await db.execute(
                "INSERT INTO last_task (id, chat_id, msg_ids) VALUES (1, ?, ?)",
                (row[0], json.dumps([row[1]]))
            )
    cursor = await db.execute("PRAGMA table_info(last_task)")
    columns = [row[1] for row in await cursor.fetchall()]
    print(">>> last_task columns:", columns)

    await db.commit()
    await db.close()



async def save_last_task(chat_id: int, message_ids: list[int]) -> None:
    db = await get_db()
    await db.execute("""
        INSERT INTO last_task (id, chat_id, msg_ids)
        VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            chat_id = excluded.chat_id,
            msg_ids = excluded.msg_ids
    """, (chat_id, json.dumps(message_ids)))
    await db.commit()
    await db.close()


async def get_last_task() -> tuple[int, list[int]] | None:
    db = await get_db()
    cursor = await db.execute(
        "SELECT chat_id, msg_ids FROM last_task WHERE id = 1"
    )
    row = await cursor.fetchone()
    await db.close()
    if not row:
        return None
    return (row[0], json.loads(row[1]))
