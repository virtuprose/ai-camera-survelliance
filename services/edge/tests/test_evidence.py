import time

import numpy as np

from foodsafe_edge.evidence import EvidenceBuffer
from foodsafe_edge.store import EventInput, EventStore


def test_snapshot_and_clip_receive_integrity_digests(tmp_path) -> None:
    store = EventStore(tmp_path / "edge.db")
    event = store.add_event(EventInput(type="test", title="Proof", detail="Integrity test"))
    evidence = EvidenceBuffer(tmp_path / "evidence", store, camera_fps=2)
    frame = np.full((96, 128, 3), 100, dtype=np.uint8)

    evidence.capture(event["id"], frame)
    snapshot_event = store.get_event(event["id"])
    assert snapshot_event["metadata"]["evidence_status"] == "snapshot_ready_clip_pending"
    assert len(snapshot_event["metadata"]["snapshot_sha256"]) == 64
    assert snapshot_event["metadata"]["snapshot_bytes"] > 0

    for _ in range(4):
        evidence.add_frame(frame)
    deadline = time.monotonic() + 3
    completed_event = store.get_event(event["id"])
    while completed_event["metadata"].get("evidence_status") != "complete":
        if time.monotonic() >= deadline:
            raise AssertionError("Evidence clip did not complete")
        time.sleep(0.05)
        completed_event = store.get_event(event["id"])

    assert len(completed_event["metadata"]["clip_sha256"]) == 64
    assert completed_event["metadata"]["clip_bytes"] > 0
    assert (tmp_path / "evidence" / f"{event['id']}.mp4").is_file()
