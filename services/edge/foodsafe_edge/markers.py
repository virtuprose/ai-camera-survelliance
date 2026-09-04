from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(slots=True)
class Marker:
    marker_id: int
    corners: np.ndarray
    centre: tuple[int, int]
    confidence: float


class ArucoMarkerReader:
    def __init__(self):
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_1000)
        parameters = cv2.aruco.DetectorParameters()
        parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        self.detector = cv2.aruco.ArucoDetector(dictionary, parameters)

    def read(self, frame: np.ndarray) -> list[Marker]:
        corners, ids, _rejected = self.detector.detectMarkers(frame)
        if ids is None:
            return []
        output: list[Marker] = []
        for index, marker_id in enumerate(ids.flatten().tolist()):
            points = corners[index].reshape(4, 2)
            centre = tuple(map(int, points.mean(axis=0)))
            perimeter = cv2.arcLength(points.astype(np.float32), True)
            confidence = min(0.99, max(0.5, perimeter / 400.0))
            output.append(Marker(int(marker_id), points, centre, confidence))
        return output


EMPLOYEE_MARKERS = {
    101: {
        "employeeId": "EMP-001",
        "displayName": "Demo Operator A",
        "badgeMarkerId": 101,
        "photoUrl": None,
    },
    102: {
        "employeeId": "EMP-002",
        "displayName": "Demo Operator B",
        "badgeMarkerId": 102,
        "photoUrl": None,
    },
}
TRAY_MARKERS = {201: "TRAY-01"}
INVENTORY_MARKERS = {
    301: "SKU-001",
    302: "SKU-002",
    303: "SKU-003",
    304: "SKU-004",
    305: "SKU-005",
}
