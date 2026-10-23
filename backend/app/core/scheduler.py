"""Time-based checks. Called every minute by the local loop, or every few minutes
by EventBridge Scheduler → Lambda in AWS."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from ..store.base import Store
from ..timeutil import at_local, today
from .checkins import send_day_summary
from .digest import run_digest
from .noshow import run_noshow
from .sessionizer import is_work_day

log = logging.getLogger("crewlog.scheduler")


def tick(store: Store, now: datetime | None = None) -> dict:
    now = now or datetime.now(tz=timezone.utc)
    done = {"noshow": [], "digest": [], "summary": []}
    for job in store.list_jobs():
        day = today(job.tz, now)
        try:
            if is_work_day(job, day):
                deadline = at_local(day, job.expected_start, job.tz) + timedelta(minutes=job.grace_min)
                if now >= deadline and run_noshow(store, job, day, now):
                    done["noshow"].append(job.id)
            if now >= at_local(day, job.digest_time, job.tz):
                if not store.get_digest(job.id, day) and run_digest(store, job, day):
                    done["digest"].append(job.id)
                if send_day_summary(store, job, day, now):  # after the digest, so it can quote it
                    done["summary"].append(job.id)
        except Exception:  # noqa: BLE001 — one bad job must not stop the others
            log.exception("scheduler tick failed for job %s", job.id)
    return done
