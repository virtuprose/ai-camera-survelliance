from pathlib import Path

import cv2

OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "markers"
LABELS = {
    101: "EMP-001 Demo Operator A badge",
    102: "EMP-002 Demo Operator B badge",
    201: "TRAY-01 process tray",
    301: "SKU-001 Product A",
    302: "SKU-002 Product B",
    303: "SKU-003 Product C",
    304: "SKU-004 Product D",
    305: "SKU-005 Product E",
}


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_1000)
    for marker_id, label in LABELS.items():
        marker = cv2.aruco.generateImageMarker(dictionary, marker_id, 900, borderBits=1)
        canvas = cv2.copyMakeBorder(marker, 120, 220, 120, 120, cv2.BORDER_CONSTANT, value=255)
        cv2.putText(canvas, f"TAG {marker_id}", (120, 1035), cv2.FONT_HERSHEY_SIMPLEX, 1.5, 0, 3, cv2.LINE_AA)
        cv2.putText(canvas, label, (120, 1090), cv2.FONT_HERSHEY_SIMPLEX, 0.8, 0, 2, cv2.LINE_AA)
        cv2.imwrite(str(OUTPUT / f"tag-{marker_id}.png"), canvas)
    print(f"Generated {len(LABELS)} markers in {OUTPUT}")


if __name__ == "__main__":
    main()
