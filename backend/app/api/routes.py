"""HTTP API: Ring webhook, homeowner dashboard, public weekly report, demo helpers."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from ..config import settings
from ..core import checkins, snapshots
from ..core.days import get_day, get_events
from ..core.digest import run_digest
from ..core.noshow import run_noshow
from ..core.progress import day_flag, stall_run
from ..models import Job, JobIn, JobPatch, RingEvent
from ..ring import webhook
from ..ring.client import RingClient
from ..store import get_store
from ..timeutil import shift_day, today

log = logging.getLogger("crewlog.api")
router = APIRouter()


def _job(job_id: str) -> Job:
    job = get_store().get_job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job


# --------------------------------------------------------------------------- Ring webhook


@router.post("/webhooks/ring")
async def ring_webhook(request: Request):
    raw = await request.body()
    if not webhook.verify(settings.ring_webhook_secret, raw, request.headers.get(webhook.SIGNATURE_HEADER)):
        raise HTTPException(401, "invalid signature")
    try:
        evt = webhook.parse(raw)
    except webhook.WebhookFormatError as exc:
        raise HTTPException(400, str(exc)) from exc

    if evt.source_type != "devices" or not evt.device_id:
        return {"ok": True, "ignored": evt.type}

    store = get_store()
    job = store.job_by_device(evt.device_id)
    if job is None:
        unbound = [j for j in store.list_jobs() if not j.device_id]
        if len(unbound) != 1:
            return {"ok": True, "ignored": "no job for device"}
        job = unbound[0]
        job.device_id = evt.device_id  # first-run convenience: bind the only unbound job
        store.put_job(job)

    event = RingEvent(
        id=evt.event_id,
        job_id=job.id,
        device_id=evt.device_id,
        type=evt.type,
        sub_type=evt.sub_type,
        ts_ms=evt.ts_ms,
        request_id=evt.request_id,
    )
    stored = store.add_event(event)
    if stored:
        try:
            checkins.on_event(store, job, event)
        except Exception:  # noqa: BLE001 — never fail (and make Ring retry) over a notification
            log.exception("check-in notification failed for job %s", job.id)
    return {"ok": True, "job_id": job.id, "duplicate": not stored}


# --------------------------------------------------------------------------- Ring devices


@router.get("/api/ring/devices")
def ring_devices():
    try:
        return {"devices": RingClient().list_devices()}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Ring API unavailable: {exc}") from exc


# --------------------------------------------------------------------------- jobs


@router.get("/api/jobs")
def list_jobs():
    return {"jobs": [j.model_dump() for j in get_store().list_jobs()]}


@router.post("/api/jobs")
def create_job(body: JobIn):
    data = body.model_dump()
    data["tz"] = data.get("tz") or settings.default_tz
    job = Job(**data)
    get_store().put_job(job)
    return job.model_dump()


@router.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    return _job(job_id).model_dump()


@router.patch("/api/jobs/{job_id}")
def patch_job(job_id: str, body: JobPatch):
    job = _job(job_id)
    updated = job.model_copy(update={k: v for k, v in body.model_dump().items() if v is not None})
    get_store().put_job(updated)
    return updated.model_dump()


# --------------------------------------------------------------------------- day / week


def _day_payload(job: Job, day: str, public: bool = False) -> dict:
    store = get_store()
    summary = get_day(store, job, day)
    digest = store.get_digest(job.id, day)
    # The shared report shows crew visits only: household and neighbour visits are the homeowner's private life.
    out = {
        "summary": summary.model_dump(exclude={"other_visits"} if public else None),
        "digest": digest.model_dump() if digest else None,
        "flag": day_flag(summary, digest),
    }
    if not public:
        out["events"] = [
            {"ts_ms": e.ts_ms, "sub_type": e.sub_type, "type": e.type} for e in get_events(store, job, day)
        ]
        out["alerts"] = [a.model_dump() for a in store.list_alerts(job.id) if a.date == day]
    return out


@router.get("/api/jobs/{job_id}/day")
def day_view(job_id: str, date: str | None = None):
    job = _job(job_id)
    return {"job": job.model_dump(), "date": date or today(job.tz), **_day_payload(job, date or today(job.tz))}


def _week(job: Job, end: str, public: bool) -> dict:
    days = [_day_payload(job, shift_day(end, -i), public) for i in range(6, -1, -1)]
    worked = [d for d in days if d["summary"]["status"] == "worked"]
    return {
        "start": shift_day(end, -6),
        "end": end,
        "days": days,
        "totals": {
            "days_worked": len(worked),
            "total_min": sum(d["summary"]["total_min"] for d in days),
            "no_shows": sum(1 for d in days if d["summary"]["status"] == "no_show"),
            "scheduled_days": sum(1 for d in days if d["summary"]["is_work_day"]),
            "no_progress_days": sum(1 for d in days if d["flag"] == "no_progress"),
            "short_visits": sum(1 for d in days if d["flag"] == "short_visit"),
            "stalled_days": stall_run([(d["summary"]["date"], d["summary"]["status"], d["flag"]) for d in days]),
        },
    }


@router.get("/api/jobs/{job_id}/week")
def week_view(job_id: str, end: str | None = None):
    job = _job(job_id)
    return {"job": job.model_dump(), **_week(job, end or today(job.tz), public=False)}


@router.get("/api/jobs/{job_id}/alerts")
def alerts(job_id: str):
    _job(job_id)
    return {"alerts": [a.model_dump() for a in get_store().list_alerts(job_id)]}


@router.post("/api/jobs/{job_id}/digest/run")
def digest_now(job_id: str, date: str | None = None, force: bool = True, demo_stall: bool = False):
    job = _job(job_id)
    if demo_stall and not settings.demo_mode:
        raise HTTPException(403, "demo mode disabled")
    digest = run_digest(get_store(), job, date or today(job.tz), force=force, demo_stall=demo_stall)
    if not digest:
        raise HTTPException(409, "no work recorded on that day — nothing to summarise")
    return digest.model_dump()


@router.post("/api/jobs/{job_id}/summary/run")
def summary_now(job_id: str, date: str | None = None):
    job = _job(job_id)
    alert = checkins.send_day_summary(get_store(), job, date or today(job.tz))
    return {"alert": alert.model_dump() if alert else None}


@router.post("/api/jobs/{job_id}/noshow/run")
def noshow_now(job_id: str, date: str | None = None):
    job = _job(job_id)
    alert = run_noshow(get_store(), job, date or today(job.tz))
    return {"alert": alert.model_dump() if alert else None}


# --------------------------------------------------------------------------- media + public report


@router.get("/api/snapshots/{job_id}/{day}/{slot}")
def snapshot(job_id: str, day: str, slot: str):
    if slot not in {"am", "pm"}:
        raise HTTPException(404)
    img = snapshots.load(job_id, day, slot)
    if not img:
        raise HTTPException(404, "no snapshot")
    return Response(content=img[0], media_type=img[1], headers={"Cache-Control": "max-age=3600"})


@router.get("/api/report/{token}")
def public_report(token: str, end: str | None = None):
    job = get_store().job_by_token(token)
    if not job:
        raise HTTPException(404, "report not found")
    public_job = {"name": job.name, "contractor_name": job.contractor_name, "tz": job.tz, "expected_start": job.expected_start}
    return {"job": public_job, **_week(job, end or today(job.tz), public=True)}


# --------------------------------------------------------------------------- demo helpers


@router.post("/api/demo/reset")
def demo_reset():
    if not settings.demo_mode:
        raise HTTPException(403, "demo mode disabled")
    get_store().reset()
    return {"ok": True}


# The autoplay script (scripts/demo_autoplay.py) "directs" the open dashboard: it sets which
# page to show and what to scroll to, and the dashboard follows within a second.
# In-memory and DEMO_MODE only.
_demo_view: dict = {"seq": 0, "view": "today", "focus": "top", "token": None}


class DemoView(BaseModel):
    view: Literal["today", "week", "setup", "report", "reload"]
    focus: str = "top"  # "top", or the id of an element to scroll to
    token: str | None = None  # share token, for view="report"


@router.get("/api/demo/view")
def demo_view_get():
    if not settings.demo_mode:
        raise HTTPException(404)
    return _demo_view


@router.post("/api/demo/view")
def demo_view_set(body: DemoView):
    if not settings.demo_mode:
        raise HTTPException(403, "demo mode disabled")
    _demo_view.update(body.model_dump(), seq=_demo_view["seq"] + 1)
    return _demo_view
