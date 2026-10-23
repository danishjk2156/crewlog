# CrewLog demo video: script (target 2:45)

## Before you record (10 minutes)

**Screen layout:** browser on the left (about 2/3 of the screen), one PowerShell window on the right (about 1/3). Zoom the browser to 110–125% so text is readable on YouTube.

**Recorder:** Windows Snipping Tool → **Record** (Win+Shift+R), or Clipchamp / OBS. Record the whole screen, with your microphone on.

**Terminal 1** (leave running, off-screen):
```powershell
cd D:\hackathon\amazon\backend
ring-sandbox serve --port 8787 --media-dir demo_media
```

**Terminal 2** (leave running, off-screen). `SCHEDULER=false` stops a surprise "no-show" alert for today appearing before you inject the arrival:
```powershell
cd D:\hackathon\amazon\backend
$env:SCHEDULER="false"; uvicorn app.main:app --port 8000
```

**Terminal 3** (the one on camera):
```powershell
cd D:\hackathon\amazon\backend
$env:PYTHONIOENCODING="utf-8"
python scripts\demo.py all
```
Then open **http://127.0.0.1:8000** in the browser, click **This week** once (to check the seeded week is there), then back to **Today**. Clear the terminal (`cls`).

Do a full dry run once. Then run `python scripts\demo.py all` again to reset before the real take.

> Times use `--at` so the crew counts as working hours even when you record at night. The dashboard refreshes every 3 seconds, so each command shows up on screen right away.

---

## Shot list

### 0:00–0:20 · The hook (Today page, nothing happened yet)
> "You're paying a contractor forty thousand dollars for a kitchen. Did anyone actually show up today? You're at work, so you'd have to scroll through hours of doorbell video to find out. CrewLog turns the Ring camera you already own into an honest work log."

### 0:20–0:55 · The crew arrives and checks in
Run:
```powershell
python scripts\demo.py arrive --at 08:05
```
> "Ring sends CrewLog a signed webhook every time it sees a person or a vehicle. Here's the work van and the crew at five past eight."

(The page shows "Crew worked today, 8:05 AM" and a **CHECKED IN** card.)
```powershell
python scripts\demo.py checkin --at 08:08
```
> "The crew taps the doorbell to check in, and the homeowner gets a notification. CrewLog never identifies anyone: no face recognition. It recognises a work pattern: the van, a doorbell check-in, a long stay during work hours."

### 0:55–1:20 · The workday, and who is not crew
```powershell
python scripts\demo.py out --at 11:40
python scripts\demo.py leave --at 15:00
python scripts\demo.py checkout --at 15:03
```
> "They step out to the truck, come back, and check out at three. Seven hours on site, logged automatically: no timesheets."

```powershell
python scripts\demo.py neighbour --at 19:30
```
> "A neighbour drops by in the evening. CrewLog shows it as 'also seen', but it never counts as work hours, and it never appears on the contractor's report."

(Scroll a little to show the time-on-site bar and the CHECKED IN / CHECKED OUT cards.)

### 1:20–1:50 · Presence isn't progress
```powershell
python scripts\demo.py digest --stall
```
> "Showing up isn't the same as working. Each evening CrewLog compares a morning and an evening still of the work area. Today nothing changed, and nothing changed yesterday either. So CrewLog flags it and drafts a polite check-in message, a question, not an accusation, because some work isn't visible."

(Scroll to the "no visible progress" alert with the drafted message; click **Copy message**.)

### 1:50–2:15 · The week and the shared report
Click **This week** (the bars animate).
> "The week at a glance: four of five days worked, one no-show, which triggered an alert that morning, and two quiet days flagged."

Go to **Settings**, click **Copy link**, paste it in a new tab.
> "And this is the key: the contractor gets the same report. Hours and progress only: no contact details, no neighbours, no raw camera log. A shared record, not surveillance."

### 2:15–2:45 · How it's built, and what's next
(Stay on the report, or show the README architecture section.)
> "Under the hood: Ring Partner API webhooks verified with HMAC, a FastAPI backend, DynamoDB, S3, SNS alerts, EventBridge every five minutes, and Lambda. The progress notes use the Amazon Bedrock Converse API with Nova Lite. My new AWS account returned 'Operation not allowed', so this demo shows the built-in offline fallback; that's in my friction log.
> Next: construction-loan draw checks for lenders, Verified Pro badges, and every recurring home service. CrewLog: did the crew show up? Now you know."

---

## Checklist after recording
- [ ] Under 3:00, English, shows the app working
- [ ] Upload to YouTube as **Public** (or Vimeo), title "CrewLog – Ring hackathon demo"
- [ ] Paste the link into Devpost
- [ ] Repo public with the MIT license (or add the listed reviewers)
- [ ] Remove the "draft" line from `docs/friction-log.md`
