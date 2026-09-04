# ORVIA AI Surveillance

Local-first AI video analytics for food-safety operations. This repository contains a controlled, single-camera demonstration of person tracking, identity-independent PPE checks, optional badge identity, process timing, inventory movement, temperature alerts, evidence, incidents, reports, and future Oracle ERP integration boundaries.

> **Important:** this is a working pilot application, not a safety certification or a claim of universal detection accuracy. The included PPE verifier is a controlled-scene prototype. Production use requires site footage, camera validation, approved model licensing, formal accuracy testing, privacy review, and stakeholder acceptance.

## Capability status

| Capability | Repository status | Demonstration boundary |
| --- | --- | --- |
| Person detection and tracking | Implemented locally | Single controlled camera; performance depends on framing and lighting |
| PPE checks | Implemented controlled prototype | Pose-gated blue mask and red glove profile; identity is not required |
| Employee identity | Optional ArUco badges | No facial recognition; future access-control adapter is documented |
| Process timing | Implemented | Tagged tray and configured start/complete zones |
| Inventory movement | Implemented | Tagged items crossing a configured stock boundary |
| Temperature monitoring | Simulated by default | Serial and MQTT adapters activate only after sensor selection and calibration |
| Evidence and incidents | Implemented locally | Silent snapshots/clips, review state, hashes, timestamps, and retention dates |
| Reports and audit exports | Implemented locally | CSV and one-page PDF exports from the loaded ledger |
| Offline operation | Implemented locally | SQLite persistence and an idempotent synchronization queue |
| Cloud services | Optional configuration | Requires deployment-owned Supabase, LiveKit, and Vercel credentials |
| Oracle ERP | Contract and mappings only | No external ERP request is enabled |

All simulated inputs and events are labelled `Simulated` in the interface and data records.

## Quick start on macOS

The currently validated local path is macOS with Apple silicon. RTSP and video-file sources are camera-adapter options for other deployment environments.

### 1. Install prerequisites

- [Bun](https://bun.sh/) 1.3 or newer
- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- FFmpeg

With Homebrew:

```bash
brew install bun python@3.12 uv ffmpeg
```

### 2. Clone and install

```bash
git clone https://github.com/virtuprose/ai-camera-survelliance.git
cd ai-camera-survelliance
bun install --frozen-lockfile
cd services/edge
uv sync --frozen
cd ../..
```

Model weights and runtime databases are intentionally not stored in Git. The first Ultralytics start may download the configured YOLO weight. Review [the model card](services/edge/MODEL_CARD.md) before any commercial deployment.

### 3. Allow the camera

Open **System Settings → Privacy & Security → Camera** and allow access for the terminal application that starts the project.

### 4. Start the complete local demo

```bash
bun run local
```

Then open [http://localhost:3000/live](http://localhost:3000/live). On macOS, `Start ORVIA Demo.command` provides the same startup flow without typing a command.

The launcher starts both services:

- Dashboard: `http://localhost:3000`
- Edge API: `http://127.0.0.1:8787`

The **Change source** menu can switch among cameras exposed by macOS, an RTSP source configured in the edge environment, and the included synthetic prerecorded fallback. A requested camera is accepted only after it supplies a fresh frame.

## Demo markers and PPE profile

Printable ArUco markers are stored in `services/edge/assets/markers/`:

- `101`: Demo Operator A (`EMP-001`)
- `102`: Demo Operator B (`EMP-002`)
- `201`: process tray `TRAY-01`
- `301`–`305`: five sample inventory items

Regenerate them with `bun run markers`.

PPE monitoring begins when a person is tracked, even if no employee badge is visible. An unidentified person is shown as **Unidentified staff member**. The current controlled profile expects a blue mask and red gloves; hidden face or hand regions remain `Not visible` and are not reported as missing.

## Architecture

```text
Camera, RTSP stream, or video file
        │
        ▼
Python edge service
  ├─ person/pose detector and tracker
  ├─ controlled PPE verifier
  ├─ ArUco badge, tray, and item markers
  ├─ process, inventory, and temperature rules
  ├─ SQLite event/evidence store
  └─ optional idempotent cloud synchronization
        │
        ▼
Next.js operations dashboard
  ├─ live operations and camera source control
  ├─ food safety, process, staff, cold-chain, and inventory views
  ├─ incidents, evidence, reports, and audit exports
  └─ platform health and Oracle integration boundary
```

See [Architecture](docs/ARCHITECTURE.md) for the service interfaces, event lifecycle, security boundary, and scale-out direction.

## Common commands

```bash
bun run local          # edge camera service and dashboard
bun run edge:fallback  # synthetic prerecorded fallback, visibly simulated
bun run lint           # dashboard lint
bun run typecheck      # TypeScript validation
bun run test           # dashboard unit tests
bun run edge:test      # Python tests
bun run build          # production dashboard build
bun run test:e2e       # starts isolated services, then runs Playwright and axe
bun run camera:soak    # 10-minute camera pipeline check
bun run demo:rehearse  # 8-minute system rehearsal
bun run repo:audit     # public-source privacy, secret, and file-size checks
```

`bun run ppe:acceptance` is an engineering repeatability report. It is not required to operate the application and does not replace physical acceptance testing on the selected camera.

## Repository layout

```text
apps/dashboard/       Next.js TypeScript operations dashboard
services/edge/        Python camera, AI/rules, evidence, and sync service
supabase/             Optional cloud schema, functions, and sample data
docs/                 Setup, architecture, runbook, accuracy, and integration docs
scripts/              Local launcher and public-release audit
PLAN.md               Product architecture and acceptance criteria
AGENTS.md             Engineering and product-boundary rules
```

Private runtime data, evidence, employee photos, credentials, model weights, internal progress notes, and client presentation files are intentionally excluded from Git.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Camera setup](docs/CAMERA_SETUP.md)
- [Local demonstration runbook](docs/DEMO_RUNBOOK.md)
- [Detection accuracy and acceptance](docs/DETECTION_ACCURACY_AND_ACCEPTANCE.md)
- [Production requirements](docs/PRODUCTION_REQUIREMENTS_AND_ARCHITECTURE.md)
- [Oracle integration contract](docs/ORACLE_INTEGRATION_CONTRACT.md)
- [Optional cloud setup](docs/CLOUD_SETUP.md)
- [Project status](docs/PROJECT_STATUS.md)
- [Security policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)

## Privacy and security

- Camera audio is not captured.
- Facial recognition is not implemented.
- Employee identity is optional and comes from a printed badge in this demo.
- Evidence is limited to event snapshots and short silent clips.
- Credentials belong only in ignored environment files.
- Local event storage and cloud identities are separated.
- Production roles, retention enforcement, encryption, access logging, and data residency must be approved during deployment design.

Report security concerns through a private channel; do not place credentials, personal footage, or vulnerability details in a public issue. See [SECURITY.md](SECURITY.md).

## Licensing and trademarks

No open-source license is currently granted by this repository. Public visibility allows the repository to be viewed and cloned, but reuse and redistribution remain subject to applicable copyright law and written permission.

Third-party packages, models, and assets retain their own licenses. In particular, the optional Ultralytics package and weights require an AGPL-3.0 compliance review or an appropriate commercial license for proprietary deployment. **ORVIA** and the ORVIA logo are trademarks of their owner; no trademark license is granted. See [NOTICE.md](NOTICE.md).
