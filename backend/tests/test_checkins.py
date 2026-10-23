from datetime import timezone

from app.core.checkins import on_event, send_day_summary
from app.core.digest import run_digest
from app.models import Job, RingEvent
from app.store import get_store
from app.timeutil import at_local

TZ = "Asia/Kolkata"
DAY = "2026-10-21"  # a Wednesday
JOB = Job(tz=TZ, name="Kitchen renovation", device_id="d")


def now(hhmm, day=DAY):
    return at_local(day, hhmm, TZ).astimezone(timezone.utc)


def event(hhmm, sub="human", type_="motion_detected", day=DAY):
    ts = int(at_local(day, hhmm, TZ).timestamp() * 1000)
    e = RingEvent(id=f"{type_}-{sub}-{ts}", job_id=JOB.id, device_id="d", type=type_, sub_type=sub, ts_ms=ts)
    get_store().add_event(e)
    return on_event(get_store(), JOB, e, now(hhmm, day))


def press(hhmm):
    return event(hhmm, sub=None, type_="button_press")


def kinds():
    return sorted(a.kind for a in get_store().list_alerts(JOB.id))


def setup_function():
    get_store().put_job(JOB)


def test_check_in_once_when_crew_arrives():
    assert event("08:05", "vehicle") is None  # a sighting or two isn't a visit yet
    assert event("08:06") is None
    alert = event("08:07")
    assert alert.kind == "check_in"
    assert alert.message == "Crew arrived at 8:05 AM (work van seen)."
    assert event("08:30") is None
    assert kinds() == ["check_in"]


def test_doorbell_check_in_and_check_out():
    for t in ("08:05", "08:06", "08:07"):
        assert event(t) is None  # on foot, no van: could be anyone until they check in
    assert press("08:08").message == "Crew arrived at 8:05 AM (checked in at the doorbell)."
    assert press("08:20") is None  # too soon after arrival to be a check-out
    event("12:00")
    event("15:48")
    out = press("15:50")
    assert out.kind == "check_out"
    assert out.message == "Crew checked out at 3:50 PM. 7h 43m on site today."
    assert press("15:55") is None  # once a day
    assert kinds() == ["check_in", "check_out"]


def test_neighbour_does_not_notify():
    for t in ("14:00", "14:02", "14:04"):
        assert event(t) is None
    assert kinds() == []


def test_history_stays_silent():
    # events for an earlier day (seeding, backfill) never notify
    ts = int(at_local("2026-10-20", "08:05", TZ).timestamp() * 1000)
    for i, t in enumerate((ts, ts + 3 * 60_000)):
        e = RingEvent(id=f"old{i}", job_id=JOB.id, device_id="d", type="motion_detected", sub_type="vehicle", ts_ms=t)
        get_store().add_event(e)
        assert on_event(get_store(), JOB, e, now("09:00")) is None


def test_day_summary_once_and_only_on_worked_days():
    assert send_day_summary(get_store(), JOB, DAY, now("18:00")) is None  # no crew → no recap
    for t, sub in (("08:05", "vehicle"), ("08:07", "human"), ("08:09", "human"), ("12:00", "human"), ("15:40", "human")):
        event(t, sub)
    run_digest(get_store(), JOB, DAY)
    alert = send_day_summary(get_store(), JOB, DAY, now("18:00"))
    assert alert.kind == "day_summary"
    assert alert.message == "Today at Kitchen renovation: crew on site 8:05 AM to 3:40 PM, 7h 35m in total."
    assert send_day_summary(get_store(), JOB, DAY, now("18:05")) is None
