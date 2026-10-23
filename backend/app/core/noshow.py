"""No-show detection: a scheduled work day passes start + grace with no crew."""

from __future__ import annotations

from datetime import datetime

from ..ai import bedrock
from ..models import Alert, Job
from ..notify import notifier
from ..store.base import Store
from ..timeutil import at_local
from .days import get_day


def run_noshow(store: Store, job: Job, day: str, now: datetime | None = None) -> Alert | None:
    if store.has_alert(job.id, day, "no_show"):
        return None
    summary = get_day(store, job, day, now)
    if summary.status != "no_show":
        return None
    expected = at_local(day, job.expected_start, job.tz).strftime("%I:%M %p").lstrip("0")
    message = (
        f"No crew activity at {job.name} yet today. Expected by {expected} "
        f"(+{job.grace_min} min grace) and the Ring camera has seen no one."
    )
    drafted, _ = bedrock.draft_contractor_message(job.contractor_name, job.name, expected)
    channels = notifier.send(f"CrewLog: no-show at {job.name}", f"{message}\n\nSuggested message to {job.contractor_name}:\n{drafted}")
    alert = Alert(job_id=job.id, date=day, message=message, drafted_reply=drafted, channels=channels)
    store.put_alert(alert)
    return alert
