from datetime import datetime, timedelta, timezone

from app.core.sessionizer import build_day, build_sessions
from app.models import Job, RingEvent
from app.timeutil import at_local

TZ = "Asia/Kolkata"
DAY = "2026-10-21"  # a Wednesday
JOB = Job(tz=TZ, work_days=[0, 1, 2, 3, 4], expected_start="08:00", grace_min=60)


def ev(hhmm: str, sub="human", day=DAY, i=[0]):  # noqa: B006 — counter for unique ids
    i[0] += 1
    ts = int(at_local(day, hhmm, TZ).timestamp() * 1000)
    return RingEvent(id=f"e{i[0]}", job_id=JOB.id, device_id="d", type="motion_detected", sub_type=sub, ts_ms=ts)


def test_single_session_hours():
    s = build_sessions([ev("08:12"), ev("08:15", "vehicle"), ev("10:30"), ev("12:00"), ev("15:40")])
    assert len(s) == 1
    assert s[0].duration_min == 448  # 08:12 → 15:40
    assert s[0].vehicle_count == 1


def test_gap_splits_sessions():
    # morning visit, then a 4.5 h quiet gap, then an afternoon visit
    s = build_sessions([ev("08:00"), ev("08:30"), ev("13:00"), ev("13:20")])
    assert [x.duration_min for x in s] == [30, 20]


def test_long_indoor_stretch_stays_one_session():
    # crew goes inside at 08:12 and is only seen again stepping out at 11:40 and leaving 15:40
    s = build_sessions([ev("08:12"), ev("11:40"), ev("15:40")])
    assert len(s) == 1 and s[0].duration_min == 448


def test_passer_by_dropped_but_burst_kept():
    assert build_sessions([ev("14:00")]) == []
    burst = build_sessions([ev("14:00"), ev("14:01"), ev("14:02")])
    assert len(burst) == 1


def test_package_and_other_motion_not_attendance():
    s = build_sessions([ev("09:00", "package_delivery"), ev("09:01", "other_motion"), ev("09:30", None)])
    assert s == []


def _now(hhmm, day=DAY):
    return at_local(day, hhmm, TZ).astimezone(timezone.utc)


def test_status_matrix():
    assert build_day(JOB, DAY, [ev("08:00"), ev("16:00"), ev("11:00"), ev("14:00")], _now("17:00")).status == "worked"
    assert build_day(JOB, DAY, [], _now("08:30")).status == "pending"
    assert build_day(JOB, DAY, [], _now("09:01")).status == "no_show"
    assert build_day(JOB, DAY, [ev("10:00", "package_delivery")], _now("17:00")).status == "delivery_only"
    saturday = "2026-10-24"
    assert build_day(JOB, saturday, [], _now("17:00", saturday)).status == "off"


def test_day_totals():
    # two short crew visits (each starts with the work van)
    d = build_day(JOB, DAY, [ev("08:00", "vehicle"), ev("08:20"), ev("13:00", "vehicle"), ev("13:30"), ev("13:40")], _now("18:00"))
    assert d.total_min == 20 + 40
    assert d.first_arrival_ms == ev("08:00").ts_ms
    assert d.last_departure_ms == ev("13:40").ts_ms


def press(hhmm, day=DAY, i=[0]):  # noqa: B006
    i[0] += 1
    ts = int(at_local(day, hhmm, TZ).timestamp() * 1000)
    return RingEvent(id=f"p{i[0]}", job_id=JOB.id, device_id="d", type="button_press", sub_type=None, ts_ms=ts)


def roles(events, job=JOB, day=DAY):
    d = build_day(job, day, events, _now("23:00", day))
    return [(v.role, v.reason) for v in sorted(d.sessions + d.other_visits, key=lambda v: v.start_ms)]


def test_who_was_it():
    # crew: checked in at the doorbell (strongest signal), even for a short visit
    assert roles([press("09:00"), ev("09:01"), ev("09:20")]) == [("crew", "Checked in at the doorbell")]
    # crew: the work van during work hours
    assert roles([ev("09:00", "vehicle"), ev("09:30")])[0][0] == "crew"
    # crew: a long stay inside work hours
    assert roles([ev("09:00"), ev("11:00")])[0] == ("crew", "Long stay during work hours")
    # neighbour: short, no van, no check-in
    assert roles([ev("14:00"), ev("14:02"), ev("14:04")]) == [("visitor", "Short visit, no work vehicle")]
    # household: a long stay in the evening
    assert roles([ev("19:30"), ev("21:30")]) == [("household", "Long stay outside work hours")]


def test_evening_household_does_not_extend_crew_day():
    d = build_day(JOB, DAY, [ev("08:00", "vehicle"), ev("08:05"), ev("12:00"), ev("16:00"), ev("19:10"), ev("21:00")], _now("23:00"))
    assert [s.role for s in d.sessions] == ["crew"]
    assert d.last_departure_ms == ev("16:00").ts_ms
    assert [v.role for v in d.other_visits] == ["household"]


def test_only_household_and_visitors_is_still_a_no_show():
    d = build_day(JOB, DAY, [ev("10:00"), ev("10:02"), ev("10:04")], _now("17:00"))
    assert d.status == "no_show" and d.total_min == 0
    assert [v.role for v in d.other_visits] == ["visitor"]


def test_homeowner_label_wins():
    job = JOB.model_copy(update={"visit_labels": {str(ev("09:00", "vehicle").ts_ms): "household"}})
    d = build_day(job, DAY, [ev("09:00", "vehicle"), ev("10:30")], _now("23:00"))
    assert d.sessions == [] and d.other_visits[0].reason == "Marked by you"
