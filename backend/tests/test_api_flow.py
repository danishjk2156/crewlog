import json
import uuid
from datetime import timezone

from fastapi.testclient import TestClient

from app.config import settings
from app.core.noshow import run_noshow
from app.main import app
from app.ring.webhook import sign
from app.store import get_store
from app.timeutil import at_local

client = TestClient(app)
TZ = "Asia/Kolkata"
DAY = "2026-10-21"
DEVICE = "ava1.ring.device.TEST000000000000001"


def payload(hhmm, sub="human", day=DAY, request_id=None, device=DEVICE):
    ts = int(at_local(day, hhmm, TZ).timestamp() * 1000)
    return {
        "meta": {"version": "1.1", "time": "2026-10-21T00:00:00Z", "request_id": request_id or str(uuid.uuid4()), "account_id": "a"},
        "data": {
            "id": f"{device}_motion_detected_{ts}",
            "type": "motion_detected",
            "attributes": {"source": device, "source_type": "devices", "timestamp": ts, "sub_type": sub},
            "relationships": {"devices": {"links": {"self": f"/v1/devices/{device}"}}},
        },
    }


def post(body: dict, secret: str | None = None, tamper: bool = False):
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    sig = sign(secret or settings.ring_webhook_secret, raw)
    if tamper:
        raw = raw.replace(b"human", b"vehicle")
    return client.post("/webhooks/ring", content=raw, headers={"X-Signature": sig, "Content-Type": "application/json"})


def make_job(**kw):
    body = {"name": "Kitchen renovation", "contractor_name": "Mike's Remodeling", "contractor_contact": "+1-555-0100", "tz": TZ, **kw}
    return client.post("/api/jobs", json=body).json()


def test_signature_enforced():
    make_job()
    assert post(payload("08:00"), secret="wrong").status_code == 401
    assert post(payload("08:00"), tamper=True).status_code == 401
    r = client.post("/webhooks/ring", content=b"{}", headers={"Content-Type": "application/json"})
    assert r.status_code == 401


def test_full_flow_and_dedupe():
    job = make_job()
    for t in ["08:12", "08:14", "10:00", "11:30", "13:00", "14:20", "15:40"]:
        assert post(payload(t)).status_code == 200
    # auto-bound to the only job
    assert client.get(f"/api/jobs/{job['id']}").json()["device_id"] == DEVICE

    dup = payload("15:45", request_id="same-request")
    assert post(dup).json()["duplicate"] is False
    assert post(dup).json()["duplicate"] is True

    day = client.get(f"/api/jobs/{job['id']}/day", params={"date": DAY}).json()
    assert day["summary"]["status"] == "worked"
    assert len(day["summary"]["sessions"]) == 1
    assert day["summary"]["total_min"] == 453  # 08:12 → 15:45
    assert len(day["events"]) == 8

    digest = client.post(f"/api/jobs/{job['id']}/digest/run", params={"date": DAY}).json()
    assert digest["model"] == "offline"
    assert digest["am_snapshot"] and digest["pm_snapshot"]
    img = client.get(digest["am_snapshot"])
    assert img.status_code == 200 and img.content[:4] == b"\x89PNG"

    week = client.get(f"/api/jobs/{job['id']}/week", params={"end": DAY}).json()
    assert week["totals"]["days_worked"] == 1
    assert week["totals"]["total_min"] == 453

    report = client.get(f"/api/report/{job['share_token']}", params={"end": DAY}).json()
    assert "contractor_contact" not in report["job"]
    assert "events" not in report["days"][-1]
    assert report["days"][-1]["digest"]["summary"]


def test_non_device_events_ignored():
    make_job()
    body = payload("08:00")
    body["data"]["type"] = "app_integration_added"
    body["data"]["attributes"]["source_type"] = "accounts"
    assert post(body).json()["ignored"] == "app_integration_added"


def test_noshow_alert_once():
    job = make_job()
    store = get_store()
    j = store.get_job(job["id"])
    late = at_local(DAY, "09:30", TZ).astimezone(timezone.utc)
    early = at_local(DAY, "08:30", TZ).astimezone(timezone.utc)
    assert run_noshow(store, j, DAY, early) is None
    alert = run_noshow(store, j, DAY, late)
    assert alert and "Mike" in alert.drafted_reply
    assert run_noshow(store, j, DAY, late) is None  # idempotent
    assert len(client.get(f"/api/jobs/{job['id']}/alerts").json()["alerts"]) == 1


def test_digest_refuses_empty_day():
    job = make_job()
    r = client.post(f"/api/jobs/{job['id']}/digest/run", params={"date": DAY})
    assert r.status_code == 409


def test_public_report_hides_household_and_visitors():
    job = make_job()
    for t, sub in [("08:10", "vehicle"), ("08:12", "human"), ("15:30", "human"), ("20:00", "human"), ("20:02", "human"), ("20:04", "human")]:
        assert post(payload(t, sub)).status_code == 200
    day = client.get(f"/api/jobs/{job['id']}/day", params={"date": DAY}).json()
    assert [v["role"] for v in day["summary"]["other_visits"]] == ["visitor"]
    report = client.get(f"/api/report/{job['share_token']}", params={"end": DAY}).json()
    summaries = [d["summary"] for d in report["days"]]
    assert all("other_visits" not in s for s in summaries)
    assert "visit_labels" not in report["job"]
