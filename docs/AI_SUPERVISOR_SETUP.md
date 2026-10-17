# AI Operations Supervisor — Secure Local Setup

## Current phase

Phases 4 and 5 add seven source-grounded operational interpretations plus a fail-closed client-demo preflight. Local computer vision, tags, sensor records, timestamps, event status, and operator review remain authoritative. AI is advisory and read-only.

The supervisor can explain the latest alert, interpret a process run, analyze the latest inventory movement, review cold-chain data, show the next approved SOP step, correlate current operations, and generate a shift summary. The browser cannot submit operational facts for these actions. The edge service selects exact local records, sends only those bounded facts, and replaces model-supplied provenance with server-controlled source references.

## Configure OpenAI

1. Copy `services/edge/.env.example` to the ignored `services/edge/.env` file if it does not already exist.
2. Add the key only to that local file:

   ```text
   OPENAI_API_KEY=your-key-here
   ```

3. Keep the default model unless an approved account-specific override is required:

   ```text
   OPENAI_MODEL=gpt-5.6-terra
   ```

Never place the key in the dashboard, source code, screenshots, Git, client documents, or chat messages. The edge service sends requests with `store: false`, strict structured outputs, an eight-second timeout, and one bounded network retry.

Official references:

- [GPT-5.6 Terra model](https://developers.openai.com/api/docs/models/gpt-5.6-terra)
- [Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create)

## Local API

### Provider status

```bash
curl http://127.0.0.1:8787/api/ai/status
```

The response reports configuration, model, queue depth, last success/failure, and circuit-breaker state. It never returns the API key.

### Create a bounded smoke job

```bash
curl -X POST http://127.0.0.1:8787/api/ai/jobs \
  -H 'Content-Type: application/json' \
  -d '{"action":"provider_smoke","sourceRecordIds":["health-local"],"facts":{"purpose":"configuration check"}}'
```

### Read a job

```bash
curl http://127.0.0.1:8787/api/ai/jobs/JOB_ID
```

Job states are `queued`, `analyzing`, `completed`, `needs_review`, `unavailable`, and `failed`.

The generic job endpoint enables only `provider_smoke`. It never accepts camera images from a browser or API client.

### Review current PPE

```bash
curl -X POST http://127.0.0.1:8787/api/ai/ppe/review
```

This specialized endpoint does not accept an image body. It asks the edge pipeline to use the active track's server-selected in-memory observations. It returns `409` when no visible stable region has three fresh observations. The dashboard exposes the same action as **Review current PPE** and also allows one deduplicated automatic review after a stable local PPE state change.

### Operations supervisor

```bash
curl http://127.0.0.1:8787/api/ai/features
curl -X POST http://127.0.0.1:8787/api/ai/actions/explain_latest_alert
```

The action endpoint is release-gated. It returns `409` until configuration, automated tests, grounded fixtures, a live smoke test, and the current readiness window all pass. Each action has an independent kill switch. Missing records produce `Insufficient operational evidence` without asking the model to invent an answer.

Open the operator workspace at `http://localhost:3000/ai-supervisor`.

### Client demo preflight

```bash
curl http://127.0.0.1:8787/api/preflight
```

Open `http://localhost:3000/preflight` to review camera permission/source, frame freshness, FPS, lighting/framing, PPE self-test, evidence storage, provider status, live smoke freshness, browser sound, clean ledger, hotspot, 30/30 PPE acceptance, camera soak, rehearsal, fallback video, recovery material, and every independent AI action gate.

## Safety behavior

- The worker queue is separate from the camera processing thread.
- The queue is bounded and accepts at most six jobs per minute.
- Repeated failures open a temporary circuit breaker.
- Duplicate requests reuse the recent job UUID.
- Request facts are held only in memory while a job is queued or running.
- Submitted image bytes are passed from memory and are not written to SQLite or disk.
- Durable records contain source references, structured results, latency, failure state, timestamps, and a one-year retention date.
- The generic endpoint rejects image, frame, crop, credential, token, and secret fields. The PPE endpoint accepts no client-supplied image body.
- Lower-face, left-hand, and right-hand contact sheets require three fresh observations, acceptable lighting, landmark visibility, and a stable local decision.
- Hidden anatomy is never submitted and can never become an AI-generated violation.
- Contact-sheet bytes are removed from memory after the job and are never written to SQLite, evidence storage, or disk.
- `Two-model agreement` is shown only when every submitted region agrees and image quality is adequate. All other results are `Needs human review`.
- Completed review IDs may be appended to related event metadata; the original event measurements and evidence remain unchanged.
- Provider failure never dismisses evidence, changes measurements, controls equipment, identifies faces, or interrupts local monitoring.
- Operations prompts cannot be supplied from the browser; action facts are assembled from local server records.
- Exact counts, measurements, timestamps, directions, thresholds, and source labels are returned separately as deterministic local facts. AI supplies narrative only.
- Every operational result is labelled `AI-assisted`, retains source record IDs, and is advisory.
- AI cannot identify faces or demographics, evaluate or discipline employees, alter an SOP, resolve an incident, control equipment, or write to Oracle.
- Unverified or expired actions remain disabled in the client interface. Test stubs are never displayed as live AI.

## Remaining acceptance gates

The real provider smoke request has succeeded with the configured account and `gpt-5.6-terra`. Phase 4 and Phase 5 code and automated checks are implemented, but all seven client-facing actions intentionally remain pending until their live action smoke tests and current readiness records pass. The exact meeting camera still requires a measured FPS comparison, the 30-run controlled PPE matrix, operator review, camera soak, recovery-package verification, and two final rehearsals. The preflight screen must remain blocked until those checks are recorded.
