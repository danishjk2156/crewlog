"""Turn raw Ring motion events into visits, decide who each visit was, and summarise the day.

Ring only says "a person / a vehicle moved". CrewLog never identifies anyone: it reads
the *pattern* of a visit (check-in at the doorbell, the work van, a long stay inside
work hours) to tell the crew apart from the household and from visitors such as
neighbours. Only crew visits count as work; the homeowner can correct any visit.

Pure functions: same events in → same summary out. That makes the pipeline
idempotent (duplicate webhooks, re-runs) and trivially testable.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone

from ..models import DaySummary, Job, RingEvent, Session
from ..timeutil import at_local

ATTENDANCE_SUBTYPES = {"human", "vehicle"}
# A doorbell/entry camera sees the crew arrive, step out to the truck and leave —
# not continuous presence inside. So a session spans from first sighting until a
# quiet gap longer than this (covers lunch breaks and long indoor stretches).
GAP_MS = 4 * 60 * 60 * 1000
MIN_SESSION_MS = 5 * 60 * 1000  # shorter sessions are passers-by...
MIN_EVENTS_FOR_SHORT = 3  # ...unless they produced several events

# Who-was-it rules
WINDOW_BEFORE_MIN = 120  # work window opens this long before the expected start...
WINDOW_AFTER_MIN = 60  # ...and closes this long after the end of the work day (digest_time)
LONG_STAY_MIN = 60  # a stay this long during work hours looks like work
CHECKIN_SLACK_MS = 15 * 60 * 1000  # a doorbell press this close to a visit belongs to it


def build_sessions(events: Iterable[RingEvent]) -> list[Session]:
    att = sorted((e for e in events if e.sub_type in ATTENDANCE_SUBTYPES), key=lambda e: e.ts_ms)
    raw: list[dict] = []
    for e in att:
        if not raw or e.ts_ms - raw[-1]["end"] > GAP_MS:
            raw.append({"start": e.ts_ms, "end": e.ts_ms, "events": 0, "vehicles": 0})
        cur = raw[-1]
        cur["end"] = e.ts_ms
        cur["events"] += 1
        if e.sub_type == "vehicle":
            cur["vehicles"] += 1
    sessions = []
    for s in raw:
        span = s["end"] - s["start"]
        if span < MIN_SESSION_MS and s["events"] < MIN_EVENTS_FOR_SHORT:
            continue
        sessions.append(
            Session(
                start_ms=s["start"],
                end_ms=s["end"],
                duration_min=round(span / 60000),
                event_count=s["events"],
                vehicle_count=s["vehicles"],
            )
        )
    return sessions


def is_work_day(job: Job, day: str) -> bool:
    return date.fromisoformat(day).weekday() in job.work_days


def work_window(job: Job, day: str) -> tuple[int, int]:
    start = at_local(day, job.expected_start, job.tz) - timedelta(minutes=WINDOW_BEFORE_MIN)
    end = at_local(day, job.digest_time, job.tz) + timedelta(minutes=WINDOW_AFTER_MIN)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def classify(visit: Session, in_window: bool, presses: list[int]) -> tuple[str, str, bool]:
    """(role, reason, checked_in) for one visit, strongest signal first."""
    checked_in = any(visit.start_ms - CHECKIN_SLACK_MS <= p <= visit.end_ms + CHECKIN_SLACK_MS for p in presses)
    if in_window and checked_in:
        return "crew", "Checked in at the doorbell", True
    if in_window and visit.vehicle_count:
        return "crew", "Work vehicle arrived during work hours", False
    if in_window and visit.duration_min >= LONG_STAY_MIN:
        return "crew", "Long stay during work hours", False
    if not in_window and visit.duration_min >= LONG_STAY_MIN:
        return "household", "Long stay outside work hours", checked_in
    if checked_in:
        return "visitor", "Rang the doorbell, short visit", True
    return "visitor", "Short visit, no work vehicle", False


def build_visits(job: Job, day: str, events: list[RingEvent]) -> list[Session]:
    """All visits of the day, each with a role. Visits never straddle the work window,
    so the household coming home in the evening doesn't extend the crew's day."""
    presses = [e.ts_ms for e in events if e.type == "button_press"]
    if is_work_day(job, day):
        lo, hi = work_window(job, day)
        inside = [e for e in events if lo <= e.ts_ms < hi]
        outside = [e for e in events if not lo <= e.ts_ms < hi]
    else:
        inside, outside = [], events
    visits = []
    for group, in_window in ((inside, True), (outside, False)):
        for v in build_sessions(group):
            role, reason, checked_in = classify(v, in_window, presses)
            if (label := job.visit_labels.get(str(v.start_ms))) is not None:
                role, reason = label, "Marked by you"
            visits.append(v.model_copy(update={"role": role, "reason": reason, "checked_in": checked_in}))
    return sorted(visits, key=lambda v: v.start_ms)


def build_day(job: Job, day: str, events: Iterable[RingEvent], now: datetime | None = None) -> DaySummary:
    events = list(events)
    now = now or datetime.now(tz=timezone.utc)
    visits = build_visits(job, day, events)
    sessions = [v for v in visits if v.role == "crew"]
    deliveries = sum(1 for e in events if e.sub_type == "package_delivery")
    work_day = is_work_day(job, day)

    if sessions:
        status = "worked"
    elif deliveries:
        status = "delivery_only"
    elif not work_day:
        status = "off"
    else:
        deadline = at_local(day, job.expected_start, job.tz) + timedelta(minutes=job.grace_min)
        status = "pending" if now < deadline else "no_show"

    return DaySummary(
        date=day,
        status=status,
        sessions=sessions,
        other_visits=[v for v in visits if v.role != "crew"],
        total_min=sum(s.duration_min for s in sessions),
        first_arrival_ms=sessions[0].start_ms if sessions else None,
        last_departure_ms=sessions[-1].end_ms if sessions else None,
        deliveries=deliveries,
        is_work_day=work_day,
    )
