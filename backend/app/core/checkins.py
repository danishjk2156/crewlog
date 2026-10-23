"""Owner notifications for the crew's day: arrival, doorbell check-out, end-of-day summary.

Arrival is sent the first time a visit counts as crew. Departure can't be seen live
(a quiet camera may just mean the crew is inside), so check-out needs a doorbell press
on the way out; the end-of-day summary covers crews that forget.
Each notification is sent at most once per job and day.
"""

from __future__ import annotations

from datetime import datetime

from ..models import Alert, Job, RingEvent
from ..notify import notifier
from ..store.base import Store
from ..timeutil import fmt_clock, local_date, today
from .days import get_day

CHECKOUT_MIN_AFTER_ARRIVAL = 60  # an earlier press is the check-in itself, not a check-out

HOW_IT_KNEW = {
    "Checked in at the doorbell": "checked in at the doorbell",
    "Work vehicle arrived during work hours": "work van seen",
    "Long stay during work hours": "on site for over an hour",
}


def _hours(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def _send(store: Store, job: Job, day: str, kind: str, subject: str, message: str) -> Alert:
    channels = notifier.send(f"CrewLog: {subject}", message)
    alert = Alert(job_id=job.id, date=day, kind=kind, message=message, channels=channels)
    store.put_alert(alert)
    return alert


def on_event(store: Store, job: Job, evt: RingEvent, now: datetime | None = None) -> Alert | None:
    """Called after each stored Ring event. Only today's events notify, so seeded or
    backfilled history stays silent."""
    day = local_date(evt.ts_ms, job.tz)
    if day != today(job.tz, now):
        return None
    summary = get_day(store, job, day, now)
    if not summary.sessions:
        return None  # only household or visitors so far
    if not store.has_alert(job.id, day, "check_in"):
        first = summary.sessions[0]
        how = HOW_IT_KNEW.get(first.reason, first.reason.lower())
        return _send(
            store, job, day, "check_in", f"crew arrived at {job.name}",
            f"Crew arrived at {fmt_clock(first.start_ms, job.tz)} ({how}).",
        )
    is_checkout_press = (
        evt.type == "button_press"
        and evt.ts_ms >= summary.first_arrival_ms + CHECKOUT_MIN_AFTER_ARRIVAL * 60_000
    )
    if is_checkout_press and not store.has_alert(job.id, day, "check_out"):
        return _send(
            store, job, day, "check_out", f"crew left {job.name}",
            f"Crew checked out at {fmt_clock(evt.ts_ms, job.tz)}. {_hours(summary.total_min)} on site today.",
        )
    return None


def send_day_summary(store: Store, job: Job, day: str, now: datetime | None = None) -> Alert | None:
    """End-of-day recap for days the crew worked (no-show days already got their alert)."""
    if store.has_alert(job.id, day, "day_summary"):
        return None
    summary = get_day(store, job, day, now)
    if summary.status != "worked":
        return None
    message = (
        f"Today at {job.name}: crew on site {fmt_clock(summary.first_arrival_ms, job.tz)} to "
        f"{fmt_clock(summary.last_departure_ms, job.tz)}, {_hours(summary.total_min)} in total."
    )
    digest = store.get_digest(job.id, day)
    if digest and (digest.model != "offline" or digest.progress == "none"):  # skip the bare offline placeholder
        message += f" Progress note: {digest.summary}"
    return _send(store, job, day, "day_summary", f"today's summary for {job.name}", message)
