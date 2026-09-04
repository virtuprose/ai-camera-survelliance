from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class Zone:
    name: str
    points: tuple[tuple[float, float], ...]
    colour: tuple[int, int, int]

    def pixels(self, width: int, height: int) -> np.ndarray:
        return np.array([(int(x * width), int(y * height)) for x, y in self.points], dtype=np.int32)

    def contains(self, point: tuple[int, int], width: int, height: int) -> bool:
        return cv2.pointPolygonTest(self.pixels(width, height), point, False) >= 0


ZONES = (
    Zone("Entrance", ((0.01, 0.05), (0.19, 0.05), (0.19, 0.95), (0.01, 0.95)), (128, 180, 255)),
    Zone("Preparation", ((0.20, 0.05), (0.79, 0.05), (0.79, 0.95), (0.20, 0.95)), (104, 186, 137)),
    Zone("Process Start", ((0.22, 0.58), (0.48, 0.58), (0.48, 0.93), (0.22, 0.93)), (88, 189, 239)),
    Zone("Process Complete", ((0.51, 0.58), (0.77, 0.58), (0.77, 0.93), (0.51, 0.93)), (93, 213, 154)),
    Zone("Inventory", ((0.81, 0.05), (0.99, 0.05), (0.99, 0.95), (0.81, 0.95)), (210, 168, 117)),
)


def zone_for(point: tuple[int, int], width: int, height: int, preferred: tuple[str, ...] = ()) -> str:
    ordered = sorted(ZONES, key=lambda zone: 0 if zone.name in preferred else 1)
    for zone in ordered:
        if zone.contains(point, width, height):
            return zone.name
    return "Unassigned"


def draw_zones(frame: np.ndarray) -> None:
    overlay = frame.copy()
    height, width = frame.shape[:2]
    for zone in ZONES:
        points = zone.pixels(width, height)
        cv2.polylines(frame, [points], True, zone.colour, 1, cv2.LINE_AA)
        cv2.fillPoly(overlay, [points], zone.colour)
        x, y = points[0]
        cv2.putText(
            frame,
            zone.name.upper(),
            (x + 6, y + 17),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            zone.colour,
            1,
            cv2.LINE_AA,
        )
    cv2.addWeighted(overlay, 0.035, frame, 0.965, 0, frame)
