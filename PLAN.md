# ORVIA AI Surveillance — Enterprise Demo Upgrade

## Objective

Deliver an enterprise-grade, single-camera food-preparation demonstration that is fully usable in local mode and is honest about live, simulated, planned, and not-connected capabilities. The demo proves operational workflows; it is not regulatory certification or production accuracy acceptance.

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
     -> optional idempotent cloud synchronization

Next.js dashboard
  -> local edge APIs (mandatory path)
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
- Staff activity is limited to supported zone/SOP context. Detailed action recognition and multi-camera handoff require site data and production discovery.

## Demo controls and safety

- Tools can create simulated PPE, temperature, process-overtime, stock movement, inventory-variance, and guided enterprise exception scenarios.
- Reset requires the exact phrase `RESET SIMULATED DATA`, removes only simulated records, restores five tagged SKUs, and creates one labelled 150-second baseline process run.
- Optional browser violation chime starts muted and never replaces visual alerts.
- No facial recognition, camera audio, automatic appliance control, multi-camera handoff, LLM control, firmware, or live Oracle connection.

## Acceptance criteria

- Every primary route is functional in local mode without cloud credentials.
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
