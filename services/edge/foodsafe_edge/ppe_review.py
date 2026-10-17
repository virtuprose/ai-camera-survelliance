from __future__ import annotations

import hashlib
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import cv2
import numpy as np

from .ppe import PPEResult

REVIEW_ITEMS = ("mask", "left_glove", "right_glove")
REGION_NAMES = {
    "mask": "lower_face",
    "left_glove": "left_hand",
    "right_glove": "right_hand",
}


@dataclass(slots=True)
class ReviewObservation:
    captured_monotonic: float
    captured_at: str
    jpeg: bytes
    sha256: str
    width: int
    height: int
    visibility_confidence: float
    brightness: float


@dataclass(slots=True)
class PPEReviewBundle:
    track_id: int
    images: list[bytes]
    regions: list[str]
    local_decisions: dict[str, str]
    metadata: dict[str, Any]


class PPEReviewUnavailable(ValueError):
    pass


class PPEReviewBuffer:
    """Keep short-lived PPE crops in memory and build contact sheets on demand."""

    def __init__(
        self,
        *,
        minimum_observations: int = 3,
        maximum_age_seconds: float = 4.0,
        minimum_visibility_confidence: float = 0.45,
        capture_interval_seconds: float = 0.3,
    ) -> None:
        self.minimum_observations = minimum_observations
        self.maximum_age_seconds = maximum_age_seconds
        self.minimum_visibility_confidence = minimum_visibility_confidence
        self.capture_interval_seconds = capture_interval_seconds
        self._observations: dict[tuple[int, str], deque[ReviewObservation]] = {}
        self._latest_ppe: dict[int, PPEResult] = {}
        self._last_capture: dict[tuple[int, str], float] = {}
        self._lock = threading.RLock()

    def clear(self) -> None:
        with self._lock:
            self._observations.clear()
            self._latest_ppe.clear()
            self._last_capture.clear()

    def clear_track(self, track_id: int) -> None:
        with self._lock:
            self._latest_ppe.pop(track_id, None)
            for key in [key for key in self._observations if key[0] == track_id]:
                self._observations.pop(key, None)
                self._last_capture.pop(key, None)

    def add(self, frame: np.ndarray, track_id: int, ppe: PPEResult) -> None:
        now = time.monotonic()
        captured_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        with self._lock:
            self._latest_ppe[track_id] = ppe
            if not ppe.assessment_available or not ppe.readiness.lighting_ready:
                return
            frame_height, frame_width = frame.shape[:2]
            for item in REVIEW_ITEMS:
                assessment = ppe.items[item]
                key = (track_id, item)
                if (
                    assessment.roi is None
                    or assessment.visibility_confidence < self.minimum_visibility_confidence
                    or assessment.state == "not_visible"
                    or now - self._last_capture.get(key, 0.0) < self.capture_interval_seconds
                ):
                    continue
                x1, y1, x2, y2 = assessment.roi
                x1, x2 = max(0, x1), min(frame_width, x2)
                y1, y2 = max(0, y1), min(frame_height, y2)
                if x2 - x1 < 8 or y2 - y1 < 8:
                    continue
                crop = frame[y1:y2, x1:x2]
                encoded, jpeg = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 88])
                if not encoded:
                    continue
                payload = jpeg.tobytes()
                observations = self._observations.setdefault(
                    key, deque(maxlen=max(9, self.minimum_observations * 3))
                )
                observations.append(
                    ReviewObservation(
                        captured_monotonic=now,
                        captured_at=captured_at,
                        jpeg=payload,
                        sha256=hashlib.sha256(payload).hexdigest(),
                        width=crop.shape[1],
                        height=crop.shape[0],
                        visibility_confidence=assessment.visibility_confidence,
                        brightness=ppe.readiness.brightness,
                    )
                )
                self._last_capture[key] = now
            self._prune_locked(now)

    def readiness(self, track_id: int | None) -> dict[str, Any]:
        if track_id is None:
            return {
                "ready": False,
                "regions": [],
                "unavailableRegions": list(REVIEW_ITEMS),
                "guidance": "Stand in the camera view before requesting AI review.",
            }
        with self._lock:
            now = time.monotonic()
            self._prune_locked(now)
            ppe = self._latest_ppe.get(track_id)
            ready: list[str] = []
            unavailable: list[str] = []
            for item in REVIEW_ITEMS:
                assessment = ppe.items[item] if ppe else None
                observations = self._fresh_locked(track_id, item, now)
                if (
                    assessment is not None
                    and assessment.state in {"detected", "missing"}
                    and len(observations) >= self.minimum_observations
                ):
                    ready.append(item)
                else:
                    unavailable.append(item)
            guidance = None
            if not ready:
                if ppe is None or not ppe.assessment_available:
                    guidance = "PPE pose landmarks are unavailable; local monitoring continues."
                elif not ppe.readiness.lighting_ready:
                    guidance = "Increase front lighting before requesting AI review."
                else:
                    guidance = "Keep the face or hands visible until the local PPE state stabilizes."
            return {
                "ready": bool(ready),
                "regions": ready,
                "unavailableRegions": unavailable,
                "guidance": guidance,
            }

    def build(self, track_id: int) -> PPEReviewBundle:
        with self._lock:
            now = time.monotonic()
            self._prune_locked(now)
            ppe = self._latest_ppe.get(track_id)
            if ppe is None:
                raise PPEReviewUnavailable("No active PPE observation is available for review.")
            images: list[bytes] = []
            regions: list[str] = []
            local_decisions: dict[str, str] = {}
            region_metadata: list[dict[str, Any]] = []
            for item in REVIEW_ITEMS:
                assessment = ppe.items[item]
                observations = self._fresh_locked(track_id, item, now)
                if (
                    assessment.state not in {"detected", "missing"}
                    or len(observations) < self.minimum_observations
                ):
                    continue
                selected = list(observations)[-self.minimum_observations :]
                contact_sheet = self._contact_sheet(selected)
                region_name = REGION_NAMES[item]
                images.append(contact_sheet)
                regions.append(region_name)
                local_decisions[region_name] = (
                    "present" if assessment.state == "detected" else "missing"
                )
                region_metadata.append(
                    {
                        "item": item,
                        "region": region_name,
                        "frameCount": len(selected),
                        "capturedAt": selected[-1].captured_at,
                        "sourceAgeMs": round((now - selected[-1].captured_monotonic) * 1000),
                        "sourceHashes": [observation.sha256 for observation in selected],
                        "sourceDimensions": [
                            [observation.width, observation.height] for observation in selected
                        ],
                        "visibilityConfidence": round(
                            min(observation.visibility_confidence for observation in selected), 4
                        ),
                        "brightness": round(
                            sum(observation.brightness for observation in selected) / len(selected),
                            2,
                        ),
                    }
                )
            if not images:
                raise PPEReviewUnavailable(
                    "No well-lit, visible PPE region has three fresh stable observations."
                )
            return PPEReviewBundle(
                track_id=track_id,
                images=images,
                regions=regions,
                local_decisions=local_decisions,
                metadata={
                    "trackId": track_id,
                    "regions": region_metadata,
                    "contactSheetsPersisted": False,
                },
            )

    def _fresh_locked(
        self, track_id: int, item: str, now: float
    ) -> list[ReviewObservation]:
        return [
            observation
            for observation in self._observations.get((track_id, item), ())
            if now - observation.captured_monotonic <= self.maximum_age_seconds
        ]

    def _prune_locked(self, now: float) -> None:
        for key, observations in list(self._observations.items()):
            fresh = [
                observation
                for observation in observations
                if now - observation.captured_monotonic <= self.maximum_age_seconds
            ]
            if fresh:
                self._observations[key] = deque(fresh, maxlen=observations.maxlen)
            else:
                self._observations.pop(key, None)

    @staticmethod
    def _contact_sheet(observations: list[ReviewObservation]) -> bytes:
        crops = [
            cv2.imdecode(np.frombuffer(item.jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
            for item in observations
        ]
        if any(crop is None for crop in crops):
            raise PPEReviewUnavailable("A temporary PPE crop could not be decoded.")
        target_height = 192
        resized: list[np.ndarray] = []
        for crop in crops:
            assert crop is not None
            scale = target_height / crop.shape[0]
            width = max(8, round(crop.shape[1] * scale))
            resized.append(cv2.resize(crop, (width, target_height)))
        separator = np.full((target_height, 4, 3), 235, dtype=np.uint8)
        sheet = resized[0]
        for crop in resized[1:]:
            sheet = np.hstack((sheet, separator, crop))
        encoded, jpeg = cv2.imencode(".jpg", sheet, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not encoded:
            raise PPEReviewUnavailable("A temporary PPE contact sheet could not be encoded.")
        return jpeg.tobytes()
