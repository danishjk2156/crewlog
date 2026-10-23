"""Read-side helpers: compute day summaries from stored events (never cached)."""

from __future__ import annotations

from datetime import datetime

from ..models import DaySummary, Job
from ..store.base import Store
from ..timeutil import day_bounds_ms, shift_day
from .sessionizer import build_day


def get_day(store: Store, job: Job, day: str, now: datetime | None = None) -> DaySummary:
    start, end = day_bounds_ms(day, job.tz)
    return build_day(job, day, store.events_between(job.id, start, end), now)


def get_events(store: Store, job: Job, day: str):
    start, end = day_bounds_ms(day, job.tz)
    return store.events_between(job.id, start, end)


def worked_days_before(store: Store, job: Job, day: str, max_lookback: int = 60) -> int:
    """Worked days with progress between the job start and ``day`` (exclusive).

    Picks the demo stage image, so a day with no visible change does not advance it.
    """
    first = job.start_date or shift_day(day, -14)
    count, cur, steps = 0, first, 0
    while cur < day and steps < max_lookback:
        digest = store.get_digest(job.id, cur)
        if get_day(store, job, cur).status == "worked" and not (digest and digest.progress == "none"):
            count += 1
        cur, steps = shift_day(cur, 1), steps + 1
    return count
