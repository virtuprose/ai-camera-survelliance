from pathlib import Path

import cv2

from foodsafe_edge.markers import EMPLOYEE_MARKERS, ArucoMarkerReader


def test_employee_badges_are_registered_and_readable() -> None:
    expected = {
        101: ("EMP-001", "Ahmed Hassan"),
        102: ("EMP-002", "Muhammad Zaid"),
        103: ("EMP-003", "Fatima Ali"),
    }
    for marker_id, (employee_id, display_name) in expected.items():
        employee = EMPLOYEE_MARKERS[marker_id]
        assert employee == {
            "employeeId": employee_id,
            "displayName": display_name,
            "badgeMarkerId": marker_id,
            "photoUrl": None,
        }

        marker_path = Path(__file__).resolve().parents[1] / "assets" / "markers" / f"tag-{marker_id}.png"
        frame = cv2.imread(str(marker_path))
        assert frame is not None
        assert [marker.marker_id for marker in ArucoMarkerReader().read(frame)] == [marker_id]
