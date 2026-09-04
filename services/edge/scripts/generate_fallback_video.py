from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets" / "fallback-demo.mp4"
WIDTH, HEIGHT, FPS, SECONDS = 1280, 720, 15, 24


def marker(marker_id: int, size: int) -> np.ndarray:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_1000)
    image = cv2.aruco.generateImageMarker(dictionary, marker_id, size, borderBits=1)
    return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)


def paste(frame: np.ndarray, image: np.ndarray, centre: tuple[int, int]) -> None:
    height, width = image.shape[:2]
    x1, y1 = centre[0] - width // 2, centre[1] - height // 2
    frame[y1 : y1 + height, x1 : x1 + width] = image


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(OUTPUT), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (WIDTH, HEIGHT))
    if not writer.isOpened():
        raise SystemExit("Could not create fallback video")
    employee_tag, tray_tag, item_tag = marker(101, 150), marker(201, 120), marker(301, 110)
    try:
        for frame_number in range(FPS * SECONDS):
            second = frame_number / FPS
            frame = np.full((HEIGHT, WIDTH, 3), (20, 27, 29), dtype=np.uint8)
            cv2.rectangle(frame, (0, 0), (WIDTH, 78), (12, 17, 19), -1)
            cv2.putText(
                frame,
                "PRERECORDED LOCAL FALLBACK - CAMERA 01",
                (30, 118),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (210, 222, 218),
                2,
                cv2.LINE_AA,
            )
            cv2.rectangle(frame, (230, 150), (1000, 660), (36, 48, 50), -1)
            cv2.rectangle(frame, (260, 450), (970, 610), (58, 74, 72), -1)
            cv2.putText(
                frame,
                "PREPARATION BENCH",
                (475, 535),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (147, 166, 159),
                2,
                cv2.LINE_AA,
            )
            # Blue demo PPE regions are deliberately visible on the stylized operator.
            cv2.circle(frame, (455, 242), 62, (70, 92, 95), -1)
            cv2.ellipse(frame, (455, 198), (58, 22), 0, 180, 360, (255, 110, 15), -1)
            cv2.rectangle(frame, (418, 238), (492, 270), (255, 110, 15), -1)
            cv2.rectangle(frame, (378, 305), (532, 525), (255, 110, 15), -1)
            cv2.rectangle(frame, (350, 420), (395, 470), (255, 110, 15), -1)
            cv2.rectangle(frame, (515, 420), (560, 470), (255, 110, 15), -1)
            paste(frame, employee_tag, (455, 380))
            tray_x = int(345 + min(1.0, max(0.0, (second - 4) / 10)) * 390)
            paste(frame, tray_tag, (tray_x, 555))
            item_x = int(720 + min(1.0, max(0.0, (second - 12) / 6)) * 390)
            paste(frame, item_tag, (item_x, 360))
            writer.write(frame)
    finally:
        writer.release()
    print(f"Generated {SECONDS}s fallback video: {OUTPUT}")


if __name__ == "__main__":
    main()
