import asyncio
import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter
import math
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from datetime import datetime, timezone, timedelta

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.archive import get_all_weeks, create_week, add_archive_task
from db.users import get_all_chat_ids, delete_user_by_chat_id, get_stats, get_last_update_time, set_last_broadcast_time, ban_user, unban_user
from bot.texts import (
    ARCHIVE_CHOOSE_WEEK_TEXT,
    ARCHIVE_NEW_WEEK_PROMPT_TEXT,
    ARCHIVE_SAVED_TEXT,
    ARCHIVE_SKIPPED_TEXT,
    PEOPLE_TEXT,
    PEOPLE_LOADING_TEXT,
    BROADCAST_STAGE_0,
    BROADCAST_STAGE_25,
    BROADCAST_STAGE_50,
    BROADCAST_STAGE_75,
    BROADCAST_DONE_TEXT,
    BAN_USAGE_TEXT,
    UNBAN_USAGE_TEXT,
    BAN_SUCCESS_TEXT,
    UNBAN_SUCCESS_TEXT,
    BAN_NOT_FOUND_TEXT,
    UNBAN_NOT_FOUND_TEXT,
)

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
class ArchiveFSM(StatesGroup):
    choosing_week = State()
    entering_week_name = State()


router = Router(name="admin")
logger = logging.getLogger(__name__)

async def keep_typing(bot, chat_id: int, stop_event: asyncio.Event):
    while not stop_event.is_set():
        await bot.send_chat_action(chat_id, "typing")
        await asyncio.sleep(4)


# Буфер последнего альбома от админа: media_group_id -> [message_id, ...]
_admin_album_buffer: dict[str, list[Message]] = {}


@router.message(F.media_group_id, F.from_user.id.in_(ADMIN_IDS), ~F.reply_to_message)
async def handle_admin_album(message: Message):
    group_id = message.media_group_id
    if group_id not in _admin_album_buffer:
        _admin_album_buffer[group_id] = []
    _admin_album_buffer[group_id].append(message)
    logger.info("Buffered admin album %s: msg_id=%s", group_id, message.message_id)



@router.message(Command("post"), F.from_user.id.in_(ADMIN_IDS))
async def cmd_post(message: Message, state: FSMContext):
    logger.info("CMD /post from admin id=%s", message.from_user.id)

    if not message.reply_to_message:
        await message.answer(POST_ONLY_REPLY_TEXT)
        return

    args = message.text.split()[1:]
    do_pin = "pin" in args

    src_msg = message.reply_to_message
    loading_msg = await message.answer(POST_STARTED_TEXT)

    group_id = src_msg.media_group_id
    if group_id:
        await asyncio.sleep(0.7)

    if group_id and group_id in _admin_album_buffer:
        album_messages = sorted(_admin_album_buffer.pop(group_id), key=lambda m: m.message_id)
        message_ids = [m.message_id for m in album_messages]
        album_caption = next(
            (m.caption for m in album_messages if m.caption),
            None
        )
        is_album = True
    else:
        album_messages = None
        album_caption = None
        message_ids = [src_msg.message_id]
        is_album = False

    chat_ids = await get_all_chat_ids()
    total = len(chat_ids)
    logger.info("Broadcast to %s chats, album=%s, pin=%s", total, is_album, do_pin)

    sent = 0
    removed = 0
    last_stage = -1

    BROADCAST_STAGES = [
        (0,  BROADCAST_STAGE_0),
        (25, BROADCAST_STAGE_25),
        (50, BROADCAST_STAGE_50),
        (75, BROADCAST_STAGE_75),
    ]

    stop_typing = asyncio.Event()
    asyncio.create_task(keep_typing(message.bot, message.chat.id, stop_typing))

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

                percent = int(sent / total * 100) if total > 0 else 100
                for threshold, text in reversed(BROADCAST_STAGES):
                    if percent >= threshold and threshold > last_stage:
                        try:
                            await loading_msg.edit_text(text, parse_mode="HTML")
                        except Exception:
                            pass
                        last_stage = threshold
                        break

                await asyncio.sleep(0.05)
                break

            except TelegramRetryAfter as e:
                logger.warning("Rate limit, sleeping %s sec", e.retry_after)
                try:
                    await loading_msg.edit_text(
                        f"⏳ Пауза {e.retry_after} сек (лимит Telegram)...",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
                await asyncio.sleep(e.retry_after)
                retries -= 1

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

    stop_typing.set()
    await set_last_broadcast_time() 


    await loading_msg.edit_text(
        BROADCAST_DONE_TEXT.format(sent=sent, total=total, removed=removed),
        parse_mode="HTML"
    )

    if do_pin and sent > 0:
        await save_last_task(src_msg.chat.id, message_ids)
        logger.info("Saved last task: chat_id=%s msg_ids=%s", src_msg.chat.id, message_ids)

        raw_text = src_msg.text or src_msg.caption or album_caption or ""
        title = (raw_text.split(".", 1)[0].strip() + ".") if raw_text else "Без названия."

        weeks = await get_all_weeks()
        kb = _choose_week_keyboard(weeks, page=0)
        await message.answer(ARCHIVE_CHOOSE_WEEK_TEXT, reply_markup=kb.as_markup())

        await state.set_state(ArchiveFSM.choosing_week)
        await state.update_data(
            arc_chat_id=src_msg.chat.id,
            arc_message_ids=message_ids,
            arc_is_album=is_album,
            arc_title=title,
            arc_page=0,
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

@router.message(Command("people"), F.from_user.id.in_(ADMIN_IDS))
async def cmd_people(message: Message):
    loading_msg = await message.answer(PEOPLE_LOADING_TEXT)
    stats = await get_stats()
    last_update = await get_last_update_time()

    if last_update:
        # Форматируем "2026-03-01 10:32:00" → "01.03.2026 в 10:32"
        dt = datetime.strptime(last_update, "%Y-%m-%d %H:%M:%S")
        dt_moscow = dt.replace(tzinfo=timezone.utc) + timedelta(hours=3)
        last_update_str = dt_moscow.strftime("%d.%m.%Y в %H:%M")
    else:
        last_update_str = "ещё не было"

    text = PEOPLE_TEXT.format(
        total=stats["total"],
        day_joined=stats["day"]["joined"],
        day_left=stats["day"]["left"],
        week_joined=stats["week"]["joined"],
        week_left=stats["week"]["left"],
        month_joined=stats["month"]["joined"],
        month_left=stats["month"]["left"],
        last_update=last_update_str,
    )
    await loading_msg.delete()
    await message.answer(text)


@router.message(Command("people"))
async def not_admin_people(message: Message):
    await message.answer(NOT_ADMIN_TEXT)

@router.message(Command("ban"), F.from_user.id.in_(ADMIN_IDS))
async def cmd_ban(message: Message):
    args = message.text.split()[1:]
    if not args or not args[0].isdigit():
        await message.answer(BAN_USAGE_TEXT)
        return
    user_id = int(args[0])
    success = await ban_user(user_id)
    if success:
        await message.answer(BAN_SUCCESS_TEXT.format(user_id=user_id))
    else:
        await message.answer(BAN_NOT_FOUND_TEXT.format(user_id=user_id))


@router.message(Command("ban"))
async def not_admin_ban(message: Message):
    await message.answer(NOT_ADMIN_TEXT)


@router.message(Command("unban"), F.from_user.id.in_(ADMIN_IDS))
async def cmd_unban(message: Message):
    args = message.text.split()[1:]
    if not args or not args[0].isdigit():
        await message.answer(UNBAN_USAGE_TEXT)
        return
    user_id = int(args[0])
    success = await unban_user(user_id)
    if success:
        await message.answer(UNBAN_SUCCESS_TEXT.format(user_id=user_id))
    else:
        await message.answer(UNBAN_NOT_FOUND_TEXT.format(user_id=user_id))


@router.message(Command("unban"))
async def not_admin_unban(message: Message):
    await message.answer(NOT_ADMIN_TEXT)


def _choose_week_keyboard(weeks: list[dict], page: int) -> InlineKeyboardBuilder:
    WEEKS_PER_PAGE = 8
    total_pages = max(1, math.ceil(len(weeks) / WEEKS_PER_PAGE))
    start = page * WEEKS_PER_PAGE
    page_weeks = weeks[start: start + WEEKS_PER_PAGE]

    builder = InlineKeyboardBuilder()

    for i, w in enumerate(page_weeks):
        global_num = start + i + 1
        builder.row(InlineKeyboardButton(
            text=f"Неделя {global_num}: {w['title']}",
            callback_data=f"aw_week:{w['id']}",
        ))

    builder.row(InlineKeyboardButton(text="➕ Новая неделя", callback_data="aw_new"))
    builder.row(InlineKeyboardButton(text="Пропустить", callback_data="aw_skip"))

    if total_pages > 1:
        prev_page = (page - 1) % total_pages
        next_page = (page + 1) % total_pages
        builder.row(
            InlineKeyboardButton(text="<<|", callback_data=f"aw_page:{prev_page}"),
            InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="aw_noop"),
            InlineKeyboardButton(text="|>>", callback_data=f"aw_page:{next_page}"),
        )

    return builder



@router.callback_query(ArchiveFSM.choosing_week, F.data.startswith("aw_week:"))
async def cb_aw_choose_week(call: CallbackQuery, state: FSMContext):
    week_id = int(call.data.split(":")[1])
    data = await state.get_data()
    await add_archive_task(
        week_id=week_id,
        chat_id=data["arc_chat_id"],
        message_ids=data["arc_message_ids"],
        is_album=data["arc_is_album"],
        title=data["arc_title"],
    )
    await state.clear()
    await call.message.edit_text(ARCHIVE_SAVED_TEXT)
    await call.answer()


@router.callback_query(ArchiveFSM.choosing_week, F.data == "aw_new")
async def cb_aw_new_week(call: CallbackQuery, state: FSMContext):
    await state.set_state(ArchiveFSM.entering_week_name)
    await call.message.edit_text(ARCHIVE_NEW_WEEK_PROMPT_TEXT)
    await call.answer()


@router.message(ArchiveFSM.entering_week_name, F.from_user.id.in_(ADMIN_IDS))
async def cb_aw_enter_name(message: Message, state: FSMContext):
    title = message.text.strip()
    data = await state.get_data()
    week_id = await create_week(title)
    await add_archive_task(
        week_id=week_id,
        chat_id=data["arc_chat_id"],
        message_ids=data["arc_message_ids"],
        is_album=data["arc_is_album"],
        title=data["arc_title"],
    )
    await state.clear()
    await message.answer(ARCHIVE_SAVED_TEXT)


@router.callback_query(ArchiveFSM.choosing_week, F.data == "aw_skip")
async def cb_aw_skip(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(ARCHIVE_SKIPPED_TEXT)
    await call.answer()


@router.callback_query(ArchiveFSM.choosing_week, F.data.startswith("aw_page:"))
async def cb_aw_page(call: CallbackQuery, state: FSMContext):
    page = int(call.data.split(":")[1])
    weeks = await get_all_weeks()
    kb = _choose_week_keyboard(weeks, page=page)
    await call.message.edit_reply_markup(reply_markup=kb.as_markup())
    await state.update_data(arc_page=page)
    await call.answer()


@router.callback_query(ArchiveFSM.choosing_week, F.data == "aw_noop")
async def cb_aw_noop(call: CallbackQuery):
    await call.answer()
