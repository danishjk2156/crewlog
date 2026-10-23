"""Domain models shared by the API, storage and core logic."""

from __future__ import annotations

import secrets
import time
import uuid
from typing import Literal

from pydantic import BaseModel, Field

DayStatus = Literal["worked", "no_show", "delivery_only", "off", "pending"]
# Did the morning → evening stills change? "unknown" when it could not be judged.
Progress = Literal["visible", "none", "unknown"]
# Who a visit most likely was. Inferred from timing, the work van and doorbell check-ins —
# never from faces.
VisitRole = Literal["crew", "household", "visitor"]


def _now_ms() -> int:
    return int(time.time() * 1000)


class JobIn(BaseModel):
    name: str = "Kitchen renovation"
    contractor_name: str = "Mike's Remodeling"
    contractor_contact: str = ""
    device_id: str | None = None
    work_days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])  # 0 = Monday
    expected_start: str = "08:00"
    grace_min: int = 60
    digest_time: str = "18:00"
    tz: str | None = None
    start_date: str | None = None  # YYYY-MM-DD, used to number progress days


class JobPatch(BaseModel):
    name: str | None = None
    contractor_name: str | None = None
    contractor_contact: str | None = None
    device_id: str | None = None
    work_days: list[int] | None = None
    expected_start: str | None = None
    grace_min: int | None = None
    digest_time: str | None = None
    tz: str | None = None
    start_date: str | None = None


class Job(JobIn):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    visit_labels: dict[str, VisitRole] = Field(default_factory=dict)  # str(visit start_ms) → homeowner's correction
    tz: str = "Asia/Kolkata"
    share_token: str = Field(default_factory=lambda: secrets.token_urlsafe(16))
    created_at: int = Field(default_factory=_now_ms)


class RingEvent(BaseModel):
    id: str
    job_id: str
    device_id: str
    type: str
    sub_type: str | None = None
    ts_ms: int
    request_id: str = ""


class Session(BaseModel):
    start_ms: int
    end_ms: int
    duration_min: int
    event_count: int
    vehicle_count: int
    role: VisitRole = "crew"
    reason: str = ""
    checked_in: bool = False


class DaySummary(BaseModel):
    date: str
    status: DayStatus
    sessions: list[Session] = Field(default_factory=list)  # crew visits only: these count as work
    other_visits: list[Session] = Field(default_factory=list)  # household and visitors, never counted
    total_min: int = 0
    first_arrival_ms: int | None = None
    last_departure_ms: int | None = None
    deliveries: int = 0
    is_work_day: bool = True


class Digest(BaseModel):
    job_id: str
    date: str
    summary: str
    changes: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    progress: Progress = "unknown"
    model: str = "offline"
    am_snapshot: str | None = None
    pm_snapshot: str | None = None
    created_at: int = Field(default_factory=_now_ms)


class Alert(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    job_id: str
    date: str
    kind: Literal["no_show", "low_progress", "check_in", "check_out", "day_summary"] = "no_show"
    message: str
    drafted_reply: str = ""
    channels: list[str] = Field(default_factory=list)
    created_at: int = Field(default_factory=_now_ms)
