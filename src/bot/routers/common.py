from aiogram import Router, F
from aiogram.types import Message
import logging

from db.users import add_user_from_message
from bot import texts
from config import TASKS_CHANNEL_ID

logger = logging.getLogger(__name__)

router = Router(name="common")


@router.message(~F.text.startswith("/"))
async def handle_task_answer(message: Message):
    # 0. Теперь сюда команды вообще не попадают — фильтр на уровне декоратора
    
    # 1. Должно быть reply
    if not message.reply_to_message:
        return

    src = message.reply_to_message

    # 2. Ответ только на сообщения бота
    if not src.from_user or not src.from_user.is_bot:
        return

    # 3. В сообщении с заданием должен быть текст с заголовком
    if not src.text:
        await message.answer(texts.NO_TITLE_TEXT)
        return

    task_title = extract_task_title(src.text)
    if not task_title:
        await message.answer(texts.NO_TITLE_TEXT)
        return

    if not TASKS_CHANNEL_ID:
        await message.answer("Канал для ответов не настроен.")
        return

    try:
        await message.bot.copy_message(
            chat_id=TASKS_CHANNEL_ID,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
    except Exception as e:
        logger.exception("Не удалось переслать ответ в канал: %s", e)
        await message.answer("Не удалось переслать ответ в канал.")
        return

    username = message.from_user.username
    if username:
        author_tag = f"@{username}"
    else:
        full_name = " ".join(
            filter(None, [message.from_user.first_name, message.from_user.last_name])
        ) or "Без имени"
        author_tag = f"{full_name} (id: {message.from_user.id})"

    caption = f"{task_title}\n\n{author_tag}"

    await message.bot.send_message(
        chat_id=TASKS_CHANNEL_ID,
        text=caption,
    )

@router.message(F.text == "/start")
async def cmd_start(message: Message):
    await add_user_from_message(message)
    await message.answer(texts.WELCOME_TEXT)


@router.message(F.text == "/help")
async def cmd_help(message: Message):
    await add_user_from_message(message)
    await message.answer(texts.HELP_TEXT)


def extract_task_title(text: str) -> str | None:
    if not text:
        return None
    parts = text.split(".", 1)
    title = parts[0].strip()
    return title or None


@router.message()  # универсальный, но с доп.проверками внутри
async def handle_task_answer(message: Message):
    """
    Обрабатываем только обычные сообщения, которые:
    - не являются командами,
    - являются reply на сообщение БОТА.
    """

    # 0. Игнорим команды (включая /post), за них отвечают другие хендлеры
    if message.text and message.text.startswith("/"):
        return

    # 1. Должно быть reply
    if not message.reply_to_message:
        return

    src = message.reply_to_message

    # 2. Ответ только на сообщения бота
    if not src.from_user or not src.from_user.is_bot:
        # это reply на чьё-то чужое сообщение → игнор
        return

    # 3. В сообщении с заданием должен быть текст с заголовком
    if not src.text:
        await message.answer(texts.NO_TITLE_TEXT)
        return

    task_title = extract_task_title(src.text)
    if not task_title:
        await message.answer(texts.NO_TITLE_TEXT)
        return

    if not TASKS_CHANNEL_ID:
        await message.answer("Канал для ответов не настроен.")
        return

    # 4. Копируем ответ пользователя в канал
    try:
        await message.bot.copy_message(
            chat_id=TASKS_CHANNEL_ID,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
    except Exception as e:
        logger.exception("Не удалось переслать ответ в канал: %s", e)
        await message.answer("Не удалось переслать ответ в канал.")
        return

    # 5. Подпись: номер задания + автор
    username = message.from_user.username
    if username:
        author_tag = f"@{username}"
    else:
        full_name = " ".join(
            filter(
                None,
                [message.from_user.first_name, message.from_user.last_name],
            )
        ) or "Без имени"
        author_tag = f"{full_name} (id: {message.from_user.id})"

    caption = f"{task_title}\n\n{author_tag}"

    await message.bot.send_message(
        chat_id=TASKS_CHANNEL_ID,
        text=caption,
    )

