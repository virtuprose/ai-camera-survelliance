from pathlib import Path

import cv2

from foodsafe_edge.markers import EMPLOYEE_MARKERS, ArucoMarkerReader


def test_second_demo_employee_badge_is_registered_and_readable() -> None:
    employee = EMPLOYEE_MARKERS[102]
    assert employee == {
        "employeeId": "EMP-002",
        "displayName": "Demo Operator B",
        "badgeMarkerId": 102,
        "photoUrl": None,
    }

    marker_path = Path(__file__).resolve().parents[1] / "assets" / "markers" / "tag-102.png"
    frame = cv2.imread(str(marker_path))
    assert frame is not None
    assert [marker.marker_id for marker in ArucoMarkerReader().read(frame)] == [102]
