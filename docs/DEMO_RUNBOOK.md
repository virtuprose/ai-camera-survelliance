# Client demonstration runbook

## Before the meeting

1. Place the camera in a fixed position with the full operator, preparation bench, start/complete areas, and inventory line visible.
2. Print the marker images in `services/edge/assets/markers/`; keep black borders flat and unobstructed.
3. Keep employee badge `101` (Ahmed Hassan), `102` (Muhammad Zaid), or `103` (Fatima Ali) available only as an optional identity demonstration. Begin PPE monitoring without a badge. After verification, step completely out of view and return alone to demonstrate the clearly labelled 10-minute **Session reassociated** state. Use tray `201` and product `301` for the short presentation.
4. Use a blue mask and both red gloves for the controlled PPE demonstration. Hairnet and apron are monitor-only until separately enabled and calibrated.
5. Run `bun run local`; it starts the edge service, dashboard, and automatic monitoring together. Confirm the automatic status on **Live Operations** and every item on **System status**.
6. Run the scripted scenario once and restart both services before the client joins.
7. Confirm **AI PPE Assurance** reports the provider as available, then complete one real review. Do not present the AI panel live until the physical 30/30 PPE matrix and camera-performance comparison are recorded. Local PPE remains the authoritative result.
8. Keep the prerecorded fallback available; do not hide that it is prerecorded if used.

## Eight-minute presentation

1. **0:00–0:45** — Explain that the pilot is one-camera, silent, does not use facial recognition, and does not require employee identity for PPE monitoring.
2. **0:45–1:30** — Enter without a badge; show `Unidentified staff member`, neutral `Identity not associated`, the movement trail, and the face/hand readiness states. Explain that PPE remains independent of identity.
3. **1:30–2:30** — Briefly show a badge, hide it, leave the camera view, and return alone. Explain the difference between `Badge identified`, `Identity retained`, and `Session reassociated`; show that ambiguous returns remain unidentified and that **Clear identity session** preserves evidence. Then show the bare visible face with hands hidden: `Mask not detected` must appear while both hands remain `Not visible`. Show the blue mask and both red gloves, remove one required item, and review the deduplicated evidence. If the Phase 3 gate has passed, select **Review current PPE** and explain `Two-model agreement` versus `Needs human review`; never describe the AI result as a replacement for local detection.
4. **2:30–3:30** — Move tray `201` from Process Start to Process Complete; show the timer and stored duration.
5. **3:30–4:30** — Move product `301` across the inventory line in both directions; show quantity and transaction direction.
6. **4:30–5:15** — Use **Raise high**; point out the `Simulated sensor` label and instant alert, then return it to safe.
7. **5:15–6:30** — Open Events & Evidence, acknowledge one event, and export CSV.
8. **6:30–7:15** — Open Reports & Audit and Platform; show process, PPE, temperature, inventory, queue, retention, exports, and freshness.
9. **7:15–8:00** — State the pilot limitations and explain the VIGI/Supabase/LiveKit/Oracle production path.

## Recovery

- Camera permission failure: use `bun run edge:fallback` and clearly say it is the prerecorded local fallback.
- Internet failure: stay on the local dashboard; events remain in SQLite and queue by UUID.
- AI timeout, rate limit, or provider failure: point to `Cloud unavailable — local monitoring continues`; continue the local PPE demonstration and do not retry repeatedly.
- Dashboard failure: keep the edge service running, restart `bun run dev`, and refresh.
- RTSP failure: verify the camera in VLC using `stream1`, then check IP, credentials, H.264, and LAN reachability.
