import re
import zoneinfo
from datetime import datetime, timedelta

import dateparser

from config import settings

TZ = zoneinfo.ZoneInfo(settings.TIMEZONE)
UTC = zoneinfo.ZoneInfo("UTC")


def parse_datetime(text: str) -> datetime | None:
    text = text.strip()
    now = datetime.now(tz=TZ)

    # завтра / послезавтра
    lower = text.lower()
    base_day = None
    time_part = text
    if lower.startswith("завтра"):
        base_day = now.date() + timedelta(days=1)
        time_part = text[6:].strip()
    elif lower.startswith("послезавтра"):
        base_day = now.date() + timedelta(days=2)
        time_part = text[11:].strip()

    if base_day:
        m = re.match(r"(\d{1,2}):(\d{2})", time_part)
        if m:
            hour, minute = int(m[1]), int(m[2])
            dt = datetime(base_day.year, base_day.month, base_day.day, hour, minute, tzinfo=TZ)
            return dt.astimezone(UTC).replace(tzinfo=None)
        return None

    # DD.MM HH:MM  или  DD.MM.YYYY HH:MM
    m = re.match(r"(\d{1,2})\.(\d{2})(?:\.(\d{2,4}))?\s+(\d{1,2}):(\d{2})$", text)
    if m:
        day, month = int(m[1]), int(m[2])
        year_raw = m[3]
        hour, minute = int(m[4]), int(m[5])
        if year_raw is None:
            year = now.year
        elif len(year_raw) == 2:
            year = 2000 + int(year_raw)
        else:
            year = int(year_raw)
        try:
            dt = datetime(year, month, day, hour, minute, tzinfo=TZ)
            if year_raw is None and dt < now:
                dt = dt.replace(year=year + 1)
            return dt.astimezone(UTC).replace(tzinfo=None)
        except ValueError:
            pass

    # fallback: dateparser
    parsed = dateparser.parse(
        text,
        languages=["ru", "en"],
        settings={
            "PREFER_DATES_FROM": "future",
            "RETURN_AS_TIMEZONE_AWARE": False,
            "TIMEZONE": settings.TIMEZONE,
            "TO_TIMEZONE": "UTC",
        },
    )
    return parsed


def parse_remind_before(text: str) -> int | None:
    text = text.lower().strip()
    patterns = [
        (r"(\d+)\s*(?:мин|минут|минуту|минуты)", 1),
        (r"(\d+)\s*(?:ч\b|час|часа|часов)", 60),
        (r"(\d+)\s*(?:д\b|день|дня|дней)", 1440),
        (r"(\d+)\s*(?:min|minutes?)", 1),
        (r"(\d+)\s*(?:h\b|hour|hours?)", 60),
    ]
    for pattern, multiplier in patterns:
        m = re.search(pattern, text)
        if m:
            return int(m.group(1)) * multiplier
    # просто число — считаем минутами
    m = re.match(r"^(\d+)$", text)
    if m:
        return int(m.group(1))
    return None


def fmt_dt(dt: datetime) -> str:
    local = dt.replace(tzinfo=UTC).astimezone(TZ)
    return local.strftime("%d.%m.%Y %H:%M")
