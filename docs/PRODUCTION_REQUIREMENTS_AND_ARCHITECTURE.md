# Production requirements and architecture

This document defines the production discovery boundary for a regulated food-preparation deployment. It does not convert the single-camera controlled demonstration into a production-certified system.

## Existing surveillance coexistence

The client's existing cameras, NVR, and VMS should remain operational and under client ownership. ORVIA should consume separate **read-only** live streams so the current surveillance recording, operator stations, and retention continue unchanged.

Reuse is conditional on a representative stream test confirming:

- vendor/model, firmware and support status;
- RTSP or an approved VMS SDK/API; ONVIF discovery alone does not guarantee analytics access;
- H.264/H.265 codec, resolution, frame rate, keyframe interval and concurrent-stream capacity;
- fixed view, sufficient pixels on each required face/hand/object region, light and occlusion;
- read-only service credentials, network route, VLAN/firewall policy and NTP time;
- NVR/VMS capacity when ORVIA opens an additional stream;
- the client's cybersecurity and camera-vendor licence conditions.

Test one camera from each model/firmware group before promising reuse across all 80 cameras. Cameras that cannot provide a suitable analytical view may continue serving security while a dedicated operational camera is added for the affected workstation.

## Reference production topology

1. Existing cameras and approved temperature gateways publish live data on the client OT/video network.
2. ORVIA edge inference nodes consume read-only camera substreams and sensor messages locally.
3. Each edge node emits compact UUID events, evidence references, health telemetry and model/version metadata; raw frames do not need to leave the site unless policy explicitly allows it.
4. A local durable queue preserves events during network interruption and retries idempotently.
5. The secure platform provides RBAC, incidents, reports, retention, audit and optional mobile notifications.
6. An integration service exchanges approved records with Oracle through the client's supported API or Oracle Integration Cloud pattern. Direct database writes are excluded unless Oracle owners expressly approve them.

Sizing for 80 cameras must be benchmark-derived. Do not promise a camera-per-GPU ratio before testing the actual streams, selected model, inference resolution, required FPS and simultaneous rules. Use production GPU servers or approved edge appliances with N+1 capacity; the MacBook is a presentation device only.

## Required production hardware categories

| Category | Minimum requirement | Selection dependency |
| --- | --- | --- |
| Cameras | Fixed view, RTSP/approved VMS stream, H.264/H.265, stable exposure, adequate analytical pixel density; PoE preferred | Existing-camera survey and representative stream benchmark |
| Edge inference | Commercially supported GPU, encrypted OS/storage, dual network interfaces where required, health monitoring, UPS and N+1 capacity | Camera count, model benchmark, FPS/SLA and resiliency target |
| Temperature sensing | Calibrated industrial probe/logger, required measurement range and accuracy, traceable calibration, serial/Modbus/MQTT or approved gateway, stale-data alarm | Cold-room/food-contact location, HACCP policy, local regulation, calibration owner |
| Identity | Existing access-control event feed, privacy-approved staff badge, or camera-visible machine-readable badge | Client identity/privacy policy; no biometric identity in the current scope |
| Process/inventory tags | Durable washable tags or labels where tag-based workflow is approved | SOP, cleaning method, item packaging, distance and field of view |
| Network | Segmented VLAN, managed switching, PoE budget, bandwidth/QoS, firewall allow-list, NTP/DNS | Client IT/security architecture |
| Storage | Encrypted event/evidence store, backups, restore testing, immutable/audit controls where required | Event rate, clip duration/quality, legal hold, deletion policy and whether raw video is retained |
| Operator devices | Browser workstations and optional managed mobile devices | Role model, MDM, notification and data-residency policy |

Off-the-shelf devices should be used wherever possible. Custom firmware is not required for IP cameras or standard serial/MQTT sensors; firmware work is only needed if the client selects a custom sensor/gateway device.

## Retention scope that must be decided

“One-year retention” must be separated into:

- structured events and audit history;
- event snapshots and short clips;
- process, inventory and temperature histories;
- continuous surveillance video, if requested;
- backups, legal hold and deletion after expiry.

The current implementation assigns a minimum 365-day date to operational records and event evidence. It does not claim one year of continuous 80-camera video. Storage capacity and cost cannot be finalized until the client confirms the retained data classes, expected event volume, evidence duration/quality, redundancy, data residency and recovery objectives.

## Oracle discovery inputs

- Oracle product and version, such as Fusion Cloud ERP or E-Business Suite;
- approved REST/SOAP/OIC interfaces and authentication method;
- item, employee, location, lot/batch, work-order and quality object mappings;
- stock movement posting rules, units of measure and reversal/reconciliation logic;
- test environment and representative non-production master data;
- integration owner, network path, rate limits, retry policy and error ownership;
- acceptance evidence and cutover/rollback approvals.

ORVIA camera observations must remain proposed transactions until Oracle validation accepts them. Failed or rejected postings stay visible in a reconciliation queue and are never silently discarded.

## Client inputs required before production commitment

- floor plans, operational zones and the full 80-camera inventory;
- sample streams from each camera family and current NVR/VMS details;
- PPE/SOP rules, exception persistence and escalation matrix;
- representative site footage with staff consent and privacy approval;
- process names, start/complete definitions and target durations;
- temperature locations, limits, sensor accuracy and calibration policy;
- inventory master, units, packaging and movement/reconciliation rules;
- retention, cybersecurity, data-residency, IAM, backup and audit policies;
- Oracle details listed above;
- pilot area, stakeholders, measurable acceptance criteria and final approver.

## Recommended delivery stages

1. Technical discovery and site survey.
2. Existing-camera/VMS compatibility proof and workload benchmark.
3. SOP, PPE, sensor, inventory and Oracle contract definition.
4. Data collection, annotation, model/licence review and per-camera calibration.
5. One-area controlled pilot with agreed acceptance testing.
6. Security, privacy, retention, backup/restore and Oracle UAT.
7. Phased multi-camera rollout with monitoring, support and retraining governance.
