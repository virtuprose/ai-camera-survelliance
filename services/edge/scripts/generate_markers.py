from pathlib import Path

import cv2

from foodsafe_edge.markers import EMPLOYEE_MARKERS

OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "markers"
LABELS = {
    **{
        marker_id: f"{employee['employeeId']}  {employee['displayName']}  employee badge"
        for marker_id, employee in EMPLOYEE_MARKERS.items()
    },
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
        canvas = cv2.copyMakeBorder(marker, 120, 300, 120, 120, cv2.BORDER_CONSTANT, value=255)
        cv2.putText(canvas, f"TAG {marker_id}", (120, 1110), cv2.FONT_HERSHEY_SIMPLEX, 1.4, 0, 3, cv2.LINE_AA)
        cv2.putText(canvas, label, (120, 1180), cv2.FONT_HERSHEY_SIMPLEX, 0.72, 0, 2, cv2.LINE_AA)
        cv2.imwrite(str(OUTPUT / f"tag-{marker_id}.png"), canvas)
    print(f"Generated {len(LABELS)} markers in {OUTPUT}")


if __name__ == "__main__":
    main()
