# ORVIA AI Surveillance — Enterprise Demo Upgrade

## Objective

Deliver an enterprise-grade, single-camera food-preparation demonstration that is fully usable in local mode and is honest about live, simulated, planned, and not-connected capabilities. Add a read-only AI Operations Supervisor that reviews uncertain vision, interprets operational exceptions, explains evidence, guides operators through approved SOPs, and summarizes the shift without controlling equipment or replacing deterministic safety rules. The demo proves operational workflows; it is not regulatory certification or production accuracy acceptance.

## Operating model

- Main Production Facility: Kitchen 01 is live; Receiving, Cold Storage, and Inventory Store are interactive simulated workspaces.
- Secondary Facility: planned, disabled, and contains no operational data.
- Demo views: Executive, QA Supervisor, Operations, and IT. These change navigation emphasis only and are always labelled `View as · Demo`; they are not authorization roles.
- Shift and timestamps: Day Shift, Asia/Kuwait display time, UTC storage.

## Application architecture

```text
Camera / RTSP / video file
  -> Python edge service
     -> replaceable detection + tracking adapters
     -> Person-localized PPE (identity optional)
     -> ArUco employee / tray / inventory identity
     -> SQLite event, process, evidence, incident, and audit domain
     -> bounded AI job worker
        -> selective PPE region review
        -> process and inventory exception interpretation
        -> evidence-grounded explanations, SOP guidance, and summaries
     -> optional idempotent cloud synchronization

Next.js dashboard
  -> local edge APIs (mandatory path)
  -> AI Operations Supervisor (optional, read-only, asynchronous)
  -> optional private cloud data/video adapters
```

Primary routes:

- `/` Command Center
- `/live` Live Operations
- `/food-safety` Food Safety & PPE
- `/processes` Process Assurance
- `/staff` Staff Visibility
- `/cold-chain` Cold Chain
- `/inventory` Inventory
- `/incidents` Incidents & Evidence
- `/reports` Reports & Audit
- `/platform` Platform
- `/events` and `/system` redirect to their enterprise replacements.

## Enterprise domain

- Sites, workspaces, shifts, and explicit live/simulated/planned modes.
- Determinate PPE observations; unknown observations are retained but excluded from the compliance denominator.
- PPE evaluation and violations continue for an `Unidentified staff member`; ArUco or future access-control identity enriches but never gates PPE monitoring.
- Versioned SOP templates and stages linked to process runs.
- Incidents generated idempotently from qualifying PPE, temperature, process, and inventory events.
- Lifecycle: Open -> Investigating -> Action required -> Resolved -> Closed.
- Ownership is required before investigation. Root cause and corrective action are required before resolution.
- SLA due times, evidence, source mode, retention date, activity history, and immutable audit records.
- Oracle readiness contract is visible as `Not connected`; proposed mappings never make external requests.

## Reliability hardening

- The PPE verifier rejects total-colour-only positives and requires face/hand visibility plus a central connected controlled-PPE shape. Its bare-face, peripheral-blue, and central-positive decisions run as an automatic startup self-test; failure disables PPE findings.
- Mask and each glove retain separate visibility, checking, verified, and missing states. Unknown anatomy is not scored, and identity remains optional.
- Process and inventory transitions require stable marker dwell; inventory uses line hysteresis and cooldown to reject jitter and duplicate crossings.
- Temperature uses a labelled simulator for the client demo and fail-closed serial/MQTT adapters for later calibrated hardware.
- Local SQLite and evidence directories perform automatic write checks. Snapshots and clips retain separate hashes and byte counts locally and in the proposed cloud schema.
- Staff activity is limited to supported zone/SOP context. AI may interpret bounded evidence and describe a likely process or inventory exception, but it must label uncertainty and cannot create unsupported activity facts. Production action recognition and multi-camera handoff require site data and production discovery.

## AI Operations Supervisor — Thursday scope

Implement the complete supervisor in the same delivery rather than deferring operational capabilities to a later phase.

### Responsibilities

- **PPE assurance:** review selected lower-face, left-hand, and right-hand crops when local PPE is stable, uncertain, or manually submitted; return `present`, `missing`, or `uncertain` for each visible item.
- **Process interpretation:** explain a tagged process start, completion, overtime condition, or ambiguous zone transition using the retained process state, timestamps, configured SOP, and selected evidence. It does not invent an unobserved food-handling action.
- **Inventory exception analysis:** explain stock-in/out movements, duplicate or conflicting observations, and count variances using tagged movement history and retained evidence. The tagged ledger remains the source of truth for the demo.
- **Cold-chain reasoning:** summarize simulated or sensor-derived excursions, duration, recovery, and threshold context. The AI never estimates or modifies a temperature reading.
- **SOP guidance:** give concise next-step guidance from the versioned local SOP and incident state. Guidance is advisory and cannot resolve an incident automatically.
- **Cross-system anomaly review:** correlate PPE, process, inventory, temperature, camera health, and evidence freshness to highlight a possible operational issue, while identifying the exact source records used.
- **Alert explanation:** translate technical confidence, visibility, persistence, zone, timestamp, and evidence metadata into clear operator language.
- **Shift summary:** produce a grounded executive/QA summary with counts, exceptions, unresolved incidents, and explicit real/simulated boundaries.

### OpenAI integration

- Use a provider-neutral `VisionVerifier` and `OperationsReasoner`; OpenAI is the first configured provider.
- Use the Responses API with strict structured outputs, `store: false`, high-detail image input for PPE crops, and bounded JSON input for non-visual analysis.
- Default model is `gpt-5.6-terra` with low reasoning effort; expose an environment override and fail visibly if the configured model is unavailable. Never silently switch providers or models.
- Store the key only in the ignored edge `.env`; expose placeholders through `.env.example` and never send the key to the dashboard.
- Use an eight-second total timeout, one bounded network retry, six jobs per minute, a small local worker queue, and a circuit breaker after repeated failures.
- Send only temporary crops from the consenting presenter. Do not upload the continuous stream, full evidence clips, employee profiles, badge data, or full-frame images.
- Do not retain submitted crops after the request. Retain only crop hashes/dimensions, job provenance, structured result, latency, and audit timestamps.
- OpenAI or internet failure never interrupts local detection, evidence, reports, process timing, inventory, or temperature monitoring.

### Decision policy

- Local computer vision, tags, sensors, and deterministic timing remain the authoritative measurement layer.
- A stable local PPE result may be reviewed automatically once; the operator can also request a review manually.
- Local and AI agreement is shown as `Two-model agreement` without presenting it as certification.
- Disagreement becomes `Needs human review`; AI cannot dismiss or overwrite the local event.
- `Not visible` and `Unavailable` can never be converted into a missing-PPE violation by AI.
- AI must not generate a combined or invented confidence percentage. Local confidence and AI decision provenance remain separate.
- Every AI statement must cite the event, process run, transaction, temperature reading, SOP stage, or health record that supports it. Unsupported questions return `Insufficient operational evidence`.

### Interfaces and audit records

- `GET /api/ai/status`: provider availability, model, queue depth, last successful job, and failure state without exposing credentials.
- `POST /api/ai/jobs`: create `review_ppe`, `explain_event`, `interpret_process`, `analyze_inventory`, `review_cold_chain`, `sop_guidance`, `cross_system_review`, or `shift_summary` jobs.
- `GET /api/ai/jobs/{jobId}`: return queued, analyzing, completed, needs-review, unavailable, or failed state and the structured result.
- Persist AI jobs in an additive SQLite table with UUID, action, linked source records, status, model, prompt version, local decision, AI decision, rationale, crop hashes, latency, timestamps, and 365-day retention.
- Append only the AI review ID and agreement state to event metadata. Preserve original evidence, confidence, event status, and audit history.

### Dashboard experience

- Add a compact **AI Operations Supervisor** panel below the live detection rail so the camera remains the dominant workspace; open the detailed result in a responsive Sheet on smaller screens.
- Present task-oriented actions: `Review current PPE`, `Explain latest alert`, `Interpret process`, `Analyze inventory`, `Review cold chain`, `Show SOP guidance`, `Review operations`, and `Generate shift summary`.
- Display `Ready`, `Analyzing`, `AI review complete`, `Needs human review`, `Insufficient evidence`, and `Cloud unavailable — local monitoring continues` with icon and text, never colour alone.
- Show local measurement and AI interpretation separately, including source records and freshness.
- Label outputs `AI-assisted`; do not display provider branding in the client-facing interface.
- Reuse the existing semantic tokens and shadcn primitives. Use blue for informational AI state, amber for uncertainty, red only for active measured violations, and green only for confirmed local compliance.
- Announce completion/failure through an accessible live region; preserve keyboard navigation, visible focus, reduced motion, mobile focus trapping, and safe retry.

## Demo controls and safety

- Tools can create simulated PPE, temperature, process-overtime, stock movement, inventory-variance, and guided enterprise exception scenarios.
- Reset requires the exact phrase `RESET SIMULATED DATA`, removes only simulated records, restores five tagged SKUs, and creates one labelled 150-second baseline process run.
- Optional browser violation chime starts muted and never replaces visual alerts.
- The AI Operations Supervisor is read-only. It cannot delete or dismiss evidence, resolve incidents, identify faces, discipline employees, change thresholds/SOPs, control equipment, or write to Oracle.
- No facial recognition, demographic inference, camera audio, automatic appliance control, multi-camera handoff, autonomous LLM control, firmware, or live Oracle connection.

## Thursday client-demo flow

1. Start `bun run local`; confirm MacBook camera, fresh frame, at least 6 processed FPS, storage, PPE self-test, and AI service availability.
2. Enter without a badge and show that PPE remains active for `Unidentified staff member`.
3. Show bare face and visible bare hands; request PPE review and present local/AI evidence separately.
4. Wear the blue mask and red gloves; repeat the review and show agreement or an honest review state.
5. Remove one required item; show persistence, one deduplicated alert, evidence, optional chime, AI explanation, and operator review.
6. Start/complete the tagged process and ask the supervisor to interpret the retained timing and SOP state.
7. Trigger one tagged inventory movement/variance and show the supervisor's source-grounded exception analysis.
8. Raise and recover the visibly simulated temperature excursion and show cold-chain reasoning without presenting it as sensor hardware.
9. Run cross-system review and shift summary; verify all counts match the retained ledger.
10. Show incidents, reports, retention, offline resilience, and Oracle readiness; then reset simulated records to a clean state.
11. Keep a verified prerecorded fallback ready and identify it honestly if any live gate fails.

## Acceptance criteria

- Every primary route is functional in local mode without cloud credentials.
- AI is optional to runtime operation; disabling the key or internet preserves every local capability and displays a clear unavailable state.
- Camera source remains swappable between macOS, RTSP, and prerecorded fallback.
- Simulated and planned states are unmistakable in the UI, API, reports, and exports.
- Incident transitions are validated by both API and interface.
- Audit PDF and CSV exports are downloadable and source-aware.
- Legacy routes redirect safely.
- Lint, typecheck, frontend unit tests, edge/API tests, Python lint, production build, Playwright flows, and axe WCAG 2.2 AA checks pass.
- Rendered views are reviewed at 375, 768, 1024, and 1440 px with no page-level horizontal overflow.
- Final hardware, cloud activation, general PPE accuracy acceptance, and Oracle connection remain explicit deployment gates.
- The archived bare-face false-positive frame must evaluate as mask missing, and the portable peripheral-blue regression must remain green.
- The exact client camera must pass a ten-minute soak; live PPE requires 30/30 controlled physical scenarios and one uninterrupted rehearsal. A failed physical gate switches the presenter to the labelled fallback.
- The 30-run matrix covers bare face/hidden hands, bare face/visible hands, blue mask/bare hands, blue mask/red gloves, hidden face/visible hands, and visible face/hidden hands. Invisible anatomy must never create a violation.
- AI tests cover structured parsing, grounding, disagreement, insufficient evidence, missing key, timeout, refusal, malformed response, rate limiting, deduplication, retry, circuit breaker, offline continuation, and non-retention of crops.
- A live OpenAI smoke test must complete each supervisor action once; deterministic provider stubs cover automated tests without consuming the real API.
- AI jobs complete within eight seconds or fail safely; running a job must not reduce local processed FPS by more than 10%, produce stale frames above two seconds, or create duplicate events.
- Ten grounded summary fixtures must reproduce exact ledger counts and source labels with no invented employee identity, process action, stock quantity, temperature reading, or incident status.
- Playwright/axe verifies the full supervisor flow, loading/success/review/offline states, keyboard operation, live-region announcements, mobile Sheet behavior, and responsive rendering at 375, 768, 1024, and 1440 px.
- Final verification runs `bun run lint`, `bun run typecheck`, `bun run test`, `bun run edge:test`, `bun run build`, `bun run test:e2e`, `bun run camera:soak`, `bun run demo:rehearse`, and `bun run repo:audit`.
