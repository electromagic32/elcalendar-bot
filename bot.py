import asyncio
import logging

from aiogram import Bot, Dispatcher, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, Message, WebAppInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import uvicorn
from api import app as api_app

from config import settings
from db import cleanup_old_events, get_due_reminders, increment_send_count, init_db
from datetime import datetime

from utils import fmt_dt

logging.basicConfig(level=logging.INFO)
router = Router()


async def is_member(bot: Bot, user_id: int) -> bool:
    if not settings.HOME_GROUP_IDS:
        return True
    for group_id in settings.HOME_GROUP_IDS:
        try:
            member = await bot.get_chat_member(group_id, user_id)
            if member.status in ("member", "administrator", "creator"):
                return True
        except Exception:
            continue
    return False


def webapp_button(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="📅 Открыть календарь",
            web_app=WebAppInfo(url=f"{settings.WEBAPP_URL}?cid={chat_id}"),
        )
    ]])


@router.message(Command("start"))
async def cmd_start(message: Message, bot: Bot):
    args = message.text.split(maxsplit=1)
    if not await is_member(bot, message.from_user.id):
        return
    if len(args) > 1 and args[1].startswith("c"):
        group_id = -int(args[1][1:])
        await message.reply(
            "Нажми чтобы открыть календарь группы:",
            reply_markup=webapp_button(group_id),
        )
        return
    await message.reply(
        "👋 Привет! Я бот-календарь.\n\n"
        "/cal — открыть календарь",
        reply_markup=webapp_button(message.chat.id),
    )



@router.message(Command("cal"))
async def cmd_cal(message: Message, bot: Bot):
    if not await is_member(bot, message.from_user.id):
        return
    if message.chat.type in ("group", "supergroup"):
        group_id = abs(message.chat.id)
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="📅 Открыть календарь",
                url=f"https://t.me/{settings.BOT_USERNAME}?start=c{group_id}",
            )
        ]])
        reply = await message.reply("👆", reply_markup=kb)
        await asyncio.sleep(7)
        for msg_id in (message.message_id, reply.message_id):
            try:
                await bot.delete_message(message.chat.id, msg_id)
            except TelegramBadRequest:
                pass
    else:
        await message.reply(
            "Нажми чтобы открыть:",
            reply_markup=webapp_button(message.chat.id),
        )



async def send_reminders(bot: Bot):
    pairs = await get_due_reminders()
    for reminder, event in pairs:
        loc_text = f"\n📍 {event.location}" if event.location else ""
        total = reminder.repeat_count
        current = reminder.send_count + 1
        count_text = f" ({current}/{total})" if total > 1 else ""
        now = datetime.utcnow()
        mins_left = max(0, int((event.event_time - now).total_seconds() / 60))
        if mins_left >= 60:
            time_left = f"{mins_left // 60} ч" + (f" {mins_left % 60} мин" if mins_left % 60 else "")
        else:
            time_left = f"{mins_left} мин"
        try:
            await bot.send_message(
                event.chat_id,
                f"⏰ <b>Напоминание{count_text}!</b>\n\n"
                f"📌 <b>{event.title}</b>\n"
                f"🕐 {fmt_dt(event.event_time)}"
                f"{loc_text}\n"
                f"<i>Через {time_left}</i>",
                parse_mode="HTML",
            )
        except Exception as e:
            logging.error(f"Failed to send reminder {reminder.id}: {e}")
        await increment_send_count(reminder.id)


async def main():
    await init_db()

    from aiogram.types import BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats

    bot = Bot(token=settings.BOT_TOKEN)
    await bot.delete_my_commands(scope=BotCommandScopeAllPrivateChats())
    await bot.delete_my_commands(scope=BotCommandScopeAllGroupChats())
    await bot.set_my_commands(
        [BotCommand(command="cal", description="Открыть календарь")],
        scope=BotCommandScopeAllPrivateChats(),
    )
    await bot.set_my_commands(
        [BotCommand(command="cal", description="Открыть календарь")],
        scope=BotCommandScopeAllGroupChats(),
    )
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="📅 Календарь",
            web_app=WebAppInfo(url=settings.WEBAPP_URL),
        )
    )

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_reminders, "interval", seconds=30, args=[bot])
    if settings.EVENT_TTL_MINUTES > 0:
        scheduler.add_job(cleanup_old_events, "interval", minutes=5, args=[settings.EVENT_TTL_MINUTES])
    scheduler.start()

    logging.info("Bot started")

    api_app.state.bot = bot
    api_config = uvicorn.Config(api_app, host="0.0.0.0", port=8080, log_level="warning")
    api_server = uvicorn.Server(api_config)

    await asyncio.gather(
        dp.start_polling(bot, allowed_updates=["message"]),
        api_server.serve(),
    )


if __name__ == "__main__":
    asyncio.run(main())
