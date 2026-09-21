# Phase 1 — Baseline Audit and PPE Reliability

Date: 2026-09-21 (Asia/Kuwait)

## Decision

Phase 1 is **technically verified but not yet approval-ready**. Automated PPE regressions, storage integrity, evidence behavior, dashboard checks, and the FaceTime camera pipeline pass. The remaining approval gate is one operator-assisted physical run of each of the six scenarios using the exact blue mask, red gloves, lighting, camera position, and presenter.

Phase 2 must not begin until the physical run is recorded and Muhammad Zaid explicitly approves Phase 1.

## Preserved baseline

- Original runtime store: 159 events, 1,250 PPE observations, 74 incidents, 159 snapshots, and 159 clips.
- Recoverable backup: `services/edge/data/backups/phase1-baseline-20260921-159-events`.
- SQLite integrity: `ok`.
- SHA-256 manifest: 319 of 319 archived files verified, zero failures.
- The active `services/edge/data/client-demo` store was recreated from a clean directory.

## Findings and corrections

### 1. Known mask false positive

Cause: the original prototype accepted broad blue-pixel coverage inside an estimated face rectangle. Blue clothing or background could overlap the region and be mistaken for a mask.

Current control: landmark-derived lower-face region, connected-component shape checks, centre coverage, horizontal and vertical span, colour quality, pose visibility, low-light gating, and 15-frame/12-observation consensus. A regression confirms peripheral blue remains `missing` rather than `detected`.

### 2. Known blue-mask false negative

Cause: a real surgical mask had strong blue coverage but its lower-face component centroid was 0.3894 from the expected centre, just beyond the former 0.38 limit.

Current control: the mask-specific offset allowance is 0.50 while independent centre, component, span, vertical coverage, and quality gates remain. The exact archived measurements are covered by a regression test.

### 3. Bare hand versus red glove

Cause addressed: red hue alone can include warm skin tones.

Current control: the red-glove profile requires saturation/value limits, a strong red-channel lead, a central connected component, shape span, centre proximity, and quality. Synthetic red-glove positives and bare-hand negatives pass.

### 4. Hidden anatomy and low light

Current control: face, left wrist, and right wrist visibility are independent prerequisites. Hidden or poorly lit regions return `not_visible`; they do not produce a missing-PPE violation. If pose inference is unavailable, PPE is `unavailable` rather than guessed.

### 5. Evidence could contradict stabilized state

Archived audit found two contradictory records: one `Right glove not detected` event whose current-frame measurement said the glove shape was verified, and one compliance-restored event whose current-frame measurement said no glove shape was verified.

Cause: rolling consensus correctly retained the stable state through a one-frame transition, but event evidence used measurements and the snapshot from that contrary current frame.

Correction: every PPE item now exposes its frame-level `observationState` separately from its stabilized `state`. A violation or recovery can be retained only when the current frame agrees with the stabilized decision. The event metadata records both values. Regression tests cover both violation and recovery paths.

## Automated scenario matrix

All six controlled local-state scenarios pass in the deterministic pose/colour fixture:

| Scenario | Expected mask | Expected left glove | Expected right glove | Result |
| --- | --- | --- | --- | --- |
| Bare face, hands hidden | Missing | Not visible | Not visible | Pass |
| Bare face, bare hands visible | Missing | Missing | Missing | Pass |
| Blue mask, bare hands visible | Detected | Missing | Missing | Pass |
| Blue mask and red gloves | Detected | Detected | Detected | Pass |
| Face hidden, hands visible | Not visible | Missing | Missing | Pass |
| Face visible, hands hidden | Missing | Not visible | Not visible | Pass |

These fixtures verify logic and regression behavior; they do not replace the physical acceptance run or establish production accuracy.

## Verification evidence

- `uv run ruff check foodsafe_edge tests scripts` — pass.
- `uv run pytest` — 59 passed, including continuous badge-occlusion retention, temporary track-loss grace, safe expiry, reset, evidence attribution, transient-state promotion, conflicting-badge rejection, and one-badge/one-track isolation.
- Focused PPE matrix/regressions — 10 passed.
- `bun run lint` — pass.
- `bun run typecheck` — pass.
- `bun run test` — 2 files, 5 tests passed.
- `bun run build` — pass, 16 application routes.
- FaceTime baseline soak — 600 seconds, 1,187 checks, 9.2–10.0 processed FPS, zero stale frames, duplicates, or incomplete evidence.
- Corrected-build FaceTime soak — 600 seconds, 1,187 checks, 8.5–9.9 processed FPS, zero stale frames, duplicates, or incomplete evidence.
- Runtime PPE self-test — pass.
- Runtime camera, stream, and local storage — online.
- Clean soak ledger before correction — zero events, zero incidents, zero process runs.
- `bun run test:e2e` — 17 Playwright/axe tests passed; tested routes, identity-independent PPE, visible track-session identity retention, camera selection, and 375/768/1024/1440 px layouts.
- After verification, ports 3000 and 8787 are stopped and the active client-demo directory is clean.

## Remaining Phase 1 gate

Run each physical scenario once while the exact meeting setup is visible to the camera. Record final item states, landmark visibility, lighting, processed FPS, event order, deduplication, evidence snapshot, completed clip, and recovery. Do not adjust thresholds unless the captured measurements demonstrate a specific failure.

If any scenario fails, Phase 1 remains open and Phase 2 does not begin.
