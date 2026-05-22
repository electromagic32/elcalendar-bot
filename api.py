import hashlib
import hmac
import json
from datetime import datetime
from urllib.parse import parse_qsl, unquote
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import delete, select

from config import settings
from db import Event, Reminder, Session, create_event, get_upcoming_events, update_event

app = FastAPI()

UTC = ZoneInfo("UTC")
TZ = ZoneInfo(settings.TIMEZONE)


def validate_init_data(init_data: str) -> dict | None:
    try:
        parsed = dict(parse_qsl(unquote(init_data), keep_blank_values=True))
        check_hash = parsed.pop("hash", "")
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", settings.BOT_TOKEN.encode(), hashlib.sha256).digest()
        computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(computed, check_hash):
            return None
        if "user" in parsed:
            parsed["user"] = json.loads(parsed["user"])
        if "chat" in parsed:
            parsed["chat"] = json.loads(parsed["chat"])
        return parsed
    except Exception:
        return None


def require_auth(x_init_data: str) -> dict:
    data = validate_init_data(x_init_data)
    if not data:
        raise HTTPException(status_code=401, detail="Invalid initData")
    return data


async def require_member(request: Request, user_id: int):
    if not settings.HOME_GROUP_ID:
        return
    try:
        bot = request.app.state.bot
        member = await bot.get_chat_member(settings.HOME_GROUP_ID, user_id)
        if member.status not in ("member", "administrator", "creator"):
            raise HTTPException(status_code=403, detail="Not a group member")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=403, detail="Could not verify membership")


@app.get("/api/events")
async def list_events(request: Request, chat_id: int, past: bool = False, x_init_data: str = Header(...)):
    data = require_auth(x_init_data)
    await require_member(request, data["user"]["id"])
    rows = await get_upcoming_events(chat_id, past=past)
    return [
        {
            "id": event.id,
            "title": event.title,
            "event_time": event.event_time.isoformat(),
            "location": event.location,
            "reminders": [
                {
                    "remind_before": r.remind_before,
                    "repeat_count": r.repeat_count,
                    "repeat_interval": r.repeat_interval,
                }
                for r in reminders
            ],
        }
        for event, reminders in rows
    ]


class ReminderIn(BaseModel):
    remind_before: int
    repeat_count: int = 1
    repeat_interval: int = 0


class CreateEventRequest(BaseModel):
    chat_id: int
    created_by: int
    title: str
    event_time: str  # UTC ISO: YYYY-MM-DDTHH:MM
    location: str | None = None
    reminders: list[ReminderIn]


@app.post("/api/events")
async def api_create_event(request: Request, req: CreateEventRequest, x_init_data: str = Header(...)):
    data = require_auth(x_init_data)
    await require_member(request, data["user"]["id"])
    dt = datetime.fromisoformat(req.event_time)
    event = await create_event(
        chat_id=req.chat_id,
        created_by=req.created_by,
        title=req.title,
        event_time=dt,
        location=req.location,
        reminders=[r.model_dump() for r in req.reminders],
    )
    return {"id": event.id, "title": event.title}


class UpdateEventRequest(BaseModel):
    title: str
    event_time: str
    location: str | None = None
    reminders: list[ReminderIn]


@app.put("/api/events/{event_id}")
async def api_update_event(request: Request, event_id: int, req: UpdateEventRequest, x_init_data: str = Header(...)):
    data = require_auth(x_init_data)
    await require_member(request, data["user"]["id"])
    dt = datetime.fromisoformat(req.event_time)
    event = await update_event(
        event_id=event_id,
        title=req.title,
        event_time=dt,
        location=req.location,
        reminders=[r.model_dump() for r in req.reminders],
    )
    return {"id": event.id, "title": event.title}


@app.delete("/api/events/{event_id}")
async def api_delete_event(request: Request, event_id: int, x_init_data: str = Header(...)):
    data = require_auth(x_init_data)
    await require_member(request, data["user"]["id"])
    async with Session() as s:
        await s.execute(delete(Event).where(Event.id == event_id))
        await s.commit()
    return {"ok": True}


# Static files — mounted last so API routes take priority
app.mount("/", StaticFiles(directory="webapp", html=True), name="webapp")
