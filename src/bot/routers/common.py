import asyncio
import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from db.users import add_user_from_message, is_user_banned
from db.tasks import get_last_task
from bot import texts
from config import TASKS_CHANNEL_ID
from bot.texts import BANNED_REPLY_TEXT

logger = logging.getLogger(__name__)

router = Router(name="common")

# Буфер для медиагрупп: media_group_id -> список сообщений
_media_buffer: dict[str, list[Message]] = {}
# Флаг запущенного таймера для группы
_media_timers: set[str] = set()

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Архив")]],
    resize_keyboard=True,
    input_field_placeholder="Сделай это...",
)

@router.message(Command("start"))
async def cmd_start(message: Message):
    await add_user_from_message(message)
    await message.answer(texts.WELCOME_TEXT, reply_markup=MAIN_KEYBOARD)

    last_task = await get_last_task()
    if last_task:
        task_chat_id, task_msg_ids = last_task
        try:
            if len(task_msg_ids) == 1:
                result = await message.bot.copy_message(
                    chat_id=message.chat.id,
                    from_chat_id=task_chat_id,
                    message_id=task_msg_ids[0],
                )
                pin_msg_id = result.message_id
            else:
                results = await message.bot.copy_messages(
                    chat_id=message.chat.id,
                    from_chat_id=task_chat_id,
                    message_ids=task_msg_ids,
                )
                pin_msg_id = results[0].message_id

            await message.bot.pin_chat_message(
                chat_id=message.chat.id,
                message_id=pin_msg_id,
                disable_notification=True,
            )
        except Exception as e:
            logger.warning("Не удалось отправить/закрепить задание при /start: %s", e)



@router.message(Command("help"))
async def cmd_help(message: Message):
    await add_user_from_message(message)
    await message.answer(texts.HELP_TEXT)


@router.message(
    ~F.text.startswith("/"),
    F.text != texts.ARCHIVE_BUTTON_TEXT,
    F.content_type == "text",
)
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

    await _forward_and_tag(message, task_title)


@router.message(F.media_group_id, ~F.text.startswith("/"))
async def handle_media_group(message: Message):
    if not message.reply_to_message:
        if not message.media_group_id:
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

    # Проверка бана — здесь, до буфера
    if await is_user_banned(message.from_user.id):
        await message.answer(BANNED_REPLY_TEXT)
        return

    group_id = message.media_group_id

    if group_id not in _media_buffer:
        _media_buffer[group_id] = []
    _media_buffer[group_id].append(message)

    if group_id in _media_timers:
        return
    _media_timers.add(group_id)

    await asyncio.sleep(0.7)

    messages = _media_buffer.pop(group_id, [])
    _media_timers.discard(group_id)

    if not messages:
        return

    messages.sort(key=lambda m: m.message_id)
    message_ids = [m.message_id for m in messages]

    await message.bot.send_chat_action(message.chat.id, "typing")

    try:
        await message.bot.copy_messages(
            chat_id=TASKS_CHANNEL_ID,
            from_chat_id=message.chat.id,
            message_ids=message_ids,
        )
    except Exception as e:
        logger.exception("Не удалось переслать альбом в канал: %s", e)
        await messages[0].answer(texts.FORWARD_ERROR_TEXT)
        return

    author_tag = _get_author_tag(message)
    await message.bot.send_message(
        chat_id=TASKS_CHANNEL_ID,
        text=f"{task_title}\n\n{author_tag}",
    )

    await messages[0].answer(texts.TASK_ACCEPTED_TEXT)



@router.message(~F.media_group_id, ~F.text.startswith("/"), F.content_type.in_({"photo", "video", "document", "audio", "voice", "video_note"}))
async def handle_single_media(message: Message):
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

    await _forward_and_tag(message, task_title)


async def _forward_and_tag(message: Message, task_title: str):
    if await is_user_banned(message.from_user.id):
        await message.answer(BANNED_REPLY_TEXT)
        return
    await message.bot.send_chat_action(message.chat.id, "typing")
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

    author_tag = _get_author_tag(message)
    await message.bot.send_message(
        chat_id=TASKS_CHANNEL_ID,
        text=f"{task_title}\n\n{author_tag}",
        parse_mode="HTML",
    )
    await message.answer(texts.TASK_ACCEPTED_TEXT)


def _get_author_tag(message: Message) -> str:
    user = message.from_user
    if user.username:
        return f"@{user.username} (id: <code>{user.id}</code>)"
    full_name = " ".join(
        filter(None, [user.first_name, user.last_name])
    ) or "безымени"
    return f"{full_name} (id: <code>{user.id}</code>)"




def extract_task_title(text: str) -> str | None:
    if not text:
        return None
    parts = text.split(".", 1)
    title = parts[0].strip()
    return title or None
