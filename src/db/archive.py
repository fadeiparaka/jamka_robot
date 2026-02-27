import json
from db.database import get_db


async def init_archive_tables() -> None:
    db = await get_db()
    await db.execute("""
        CREATE TABLE IF NOT EXISTS weeks (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS archive_tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            week_id     INTEGER NOT NULL REFERENCES weeks(id),
            chat_id     INTEGER NOT NULL,
            message_ids TEXT    NOT NULL,
            is_album    INTEGER NOT NULL DEFAULT 0,
            title       TEXT    NOT NULL,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await db.commit()
    await db.close()


async def create_week(title: str) -> int:
    """Создаёт новую неделю, возвращает её id."""
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO weeks (title) VALUES (?)", (title,)
    )
    await db.commit()
    week_id = cursor.lastrowid
    await db.close()
    return week_id


async def get_all_weeks() -> list[dict]:
    """Возвращает все недели [{id, title}, ...]."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, title FROM weeks ORDER BY created_at ASC"
    )
    rows = await cursor.fetchall()
    await db.close()
    return [{"id": row[0], "title": row[1]} for row in rows]


async def get_weeks_count() -> int:
    db = await get_db()
    cursor = await db.execute("SELECT COUNT(*) FROM weeks")
    row = await cursor.fetchone()
    await db.close()
    return row[0]


async def add_archive_task(
    week_id: int,
    chat_id: int,
    message_ids: list[int],
    is_album: bool,
    title: str,
) -> None:
    db = await get_db()
    await db.execute(
        """
        INSERT INTO archive_tasks (week_id, chat_id, message_ids, is_album, title)
        VALUES (?, ?, ?, ?, ?)
        """,
        (week_id, chat_id, json.dumps(message_ids), int(is_album), title),
    )
    await db.commit()
    await db.close()


async def get_tasks_by_week(week_id: int) -> list[dict]:
    """Возвращает все задания недели [{id, chat_id, message_ids, is_album, title}, ...]."""
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT id, chat_id, message_ids, is_album, title
        FROM archive_tasks
        WHERE week_id = ?
        ORDER BY created_at ASC
        """,
        (week_id,),
    )
    rows = await cursor.fetchall()
    await db.close()
    return [
        {
            "id": row[0],
            "chat_id": row[1],
            "message_ids": json.loads(row[2]),
            "is_album": bool(row[3]),
            "title": row[4],
        }
        for row in rows
    ]

async def get_task_by_id(task_id: int) -> dict | None:
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, chat_id, message_ids, is_album, title FROM archive_tasks WHERE id = ?",
        (task_id,)
    )
    row = await cursor.fetchone()
    await db.close()
    if not row:
        return None
    return {
        "id": row[0],
        "chat_id": row[1],
        "message_ids": json.loads(row[2]),
        "is_album": bool(row[3]),
        "title": row[4],
    }
