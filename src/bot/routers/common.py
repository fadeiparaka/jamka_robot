from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
import logging

from db.users import add_user_from_message
from bot import texts
from config import TASKS_CHANNEL_ID
from db.tasks import get_last_task

logger = logging.getLogger(__name__)

router = Router(name="common")


@router.message(Command("start"))
async def cmd_start(message: Message):
    await add_user_from_message(message)
    await message.answer(texts.WELCOME_TEXT)
    last_task = await get_last_task()
    if last_task:
        task_chat_id, task_msg_id = last_task
        try:
            result = await message.bot.copy_message(
                chat_id=message.chat.id,
                from_chat_id=task_chat_id,
                message_id=task_msg_id,
            )
            await message.bot.pin_chat_message(
                chat_id=message.chat.id,
                message_id=result.message_id,
                disable_notification=True,
            )
        except Exception as e:
            logger.warning("Не удалось отправить/закрепить задание при /start: %s", e)


@router.message(Command("help"))
async def cmd_help(message: Message):
    await add_user_from_message(message)
    await message.answer(texts.HELP_TEXT)


@router.message(~F.text.startswith("/"), F.content_type == "text")
async def handle_task_answer(message: Message):
    if not message.reply_to_message:
        await message.answer(texts.NO_REPLY_TEXT)
        return

    src = message.reply_to_message

    if not src.from_user or not src.from_user.is_bot:
        return

    src_text = src.text or src.caption
    if not src_text:
        await message.answer(texts.NO_TITLE_TEXT)
        return

    task_title = extract_task_title(src_text)
    if not task_title:
        await message.answer(texts.NO_TITLE_TEXT)
        return

    if not TASKS_CHANNEL_ID:
        await message.answer(texts.CHANNEL_NOT_CONFIGURED_TEXT)
        return

    try:
        await message.bot.copy_message(
            chat_id=TASKS_CHANNEL_ID,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
    except Exception as e:
        logger.exception("Не удалось переслать ответ в канал: %s", e)
        await message.answer(texts.FORWARD_ERROR_TEXT)
        return

    username = message.from_user.username
    if username:
        author_tag = f"@{username}"
    else:
        full_name = " ".join(
            filter(None, [message.from_user.first_name, message.from_user.last_name])
        ) or "Без имени"
        author_tag = f"{full_name} (id: {message.from_user.id})"

    await message.bot.send_message(
        chat_id=TASKS_CHANNEL_ID,
        text=f"{task_title}\n\n{author_tag}",
    )

    await message.answer(texts.TASK_ACCEPTED_TEXT)


def extract_task_title(text: str) -> str | None:
    if not text:
        return None
    parts = text.split(".", 1)
    title = parts[0].strip()
    return title or None
