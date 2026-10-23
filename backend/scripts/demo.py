"""Drive a CrewLog demo through the Ring sandbox (real signed webhook deliveries).

Prereqs (two terminals):
    ring-sandbox serve --port 8787 --media-dir demo_media
    uvicorn app.main:app --port 8000

Then:
    python scripts/demo.py setup      # reset, create job, register webhook, bind doorbell
    python scripts/demo.py seed       # last 7 days: 4 worked days (last one: no visible progress), 1 no-show
    python scripts/demo.py arrive     # crew arrives now (or --at 08:12)
    python scripts/demo.py checkin    # crew presses the doorbell to check in  → "Crew arrived" notification
    python scripts/demo.py checkout   # doorbell press on the way out (1 h+ after arrival) → "Crew checked out"
    python scripts/demo.py summary    # send today's end-of-day summary now (normally at the daily-note time)
    python scripts/demo.py neighbour --at 19:30   # short visit, no van: "also seen", not work
                                      # (pick a time away from crew activity: overlapping visits merge)
    python scripts/demo.py out        # crew steps out to the truck
    python scripts/demo.py leave      # crew leaves
    python scripts/demo.py digest     # run today's AI digest
    python scripts/demo.py digest --stall   # on site, but nothing changed (2nd day in a row → alert)
    python scripts/demo.py all        # setup + seed
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

SANDBOX = "http://127.0.0.1:8787"
API = "http://127.0.0.1:8000"
WEBHOOK_URL = f"{API}/webhooks/ring"
SECRET = "crewlog-dev-secret"
TOKEN = {"Authorization": "Bearer sandbox-token"}

# A realistic doorbell trace: arrive (person + van), step out for tools, lunch run, leave.
WORK_DAY = [
    ("08:09", "vehicle"), ("08:12", "human"), ("08:14", "human"),
    ("10:41", "human"), ("10:44", "human"),
    ("12:31", "human"), ("12:33", "vehicle"), ("13:18", "vehicle"), ("13:20", "human"),
    ("15:36", "human"), ("15:40", "vehicle"),
]
SHORT_DAY = [("09:02", "vehicle"), ("09:05", "human"), ("11:20", "human"), ("12:10", "human"), ("12:14", "vehicle")]


def die(msg: str) -> None:
    print(f"✗ {msg}")
    sys.exit(1)


def api(method: str, path: str, **kw) -> dict:
    r = httpx.request(method, API + path, timeout=30, **kw)
    if r.status_code >= 400:
        die(f"{method} {path} → {r.status_code} {r.text}")
    return r.json()


def job() -> dict:
    jobs = api("GET", "/api/jobs")["jobs"]
    if not jobs:
        die("no job yet — run: python scripts/demo.py setup")
    return jobs[-1]


def inject(device_id: str, at: datetime, sub_type: str) -> None:
    """``sub_type`` "press" sends a doorbell button press instead of a motion event."""
    event = {"type": "button_press"} if sub_type == "press" else {"type": "motion_detected", "sub_type": sub_type}
    r = httpx.post(
        f"{SANDBOX}/_sandbox/events",
        json={"device_id": device_id, **event, "at": at.isoformat()},
        timeout=10,
    )
    if r.status_code >= 400:
        die(f"sandbox inject failed: {r.status_code} {r.text}")


def at_local(day: date, hhmm: str, tz: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=ZoneInfo(tz))


def setup(_: argparse.Namespace) -> None:
    try:
        devices = httpx.get(f"{SANDBOX}/v1/devices", headers=TOKEN, timeout=5).json()["data"]
    except httpx.HTTPError:
        die(f"ring-sandbox not reachable at {SANDBOX} — start it with: ring-sandbox serve --port 8787 --media-dir demo_media")
    doorbell = next((d for d in devices if "doorbell" in str(d).lower()), devices[0])
    api("POST", "/api/demo/reset")
    httpx.delete(f"{SANDBOX}/_sandbox/webhooks", timeout=5)
    httpx.post(f"{SANDBOX}/_sandbox/webhooks", json={"url": WEBHOOK_URL, "signing_key": SECRET}, timeout=5).raise_for_status()
    api("GET", "/api/health")
    today = datetime.now().date()
    j = api(
        "POST",
        "/api/jobs",
        json={
            "name": "Kitchen renovation",
            "contractor_name": "Mike's Remodeling",
            "contractor_contact": "+1 555 0100",
            "device_id": doorbell["id"],
            "start_date": (today - timedelta(days=7)).isoformat(),
        },
    )
    print(f"✓ job {j['id']} bound to Ring device {doorbell['id']}")
    print(f"✓ webhook {WEBHOOK_URL} registered with sandbox (HMAC-signed)")
    print(f"  dashboard: {API}/   share link: {API}/report/{j['share_token']}")


def seed(_: argparse.Namespace) -> None:
    j = job()
    tz, dev = j["tz"], j["device_id"]
    today = datetime.now(ZoneInfo(tz)).date()
    worked, plan = [], []
    for back in range(7, 0, -1):
        d = today - timedelta(days=back)
        if d.weekday() not in j["work_days"]:
            continue
        plan.append(d)
    no_show_day = plan[-2] if len(plan) >= 2 else None  # one recent no-show
    for d in plan:
        if d == no_show_day:
            continue
        trace = SHORT_DAY if d == plan[0] else WORK_DAY
        for hhmm, sub in trace:
            inject(dev, at_local(d, hhmm, tz), sub)
        if len(plan) > 1 and d == plan[1]:
            inject(dev, at_local(d, "11:02", tz), "package_delivery")  # materials delivered
        worked.append(d)
    time.sleep(1.5)  # let the sandbox finish delivering webhooks
    for d in worked:
        stall = d == worked[-1] and len(worked) > 2  # most recent day: on site, nothing changed
        params = {"date": d.isoformat(), "demo_stall": str(stall).lower()}
        dg = api("POST", f"/api/jobs/{j['id']}/digest/run", params=params)
        print(f"✓ {d} worked{' (no visible progress)' if stall else ''} — digest: {dg['summary'][:90]}…")
    if no_show_day:
        a = api("POST", f"/api/jobs/{j['id']}/noshow/run", params={"date": no_show_day.isoformat()})["alert"]
        print(f"✓ {no_show_day} no-show — alert: {a and a['drafted_reply']}")


def live(sub_types: list[str], label: str):
    def run(args: argparse.Namespace) -> None:
        j = job()
        tz = j["tz"]
        now = datetime.now(ZoneInfo(tz))
        base = at_local(now.date(), args.at, tz) if args.at else now
        for i, sub in enumerate(sub_types):
            inject(j["device_id"], base + timedelta(minutes=i * 2), sub)
        print(f"✓ {label} at {base.strftime('%I:%M %p')} ({', '.join(sub_types)})")

    return run


def digest(args: argparse.Namespace) -> None:
    j = job()
    dg = api("POST", f"/api/jobs/{j['id']}/digest/run", params={"demo_stall": str(args.stall).lower()})
    print(f"✓ digest ({dg['model']}): {dg['summary']}")
    for c in dg["changes"]:
        print(f"   • {c}")
    alerts = [a for a in api("GET", f"/api/jobs/{j['id']}/alerts")["alerts"] if a["kind"] == "low_progress"]
    if args.stall and alerts:
        print(f"✓ low-progress alert: {alerts[0]['message']}")


def summary(_: argparse.Namespace) -> None:
    j = job()
    a = api("POST", f"/api/jobs/{j['id']}/summary/run")["alert"]
    print(f"✓ end-of-day summary: {a['message']}" if a else "• no summary (already sent today, or the crew didn't work)")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup").set_defaults(fn=setup)
    sub.add_parser("seed").set_defaults(fn=seed)
    for name, subs, label in [
        ("arrive", ["vehicle", "human", "human"], "crew arrived"),
        ("checkin", ["press"], "crew checked in at the doorbell"),
        ("checkout", ["press"], "crew checked out at the doorbell"),
        ("neighbour", ["human", "human", "human"], "neighbour stopped by"),
        ("out", ["human", "human"], "crew stepped out"),
        ("leave", ["human", "vehicle"], "crew left"),
    ]:
        sp = sub.add_parser(name)
        sp.add_argument("--at", help="HH:MM local time today (default: now)")
        sp.set_defaults(fn=live(subs, label))
    dp = sub.add_parser("digest")
    dp.add_argument("--stall", action="store_true", help="demo: evening still identical to morning (no visible progress)")
    dp.set_defaults(fn=digest)
    sub.add_parser("summary").set_defaults(fn=summary)
    sub.add_parser("all").set_defaults(fn=lambda a: (setup(a), seed(a)))
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
