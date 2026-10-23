"""Presence is not progress: flag work days where the crew was on site but the
camera stills show no visible change, and alert when that repeats.

One quiet day is normal (work behind walls, drying time, inspections), so a
single day is only flagged; the homeowner is alerted after STALL_DAYS in a row.
"""

from __future__ import annotations

from datetime import date

from ..ai import bedrock
from ..models import Alert, DaySummary, Digest, Job
from ..notify import notifier
from ..store.base import Store
from ..timeutil import shift_day
from .days import get_day

SHORT_VISIT_MIN = 120  # a worked day shorter than this is a "short visit"
STALL_DAYS = 2  # worked days in a row with no visible progress before alerting
LOOKBACK_DAYS = 14


def day_flag(summary: DaySummary, digest: Digest | None) -> str | None:
    """"short_visit", "no_progress" or None for a day."""
    if summary.status != "worked":
        return None
    if summary.total_min < SHORT_VISIT_MIN:
        return "short_visit"
    if digest and digest.progress == "none":
        return "no_progress"
    return None


def stall_run(flags: list[tuple[str, str, str | None]]) -> list[str]:
    """Trailing run of no-progress worked days, oldest first.

    ``flags`` is (date, status, flag) in date order. Days without work (off,
    no-show) neither extend nor break the run; a worked day with progress does.
    """
    run: list[str] = []
    for day, status, flag in reversed(flags):
        if status != "worked":
            continue
        if flag != "no_progress":
            break
        run.append(day)
    return run[::-1]


def stalled_days(store: Store, job: Job, day: str) -> list[str]:
    flags = []
    for i in range(LOOKBACK_DAYS - 1, -1, -1):
        cur = shift_day(day, -i)
        if job.start_date and cur < job.start_date:
            continue
        summary = get_day(store, job, cur)
        flags.append((cur, summary.status, day_flag(summary, store.get_digest(job.id, cur))))
    return stall_run(flags)


def _human_days(days: list[str]) -> str:
    names = [date.fromisoformat(d).strftime("%A") for d in days]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def run_progress_check(store: Store, job: Job, day: str) -> Alert | None:
    if store.has_alert(job.id, day, "low_progress"):
        return None
    days = stalled_days(store, job, day)
    if len(days) < STALL_DAYS or days[-1] != day:
        return None
    when = _human_days(days)
    message = (
        f"The crew was on site {len(days)} work days in a row ({when}), "
        "but the camera stills show no visible change in the work area."
    )
    drafted, _ = bedrock.draft_checkin_message(job.contractor_name, job.name, when)
    channels = notifier.send(
        f"CrewLog: no visible progress at {job.name}",
        f"{message}\n\nSuggested message to {job.contractor_name}:\n{drafted}",
    )
    alert = Alert(job_id=job.id, date=day, kind="low_progress", message=message, drafted_reply=drafted, channels=channels)
    store.put_alert(alert)
    return alert
