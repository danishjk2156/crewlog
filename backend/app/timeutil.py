"""Timezone helpers. Events are bucketed by the job's *local* date, never UTC."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def tz(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def ms_to_local(ts_ms: int, tz_name: str) -> datetime:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).astimezone(tz(tz_name))


def local_date(ts_ms: int, tz_name: str) -> str:
    return ms_to_local(ts_ms, tz_name).date().isoformat()


def day_bounds_ms(day: str, tz_name: str) -> tuple[int, int]:
    """[start, end) of a local calendar day in epoch ms."""
    d = date.fromisoformat(day)
    start = datetime.combine(d, time.min, tzinfo=tz(tz_name))
    end = start + timedelta(days=1)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def at_local(day: str, hhmm: str, tz_name: str) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime.combine(date.fromisoformat(day), time(h, m), tzinfo=tz(tz_name))


def today(tz_name: str, now: datetime | None = None) -> str:
    now = now or datetime.now(tz=timezone.utc)
    return now.astimezone(tz(tz_name)).date().isoformat()


def fmt_clock(ts_ms: int | None, tz_name: str) -> str:
    if ts_ms is None:
        return "—"
    return ms_to_local(ts_ms, tz_name).strftime("%I:%M %p").lstrip("0")


def shift_day(day: str, n: int) -> str:
    return (date.fromisoformat(day) + timedelta(days=n)).isoformat()
