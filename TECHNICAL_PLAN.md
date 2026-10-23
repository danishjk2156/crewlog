# CrewLog — Technical Implementation Plan

> Companion to `IMPLEMENTATION_PLAN.md` (product scope, timeline, demo script).
> This document is the engineering spec: modules, contracts, algorithms, config, tests.

---

## 0. Design principles

1. **Runs with zero cloud setup.** Every AWS dependency has a local fallback chosen by env vars, so the app works on a laptop in 2 minutes and on AWS by flipping config.
2. **Real Ring API shapes only.** The backend talks raw Ring Partner API (JSON:API over HTTPS, HMAC-signed webhooks). `ring-sandbox` is only the *environment* we point it at — swapping `RING_API_BASE` to `https://api.amazonvision.com` is the production switch.
3. **Derived data is recomputed, never patched.** Sessions and day summaries are a pure function of stored events → idempotent, duplicate-safe, easy to test.
4. **Privacy by construction.** No face recognition, no person description; only event metadata + 2 snapshots/day.

---

## 1. Repository layout

```
amazon/
├── IMPLEMENTATION_PLAN.md        product plan
├── TECHNICAL_PLAN.md             this file
├── README.md                     setup, run, deploy, submission notes
├── LICENSE                       MIT
├── backend/
│   ├── app/
│   │   ├── main.py               FastAPI app factory, routers, static frontend, background scheduler
│   │   ├── config.py             Settings (env vars, defaults)
│   │   ├── models.py             Pydantic domain models
│   │   ├── timeutil.py           tz helpers (local date, ms ↔ datetime)
│   │   ├── ring/
│   │   │   ├── webhook.py        HMAC verify + payload parsing → RingEvent
│   │   │   └── client.py         Ring Partner API client (devices, history, image download)
│   │   ├── core/
│   │   │   ├── sessionizer.py    events → sessions → DaySummary (pure functions)
│   │   │   ├── noshow.py         no-show detection + drafted message
│   │   │   ├── digest.py         snapshot selection + Bedrock vision digest
│   │   │   ├── snapshots.py      snapshot provider (Ring API / demo stages)
│   │   │   └── scheduler.py      due-job checks (shared by local loop + Lambda)
│   │   ├── ai/bedrock.py         Bedrock Converse wrapper + offline fallback
│   │   ├── store/
│   │   │   ├── base.py           Store interface
│   │   │   ├── local.py          JSON-file store (default)
│   │   │   └── dynamo.py         DynamoDB single-table store
│   │   ├── notify/notifier.py    SNS publish + always-on in-app alert
│   │   ├── api/routes.py         dashboard + report + demo endpoints
│   │   └── lambda_handler.py     Mangum (API) + EventBridge scheduled handler
│   ├── scripts/
│   │   ├── make_demo_media.py    generates renovation-stage images (no copyrighted photos)
│   │   ├── demo.py               registers webhook, seeds a week via sandbox, runs live day
│   │   └── create_table.py       creates the DynamoDB table
│   ├── demo_media/               generated stage_0..stage_5.png
│   ├── tests/                    pytest suite
│   ├── template.yaml             AWS SAM deploy (Lambda, API GW, DynamoDB, SNS, EventBridge)
│   └── requirements.txt
└── frontend/                     React + Vite + Tailwind (built into backend/static)
```

---

## 2. Configuration (`backend/app/config.py`)

| Env var | Default | Purpose |
|---|---|---|
| `RING_API_BASE` | `http://127.0.0.1:8787` | Ring Partner API base (sandbox → prod: `https://api.amazonvision.com`) |
| `RING_ACCESS_TOKEN` | `sandbox-token` | Bearer token from OAuth account linking |
| `RING_WEBHOOK_SECRET` | `crewlog-dev-secret` | HMAC key shared with Ring |
| `STORE` | `local` | `local` (JSON file) or `dynamo` |
| `DATA_DIR` | `backend/data` | local store + snapshot files |
| `DYNAMO_TABLE` | `crewlog` | DynamoDB table |
| `AI_PROVIDER` | `offline` | `bedrock` or `offline` |
| `BEDROCK_MODEL_ID` | `us.amazon.nova-lite-v1:0` | any Converse model with image input |
| `AWS_REGION` | `us-east-1` | |
| `SNS_TOPIC_ARN` | *(empty)* | if set, alerts are published to SNS |
| `DEFAULT_TZ` | `Asia/Kolkata` | job timezone default |
| `DEMO_MODE` | `true` | enables `/api/demo/*` and stage-image snapshots |
| `SCHEDULER` | `true` | in-process 60 s loop (disable on Lambda; EventBridge drives it) |

---

## 3. Domain models (`models.py`)

```python
Job:        id, name, contractor_name, contractor_contact, device_id | None,
            work_days: list[int] (0=Mon), expected_start "08:00", grace_min 60,
            digest_time "18:00", tz, share_token, created_at
RingEvent:  id (Ring data.id), job_id, device_id, type ("motion_detected"|"button_press"),
            sub_type ("human"|"vehicle"|"package_delivery"|"other_motion"|None),
            ts_ms, request_id
Session:    start_ms, end_ms, duration_min, event_count, vehicle_count
DaySummary: date, status ("worked"|"no_show"|"delivery_only"|"off"|"pending"),
            sessions, total_min, first_arrival_ms, last_departure_ms, deliveries
Digest:     date, summary, changes[], concerns[], model, am_snapshot, pm_snapshot, created_at
Alert:      id, date, kind ("no_show"), message, drafted_reply, channels[], created_at
```

---

## 4. Ring integration

### 4.1 Webhook contract (verified against `ring-sandbox` 0.5.0 source)
```
POST /webhooks/ring
X-Signature: sha256=<hex HMAC-SHA256(secret, raw_body)>
{
  "meta": {"version":"1.1","time":"…Z","request_id":"uuid","account_id":"…"},
  "data": {"id":"<device>_motion_detected_<ms>","type":"motion_detected",
           "attributes":{"source":"<device_id>","source_type":"devices",
                         "timestamp":<ms>,"sub_type":"human"},
           "relationships":{"devices":{"links":{"self":"/v1/devices/<id>"}}}}
}
```
**Handler rules**
1. Read **raw bytes**; verify with `hmac.compare_digest` *before* JSON parsing → 401 on mismatch.
2. Dedupe on `meta.request_id` and `data.id` (Ring retries / duplicates).
3. Ignore non-device events (`app_integration_*`, `subscription_*`) with 200.
4. Resolve job by `device_id`; if no job matches and exactly one job has `device_id=None`, bind it (first-run convenience).
5. Store event → recompute that day → return `200 {"ok":true}` fast (Ring expects quick ack).

### 4.2 REST client (`ring/client.py`, httpx)
| Method | Ring endpoint | Used for |
|---|---|---|
| `list_devices()` | `GET /v1/devices` | setup screen: pick the camera |
| `history(device_id, types)` | `GET /v1/history/devices/{id}/events?event_types=motion.human,motion.vehicle` | backfill / reconciliation |
| `snapshot(device_id, ts_ms)` | `POST /v1/devices/{id}/media/image/download` `{type:"at_timestamp", timestamp}` → follows 303 | morning/evening snapshot |

---

## 5. Sessionizer (`core/sessionizer.py`) — pure functions

```
ATTENDANCE = {"human","vehicle"}; GAP = 4 h; MIN_SESSION = 5 min
# Why 4 h: a doorbell/entry camera sees the crew arrive, step out and leave — not
# continuous presence indoors. A short gap would split one workday into fragments
# (caught by tests). 4 h still separates a morning visit from an afternoon one.
build_day(events_for_local_date, job, now) -> DaySummary
  att = sorted(e for e in events if e.sub_type in ATTENDANCE)
  sessions = []
  for e in att:
      if not sessions or e.ts - sessions[-1].end > GAP: sessions.append(Session(e.ts, e.ts))
      else: sessions[-1].end = e.ts
      count event, count vehicle
  keep sessions with duration >= MIN_SESSION OR event_count >= 3   # drop passers-by
  deliveries = count(sub_type == "package_delivery")
  status:
     sessions          → "worked"
     deliveries only   → "delivery_only"
     not a work day    → "off"
     work day & now < expected_start+grace → "pending"
     else              → "no_show"
```
Events are bucketed by **local date in the job's timezone**, not UTC.

---

## 6. No-show (`core/noshow.py`)
- Trigger: scheduler tick where `now >= expected_start + grace` on a work day, and no alert for that date yet.
- Condition: `build_day(...).status == "no_show"`.
- Action: create `Alert` with a drafted, polite contractor message (Bedrock text call; offline template fallback), send via notifier. Idempotent per (job, date).

## 7. Daily digest (`core/digest.py`)
- Trigger: scheduler tick at `digest_time` for days with `status == "worked"` and no digest yet; or manual `POST …/digest/run`.
- Snapshots (`core/snapshots.py`):
  - **Ring mode**: `snapshot(first_arrival + 2 min)` and `snapshot(last_departure − 2 min)`.
  - **Demo mode**: day *n* of the job → `stage_n.png` (am) and `stage_{n+1}.png` (pm), so progress is visible.
  - Saved to `DATA_DIR/snapshots/<job>/<date>_{am,pm}.png`, served by the API.
- Bedrock Converse call: two image blocks + facts text, system prompt forbids describing people, response forced to JSON `{summary, changes[], concerns[]}`; parse defensively (strip code fences, fallback to text).
- Offline fallback: deterministic summary from session facts (clearly labelled "offline summary").

## 8. Scheduler (`core/scheduler.py`)
`tick(now)` iterates jobs → runs no-show check and digest check. Called by:
- local: asyncio background task every 60 s (`SCHEDULER=true`);
- AWS: EventBridge Scheduler `rate(5 minutes)` → `lambda_handler.scheduled`.

## 9. Storage
**Interface** (`store/base.py`): `put_job/get_job/list_jobs/job_by_device/job_by_token`, `add_event (returns False if dup)/events_between`, `put_digest/get_digest/list_digests`, `put_alert/list_alerts/has_alert`.

**DynamoDB single table** (PK/SK strings, on-demand billing):
| Item | PK | SK | GSI1 |
|---|---|---|---|
| Job | `JOB#id` | `META` | `GSI1PK=JOBS`, `GSI1SK=created_at` (list all jobs; device/token lookups filter that list — fine at household scale) |
| Event | `JOB#id` | `EVT#<ts_ms 13-digit>#<event_id>` | — |
| Dedupe | `REQ#<request_id>` | `REQ` (conditional put, TTL 7d) | — |
| Digest | `JOB#id` | `DIG#<date>` | — |
| Alert | `JOB#id` | `ALR#<date>#<kind>` | — |
Day summaries are **computed on read** (cheap: ≤ a few hundred events/day), so there is no stale cache.

**Local store**: one JSON file guarded by a lock, same interface — used for dev, tests and offline demo.

## 10. API (`api/routes.py`)
| Method | Path | Response |
|---|---|---|
| POST | `/webhooks/ring` | `{ok}` / 401 |
| GET | `/api/ring/devices` | Ring devices (setup) |
| GET/POST | `/api/jobs` | list / create |
| GET/PATCH | `/api/jobs/{id}` | job / update |
| GET | `/api/jobs/{id}/day?date=` | DaySummary + digest + events timeline |
| GET | `/api/jobs/{id}/week?end=` | 7 DaySummaries + totals |
| GET | `/api/jobs/{id}/alerts` | alerts |
| POST | `/api/jobs/{id}/digest/run?date=` | run digest now |
| POST | `/api/jobs/{id}/noshow/run?date=` | run no-show check now |
| GET | `/api/snapshots/{job}/{date}/{slot}` | PNG |
| GET | `/api/report/{share_token}` | public weekly report JSON |
| POST | `/api/demo/reset` | (DEMO_MODE) wipe data |
| GET | `/` , `/report/{token}` | built React app |

## 11. Frontend
React 18 + Vite + Tailwind. Polls `/api/jobs/{id}/day` every 3 s so sandbox injections appear live in the demo.
Views: **Today** (status hero, timeline bar 6am–9pm with session blocks, digest card with am/pm images, alerts with drafted message + copy button), **Week** (bar chart of hours/day, digests list, share link), **Setup** (contractor, schedule, device picker from Ring), **Public report** (`/report/:token`, read-only).

## 12. AWS deployment (`template.yaml`, SAM)
- `ApiFunction` (Python 3.12, Mangum) + HTTP API; `SchedulerFunction` + EventBridge `rate(5 minutes)`.
- `CrewlogTable` (PAY_PER_REQUEST, TTL attr `ttl`, GSI1 on `GSI1PK`).
- `AlertsTopic` (SNS) with email subscription parameter.
- IAM: `dynamodb:*Item/Query` on table, `bedrock:InvokeModel` on model, `sns:Publish` on topic.
- Frontend: built into `backend/static` and served by the API function (one URL to submit).

## 13. Test plan (`backend/tests`)
| Test | Asserts |
|---|---|
| `test_webhook_signature` | valid sig accepted; tampered body / wrong key / missing header → 401 |
| `test_webhook_dedupe` | same `request_id` twice → one event |
| `test_sessionizer_*` | gap split at 45 min; passer-by dropped; tz date bucketing; status matrix (worked/no_show/pending/off/delivery_only) |
| `test_noshow` | alert once per day; not before grace; not on off days |
| `test_digest_offline` | digest stored with snapshots; JSON parse of fenced model output |
| `test_api_flow` | create job → signed webhooks → `/day` shows session → `/week` totals → public report hides contractor contact |
| `test_sandbox_e2e` (manual script) | real `ring-sandbox` delivers signed webhooks to the running app |

## 14. Demo runbook
1. `ring-sandbox serve --port 8787 --media-dir backend/demo_media`
2. `uvicorn app.main:app --port 8000` (in `backend/`)
3. `python scripts/demo.py seed` → registers webhook with the sandbox, injects a realistic past week (one no-show day) through **real signed webhook deliveries**, runs digests.
4. Record: `python scripts/demo.py arrive` → dashboard flips to "Crew on site"; `python scripts/demo.py leave`; click **Run digest**; show Week + shared report.

## 15. Security notes
HMAC on raw body with constant-time compare; request-id dedupe; share links use 128-bit random tokens and omit contractor contact details; secrets only via env; no images of people sent to the model beyond the two scene snapshots, and the prompt forbids describing people.
