from __future__ import annotations

import hashlib
import logging
import tempfile
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .store import EventStore, iso

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PendingClip:
    event_id: str
    frames: list[np.ndarray]
    remaining: int
    fps: int


class EvidenceBuffer:
    def __init__(self, directory: Path, store: EventStore, camera_fps: int = 15):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.store = store
        self.camera_fps = camera_fps
        self.ring: deque[np.ndarray] = deque(maxlen=camera_fps * 3)
        self.pending: list[PendingClip] = []
        self.lock = threading.RLock()

    def health_check(self) -> None:
        """Verify the evidence directory is writable without touching retained evidence."""
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".orvia-evidence-health-", dir=self.directory, delete=True
        ) as probe:
            probe.write(b"ORVIA evidence health check")
            probe.flush()

    def add_frame(self, frame: np.ndarray) -> None:
        with self.lock:
            self.ring.append(frame.copy())
            completed: list[PendingClip] = []
            for clip in self.pending:
                clip.frames.append(frame.copy())
                clip.remaining -= 1
                if clip.remaining <= 0:
                    completed.append(clip)
            for clip in completed:
                self.pending.remove(clip)
                threading.Thread(target=self._write_clip, args=(clip,), daemon=True).start()

    def capture(self, event_id: str, frame: np.ndarray) -> str:
        snapshot_name = f"{event_id}.jpg"
        snapshot_path = self.directory / snapshot_name
        written = cv2.imwrite(str(snapshot_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
        if not written:
            self.store.merge_metadata(
                event_id,
                {"evidence_status": "snapshot_failed", "evidence_error": "JPEG write failed"},
            )
            logger.error("Could not create evidence snapshot for %s", event_id)
            return ""
        snapshot_bytes = snapshot_path.read_bytes()
        self.store.merge_metadata(
            event_id,
            {
                "evidence_status": "snapshot_ready_clip_pending",
                "snapshot_sha256": hashlib.sha256(snapshot_bytes).hexdigest(),
                "snapshot_bytes": len(snapshot_bytes),
                "snapshot_created_at": iso(),
            },
        )
        with self.lock:
            frames = [item.copy() for item in self.ring]
            self.pending.append(PendingClip(event_id, frames, self.camera_fps * 2, self.camera_fps))
        evidence_url = f"/api/edge/api/evidence/{snapshot_name}"
        self.store.set_evidence(event_id, evidence_url)
        return evidence_url

    def _write_clip(self, clip: PendingClip) -> None:
        if not clip.frames:
            return
        height, width = clip.frames[0].shape[:2]
        output = self.directory / f"{clip.event_id}.mp4"
        writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"mp4v"), clip.fps, (width, height))
        if not writer.isOpened():
            self.store.merge_metadata(
                clip.event_id,
                {"evidence_status": "clip_failed", "evidence_error": "MP4 writer unavailable"},
            )
            logger.warning("Could not create evidence clip for %s", clip.event_id)
            return
        try:
            for frame in clip.frames:
                writer.write(frame)
        finally:
            writer.release()
        clip_bytes = output.read_bytes()
        self.store.merge_metadata(
            clip.event_id,
            {
                "evidence_status": "complete",
                "clip_sha256": hashlib.sha256(clip_bytes).hexdigest(),
                "clip_bytes": len(clip_bytes),
                "clip_completed_at": iso(),
            },
        )
