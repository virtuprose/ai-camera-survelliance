# Detection accuracy and client acceptance

## Accuracy commitment

No camera analytics supplier can honestly guarantee universal 100% accuracy across every camera angle, kitchen, person, PPE design, occlusion, light level, and workflow. ORVIA therefore uses two separate acceptance statements:

1. **Controlled-demo repeatability:** every scripted demonstration scenario must pass 30 out of 30 runs before live PPE is used in a client meeting.
2. **Production acceptance:** accuracy is measured per client-approved scenario on held-out footage from the installed camera position. Precision, recall, false alerts per camera-hour, missed-event rate, alert latency, and evidence completeness are agreed before the pilot.

A failed or unavailable assessment is shown as `Not visible`, `Checking`, or `Unavailable`; it is never silently converted into a compliant or violation claim.

## Requirement readiness matrix

| Client requirement | Working demonstration | Automated protection | Production gate | Current status |
| --- | --- | --- | --- | --- |
| Hygiene and PPE | Person/pose tracking evaluates a controlled blue mask and each red glove independently. Identity is optional. | Verifier self-test on every service start; face/hand visibility gate; 15-frame/12-vote window; three-second persistence; five-second recovery; priority and UUID deduplication. | Approved PPE definitions, site footage and annotation, commercially approved trained detector, per-camera calibration, held-out acceptance set. | Software tests passed; live physical acceptance on the exact PPE and camera setup remains required. |
| Process timing | ArUco tray 201 starts and completes a configured stage through two camera zones. Tools provide a labelled simulated fallback. | Stable 0.5-second marker dwell prevents one-frame transitions; timestamps are recorded at the edge. | Client SOPs, stage definitions, camera coverage, exception rules, tag/object method, user acceptance. | Transition tests passed; physical tray run must be rehearsed. |
| Staff visibility | Person tracks, entry/zone activity, optional ArUco employee badge, and short badge-occlusion persistence. | PPE never waits for identity; an expired badge binding returns to `Unidentified staff member`; no facial recognition. | Access-control or badge integration, employee governance, privacy review, camera overlap and multi-camera identity policy. | Single-camera software path tested; site/multi-camera design pending. |
| Temperature | Clearly labelled simulator plus serial and MQTT sensor adapters. | Stale/unavailable sensor fails visibly; alerts and recovery occur only on state transitions. | Selected probe/logger, calibration certificate, placement, sampling interval, network protocol, thresholds and escalation contacts. | Simulator and adapter parsers tested; no physical sensor has been connected or calibrated. |
| Inventory | Tagged products 301-305 cross a configured stock boundary and create stock-in/out evidence. | Direction hysteresis, stable dwell, cooldown and transaction ledger prevent boundary jitter from double-counting. | Inventory master, pack/unit rules, camera coverage, reconciliation tolerance, Oracle transaction semantics, item-specific vision where tags are not acceptable. | Transition tests passed; physical marker run must be rehearsed. |
| Evidence and one-year retention | Local event rows receive UUIDs, UTC timestamps, review state, 365-day retention dates, snapshots/clips and SHA-256 file metadata. | Evidence-write failures are recorded; local queue uses event UUIDs for idempotent synchronization. | Client-owned encrypted storage, RLS/RBAC, key management, backups/restore test, legal hold/deletion policy, capacity plan and security approval. | Local implementation tested; production cloud/security acceptance pending client credentials. |
| Oracle ERP | Proposed employee, item, inventory transaction and process-run mapping is visible in Platform. | No unapproved request is sent and no credential is embedded. | Oracle product/version, available APIs, integration owner, service account, network route, test environment, field mapping, retry/reconciliation and sign-off. | Not connected; technical discovery dependency. |

## PPE false-positive controls

The original prototype counted total blue pixels inside a broad face rectangle. That allowed unrelated blue background objects to produce a false mask result. Verifier v2 now requires all of the following:

- a reliably visible face from pose landmarks;
- a central, connected blue component in the expected mask region;
- minimum component size and horizontal span;
- maximum displacement from the face-region centre;
- sufficient lighting and a stable multi-frame decision.

The archived bare-face frame that previously reported a mask now evaluates as `missing`. A replay of all 12 applicable preserved landmark-aware real-camera evidence frames produced 11 `missing`, one visibility-safe `not_visible`, and zero unexpected `detected` results. A deterministic peripheral-blue regression and an automatic startup self-test protect this failure case. This negative replay proves the known false-positive condition is controlled; it does not replace the positive/negative 30-run physical acceptance matrix. This remains a controlled-colour demonstration verifier, not the production PPE model.

## Release gates for the next live demonstration

The live camera sequence is released only when all gates pass on the exact presentation laptop and camera:

- startup reports camera/stream online, fresh frame, at least 6 processed FPS, and `PPE verifier self-test passed`;
- five repetitions of each of the six controlled PPE scenarios pass, for 30/30 total;
- mask is assessed first when the face is visible;
- hidden hands remain `Not visible`, never `Missing`;
- each sustained violation creates one event and accessible evidence;
- process tag 201 starts/completes correctly in three consecutive runs;
- inventory tag 301 records the intended direction and final count in three consecutive runs;
- simulated temperature excursion and recovery each produce one transition;
- a ten-minute camera soak has no stale period above two seconds;
- one uninterrupted 6-8 minute rehearsal succeeds;
- the prerecorded fallback and labelled Tools actions remain ready.

If a physical gate fails, use the visibly labelled fallback for that capability and do not describe it as a live inference.

## Production measurement protocol

For each camera and required rule, the client and ORVIA will approve a scenario matrix covering compliant/missing items, staff variation, occlusion, motion, lighting, cleaning cycles, background colours and representative operating peaks. A held-out test set must not be used for training or threshold tuning. The acceptance report will include confusion matrices and raw scenario counts, not only a single accuracy percentage.

The production system must also pass non-model controls: event latency, evidence integrity, offline recovery, idempotent synchronization, retention enforcement, access control, audit logs, backup/restore and Oracle reconciliation.
