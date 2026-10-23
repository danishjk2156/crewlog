# Friction log (draft — edit with your own experience before submitting)

Each entry: task · steps · expected vs actual · severity · workaround · suggestion.

## 1. Developer Playground does not deliver webhooks
- **Task:** Test the motion-event webhook handler end to end without hardware.
- **Steps:** Registered an app in the Ring Developer Portal and opened the Developer Playground.
- **Expected:** Simulated motion events POSTed to my webhook URL.
- **Actual:** The Playground simulates live view but does not deliver webhooks, so the core integration path can't be exercised without a physical device.
- **Severity:** High (blocks hardware-less development of event-driven apps).
- **Workaround:** Used the community `ring-sandbox` emulator, which signs and delivers webhooks in the same JSON:API shape.
- **Suggestion:** Add a "Send test event" button to the Playground (motion.human, motion.vehicle, ding) that delivers a signed webhook to the registered URL.

## 2. Snapshots in simulation are identical for every timestamp
- **Task:** Fetch morning and evening stills to compare progress.
- **Expected:** Different frames for different `at_timestamp` values.
- **Actual:** The sandbox returns one still per device, so before/after comparison can't be demonstrated.
- **Severity:** Medium.
- **Workaround:** Demo mode maps each work day to generated renovation-stage images.
- **Suggestion:** Let developers upload a timestamped image sequence per simulated device.

## 3. Device IDs change every emulator restart
- **Task:** Keep a job bound to a camera across restarts.
- **Actual:** New random device IDs on each run, so stored bindings break.
- **Severity:** Low.
- **Workaround:** CrewLog auto-binds the only unbound job to the first device that sends motion; the demo script re-binds on setup.
- **Suggestion:** Stable, seedable device IDs in simulators.

## 4. No documented "presence" signal for doorbells
- **Task:** Compute hours on site from a front-door camera.
- **Actual:** A doorbell only sees arrivals, departures and step-outs, not continuous presence. My first 45-minute session-gap rule split real workdays into fragments (caught by tests).
- **Severity:** Medium (design pitfall for attendance-style apps).
- **Workaround:** A 4-hour gap rule; a session runs from first sighting until a long quiet period.
- **Suggestion:** Document typical event density per device type, or expose a "zone occupied" event.

## 5. Bedrock returns "Operation not allowed" on a new account, even after upgrading
- **Task:** Call Amazon Nova Lite through the Bedrock Converse API for the daily progress note.
- **Steps:** Created an IAM user with `bedrock:InvokeModel` on the `us.` and `apac.` Nova Lite inference profiles and the foundation model. Tried `us.amazon.nova-lite-v1:0` (us-east-1, us-west-2), `amazon.nova-lite-v1:0` (us-east-1) and `apac.amazon.nova-lite-v1:0` (ap-south-1). Upgraded from the Free plan to the Paid plan and retried for several minutes. Also tried the Bedrock console playground.
- **Expected:** A model reply. The Model access page says serverless models are enabled automatically on first use.
- **Actual:** `ValidationException: Operation not allowed` in every region, from the SDK and from the console playground. IAM errors (AccessDenied) went away once the policy was right, so the block is account-level. The message doesn't say why or what to do.
- **Severity:** High (blocks the core AI feature; no self-service fix found).
- **Workaround:** CrewLog falls back to an offline summary whenever Bedrock fails, so the app keeps working. The demo is recorded with `AI_PROVIDER=offline`.
- **Suggestion:** Return an actionable error (for example "Account not yet eligible for Bedrock: reason / next step"), and say on the Free plan page exactly which Bedrock calls are blocked (cross-Region inference profiles).

## 6. Feature requests
- **Important:** Webhook test-delivery from the portal (see #1).
- **Important:** `sub_type` reference table in one place (human, vehicle, package_delivery, other_motion) with examples.
- **Nice-to-have:** Python SDK published by Ring (currently "no official Ring Partner SDK").
