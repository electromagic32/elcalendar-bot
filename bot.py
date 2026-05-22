import asyncio
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, Message, WebAppInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import uvicorn
from api import app as api_app

from config import settings
from db import create_event, get_due_reminders, get_upcoming_events, increment_send_count, init_db
from datetime import datetime

from utils import fmt_dt, parse_datetime, parse_remind_before

logging.basicConfig(level=logging.INFO)
router = Router()


class NewEvent(StatesGroup):
    title = State()
    event_time = State()
    location = State()
    remind_before = State()


WEBAPP_URL = "https://elmagique.duckdns.org:7443/cal/"


def webapp_button(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="📅 Открыть календарь",
            web_app=WebAppInfo(url=f"{WEBAPP_URL}?cid={chat_id}"),
        )
    ]])


@router.message(Command("start"))
async def cmd_start(message: Message):
    args = message.text.split(maxsplit=1)
    # Deep link from group: /start c<abs_group_id>
    if len(args) > 1 and args[1].startswith("c"):
        group_id = -int(args[1][1:])
        await message.reply(
            "Нажми чтобы открыть календарь группы:",
            reply_markup=webapp_button(group_id),
        )
        return
    await message.reply(
        "👋 Привет! Я бот-календарь.\n\n"
        "/cal — открыть календарь\n"
        "/newevent — создать событие текстом\n"
        "/events — список событий\n"
        "/cancel — отменить действие",
        reply_markup=webapp_button(message.chat.id),
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.reply(
        "📋 Команды:\n\n"
        "/cal — открыть календарь\n"
        "/newevent — создать событие текстом\n"
        "/events — список событий\n"
        "/cancel — отменить действие"
    )


@router.message(Command("cal"))
async def cmd_cal(message: Message):
    if message.chat.type in ("group", "supergroup"):
        # In groups, web_app buttons are not allowed — redirect to private chat
        group_id = abs(message.chat.id)
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="📅 Открыть в личке с ботом",
                url=f"https://t.me/Elcalendar_bot?start=c{group_id}",
            )
        ]])
        await message.reply(
            "Telegram не разрешает открывать мини-приложения прямо из групп.\n"
            "Нажми кнопку — перейдёшь в личку, там откроется календарь этой группы:",
            reply_markup=kb,
        )
    else:
        await message.reply(
            "Нажми чтобы открыть:",
            reply_markup=webapp_button(message.chat.id),
        )


@router.message(Command("cancel"), StateFilter("*"))
async def cmd_cancel(message: Message, state: FSMContext):
    if await state.get_state() is None:
        await message.reply("Нет активного действия.")
        return
    await state.clear()
    await message.reply("❌ Отменено.")


@router.message(Command("newevent"))
async def cmd_newevent(message: Message, state: FSMContext):
    await state.set_state(NewEvent.title)
    await message.reply("📌 Название события?", reply_markup=ForceReply(selective=True))


@router.message(NewEvent.title, F.reply_to_message)
async def got_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(NewEvent.event_time)
    await message.reply("🕐 Дата и время?\n(напр. <code>25.05 14:00</code> или <code>завтра 15:30</code>)", parse_mode="HTML", reply_markup=ForceReply(selective=True))


@router.message(NewEvent.event_time, F.reply_to_message)
async def got_time(message: Message, state: FSMContext):
    dt = parse_datetime(message.text)
    if not dt:
        await message.reply("❌ Не понял дату. Попробуй: <code>25.05 14:00</code> или <code>завтра 15:30</code>", parse_mode="HTML", reply_markup=ForceReply(selective=True))
        return
    await state.update_data(event_time=dt)
    await state.set_state(NewEvent.location)
    await message.reply("📍 Место? (или <code>—</code> чтобы пропустить)", parse_mode="HTML", reply_markup=ForceReply(selective=True))


@router.message(NewEvent.location, F.reply_to_message)
async def got_location(message: Message, state: FSMContext):
    skip = message.text.strip() in ("-", "—", "нет", "no", "skip")
    await state.update_data(location=None if skip else message.text.strip())
    await state.set_state(NewEvent.remind_before)
    await message.reply("⏰ За сколько напомнить?\n(напр. <code>30 мин</code>, <code>1 час</code>, <code>2 часа</code>)", parse_mode="HTML", reply_markup=ForceReply(selective=True))


@router.message(NewEvent.remind_before, F.reply_to_message)
async def got_remind_before(message: Message, state: FSMContext):
    minutes = parse_remind_before(message.text)
    if not minutes:
        await message.reply("❌ Не понял. Напр: <code>30 мин</code>, <code>1 час</code>", parse_mode="HTML")
        return

    data = await state.get_data()
    await state.clear()

    event = await create_event(
        chat_id=message.chat.id,
        created_by=message.from_user.id,
        title=data["title"],
        event_time=data["event_time"],
        location=data.get("location"),
        reminders=[{"remind_before": minutes, "repeat_count": 1, "repeat_interval": 0}],
    )

    loc_text = f"\n📍 {event.location}" if event.location else ""
    remind_text = f"{minutes} мин" if minutes < 60 else f"{minutes // 60} ч"
    await message.reply(
        f"✅ Сохранено!\n\n"
        f"📌 <b>{event.title}</b>\n"
        f"🕐 {fmt_dt(event.event_time)}"
        f"{loc_text}\n"
        f"⏰ Напомню за {remind_text}",
        parse_mode="HTML",
    )


@router.message(Command("events"))
async def cmd_events(message: Message):
    events = await get_upcoming_events(message.chat.id)
    if not events:
        await message.reply("📭 Нет предстоящих событий.")
        return

    lines = ["📅 <b>Предстоящие события:</b>\n"]
    for e in events:
        loc = f" — {e.location}" if e.location else ""
        lines.append(f"• <b>{e.title}</b> — {fmt_dt(e.event_time)}{loc}")

    await message.reply("\n".join(lines), parse_mode="HTML")


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

    bot = Bot(token=settings.BOT_TOKEN)
    await bot.set_my_commands([
        BotCommand(command="cal", description="Открыть календарь"),
        BotCommand(command="newevent", description="Создать событие"),
        BotCommand(command="events", description="Список событий"),
        BotCommand(command="cancel", description="Отменить действие"),
    ])
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="📅 Календарь",
            web_app=WebAppInfo(url=f"https://elmagique.duckdns.org:7443/cal/"),
        )
    )

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_reminders, "interval", seconds=30, args=[bot])
    scheduler.start()

    logging.info("Bot started")

    api_config = uvicorn.Config(api_app, host="0.0.0.0", port=8080, log_level="warning")
    api_server = uvicorn.Server(api_config)

    await asyncio.gather(
        dp.start_polling(bot, allowed_updates=["message"]),
        api_server.serve(),
    )


if __name__ == "__main__":
    asyncio.run(main())
