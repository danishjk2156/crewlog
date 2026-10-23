from app.ai import bedrock
from app.config import settings
from app.core.progress import day_flag, stall_run
from app.models import DaySummary, Digest

from test_api_flow import client, make_job, payload, post

WED, THU, FRI = "2026-10-21", "2026-10-22", "2026-10-23"
FULL_DAY = ["08:12", "10:40", "12:30", "15:40"]


def summary(status="worked", total_min=420):
    return DaySummary(date=WED, status=status, total_min=total_min)


def digest(progress):
    return Digest(job_id="j", date=WED, summary="s", progress=progress)


def work(day, times=FULL_DAY):
    for t in times:
        assert post(payload(t, day=day)).status_code == 200


def run_digest(job, day, stall):
    r = client.post(f"/api/jobs/{job['id']}/digest/run", params={"date": day, "demo_stall": stall})
    assert r.status_code == 200
    return r.json()


def low_progress_alerts(job):
    return [a for a in client.get(f"/api/jobs/{job['id']}/alerts").json()["alerts"] if a["kind"] == "low_progress"]


def test_day_flag():
    assert day_flag(summary(), digest("none")) == "no_progress"
    assert day_flag(summary(), digest("visible")) is None
    assert day_flag(summary(), digest("unknown")) is None  # offline, can't judge: never accuse
    assert day_flag(summary(), None) is None
    assert day_flag(summary(total_min=45), digest("visible")) == "short_visit"
    assert day_flag(summary(status="no_show", total_min=0), None) is None


def test_stall_run_skips_days_without_work():
    flags = [
        ("mon", "worked", None),
        ("tue", "worked", "no_progress"),
        ("wed", "no_show", None),
        ("thu", "worked", "no_progress"),
        ("sat", "off", None),
    ]
    assert stall_run(flags) == ["tue", "thu"]
    assert stall_run(flags + [("mon2", "worked", None)]) == []
    assert stall_run([("mon", "worked", "short_visit"), ("tue", "worked", "no_progress")]) == ["tue"]


def test_offline_identical_stills_mean_no_progress():
    img = (b"\x89PNG same", "image/png")
    result, model = bedrock.describe_progress(img, img, "crew on site 8:12 AM–3:40 PM")
    assert model == "offline" and result["progress"] == "none"
    result, _ = bedrock.describe_progress(img, (b"\x89PNG other", "image/png"), "facts")
    assert result["progress"] == "unknown"


def test_two_stalled_days_raise_one_alert():
    job = make_job(start_date=WED)
    work(WED)
    work(THU)

    assert run_digest(job, WED, stall=True)["progress"] == "none"
    assert low_progress_alerts(job) == []  # one quiet day is normal

    assert run_digest(job, THU, stall=True)["progress"] == "none"
    alerts = low_progress_alerts(job)
    assert len(alerts) == 1
    assert alerts[0]["date"] == THU
    assert "Wednesday and Thursday" in alerts[0]["message"]
    assert alerts[0]["drafted_reply"]

    run_digest(job, THU, stall=True)  # re-running the digest doesn't duplicate the alert
    assert len(low_progress_alerts(job)) == 1

    day = client.get(f"/api/jobs/{job['id']}/day", params={"date": THU}).json()
    assert day["flag"] == "no_progress"
    assert any(a["kind"] == "low_progress" for a in day["alerts"])

    week = client.get(f"/api/jobs/{job['id']}/week", params={"end": THU}).json()
    assert week["totals"]["stalled_days"] == [WED, THU]
    assert week["totals"]["no_progress_days"] == 2

    report = client.get(f"/api/report/{job['share_token']}", params={"end": THU}).json()
    assert report["totals"]["stalled_days"] == [WED, THU]
    assert all("alerts" not in d for d in report["days"])  # drafted messages stay private


def test_progress_between_stalls_resets():
    job = make_job(start_date=WED)
    for d in (WED, THU, FRI):
        work(d)
    run_digest(job, WED, stall=True)
    run_digest(job, THU, stall=False)
    run_digest(job, FRI, stall=True)
    assert low_progress_alerts(job) == []
    week = client.get(f"/api/jobs/{job['id']}/week", params={"end": FRI}).json()
    assert week["totals"]["stalled_days"] == [FRI]


def test_short_visit_flag():
    job = make_job(start_date=WED)
    assert post(payload("09:00", "vehicle", day=WED)).status_code == 200  # the van: a crew visit
    work(WED, ["09:20", "09:40"])
    day = client.get(f"/api/jobs/{job['id']}/day", params={"date": WED}).json()
    assert day["summary"]["status"] == "worked" and day["flag"] == "short_visit"


def test_demo_stall_needs_demo_mode(monkeypatch):
    job = make_job()
    work(WED)
    monkeypatch.setattr(settings, "demo_mode", False)
    r = client.post(f"/api/jobs/{job['id']}/digest/run", params={"date": WED, "demo_stall": True})
    assert r.status_code == 403
