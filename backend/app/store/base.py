"""Storage interface. Implementations: LocalStore (JSON file) and DynamoStore."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Alert, Digest, Job, RingEvent


class Store(ABC):
    # jobs
    @abstractmethod
    def put_job(self, job: Job) -> None: ...
    @abstractmethod
    def get_job(self, job_id: str) -> Job | None: ...
    @abstractmethod
    def list_jobs(self) -> list[Job]: ...

    def job_by_device(self, device_id: str) -> Job | None:
        return next((j for j in self.list_jobs() if j.device_id == device_id), None)

    def job_by_token(self, token: str) -> Job | None:
        return next((j for j in self.list_jobs() if j.share_token == token), None)

    # events
    @abstractmethod
    def add_event(self, event: RingEvent) -> bool:
        """Store an event; return False if it was a duplicate (same id or request_id)."""

    @abstractmethod
    def events_between(self, job_id: str, start_ms: int, end_ms: int) -> list[RingEvent]: ...

    # digests
    @abstractmethod
    def put_digest(self, digest: Digest) -> None: ...
    @abstractmethod
    def get_digest(self, job_id: str, day: str) -> Digest | None: ...

    # alerts
    @abstractmethod
    def put_alert(self, alert: Alert) -> None: ...
    @abstractmethod
    def list_alerts(self, job_id: str) -> list[Alert]: ...

    def has_alert(self, job_id: str, day: str, kind: str) -> bool:
        return any(a.date == day and a.kind == kind for a in self.list_alerts(job_id))

    @abstractmethod
    def reset(self) -> None: ...
