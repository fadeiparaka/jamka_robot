import asyncio
import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from config import ADMIN_IDS
from db.users import get_all_chat_ids, delete_user_by_chat_id
from bot.texts import (
    POST_ONLY_REPLY_TEXT,
    POST_STARTED_TEXT,
    POST_DONE_TEXT,
    NOT_ADMIN_TEXT,
)

router = Router(name="admin")
logger = logging.getLogger(__name__)


@router.message(Command("post"), F.from_user.id.in_(ADMIN_IDS))
async def cmd_post(message: Message):
    logger.info("CMD /post from admin id=%s", message.from_user.id)

    if not message.reply_to_message:
        await message.answer(POST_ONLY_REPLY_TEXT)
        return

    src_msg = message.reply_to_message
    loading_msg = await message.answer(POST_STARTED_TEXT)

    chat_ids = await get_all_chat_ids()
    logger.info("Broadcast to %s chats", len(chat_ids))

    sent = 0
    removed = 0

    for chat_id in chat_ids:
        try:
            await message.bot.copy_message(
                chat_id=chat_id,
                from_chat_id=src_msg.chat.id,
                message_id=src_msg.message_id,
            )
            sent += 1
            await asyncio.sleep(0.05)

        except TelegramForbiddenError:
            # Бот заблокирован пользователем — удаляем из БД
            await delete_user_by_chat_id(chat_id)
            removed += 1
            logger.info("Removed blocked user chat_id=%s", chat_id)

        except TelegramBadRequest:
            # Чат не найден или удалён — тоже удаляем
            await delete_user_by_chat_id(chat_id)
            removed += 1
            logger.info("Removed invalid chat_id=%s", chat_id)

        except Exception as e:
            # Прочие ошибки — просто пропускаем, не удаляем
            logger.warning("Failed to send to %s: %s", chat_id, e)
            continue

    await loading_msg.delete()
    await message.answer(
        f"{POST_DONE_TEXT} Отправлено: {sent}. Удалено из БД: {removed}."
    )


@router.message(Command("post"))
async def not_admin_post(message: Message):
    await message.answer(NOT_ADMIN_TEXT)
