from datetime import datetime, timedelta

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from config import settings

engine = create_async_engine(settings.DATABASE_URL)
Session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    created_by: Mapped[int] = mapped_column(BigInteger)
    title: Mapped[str] = mapped_column(String(255))
    event_time: Mapped[datetime] = mapped_column(DateTime)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_by_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    remind_before: Mapped[int] = mapped_column(Integer, default=0)   # legacy
    reminded: Mapped[bool] = mapped_column(Boolean, default=False)    # legacy
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(Integer, ForeignKey("events.id", ondelete="CASCADE"))
    remind_before: Mapped[int] = mapped_column(Integer)   # minutes before event
    repeat_count: Mapped[int] = mapped_column(Integer, default=1)
    repeat_interval: Mapped[int] = mapped_column(Integer, default=0)  # minutes between repeats
    send_count: Mapped[int] = mapped_column(Integer, default=0)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE events ADD COLUMN IF NOT EXISTS description TEXT"))
        await conn.execute(text("ALTER TABLE events ADD COLUMN IF NOT EXISTS created_by_name VARCHAR(128)"))
        await conn.execute(text("ALTER TABLE events ADD COLUMN IF NOT EXISTS updated_by_name VARCHAR(128)"))


async def create_event(
    chat_id: int,
    created_by: int,
    created_by_name: str | None,
    title: str,
    event_time: datetime,
    location: str | None,
    description: str | None,
    reminders: list[dict],
) -> Event:
    async with Session() as s:
        event = Event(
            chat_id=chat_id,
            created_by=created_by,
            created_by_name=created_by_name,
            title=title,
            event_time=event_time,
            location=location,
            description=description,
            remind_before=0,
            reminded=False,
        )
        s.add(event)
        await s.flush()
        for r in reminders:
            s.add(Reminder(
                event_id=event.id,
                remind_before=r["remind_before"],
                repeat_count=r.get("repeat_count", 1),
                repeat_interval=r.get("repeat_interval", 0),
            ))
        await s.commit()
        await s.refresh(event)
        return event


async def update_event(
    event_id: int,
    title: str,
    event_time: datetime,
    location: str | None,
    description: str | None,
    updated_by_name: str | None,
    reminders: list[dict],
) -> Event:
    async with Session() as s:
        result = await s.execute(select(Event).where(Event.id == event_id))
        event = result.scalar_one()
        event.title = title
        event.event_time = event_time
        event.location = location
        event.description = description
        event.updated_by_name = updated_by_name
        await s.execute(delete(Reminder).where(Reminder.event_id == event_id))
        for r in reminders:
            s.add(Reminder(
                event_id=event.id,
                remind_before=r["remind_before"],
                repeat_count=r.get("repeat_count", 1),
                repeat_interval=r.get("repeat_interval", 0),
            ))
        await s.commit()
        await s.refresh(event)
        return event


async def get_upcoming_events(chat_id: int, past: bool = False) -> list[tuple[Event, list[Reminder]]]:
    async with Session() as s:
        now = datetime.utcnow()
        if past:
            query = (
                select(Event)
                .where(Event.chat_id == chat_id, Event.event_time <= now)
                .order_by(Event.event_time.desc())
                .limit(30)
            )
        else:
            query = (
                select(Event)
                .where(Event.chat_id == chat_id, Event.event_time > now)
                .order_by(Event.event_time)
                .limit(10)
            )
        result = await s.execute(query)
        events = result.scalars().all()
        out = []
        for event in events:
            rems = await s.execute(select(Reminder).where(Reminder.event_id == event.id))
            out.append((event, list(rems.scalars().all())))
        return out


async def get_due_reminders() -> list[tuple[Reminder, Event]]:
    async with Session() as s:
        now = datetime.utcnow()
        result = await s.execute(
            select(Reminder, Event)
            .join(Event, Reminder.event_id == Event.id)
            .where(
                Reminder.send_count < Reminder.repeat_count,
                Event.event_time > now - timedelta(hours=1),
            )
        )
        due = []
        for reminder, event in result.all():
            next_send = (
                event.event_time
                - timedelta(minutes=reminder.remind_before)
                + timedelta(minutes=reminder.send_count * reminder.repeat_interval)
            )
            if next_send <= now:
                due.append((reminder, event))
        return due


async def increment_send_count(reminder_id: int):
    async with Session() as s:
        result = await s.execute(select(Reminder).where(Reminder.id == reminder_id))
        reminder = result.scalar_one()
        reminder.send_count += 1
        await s.commit()
