from __future__ import annotations

import argparse
from pathlib import Path

from ultralytics import YOLO


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune the replaceable PPE detector after annotation.")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--base-model", default="yolo11n.pt")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--device", default="mps")
    args = parser.parse_args()
    if not args.data.is_file():
        raise SystemExit(f"Dataset YAML not found: {args.data}")
    model = YOLO(args.base_model)
    model.train(
        data=str(args.data),
        epochs=args.epochs,
        imgsz=640,
        device=args.device,
        project="runs/ppe",
    )


if __name__ == "__main__":
    main()
