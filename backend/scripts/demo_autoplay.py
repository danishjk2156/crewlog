"""Run the whole CrewLog demo by itself, timed to docs/video-narration.txt (about 2:45).

Start the sandbox and the server first (see docs/video-script.md), open
http://127.0.0.1:8000 in the browser, then:

    python scripts/demo_autoplay.py            # reset, countdown, then the six scenes
    python scripts/demo_autoplay.py --fast     # 4x faster dry run
    python scripts/demo_autoplay.py --countdown 10

Start your screen recording during the countdown. The open dashboard follows along on
its own (Today → This week → shared report) through /api/demo/view.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import demo  # noqa: E402  (scripts/demo.py: sandbox + API helpers)

SPEED = 1.0


def wait(seconds: float) -> None:
    time.sleep(seconds / SPEED)


def caption(n: int, title: str) -> None:
    bar = "═" * 46
    print(f"\n{bar}\n  SCENE {n} · {title}\n{bar}", flush=True)


def show(view: str, focus: str = "top", token: str | None = None) -> None:
    demo.api("POST", "/api/demo/view", json={"view": view, "focus": focus, "token": token})


def ring(j: dict, hhmm: str, events: list[str], label: str) -> None:
    """Inject Ring events today at hh:mm (2 minutes apart), like `demo.py arrive --at`."""
    tz = j["tz"]
    base = demo.at_local(datetime.now(ZoneInfo(tz)).date(), hhmm, tz)
    for i, sub in enumerate(events):
        demo.inject(j["device_id"], base + timedelta(minutes=i * 2), sub)
    print(f"  ✓ {hhmm}  {label}", flush=True)


def main() -> None:
    global SPEED
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fast", action="store_true", help="run 4x faster (dry run)")
    p.add_argument("--countdown", type=int, default=5, help="seconds to start your recording (default 5)")
    p.add_argument("--no-reset", action="store_true", help="keep the current demo data")
    args = p.parse_args()
    SPEED = 4.0 if args.fast else 1.0

    if not args.no_reset:
        print("Resetting the demo week (about a minute; don't record yet)…", flush=True)
        demo.setup(args)
        demo.seed(args)
    j = demo.job()
    show("reload")
    for s in range(args.countdown, 0, -1):
        print(f"\r  Start recording now… {s} ", end="", flush=True)
        time.sleep(1)
    print("\r  Recording should be running.      ", flush=True)

    caption(1, "Did anyone show up today?")  # 0:00–0:18
    show("today")
    wait(18)

    caption(2, "The crew arrives and checks in")  # 0:18–0:50
    ring(j, "08:05", ["vehicle", "human", "human"], "work van + crew arrive")
    wait(7)
    ring(j, "08:08", ["press"], "crew taps the doorbell to check in")
    wait(4)
    show("today", "alerts")
    wait(10)
    show("today")
    wait(11)

    caption(3, "The workday, and a neighbour")  # 0:50–1:18
    ring(j, "11:40", ["human", "human"], "crew steps out to the truck")
    wait(3)
    ring(j, "15:00", ["human", "vehicle"], "crew leaves")
    wait(3)
    ring(j, "15:03", ["press"], "doorbell check-out")
    wait(4)
    show("today", "alerts")
    wait(6)
    ring(j, "19:30", ["human", "human", "human"], "a neighbour drops by")
    wait(3)
    show("today", "also-seen")
    wait(9)

    caption(4, "Presence isn't progress")  # 1:18–1:50
    demo.api("POST", f"/api/jobs/{j['id']}/digest/run", params={"demo_stall": "true"})
    print("  ✓ evening digest: no visible change, 2nd day in a row", flush=True)
    wait(3)
    show("today")
    wait(8)
    show("today", "alerts")
    wait(21)

    caption(5, "The week and the shared report")  # 1:50–2:15
    show("week")
    wait(12)
    show("report", token=j["share_token"])
    wait(13)

    caption(6, "How it's built, and what's next")  # 2:15–2:42
    show("report", "progress-notes", token=j["share_token"])
    wait(14)
    show("report", token=j["share_token"])
    wait(13)

    print("\n✓ Demo finished. Stop the recording.", flush=True)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # ✓ and box lines in any Windows console
    main()
