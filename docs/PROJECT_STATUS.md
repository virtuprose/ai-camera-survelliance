# Project status

Status date: 2026-09-04

## Included in source

- Local Next.js operations dashboard.
- Python camera and event-processing service.
- macOS camera, RTSP, and prerecorded-file adapters.
- Person tracking and identity-independent controlled PPE workflow.
- Optional ArUco employee, tray, and inventory markers.
- Local events, evidence, incidents, audit records, reports, and exports.
- Simulated temperature source plus inactive serial and MQTT adapters.
- Optional Supabase, LiveKit, Vercel, and Oracle integration contracts.
- Unit, API, browser, accessibility, camera-soak, and rehearsal commands.

## Demonstration-only or simulated

- PPE classification uses a controlled colour and pose-landmark profile.
- Temperature readings are simulated until approved hardware is installed and calibrated.
- The included fallback video is synthetic and always labelled simulated.
- Tools actions create visibly simulated records.
- Tray and inventory movement use printed markers.

## Not connected or production-approved

- Oracle ERP.
- Client or deployment cloud accounts.
- Production-grade role and tenancy configuration.
- Facility-specific model training and accuracy acceptance.
- Multi-camera handoff and fleet sizing.
- Production retention enforcement, backup, and disaster recovery.
- Facial recognition and camera audio.

## Release principle

A feature is described as implemented only when the repository contains its working local path and automated verification. Mocked, simulated, credential-dependent, and production-gated capabilities are labelled separately.
