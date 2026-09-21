# AI Camera Project Memory

Last updated: 2026-09-21 (Asia/Kuwait)

## Purpose

This file is the compact working memory for the AI food-safety surveillance project. It records verified implementation state, agreed boundaries, unresolved risks, and the next planning decisions. `PROGRESS.md` remains the detailed chronological verification log, while `PLAN.md` remains the approved product architecture.

## Client objective

The client is an airline food-management and preparation operation in Kuwait. The requested scope is:

- Hygiene and PPE monitoring with alerts and evidence.
- Food-preparation stage timing.
- Staff movement and activity visibility.
- Continuous temperature monitoring and excursions.
- Vision-assisted inventory movements.
- Reports, audit evidence, and at least one-year retention.
- Future Oracle ERP integration.

The immediate milestone is a controlled client demonstration on Thursday, 2026-09-24. It is a working pilot demonstration, not production certification.

## Current implementation

The latest recorded full verification is dated 2026-09-04 in `PROGRESS.md`. The repository was clean when inspected on 2026-09-21, but the full test suite has not been rerun during the current discussion.

- Next.js/TypeScript enterprise dashboard and Python edge service run locally.
- Camera adapters support macOS cameras, RTSP, and a labelled prerecorded fallback.
- Person localization uses YOLO11 pose/keypoints with ByteTrack.
- Employee identity is optional and uses ArUco badges; future access-control integration is allowed.
- PPE assessment continues for an `Unidentified staff member`.
- Current PPE verification is a controlled-scene colour/shape system: blue mask and red gloves, with landmark-derived face/hand regions.
- PPE states are `not_visible`, `checking`, `detected`, `missing`, and `unavailable`.
- Fifteen-frame/twelve-observation smoothing, three-second violation persistence, five-second recovery, deduplication, evidence, and review status are implemented.
- Process timing uses tagged trays and configured zones.
- Inventory uses tagged products crossing calibrated boundaries.
- Temperature is visibly simulated; serial and MQTT adapters exist for later approved sensors.
- Local SQLite, snapshots/clips, retention dates, reports, incidents, CSV/PDF exports, and an offline UUID queue exist.
- Optional cloud, LiveKit, Supabase, Vercel, Oracle, production sensors, and production camera validation are not activated.
- Facial recognition, camera audio recording, and automatic appliance control are excluded.

## Accuracy finding

The current PPE verifier is not a trained general-purpose PPE classifier. It checks configured colours and connected shapes inside pose-derived regions. This can work in a controlled demonstration but is sensitive to lighting, camera angle, occlusion, clothing/background colours, PPE geometry, and landmark quality.

An LLM API will not make per-frame tracking faster. Local processing is approximately 0.1 second per processed frame in prior verification, while a cloud vision review will normally take roughly 1-5 seconds and may take longer on poor connectivity. Therefore cloud AI must not process every frame or block the live pipeline.

No universal or production 100% accuracy claim is permitted. The immediate quality target is repeatable performance for the agreed controlled scenarios. Production accuracy requires consented site footage, annotation, a trained/licensed PPE model, camera validation, calibrated thresholds, held-out evaluation, and formal client acceptance.

## Agreed AI architecture

Use an edge-first, cloud-assisted design:

1. Local computer vision remains responsible for person detection, tracking, pose, zone transitions, and real-time event candidates.
2. Replace the colour-only PPE decision path with a trained PPE model when an adequate labelled dataset is available.
3. Add a provider-neutral `VisionVerifier` for selected uncertain face, left-hand, right-hand, head, or torso crops only.
4. The cloud vision response must be structured as `present`, `missing`, or `uncertain`, with image-quality information and a reason.
5. Local high-confidence violations may alert immediately. Medium-confidence observations may request a second opinion. Model disagreement becomes `Needs review`; the cloud result must not silently erase local evidence.
6. API failure, timeout, rate limit, or internet loss must never stop local monitoring.
7. Temperature values come only from a calibrated sensor or the visibly labelled simulator, never from an LLM.
8. Employee identity remains badge/access-control based. Do not introduce facial recognition.

## Agreed dashboard agent

Add a limited **AI Operations Copilot**, not an autonomous camera controller. Initial actions:

- `Review current PPE`: request a second opinion for selected uncertain crops.
- `Explain latest alert`: summarize the event, measurements, evidence, and uncertainty.
- `Generate shift summary`: summarize PPE, process, inventory, and temperature records.

Required interface states:

- `Analyzing`
- `AI review complete`
- `Needs human review`
- `Cloud unavailable - local monitoring continues`

The agent starts read-only. It may not delete evidence, dismiss incidents, identify faces, control equipment, discipline employees, or write to Oracle. Future actions require allowlisted tools, role-based authorization, explicit confirmation, idempotency, and an audit trail.

## Thursday demo recommendation

Prioritize reliability over feature breadth:

1. Reproduce current mask/glove false positives and false negatives using the exact meeting camera, lighting, blue mask, and red gloves.
2. Change ambiguous or invisible regions to `Not visible` or `Needs review`, never an invented detected/missing result.
3. Capture representative examples for mask on/off, left/right gloves on/off, hidden hands, hidden face, and poor lighting.
4. Add the AI Operations Copilot and selective cloud review only after the provider and image-processing permission are confirmed.
5. Keep all cloud review asynchronous so the live camera remains responsive.
6. Run the six physical PPE scenarios five times each. Use the live PPE sequence only after 30/30 controlled results on the exact setup.
7. Keep the labelled prerecorded fallback ready and disclose it if used.
8. Demonstrate other scope honestly: tagged process/inventory, simulated temperature, local evidence/reports, optional identity, and Oracle readiness rather than a live Oracle connection.

## Security requirements for the API key

- Never place the key in browser code, chat screenshots, Git history, logs, or the public repository.
- Store it in an ignored edge `.env` file or an approved secret store/macOS Keychain.
- Use timeouts, retries, rate limits, a circuit breaker, request deduplication, and a cost ceiling.
- Send minimized crops rather than full continuous video whenever possible.
- Obtain client approval before sending employee imagery to a cloud provider.
- Confirm provider data-retention, training, residency, and security terms before production use.

## Decisions required before implementation

1. Which multimodal AI provider and API key will be used?
2. Is cloud processing of cropped employee imagery permitted for the demonstration?
3. Is the Thursday demo allowed to depend on internet access, or must cloud review be optional only?
4. Should the first copilot version include all three agreed actions or PPE review only?
5. What exact camera, mask, gloves, lighting, and network will be used in the meeting?

## Next planning step

After the five decisions above, produce a short implementation plan divided into:

- Thursday-critical work.
- Post-demo accuracy/model-training work.
- Production deployment and client-discovery work.

Do not modify the application until that plan is approved.
