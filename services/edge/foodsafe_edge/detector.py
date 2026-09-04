from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

import cv2
import numpy as np

from .settings import Settings

logger = logging.getLogger(__name__)

COCO_KEYPOINTS = (
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
)


@dataclass(slots=True)
class Keypoint:
    x: float
    y: float
    confidence: float


@dataclass(slots=True)
class PersonDetection:
    xyxy: tuple[int, int, int, int]
    confidence: float
    track_id: int
    keypoints: dict[str, Keypoint] | None = None


class PersonDetector(Protocol):
    label: str

    def detect(self, frame: np.ndarray) -> list[PersonDetection]: ...

    def reset(self) -> None: ...


class CentroidTracker:
    def __init__(self, max_distance: float = 100.0):
        self.max_distance = max_distance
        self.centres: dict[int, tuple[float, float]] = {}
        self.next_id = 1

    def update(self, boxes: list[tuple[int, int, int, int]]) -> list[int]:
        assigned: list[int] = []
        available = set(self.centres)
        next_centres: dict[int, tuple[float, float]] = {}
        for x1, y1, x2, y2 in boxes:
            centre = ((x1 + x2) / 2, (y1 + y2) / 2)
            best_id, best_distance = None, float("inf")
            for track_id in available:
                old = self.centres[track_id]
                distance = float(np.hypot(centre[0] - old[0], centre[1] - old[1]))
                if distance < best_distance:
                    best_id, best_distance = track_id, distance
            if best_id is None or best_distance > self.max_distance:
                best_id = self.next_id
                self.next_id += 1
            else:
                available.discard(best_id)
            assigned.append(best_id)
            next_centres[best_id] = centre
        self.centres = next_centres
        return assigned

    def reset(self) -> None:
        self.centres.clear()
        self.next_id = 1


class HOGPersonDetector:
    label = "OpenCV HOG + centroid tracker (fallback)"

    def __init__(self):
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        self.tracker = CentroidTracker()

    def detect(self, frame: np.ndarray) -> list[PersonDetection]:
        scale = min(1.0, 640 / frame.shape[1])
        work = cv2.resize(frame, None, fx=scale, fy=scale) if scale < 1 else frame
        boxes, weights = self.hog.detectMultiScale(work, winStride=(8, 8), padding=(8, 8), scale=1.05)
        normalized = [
            (int(x / scale), int(y / scale), int((x + w) / scale), int((y + h) / scale))
            for x, y, w, h in boxes
        ]
        track_ids = self.tracker.update(normalized)
        return [
            PersonDetection(box, float(weights[index]), track_ids[index])
            for index, box in enumerate(normalized)
        ]

    def reset(self) -> None:
        self.tracker.reset()


class UltralyticsPersonDetector:

    def __init__(self, settings: Settings):
        from ultralytics import YOLO

        self.settings = settings
        self.model = YOLO(settings.detector_model)
        self.fallback_tracker = CentroidTracker()
        self.pose_enabled = "pose" in settings.detector_model or getattr(self.model, "task", None) == "pose"
        self.label = (
            "YOLO11n pose/keypoint detector + ByteTrack"
            if self.pose_enabled
            else "YOLO11n person detector + ByteTrack · PPE assessment unavailable"
        )

    def detect(self, frame: np.ndarray) -> list[PersonDetection]:
        result = self.model.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            classes=[0],
            conf=self.settings.person_confidence,
            imgsz=self.settings.detector_image_size,
            device=self.settings.detector_device,
            verbose=False,
        )[0]
        if result.boxes is None or len(result.boxes) == 0:
            self.fallback_tracker.update([])
            return []
        boxes = [tuple(map(int, values)) for values in result.boxes.xyxy.cpu().numpy().tolist()]
        confidences = result.boxes.conf.cpu().numpy().tolist()
        if result.boxes.id is not None:
            ids = [int(value) for value in result.boxes.id.cpu().numpy().tolist()]
        else:
            ids = self.fallback_tracker.update(boxes)
        pose_data = None
        if result.keypoints is not None:
            pose_data = result.keypoints.data.cpu().numpy().tolist()
        return [
            PersonDetection(
                box,
                float(confidences[index]),
                ids[index],
                {
                    name: Keypoint(float(values[0]), float(values[1]), float(values[2]))
                    for name, values in zip(COCO_KEYPOINTS, pose_data[index], strict=True)
                }
                if pose_data is not None and index < len(pose_data)
                else None,
            )
            for index, box in enumerate(boxes)
        ]

    def reset(self) -> None:
        self.fallback_tracker.reset()
        predictor = getattr(self.model, "predictor", None)
        for tracker in getattr(predictor, "trackers", []) or []:
            reset = getattr(tracker, "reset", None)
            if callable(reset):
                reset()


def create_detector(settings: Settings) -> PersonDetector:
    if settings.detector_backend == "hog":
        return HOGPersonDetector()
    try:
        return UltralyticsPersonDetector(settings)
    except Exception:
        logger.exception("YOLO detector failed to initialize; using HOG fallback")
        return HOGPersonDetector()
