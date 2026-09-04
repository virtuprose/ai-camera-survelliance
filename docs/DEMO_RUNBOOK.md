# Client demonstration runbook

## Before the meeting

1. Place the camera in a fixed position with the full operator, preparation bench, start/complete areas, and inventory line visible.
2. Print the marker images in `services/edge/assets/markers/`; keep black borders flat and unobstructed.
3. Keep employee badge `101` (Demo Operator A) or `102` (Demo Operator B) available only as an optional identity demonstration. Begin PPE monitoring without a badge. Use tray `201` and product `301` for the short presentation.
4. Use a blue mask and both red gloves for the controlled PPE demonstration. Hairnet and apron are monitor-only until separately enabled and calibrated.
5. Run `bun run local`; it starts the edge service, dashboard, and automatic monitoring together. Confirm the automatic status on **Live Operations** and every item on **System status**.
6. Run the scripted scenario once and restart both services before the client joins.
7. Keep the prerecorded fallback available; do not hide that it is prerecorded if used.

## Eight-minute presentation

1. **0:00–0:45** — Explain that the pilot is one-camera, silent, does not use facial recognition, and does not require employee identity for PPE monitoring.
2. **0:45–1:30** — Enter without a badge; show `Unidentified staff member`, neutral `Identity not associated`, the movement trail, and the face/hand readiness states. Explain that PPE remains independent of identity.
3. **1:30–2:30** — First show the bare visible face with hands hidden: `Mask not detected` must appear while both hands remain `Not visible`. Then show the blue mask and both red gloves for approximately six seconds, remove one required item for approximately six seconds, and review the single deduplicated, priority-ordered event and evidence. Demonstrate **Clear warnings** and non-destructive **Reset detection**.
4. **2:30–3:30** — Move tray `201` from Process Start to Process Complete; show the timer and stored duration.
5. **3:30–4:30** — Move product `301` across the inventory line in both directions; show quantity and transaction direction.
6. **4:30–5:15** — Use **Raise high**; point out the `Simulated sensor` label and instant alert, then return it to safe.
7. **5:15–6:30** — Open Events & Evidence, acknowledge one event, and export CSV.
8. **6:30–7:15** — Open Reports & Audit and Platform; show process, PPE, temperature, inventory, queue, retention, exports, and freshness.
9. **7:15–8:00** — State the pilot limitations and explain the VIGI/Supabase/LiveKit/Oracle production path.

## Recovery

- Camera permission failure: use `bun run edge:fallback` and clearly say it is the prerecorded local fallback.
- Internet failure: stay on the local dashboard; events remain in SQLite and queue by UUID.
- Dashboard failure: keep the edge service running, restart `bun run dev`, and refresh.
- RTSP failure: verify the camera in VLC using `stream1`, then check IP, credentials, H.264, and LAN reachability.
