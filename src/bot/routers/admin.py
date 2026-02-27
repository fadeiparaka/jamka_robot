import asyncio
import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter

from config import ADMIN_IDS
from db.users import get_all_chat_ids, delete_user_by_chat_id
from db.tasks import save_last_task
from bot.texts import (
    POST_ONLY_REPLY_TEXT,
    POST_STARTED_TEXT,
    POST_DONE_TEXT,
    NOT_ADMIN_TEXT,
    PIN_ONLY_REPLY_TEXT,
    PIN_STARTED_TEXT,
    PIN_DONE_TEXT,
    PIN_NO_RIGHTS_TEXT,
)

router = Router(name="admin")
logger = logging.getLogger(__name__)

# Буфер последнего альбома от админа: media_group_id -> [message_id, ...]
_admin_album_buffer: dict[str, list[int]] = {}


@router.message(F.media_group_id, F.from_user.id.in_(ADMIN_IDS))
async def handle_admin_album(message: Message):
    """Накапливаем message_id альбома от админа в буфер."""
    group_id = message.media_group_id
    if group_id not in _admin_album_buffer:
        _admin_album_buffer[group_id] = []
    _admin_album_buffer[group_id].append(message.message_id)
    logger.info("Buffered admin album %s: msg_id=%s", group_id, message.message_id)


@router.message(Command("post"), F.from_user.id.in_(ADMIN_IDS))
async def cmd_post(message: Message):
    logger.info("CMD /post from admin id=%s", message.from_user.id)

    if not message.reply_to_message:
        await message.answer(POST_ONLY_REPLY_TEXT)
        return

    args = message.text.split()[1:]
    do_pin = "pin" in args

    src_msg = message.reply_to_message
    loading_msg = await message.answer(POST_STARTED_TEXT)

    # Определяем: одиночное сообщение или альбом
    group_id = src_msg.media_group_id
    if group_id and group_id in _admin_album_buffer:
        message_ids = sorted(_admin_album_buffer.pop(group_id))
        is_album = True
    else:
        message_ids = [src_msg.message_id]
        is_album = False

    chat_ids = await get_all_chat_ids()
    logger.info("Broadcast to %s chats, album=%s, pin=%s", len(chat_ids), is_album, do_pin)

    sent = 0
    removed = 0

    for chat_id in chat_ids:
        retries = 3
        while retries > 0:
            try:
                if is_album:
                    results = await message.bot.copy_messages(
                        chat_id=chat_id,
                        from_chat_id=src_msg.chat.id,
                        message_ids=message_ids,
                    )
                    copied_msg_id = results[0].message_id
                else:
                    result = await message.bot.copy_message(
                        chat_id=chat_id,
                        from_chat_id=src_msg.chat.id,
                        message_id=src_msg.message_id,
                    )
                    copied_msg_id = result.message_id

                sent += 1

                if do_pin:
                    try:
                        await message.bot.pin_chat_message(
                            chat_id=chat_id,
                            message_id=copied_msg_id,
                            disable_notification=False,
                        )
                    except Exception as pin_err:
                        logger.warning("Pin failed for chat_id=%s: %s", chat_id, pin_err)

                await asyncio.sleep(0.05)
                break  # успешно — выходим из while

            except TelegramRetryAfter as e:
                logger.warning("Rate limit, sleeping %s sec", e.retry_after)
                await asyncio.sleep(e.retry_after)
                retries -= 1  # попробуем ещё раз

            except TelegramForbiddenError:
                await delete_user_by_chat_id(chat_id)
                removed += 1
                logger.info("Removed blocked user chat_id=%s", chat_id)
                break

            except TelegramBadRequest:
                await delete_user_by_chat_id(chat_id)
                removed += 1
                logger.info("Removed invalid chat_id=%s", chat_id)
                break

            except Exception as e:
                logger.warning("Failed to send to %s: %s", chat_id, e)
                break


    if do_pin and sent > 0:
        await save_last_task(src_msg.chat.id, message_ids)
        logger.info("Saved last task: chat_id=%s msg_ids=%s", src_msg.chat.id, message_ids)


    await loading_msg.delete()
    await message.answer(
        f"{POST_DONE_TEXT} Отправлено: {sent}. Удалено из БД: {removed}."
    )


@router.message(Command("post"))
async def not_admin_post(message: Message):
    await message.answer(NOT_ADMIN_TEXT)


@router.message(Command("pin"), F.from_user.id.in_(ADMIN_IDS))
async def cmd_pin(message: Message):
    logger.info("CMD /pin from admin id=%s", message.from_user.id)

    if not message.reply_to_message:
        await message.answer(PIN_ONLY_REPLY_TEXT)
        return

    loading_msg = await message.answer(PIN_STARTED_TEXT)

    try:
        await message.bot.pin_chat_message(
            chat_id=message.chat.id,
            message_id=message.reply_to_message.message_id,
            disable_notification=False,
        )
        await loading_msg.delete()
        await message.answer(PIN_DONE_TEXT)

    except TelegramForbiddenError:
        await loading_msg.delete()
        await message.answer(PIN_NO_RIGHTS_TEXT)

    except TelegramBadRequest as e:
        await loading_msg.delete()
        await message.answer(PIN_NO_RIGHTS_TEXT)
        logger.warning("pin_chat_message failed: %s", e)


@router.message(Command("pin"))
async def not_admin_pin(message: Message):
    await message.answer(NOT_ADMIN_TEXT)
