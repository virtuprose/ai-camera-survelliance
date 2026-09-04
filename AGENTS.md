# AI Food-Safety Demo — Agent Instructions

## Product boundary

- Build a controlled single-camera demonstration, not a production safety certification.
- Do not implement facial recognition or infer sensitive personal characteristics.
- Employee identity must come from an ArUco badge or a future access-control adapter.
- Oracle ERP, automatic appliance control, and multi-camera handoff are out of scope.
- Simulated inputs must always be labelled `Simulated` in the API, interface, exports, and evidence.
- Never describe model output as 100% accurate. Keep confidence, source, and review status on every event.

## Engineering rules

- The edge service must remain camera-source agnostic: macOS camera, RTSP, and video file.
- Cloud integrations must be optional. Local camera, events, evidence, reports, and demo controls must work without credentials.
- Store secrets only in ignored `.env` files; keep complete `.env.example` files.
- Do not record audio. Evidence is limited to event snapshots and short clips.
- Keep AI/model code behind replaceable interfaces and document model/data licences.
- Preserve an offline event queue and make cloud synchronization idempotent by event UUID.
- Use UTC in storage and render Asia/Kuwait time in the interface.

## UI rules

- The live camera is the dominant workspace; avoid generic card-grid dashboards.
- Use semantic design tokens and accessible status labels. Never rely on colour alone.
- Implement loading, empty, offline, permission-denied, low-confidence, simulated, and recovery states.
- Meet WCAG 2.2 AA expectations and verify 375, 768, 1024, and 1440 px viewports.

## Verification and progress

- Before handoff, run typecheck, lint, unit tests, API tests, browser tests, accessibility checks, and rendered screenshot review.
- Update `PROGRESS.md` after each milestone with the date, commands run, verified result, blockers, and next action.
- Do not mark a capability complete when it is only scaffolded, mocked, or credential-blocked.
