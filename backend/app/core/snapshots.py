"""Choose, fetch and persist the morning/evening snapshots for a work day.

Ring mode: fetch real frames via the Ring Partner API image-download endpoint.
Demo mode: Ring's sandbox returns the same still for every timestamp, so we map
work-day N of the job to generated renovation-stage images (stage_N → stage_N+1)
to make progress visible.

Persistence: S3 when SNAPSHOT_BUCKET is set (Lambda), else DATA_DIR/snapshots.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

from ..config import settings
from ..models import DaySummary, Job
from ..ring.client import RingClient

log = logging.getLogger("crewlog.snapshots")
OFFSET_MS = 2 * 60 * 1000
BUCKET = os.getenv("SNAPSHOT_BUCKET", "")

Image = tuple[bytes, str]


@lru_cache(maxsize=1)
def _s3():
    import boto3

    return boto3.client("s3", region_name=settings.aws_region)


def _local_path(job_id: str, day: str, slot: str) -> Path:
    return settings.snapshot_dir / job_id / f"{day}_{slot}.img"


def save(job_id: str, day: str, slot: str, data: bytes, mime: str) -> str:
    key = f"snapshots/{job_id}/{day}_{slot}"
    if BUCKET:
        _s3().put_object(Bucket=BUCKET, Key=key, Body=data, ContentType=mime)
    else:
        p = _local_path(job_id, day, slot)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        p.with_suffix(".mime").write_text(mime)
    return f"/api/snapshots/{job_id}/{day}/{slot}"


def load(job_id: str, day: str, slot: str) -> Image | None:
    if BUCKET:
        try:
            obj = _s3().get_object(Bucket=BUCKET, Key=f"snapshots/{job_id}/{day}_{slot}")
            return obj["Body"].read(), obj.get("ContentType", "image/png")
        except Exception:  # noqa: BLE001
            return None
    p = _local_path(job_id, day, slot)
    if not p.exists():
        return None
    mime_p = p.with_suffix(".mime")
    return p.read_bytes(), (mime_p.read_text() if mime_p.exists() else "image/png")


def _demo_pair(worked_days_before: int) -> tuple[Path, Path] | None:
    d = settings.demo_media_dir
    stages = sorted(d.glob("stage_*.png")) if d.exists() else []
    if len(stages) < 2:
        return None
    i = min(worked_days_before, len(stages) - 2)
    return stages[i], stages[i + 1]


def capture(
    job: Job, summary: DaySummary, worked_days_before: int, stall: bool = False
) -> tuple[Image | None, Image | None, str | None, str | None]:
    """Return (am, pm, am_url, pm_url) for a worked day.

    ``stall`` (demo only) uses the morning stage for the evening too: a day on site with no visible change.
    """
    if settings.demo_mode and (pair := _demo_pair(worked_days_before)):
        am: Image = (pair[0].read_bytes(), "image/png")
        pm: Image = am if stall else (pair[1].read_bytes(), "image/png")
        return am, pm, save(job.id, summary.date, "am", *am), save(job.id, summary.date, "pm", *pm)

    if not (job.device_id and summary.first_arrival_ms and summary.last_departure_ms):
        return None, None, None, None
    try:
        ring = RingClient()
        am = ring.snapshot(job.device_id, summary.first_arrival_ms + OFFSET_MS)
        pm = ring.snapshot(job.device_id, max(summary.first_arrival_ms, summary.last_departure_ms - OFFSET_MS))
        return am, pm, save(job.id, summary.date, "am", *am), save(job.id, summary.date, "pm", *pm)
    except Exception as exc:  # noqa: BLE001 — the digest still works from session facts
        log.warning("snapshot fetch failed for %s %s: %s", job.id, summary.date, exc)
        return None, None, None, None
