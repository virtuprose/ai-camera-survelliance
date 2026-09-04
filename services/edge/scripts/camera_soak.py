from __future__ import annotations

import argparse
import time

import cv2


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify uninterrupted macOS camera capture.")
    parser.add_argument("--minutes", type=float, default=10)
    parser.add_argument("--device", type=int, default=0)
    args = parser.parse_args()
    capture = cv2.VideoCapture(args.device, cv2.CAP_AVFOUNDATION)
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    capture.set(cv2.CAP_PROP_FPS, 15)
    if not capture.isOpened():
        raise SystemExit("Camera could not open. Allow camera access for Terminal/Codex and retry.")
    started, frames, failures = time.monotonic(), 0, 0
    resolution: tuple[int, int] | None = None
    target = args.minutes * 60
    try:
        while time.monotonic() - started < target:
            ok, frame = capture.read()
            if ok and frame is not None:
                resolution = (frame.shape[1], frame.shape[0])
            frames += int(ok)
            failures += int(not ok)
            if failures > 10:
                raise SystemExit(f"Camera became unstable after {frames} frames ({failures} failures).")
    finally:
        capture.release()
    elapsed = time.monotonic() - started
    if resolution != (1280, 720):
        raise SystemExit(f"Camera opened at {resolution}, expected 1280x720.")
    print(
        f"PASS: {elapsed:.1f}s, {frames} frames, {frames / elapsed:.1f} fps, "
        f"{resolution[0]}x{resolution[1]}, {failures} failures"
    )


if __name__ == "__main__":
    main()
