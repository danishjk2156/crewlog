"""JSON-file store for local development, tests and the offline demo."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from ..models import Alert, Digest, Job, RingEvent
from .base import Store

_EMPTY = {"jobs": {}, "events": {}, "seen": [], "digests": {}, "alerts": {}}


class LocalStore(Store):
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return {**json.loads(json.dumps(_EMPTY)), **json.loads(self.path.read_text("utf-8"))}
            except json.JSONDecodeError:
                pass
        return json.loads(json.dumps(_EMPTY))

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._db), "utf-8")
        tmp.replace(self.path)

    # jobs
    def put_job(self, job: Job) -> None:
        with self._lock:
            self._db["jobs"][job.id] = job.model_dump()
            self._save()

    def get_job(self, job_id: str) -> Job | None:
        raw = self._db["jobs"].get(job_id)
        return Job(**raw) if raw else None

    def list_jobs(self) -> list[Job]:
        return sorted((Job(**j) for j in self._db["jobs"].values()), key=lambda j: j.created_at)

    # events
    def add_event(self, event: RingEvent) -> bool:
        with self._lock:
            seen = set(self._db["seen"])
            keys = {f"id:{event.id}"} | ({f"rq:{event.request_id}"} if event.request_id else set())
            if seen & keys:
                return False
            self._db["seen"].extend(keys)
            self._db["events"].setdefault(event.job_id, []).append(event.model_dump())
            self._save()
            return True

    def events_between(self, job_id: str, start_ms: int, end_ms: int) -> list[RingEvent]:
        rows = self._db["events"].get(job_id, [])
        return sorted(
            (RingEvent(**r) for r in rows if start_ms <= r["ts_ms"] < end_ms), key=lambda e: e.ts_ms
        )

    # digests
    def put_digest(self, digest: Digest) -> None:
        with self._lock:
            self._db["digests"].setdefault(digest.job_id, {})[digest.date] = digest.model_dump()
            self._save()

    def get_digest(self, job_id: str, day: str) -> Digest | None:
        raw = self._db["digests"].get(job_id, {}).get(day)
        return Digest(**raw) if raw else None

    # alerts
    def put_alert(self, alert: Alert) -> None:
        with self._lock:
            self._db["alerts"].setdefault(alert.job_id, []).append(alert.model_dump())
            self._save()

    def list_alerts(self, job_id: str) -> list[Alert]:
        rows = self._db["alerts"].get(job_id, [])
        return sorted((Alert(**a) for a in rows), key=lambda a: a.created_at, reverse=True)

    def reset(self) -> None:
        with self._lock:
            self._db = json.loads(json.dumps(_EMPTY))
            self._save()
