"""Daily AI progress digest: two snapshots + session facts → Bedrock → stored Digest."""

from __future__ import annotations

from ..ai import bedrock
from ..models import Digest, Job
from ..store.base import Store
from ..timeutil import fmt_clock
from . import progress, snapshots
from .days import get_day, worked_days_before


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def facts_for(job: Job, summary) -> str:
    hrs = summary.total_min / 60
    vehicles = sum(s.vehicle_count for s in summary.sessions)
    return (
        f"crew on site {fmt_clock(summary.first_arrival_ms, job.tz)}–{fmt_clock(summary.last_departure_ms, job.tz)}, "
        f"{hrs:.1f} hours across {_count(len(summary.sessions), 'visit')}, {_count(vehicles, 'vehicle sighting')}"
    )


def run_digest(store: Store, job: Job, day: str, force: bool = False, demo_stall: bool = False) -> Digest | None:
    existing = store.get_digest(job.id, day)
    if existing and not force:
        return existing
    summary = get_day(store, job, day)
    if summary.status != "worked":
        return None
    am, pm, am_url, pm_url = snapshots.capture(job, summary, worked_days_before(store, job, day), stall=demo_stall)
    facts = facts_for(job, summary)
    result, model = bedrock.describe_progress(am, pm, facts)
    digest = Digest(
        job_id=job.id,
        date=day,
        summary=result["summary"] or facts,
        changes=result["changes"],
        concerns=result["concerns"],
        progress=result.get("progress", "unknown"),
        model=model,
        am_snapshot=am_url,
        pm_snapshot=pm_url,
    )
    store.put_digest(digest)
    progress.run_progress_check(store, job, day)
    return digest
