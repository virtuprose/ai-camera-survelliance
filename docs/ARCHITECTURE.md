# Architecture

## Purpose

ORVIA AI Surveillance is a local-first event-processing platform for controlled food-safety demonstrations. It converts camera and sensor observations into reviewable operational records while keeping capture, inference, business rules, evidence, and external integrations as separate components.

The repository demonstrates the workflow and interfaces. It does not certify a facility, replace a quality team, or establish production accuracy.

## Runtime components

### Edge service

The Python service owns the time-sensitive path:

1. Open a camera, RTSP stream, or video file through the camera adapter.
2. Detect and track people through a replaceable detector interface.
3. Use pose landmarks to decide whether relevant PPE regions are visible.
4. Apply controlled-scene PPE rules independently of employee identity.
5. Read optional ArUco markers for staff badges, process trays, and inventory items.
6. Evaluate process-zone transitions, inventory-line crossings, and temperature thresholds.
7. Persist events, evidence references, incident state, and audit records locally.
8. Queue optional cloud synchronization by event UUID so retries do not create duplicates.

If a detector or body region is unavailable, the edge service reports an unknown or unavailable state. It must not create a missing-PPE claim from an invisible region.

### Operations dashboard

The Next.js application reads the edge API through a same-origin proxy and presents:

- command-center status;
- live annotated camera output and source selection;
- PPE, process, staff, cold-chain, and inventory operations;
- incidents, evidence, ownership, and corrective action;
- reports and source-aware exports;
- local/cloud health and the Oracle integration boundary.

The local dashboard remains usable without Supabase, LiveKit, Vercel, or Oracle credentials.

### Optional cloud services

The reference cloud path separates responsibilities:

- Supabase Auth for users;
- PostgreSQL for governed operational records;
- private object storage for evidence;
- private realtime channels for event updates;
- LiveKit for a silent annotated video track;
- Vercel for the dashboard runtime.

These adapters are inactive until deployment-owned credentials are supplied and verified. Local operation is not proof that cloud authorization, tenancy, retention, or residency requirements have passed production review.

## Event lifecycle

Each event uses a UUID and records, where applicable:

- UTC occurrence time and device identifier;
- event type, severity, source mode, and review status;
- zone, track, and optional employee association;
- detector confidence and measurement metadata;
- evidence reference and integrity metadata;
- retention deadline;
- incident ownership, SLA, root cause, corrective action, and audit history.

The interface renders times for Asia/Kuwait while storage remains UTC. Simulated records carry `source_mode=simulated` through the API, interface, evidence, and exports.

## Identity boundary

Person detection is required to localize the body. Employee identity is not required to evaluate PPE.

The demonstration supports optional ArUco badges. A production deployment can add an approved access-control adapter. Facial recognition is intentionally absent. Any biometric capability would be a separate project requiring legal, privacy, security, workforce, and acceptance approval.

## Evidence boundary

Evidence consists of event snapshots and short before/after clips. Camera audio is disabled. Local files are not committed to Git. Production evidence requires approved encryption, access control, retention enforcement, deletion handling, immutable audit policy, backup, and residency design.

## Camera coexistence and scale-out

The edge service can consume a read-only RTSP stream while an existing NVR or VMS continues recording the same camera. This is conditional on vendor support, stream capacity, network design, credentials, and a successful soak test.

An 80-camera deployment is not one laptop running 80 copies of the demo. Production scale requires a camera inventory, stream compatibility test, GPU sizing benchmark, network and storage calculations, high-availability design, monitoring, and phased rollout. The same interfaces can be replicated across edge nodes while central services aggregate events and evidence.

## Production gates

Before production use, complete at minimum:

1. Site survey and camera placement validation.
2. Approved SOP, PPE, process, inventory, and temperature rules.
3. Consented site data capture, annotation, training, and held-out testing.
4. Commercial model and dependency licensing review.
5. Cybersecurity, privacy, retention, and data-residency design.
6. Sensor hardware selection and calibration.
7. Oracle product/version discovery and test-environment access.
8. Performance, failover, recovery, and user-acceptance testing.
9. Signed acceptance criteria and controlled pilot approval.
