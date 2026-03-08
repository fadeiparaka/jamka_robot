import logging
import math

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from db.archive import get_all_weeks, get_tasks_by_week, get_task_by_id
from bot import texts

from db.archive import get_all_weeks, get_tasks_by_week
from bot.texts import (
    ALL_EMPTY_TEXT,
    ALL_WEEKS_HEADER_TEXT,
    ALL_WEEK_HEADER_TEXT,
    ALL_TASK_NOT_FOUND_TEXT,
)

router = Router(name="forarchive")
logger = logging.getLogger(__name__)

WEEKS_PER_PAGE = 10  # макс. недель на страницу (+ 1 строка на стрелки = 11 кнопок)
TASKS_PER_PAGE = 7   # макс. заданий на страницу (+ 1 кнопка Назад = 8)


def _weeks_keyboard(weeks: list[dict], page: int) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    total_pages = max(1, math.ceil(len(weeks) / WEEKS_PER_PAGE))
    start = page * WEEKS_PER_PAGE
    page_weeks = weeks[start: start + WEEKS_PER_PAGE]

    for w in page_weeks:
        builder.button(
            text=f"Неделя {weeks.index(w) + 1}: {w['title']}",
            callback_data=f"arc_week:{w['id']}:0",
        )

    builder.adjust(1)

    # Навигация
    prev_page = (page - 1) % total_pages
    next_page = (page + 1) % total_pages
    builder.row(
        InlineKeyboardButton(text="<<|", callback_data=f"arc_weeks_page:{prev_page}"),
        InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="arc_noop"),
        InlineKeyboardButton(text="|>>", callback_data=f"arc_weeks_page:{next_page}"),
    )
    return builder


def _tasks_keyboard(tasks: list[dict], week_id: int) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    for i, task in enumerate(tasks):
        builder.button(
            text=task["title"],
            callback_data=f"arc_task:{task['id']}",
        )
    builder.button(text="← Назад", callback_data="arc_back_weeks:0")
    builder.adjust(1)
    return builder

@router.message(F.text == texts.ARCHIVE_BUTTON_TEXT)
async def btn_archive(message: Message):
    await cmd_all(message)

@router.message(Command("all"))
async def cmd_all(message: Message):
    weeks = await get_all_weeks()
    if not weeks:
        await message.answer(ALL_EMPTY_TEXT)
        return

    kb = _weeks_keyboard(weeks, page=0)
    await message.answer(
        ALL_WEEKS_HEADER_TEXT,
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("arc_weeks_page:"))
async def cb_weeks_page(call: CallbackQuery):
    await call.answer()
    page = int(call.data.split(":")[1])
    weeks = await get_all_weeks()
    if not weeks:
        await call.answer(ALL_EMPTY_TEXT, show_alert=True)
        return

    kb = _weeks_keyboard(weeks, page=page)
    try:
        await call.message.edit_text(
            ALL_WEEKS_HEADER_TEXT,
            reply_markup=kb.as_markup(),
        )
    except TelegramBadRequest:
        pass  


@router.callback_query(F.data.startswith("arc_back_weeks:"))
async def cb_back_weeks(call: CallbackQuery):
    await call.answer()
    page = int(call.data.split(":")[1])
    weeks = await get_all_weeks()
    if not weeks:
        await call.answer(ALL_EMPTY_TEXT, show_alert=True)
        return

    kb = _weeks_keyboard(weeks, page=page)
    try:
        await call.message.edit_text(
            ALL_WEEKS_HEADER_TEXT,
            reply_markup=kb.as_markup(),
        )
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("arc_week:"))
async def cb_week(call: CallbackQuery):
    await call.answer()
    _, week_id_str, _ = call.data.split(":")
    week_id = int(week_id_str)

    weeks = await get_all_weeks()
    week = next((w for w in weeks if w["id"] == week_id), None)
    if not week:
        await call.answer("Неделя не найдена.", show_alert=True)
        return

    week_num = weeks.index(week) + 1
    tasks = await get_tasks_by_week(week_id)

    if not tasks:
        await call.answer("В этой неделе пока нет заданий.", show_alert=True)
        return

    kb = _tasks_keyboard(tasks, week_id)
    await call.message.edit_text(
        ALL_WEEK_HEADER_TEXT.format(num=week_num, title=week["title"]),
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("arc_task:"))
async def cb_task(call: CallbackQuery):
    await call.answer()
    task_id = int(call.data.split(":")[1])
    found_task = await get_task_by_id(task_id)

    if not found_task:
        await call.answer(ALL_TASK_NOT_FOUND_TEXT, show_alert=True)
        return

    try:
        if found_task["is_album"]:
            await call.message.bot.copy_messages(
                chat_id=call.from_user.id,
                from_chat_id=found_task["chat_id"],
                message_ids=found_task["message_ids"],
            )
        else:
            await call.message.bot.copy_message(
                chat_id=call.from_user.id,
                from_chat_id=found_task["chat_id"],
                message_id=found_task["message_ids"][0],
            )
    except Exception as e:
        logger.warning("Не удалось выслать задание %s: %s", task_id, e)
        await call.message.answer(ALL_TASK_NOT_FOUND_TEXT)



@router.callback_query(F.data == "arc_noop")
async def cb_noop(call: CallbackQuery):
    """Некликабельная кнопка счётчика страниц."""
    await call.answer()
