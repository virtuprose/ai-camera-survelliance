# Contributing

## Setup

Follow the root [README](README.md) and use the pinned JavaScript and Python lockfiles.

## Product boundaries

- Keep PPE evaluation independent of employee identity.
- Do not add facial recognition or infer sensitive characteristics.
- Do not capture camera audio.
- Label simulated inputs in the data model and interface.
- Preserve confidence, source, review status, evidence, and retention metadata.
- Keep cloud services optional and local workflows functional without credentials.
- Do not describe controlled-scene results as production accuracy.

## Before opening a change

```bash
bun run lint
bun run typecheck
bun run test
bun run edge:test
bun run build
bun run test:e2e
bun run repo:audit
```

Camera and inference changes also require the documented physical scenarios, camera soak, and rehearsal checks. Update the relevant architecture, setup, model-card, and acceptance documentation when behavior changes.

## Data safety

Never commit credentials, personal photos, camera evidence, local databases, model weights, customer material, or client presentation files. Use synthetic fixtures and neutral sample operators in public tests and documentation.
