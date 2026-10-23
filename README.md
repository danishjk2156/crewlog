# CrewLog

**Verified service visits for your home, using the Ring camera you already own.**

You're paying a contractor $40,000 for a kitchen. Did anyone show up today? CrewLog listens to your Ring camera's motion events and turns them into an honest daily log:

- **Attendance:** arrival and departure times and hours on site, logged automatically. No timesheets.
- **No-show alerts:** if nobody arrives by the expected time, you get an alert plus a polite message to the contractor, drafted and ready to send.
- **Daily progress note:** Amazon Bedrock compares a morning and an evening camera still and describes what visibly changed. It never describes people.
- **Shareable weekly report:** one link you can send to the contractor so both sides see the same facts.

Built for the **Ring** track of *Build, Ship, Shape: Amazon Developer Hackathon*, plus the **AWS Builder** mini challenge.



---

## How it works

```
Ring camera ──motion_detected (human / vehicle / package)──▶ HMAC-signed webhook
        │                                                        │
        │   Ring Partner API (devices, history, image download)  ▼
        └──────────────────────────────────────────────▶  FastAPI backend
                                                         ├─ sessionizer: events → visits → day status
                                                         ├─ no-show check  ──▶ Amazon SNS alert
                                                         ├─ daily digest   ──▶ Amazon Bedrock (Nova, vision)
                                                         └─ storage        ──▶ Amazon DynamoDB + S3
                       EventBridge Scheduler (every 5 min) ─▶ Lambda: no-show + digest checks
React dashboard + public weekly report ◀── same API (one URL)
```

| AWS service | How CrewLog uses it |
|---|---|
| **Amazon Bedrock** (Converse API, Amazon Nova Lite) | Vision: compares morning and evening stills and writes the progress note as JSON. Text: drafts the polite no-show message to the contractor. |
| **Amazon DynamoDB** | Single-table store for jobs, Ring events, digests and alerts. Conditional writes deduplicate Ring webhook retries. |
| **Amazon S3** | Morning and evening snapshots. |
| **Amazon SNS** | No-show alerts by email or SMS. |
| **AWS Lambda + API Gateway** | Runs the API and dashboard (FastAPI via Mangum). |
| **Amazon EventBridge Scheduler** | Every 5 minutes, triggers the no-show and end-of-day digest checks. |

Ring integration in code: `backend/app/ring/webhook.py` (HMAC-SHA256 verification of `X-Signature` over the raw body, plus payload parsing) and `backend/app/ring/client.py` (`GET /v1/devices`, `GET /v1/history/devices/{id}/events`, `POST /v1/devices/{id}/media/image/download`).

Design notes and algorithms are in [TECHNICAL_PLAN.md](TECHNICAL_PLAN.md). Product scope and timeline are in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

---

## Run it locally (Windows PowerShell, about 5 minutes, no AWS needed)

Requires Python 3.11+ and Node 18+.

```powershell
cd D:\hackathon\amazon\backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts\make_demo_media.py          # renovation-stage demo images

cd ..\frontend
npm install
npm run build                               # builds the dashboard into backend\static
```

Open **three terminals**, each in `D:\hackathon\amazon\backend` with the venv activated:

```powershell
# Terminal 1: Ring emulator (Ring Partner API shapes, signed webhooks)
ring-sandbox serve --port 8787 --media-dir demo_media

# Terminal 2: CrewLog
uvicorn app.main:app --port 8000

# Terminal 3: demo driver
python scripts\demo.py all                  # creates the job, binds the doorbell, seeds a past week
python scripts\demo.py arrive               # crew arrives now   (or: --at 08:10)
python scripts\demo.py out                  # crew steps out to the truck
python scripts\demo.py leave                # crew leaves
python scripts\demo.py digest               # write today's progress note
```

Open **http://127.0.0.1:8000**. The Today view refreshes every 3 seconds, so injected events appear live.

### Turn on real AI (Amazon Bedrock)

1. In the AWS console (region **us-east-1**), go to Bedrock → Model access and enable **Amazon Nova Lite**.
2. Run `aws configure` with credentials that can call Bedrock.
3. Restart Terminal 2 with:
   ```powershell
   $env:AI_PROVIDER="bedrock"; uvicorn app.main:app --port 8000
   ```
4. Re-run `python scripts\demo.py all`. Each day's progress note is now written by Nova from the two stills.

### Use DynamoDB / SNS locally (optional)

```powershell
python scripts\create_table.py --region us-east-1
$env:STORE="dynamo"; $env:SNS_TOPIC_ARN="arn:aws:sns:us-east-1:<acct>:<topic>"; uvicorn app.main:app --port 8000
```

---

## Deploy to AWS (SAM)

```powershell
cd backend
sam build
sam deploy --guided   # set RingWebhookSecret, RingAccessToken, AlertEmail; RingApiBase defaults to production Ring
```

The `AppUrl` output is the dashboard. Register `<AppUrl>webhooks/ring` as the webhook URL in the Ring Developer Portal. Confirm the SNS subscription email.

---

## Tests

```powershell
cd backend
pytest -q
```

The suite covers HMAC verification (good, tampered and missing signatures), webhook dedupe, the sessionizer (gap splitting, passers-by, timezone day bucketing, the full status matrix), no-show idempotency, digest and snapshot storage, public-report privacy, and Bedrock reply parsing.

---

## Configuration

| Env var | Default | |
|---|---|---|
| `RING_API_BASE` | `http://127.0.0.1:8787` | `https://api.amazonvision.com` in production |
| `RING_ACCESS_TOKEN` | `sandbox-token` | OAuth token from Ring account linking |
| `RING_WEBHOOK_SECRET` | `crewlog-dev-secret` | HMAC key shared with Ring |
| `STORE` | `local` | `local` or `dynamo` |
| `AI_PROVIDER` | `offline` | `offline` or `bedrock` |
| `BEDROCK_MODEL_ID` | `us.amazon.nova-lite-v1:0` | any Converse model with image input |
| `SNS_TOPIC_ARN` / `SNAPSHOT_BUCKET` | *(empty)* | enable SNS alerts / S3 snapshots |
| `DEFAULT_TZ` | `Asia/Kolkata` | timezone for new jobs |
| `DEMO_MODE` | `true` | renovation-stage stills + `/api/demo/reset` |

---

## Privacy

- Uses motion event metadata plus two stills per work day, never continuous video.
- The Bedrock prompt forbids identifying or describing people. No face recognition.
- The shared report hides the contractor's contact details and the raw event log.
- The contractor gets the same report as the homeowner: a shared record, not hidden surveillance.

## What's next

Construction-loan draw verification for lenders, "Verified Pro" badges on contractor marketplaces, milestone-based payments, every recurring home service (cleaners, landscapers, pool, dog walkers), indoor Ring cams for interior progress, and asking Alexa+ "did the crew show up today?".

## License

MIT
