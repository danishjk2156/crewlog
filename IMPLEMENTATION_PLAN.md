# CrewLog — Implementation Plan

**Verified service visits for your home, using the Ring camera you already own.**

| | |
|---|---|
| Hackathon | Build, Ship, Shape: Amazon Developer Hackathon (Devpost) |
| Primary track | **Ring** |
| Mini challenges | **AWS Builder** (Bedrock, DynamoDB, SNS, EventBridge, Lambda) + **Open Source** (optional) |
| Deadline | **Oct 23, 2026, 12:00pm PDT = Oct 24, 12:30am IST** |
| Hardware | None. Ring Developer Playground + `ring-sandbox` emulator |

---

## 1. Problem & Solution (one paragraph each)

**Problem.** Homeowners pay tens of thousands of dollars for renovations and recurring home services, but have no visibility into whether workers showed up, how long they stayed, or what got done — unless they leave work or scrub through doorbell footage by hand.

**Solution.** CrewLog listens to Ring motion events, turns them into on-site work sessions, alerts the homeowner when a scheduled crew doesn't show, and uses Amazon Bedrock to describe each day's progress from a morning and evening snapshot. A weekly report can be shared with the contractor so both sides see the same facts.

---

## 2. Scope

### Must-have (MVP — required for submission)
1. **Ingest** Ring motion webhooks (`human`, `vehicle`) and store them.
2. **Sessionize** events into arrival → departure sessions with total hours per day.
3. **No-show alert** when nobody arrives by `expected_start + grace`.
4. **AI daily digest** (Bedrock vision: morning vs evening snapshot → plain-English summary).
5. **Dashboard**: today's timeline, sessions, digest, alerts, settings.
6. **Weekly report** page with a shareable read-only link.
7. **Demo** running end-to-end on `ring-sandbox`.

### Stretch (only if time remains)
- Alexa+ MCP tool: `get_crew_status()` → "Did the crew show up today?"
- Contractor-drafted message sent via SNS/email.
- Open Source mini challenge: PR to `ring-sandbox` or publish `crewlog-sessionizer` (MIT).

### Out of scope
- Face recognition / worker identification (privacy — deliberately excluded).
- Payments, marketplace integrations (future scope only).

---

## 3. Architecture

```
┌──────────────────────┐   signed webhook    ┌──────────────────────────────┐
│ Ring Partner API     │ ──────────────────▶ │ FastAPI backend               │
│ (ring-sandbox for    │                     │  /webhooks/ring               │
│  demo; real API in   │ ◀── REST (events,   │  /api/...  (dashboard)        │
│  production)         │     snapshots)      │  sessionizer, alerts, digest  │
└──────────────────────┘                     └──────┬─────────┬─────────┬────┘
                                                    │         │         │
                                          DynamoDB  │  Bedrock│     SNS │
                                     (events, sessions,  (vision  (SMS / email
                                      digests, jobs)   digest)    alerts)
                                                    │
                              EventBridge Scheduler ┘  (no-show check, evening digest)

┌──────────────────────┐
│ React + Tailwind     │  ← homeowner dashboard + shareable weekly report
└──────────────────────┘
```

**Hosting:** FastAPI on AWS Lambda (Mangum) behind API Gateway. For local development and the demo recording, run locally and expose with a tunnel if the sandbox needs a public webhook URL.

---

## 4. Tech Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.11, FastAPI, Pydantic, boto3 |
| Ring integration | Ring Partner API (JSON:API), `ring-sandbox` emulator + client |
| AI | Amazon Bedrock — Converse API with a vision-capable model (Claude or Nova; confirm model access in your region) |
| Storage | DynamoDB (single table) |
| Scheduling | EventBridge Scheduler → Lambda |
| Notifications | SNS (SMS needs verified numbers in sandbox mode — use email as fallback) |
| Frontend | React (Vite) + Tailwind CSS |
| Deploy | Lambda + API Gateway (backend), S3 + CloudFront or Amplify (frontend) |

---

## 5. Repository Structure

```
crewlog/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, routers
│   │   ├── config.py            # env vars
│   │   ├── models.py            # Pydantic models
│   │   ├── ring/
│   │   │   ├── webhook.py       # POST /webhooks/ring (HMAC verify)
│   │   │   └── client.py        # events + snapshot fetch
│   │   ├── core/
│   │   │   ├── sessionizer.py   # events → sessions
│   │   │   ├── noshow.py        # no-show check
│   │   │   └── digest.py        # Bedrock vision digest
│   │   ├── store/dynamo.py      # DynamoDB access
│   │   ├── notify/sns.py        # alerts
│   │   └── api/routes.py        # dashboard + report endpoints
│   ├── scripts/
│   │   ├── seed_history.py      # 5 past days of demo sessions
│   │   └── demo_day.sh          # live sandbox injections for the video
│   ├── tests/test_sessionizer.py
│   └── requirements.txt
├── frontend/
│   └── src/ (Dashboard, Timeline, DigestCard, WeeklyReport, Settings)
├── docs/
│   ├── architecture.png
│   └── friction-log.md
├── LICENSE (MIT)
└── README.md
```

---

## 6. Data Model (DynamoDB single table)

| Entity | PK | SK | Key attributes |
|---|---|---|---|
| Job | `JOB#<job_id>` | `META` | name, contractor_name, contractor_contact, device_id, work_days, expected_start, grace_min, digest_time, share_token |
| Event | `JOB#<job_id>` | `EVT#<iso_ts>` | type, sub_type (human/vehicle/package_delivery), device_id, raw |
| Session | `JOB#<job_id>` | `SES#<date>#<start_ts>` | start, end, duration_min, event_count, vehicle_count |
| Day summary | `JOB#<job_id>` | `DAY#<date>` | total_min, first_arrival, last_departure, status (worked/no_show/off) |
| Digest | `JOB#<job_id>` | `DIG#<date>` | summary, changes[], concerns[], morning_img, evening_img |
| Alert | `JOB#<job_id>` | `ALR#<iso_ts>` | kind (no_show), message, drafted_reply, sent |

---

## 7. Core Logic

### 7.1 Webhook ingest
- Verify the HMAC signature using the shared key.
- Accept motion events; keep `human` and `vehicle` sub-types for attendance, store `package_delivery` as a "delivery" marker.
- Map `device_id` → `job_id`, write the Event, then re-run the sessionizer for that day.

### 7.2 Sessionizer (plain rules, no ML)
```
events = today's human/vehicle events, sorted by time
for each event:
    if no open session or event.ts - last_ts > GAP (45 min):
        close previous session; open new session at event.ts
    extend session end to event.ts
day.total_min = sum(session durations)
day.first_arrival = first session start; day.last_departure = last session end
```
Edge cases: single isolated event (passer-by) → ignore sessions under 5 minutes; delivery-only days → status `delivery_only`, not `worked`.

### 7.3 No-show check
- EventBridge fires at `expected_start + grace_min` on work days.
- If no `human` event since midnight → create Alert, draft a polite message with Bedrock, notify homeowner via SNS.

### 7.4 AI daily digest
- EventBridge fires at `digest_time` (e.g. 6:00pm).
- Pick the **morning snapshot** (first after arrival) and **evening snapshot** (last before departure). Demo fallback: local sample images.
- Call Bedrock Converse with both images + session facts.

**Prompt (sketch):**
```
You are a neutral site-progress reporter for a homeowner.
Facts: crew on site {first_arrival}–{last_departure}, {total_hours}h, {vehicles} vehicles.
Image 1 = morning, Image 2 = evening, same camera angle.
Describe only visible changes. Do not identify or describe people.
Return JSON: {"summary": "<2 sentences>", "changes": [..], "concerns": [..]}
If nothing changed, say so plainly.
```

### 7.5 Weekly report
- `GET /report/<share_token>` → read-only: days worked, hours per day, digests, before/after strip.
- Same link can be sent to the contractor (transparency for both sides).

---

## 8. API Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/webhooks/ring` | Receive Ring events |
| POST | `/api/jobs` | Create job (schedule, contractor, device) |
| GET | `/api/jobs/{id}/today` | Timeline, sessions, status |
| GET | `/api/jobs/{id}/digests?from=&to=` | Daily digests |
| GET | `/api/jobs/{id}/alerts` | Alerts |
| POST | `/api/jobs/{id}/digest/run` | Trigger digest now (demo button) |
| POST | `/api/jobs/{id}/noshow/run` | Trigger no-show check now (demo button) |
| GET | `/report/{share_token}` | Public weekly report |

---

## 9. Build Timeline (IST, tonight)

| Time | Phase | Deliverable | Done when |
|---|---|---|---|
| 19:00–19:30 | **0. Setup** | Repo, FastAPI skeleton, `ring-sandbox serve`, DynamoDB table, Bedrock model access confirmed | Sandbox event reaches `/webhooks/ring` |
| 19:30–20:15 | **1. Ingest + sessionizer** | Webhook handler, event storage, sessionizer + unit test | Injected events produce a correct session |
| 20:15–20:50 | **2. No-show + alerts** | No-show check, SNS/email alert, drafted message | Manual trigger sends alert |
| 20:50–21:30 | **3. AI digest** | Bedrock vision digest with sample images | Digest JSON stored and readable |
| 21:30–22:30 | **4. Dashboard + report** | Today view, digest card, alerts, weekly report page | Full flow visible in browser |
| 22:30–23:00 | **5. Deploy + seed** | Lambda/API Gateway deploy, EventBridge schedules, `seed_history.py` | Deployed URL works with seeded week |
| 23:00–23:40 | **6. Demo video** | Record < 3 min, upload to YouTube (public) | Link works |
| 23:40–00:15 | **7. Submission** | README, product feedback, friction log, Devpost form, reviewer access | **Submitted before 00:15** |

**Rule:** if a phase overruns by 15 minutes, cut stretch items first, then simplify (e.g. run locally instead of Lambda — but keep Bedrock + DynamoDB for AWS Builder).

---

## 10. Demo Script (< 3 minutes)

| Time | Scene |
|---|---|
| 0:00–0:20 | Hook: "You're paying $40K for a kitchen. Did anyone show up today?" |
| 0:20–1:10 | Inject arrival in `ring-sandbox` → dashboard shows "Crew arrived 8:12am" live; inject departure → session totals |
| 1:10–1:40 | Trigger evening digest → AI describes visible progress |
| 1:40–2:05 | No-show day → alert + drafted message to contractor |
| 2:05–2:30 | Weekly shareable report; architecture slide (Ring API + AWS services) |
| 2:30–2:55 | Future: construction-loan draw verification, Verified Pro badges, all home services |

---

## 11. Submission Checklist (from Devpost rules)

- [ ] Text description: what it does + how it works
- [ ] GitHub repo with all source, assets, run instructions
  - [ ] Public + open-source license (MIT), **or** private + add reviewers: `knmeiss`, `giolaq`, `anishamalde`, `mosesroth`, `emersonsklar`
- [ ] Repo **calls the Ring API in code** (webhook handler + client), not just a README mention
- [ ] Demo video < 3 min, public on YouTube/Vimeo, English, shows it working via simulator
- [ ] Product feedback for every tool used (Ring API, ring-sandbox, Bedrock, DynamoDB, SNS, EventBridge, Lambda) — what worked, what didn't, onboarding, would you use again
- [ ] AWS Builder: list each AWS service and how it's used
- [ ] Track + mini challenges selected (Ring, AWS Builder, Open Source if done)
- [ ] Friction log entries (up to 10% judging bonus) — e.g. "Developer Playground doesn't deliver webhooks"
- [ ] Optional: feature requests (critical / important / nice-to-have)

---

## 12. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Ring Developer Portal access not approved in time | Build and demo fully on `ring-sandbox` (same API shapes); note in friction log |
| Sandbox can't backdate events | `seed_history.py` writes past sessions directly to DynamoDB; inject only "today" live |
| Snapshots unavailable in sandbox | Serve local before/after sample images through the same snapshot interface |
| SNS SMS blocked (sandbox mode) | Use SNS email or show alert in dashboard |
| Bedrock model not enabled in region | Enable model access first thing in Phase 0; switch region if needed |
| "Is this spying on workers?" | No face recognition, no people description in prompts; contractor gets the same report; consent notice in setup |

---

## 13. Future Scope (for README & pitch)

- Construction-loan **draw verification** for lenders
- **Verified Pro** badges on Angi / Thumbtack / Houzz
- **Milestone-based payment** release
- Expand to **all recurring home services** (cleaners, landscapers, pool, dog walkers)
- Indoor Ring cam support for interior progress
- **Alexa+**: "Did the crew show up today?"
- Insurance and warranty documentation
