import time
from datetime import UTC, datetime

import numpy as np
import pytest

from foodsafe_edge.detector import Keypoint, PersonDetection
from foodsafe_edge.markers import Marker
from foodsafe_edge.pipeline import EdgePipeline
from foodsafe_edge.ppe import ColourShapeEvidence, LandmarkColourPPEDetector, PPEStabilizer
from foodsafe_edge.settings import Settings

CONTROLLED_COLOURS = {
    "blue": (255, 100, 0),
    "red": (0, 0, 255),
}


def _person(
    *,
    face: bool = True,
    left_hand: bool = True,
    right_hand: bool = True,
    torso: bool = True,
) -> PersonDetection:
    visible = 0.95
    hidden = 0.05
    return PersonDetection(
        (20, 10, 180, 390),
        0.98,
        17,
        {
            "nose": Keypoint(100, 70, visible if face else hidden),
            "left_eye": Keypoint(90, 60, visible if face else hidden),
            "right_eye": Keypoint(110, 60, visible if face else hidden),
            "left_ear": Keypoint(75, 65, visible if face else hidden),
            "right_ear": Keypoint(125, 65, visible if face else hidden),
            "left_shoulder": Keypoint(65, 125, visible if torso else hidden),
            "right_shoulder": Keypoint(135, 125, visible if torso else hidden),
            "left_elbow": Keypoint(45, 190, visible if left_hand else hidden),
            "right_elbow": Keypoint(155, 190, visible if right_hand else hidden),
            "left_wrist": Keypoint(35, 250, visible if left_hand else hidden),
            "right_wrist": Keypoint(165, 250, visible if right_hand else hidden),
            "left_hip": Keypoint(75, 310, visible if torso else hidden),
            "right_hip": Keypoint(125, 310, visible if torso else hidden),
            "left_knee": Keypoint(75, 370, hidden),
            "right_knee": Keypoint(125, 370, hidden),
            "left_ankle": Keypoint(75, 390, hidden),
            "right_ankle": Keypoint(125, 390, hidden),
        },
    )


def _frame(value: int = 100) -> np.ndarray:
    return np.full((400, 200, 3), value, dtype=np.uint8)


def _paint(
    frame: np.ndarray,
    roi: tuple[int, int, int, int] | None,
    colour: str = "blue",
) -> None:
    assert roi is not None
    x1, y1, x2, y2 = roi
    frame[y1:y2, x1:x2] = CONTROLLED_COLOURS[colour]


def _compliant_frame(detector: LandmarkColourPPEDetector, person: PersonDetection) -> np.ndarray:
    frame = _frame()
    baseline = detector.detect(frame, person)
    for item_name, item in baseline.items.items():
        _paint(frame, item.roi, detector.colours[item_name])
    return frame


@pytest.mark.parametrize(
    ("face", "left_hand", "right_hand", "detected_items", "expected"),
    [
        (True, False, False, (), ("missing", "not_visible", "not_visible")),
        (True, True, True, (), ("missing", "missing", "missing")),
        (True, True, True, ("mask",), ("detected", "missing", "missing")),
        (
            True,
            True,
            True,
            ("mask", "left_glove", "right_glove"),
            ("detected", "detected", "detected"),
        ),
        (False, True, True, (), ("not_visible", "missing", "missing")),
        (True, False, False, (), ("missing", "not_visible", "not_visible")),
    ],
)
def test_tomorrow_controlled_mask_and_glove_scenarios(
    face: bool,
    left_hand: bool,
    right_hand: bool,
    detected_items: tuple[str, ...],
    expected: tuple[str, str, str],
) -> None:
    detector = LandmarkColourPPEDetector()
    person = _person(face=face, left_hand=left_hand, right_hand=right_hand)
    frame = _frame()
    baseline = detector.detect(frame, person)
    for item in detected_items:
        _paint(frame, baseline.items[item].roi, detector.colours[item])

    result = detector.detect(frame, person)

    assert (
        result.items["mask"].state,
        result.items["left_glove"].state,
        result.items["right_glove"].state,
    ) == expected


def test_landmarks_gate_mask_and_each_glove_independently() -> None:
    detector = LandmarkColourPPEDetector()
    person = _person(right_hand=False)
    frame = _frame()
    baseline = detector.detect(frame, person)
    _paint(frame, baseline.items["mask"].roi)
    _paint(frame, baseline.items["left_glove"].roi, "red")

    result = detector.detect(frame, person)

    assert result.items["mask"].state == "detected"
    assert result.items["left_glove"].state == "detected"
    assert result.items["right_glove"].state == "not_visible"
    assert result.gloves is None
    assert result.readiness.face_visible is True
    assert result.readiness.left_hand_visible is True
    assert result.readiness.right_hand_visible is False
    assert "Raise both hands for glove assessment" in result.readiness.guidance


def test_peripheral_blue_background_cannot_be_reported_as_a_mask() -> None:
    detector = LandmarkColourPPEDetector()
    person = _person(left_hand=False, right_hand=False)
    frame = _frame()
    baseline = detector.detect(frame, person)
    roi = baseline.items["mask"].roi
    assert roi is not None
    x1, y1, x2, y2 = roi
    strip = max(2, int((x2 - x1) * 0.18))
    frame[y1:y2, x1 : x1 + strip] = (255, 100, 0)
    frame[y1:y2, x2 - strip : x2] = (255, 100, 0)

    result = detector.detect(frame, person).items["mask"]

    assert result.blue_ratio is not None and result.blue_ratio > detector.thresholds["mask"]
    assert result.centre_ratio is not None and result.centre_ratio < 0.14
    assert result.state == "missing"
    assert result.decision_reason == "No qualifying central blue controlled-PPE shape was verified"


def test_real_surgical_mask_lower_face_geometry_is_verified() -> None:
    detector = LandmarkColourPPEDetector()
    # Measurements captured from the user's clearly visible light-blue surgical
    # mask on 2026-09-03. Every coverage/shape signal was strong; only the old
    # 0.38 centroid limit rejected it at 0.3894.
    evidence = ColourShapeEvidence(
        ratio=0.43449048152295633,
        centre_ratio=0.6430075187969925,
        component_ratio=0.2394923478910041,
        horizontal_span_ratio=0.4631578947368421,
        vertical_span_ratio=0.75177304964539,
        centre_offset_ratio=0.3894481173179827,
        quality_score=0.8705868459423242,
    )

    assert detector._shape_verified("mask", evidence, detector.thresholds["mask"]) is True
    # Hairnet geometry remains stricter; the mask calibration cannot loosen the
    # separate head-region rule.
    assert detector._shape_verified("hairnet", evidence, detector.thresholds["hairnet"]) is False


def test_blue_mask_and_red_gloves_are_item_specific() -> None:
    detector = LandmarkColourPPEDetector(mask_colour="blue", glove_colour="red")
    person = _person()
    baseline_frame = _frame()
    baseline = detector.detect(baseline_frame, person)

    wrong_colours = baseline_frame.copy()
    _paint(wrong_colours, baseline.items["mask"].roi, "red")
    _paint(wrong_colours, baseline.items["left_glove"].roi, "blue")
    _paint(wrong_colours, baseline.items["right_glove"].roi, "blue")
    wrong = detector.detect(wrong_colours, person)
    assert [wrong.items[item].state for item in ("mask", "left_glove", "right_glove")] == [
        "missing",
        "missing",
        "missing",
    ]

    configured_colours = baseline_frame.copy()
    _paint(configured_colours, baseline.items["mask"].roi, "blue")
    _paint(configured_colours, baseline.items["left_glove"].roi, "red")
    _paint(configured_colours, baseline.items["right_glove"].roi, "red")
    detected = detector.detect(configured_colours, person)
    assert [
        detected.items[item].state for item in ("mask", "left_glove", "right_glove")
    ] == ["detected", "detected", "detected"]
    assert detected.items["mask"].expected_colour == "blue"
    assert detected.items["left_glove"].expected_colour == "red"
    assert detected.items["left_glove"].blue_ratio is None
    assert detected.items["left_glove"].colour_ratio == 1.0


def test_automatic_ppe_startup_gate_and_fail_safe_disable() -> None:
    detector = LandmarkColourPPEDetector()

    assert detector.startup_self_test() == (True, [])

    detector.disable("synthetic startup failure")
    result = detector.detect(_frame(), _person())
    assert result.assessment_available is False
    assert all(item.state == "unavailable" for item in result.items.values())
    assert result.readiness.guidance == ["synthetic startup failure"]


def test_visible_wrist_is_enough_to_assess_hand_when_elbow_is_occluded() -> None:
    detector = LandmarkColourPPEDetector()
    person = _person()
    assert person.keypoints is not None
    person.keypoints["left_elbow"] = Keypoint(45, 190, 0.05)

    result = detector.detect(_frame(), person)

    assert result.readiness.left_hand_visible is True
    assert result.items["left_glove"].state == "missing"
    assert result.items["left_glove"].roi is not None


def test_hidden_anatomy_and_low_light_never_become_missing() -> None:
    detector = LandmarkColourPPEDetector()

    hidden = detector.detect(_frame(), _person(face=False, left_hand=False, right_hand=False))
    assert hidden.items["mask"].state == "not_visible"
    assert hidden.items["left_glove"].state == "not_visible"
    assert hidden.items["right_glove"].state == "not_visible"

    dark = detector.detect(_frame(25), _person())
    assert all(item.state == "not_visible" for item in dark.items.values())
    assert dark.readiness.lighting_ready is False
    assert dark.readiness.guidance[0] == "Increase front lighting"


def test_pose_unavailable_disables_ppe_instead_of_guessing() -> None:
    detector = LandmarkColourPPEDetector()
    person = PersonDetection((20, 10, 180, 390), 0.98, 17)

    result = detector.detect(_frame(), person)

    assert result.assessment_available is False
    assert all(item.state == "unavailable" for item in result.items.values())
    assert result.mask is None
    assert result.gloves is None

    stabilized = PPEStabilizer().update(17, result)
    assert all(item.confidence is None for item in stabilized.items.values())


def test_not_visible_state_never_reports_decision_confidence() -> None:
    detector = LandmarkColourPPEDetector()
    hidden = detector.detect(_frame(), _person(face=False, left_hand=False, right_hand=False))

    stabilized = PPEStabilizer().update(17, hidden)

    assert stabilized.items["mask"].state == "not_visible"
    assert stabilized.items["left_glove"].state == "not_visible"
    assert stabilized.items["right_glove"].state == "not_visible"
    assert stabilized.items["mask"].confidence is None
    assert stabilized.items["left_glove"].confidence is None
    assert stabilized.items["right_glove"].confidence is None


def test_rolling_window_requires_twelve_consistent_frames_and_rejects_one_frame_flip() -> None:
    detector = LandmarkColourPPEDetector()
    stabilizer = PPEStabilizer()
    person = _person()
    bare = detector.detect(_frame(), person)
    compliant = detector.detect(_compliant_frame(detector, person), person)

    result = bare
    for index in range(11):
        result = stabilizer.update(17, bare, now=index * 0.1)
    assert result.items["mask"].state == "checking"
    result = stabilizer.update(17, bare, now=1.1)
    assert result.items["mask"].state == "missing"

    result = stabilizer.update(17, compliant, now=1.2)
    assert result.items["mask"].state == "missing"
    for index in range(14):
        result = stabilizer.update(17, compliant, now=1.3 + index * 0.1)
    assert result.items["mask"].state == "detected"

    hidden = detector.detect(_frame(), _person(face=False, left_hand=False, right_hand=False))
    result = stabilizer.update(17, hidden, now=3.0)
    assert result.items["mask"].state == "not_visible"
    assert result.items["left_glove"].state == "not_visible"
    assert result.items["right_glove"].state == "not_visible"


class _OnePersonDetector:
    label = "Test pose detector"

    def __init__(self, person: PersonDetection | None = None) -> None:
        self.person = person or _person()
        self.reset_called = False

    def detect(self, _frame: np.ndarray) -> list[PersonDetection]:
        return [self.person]

    def reset(self) -> None:
        self.reset_called = True


class _NoMarkers:
    @staticmethod
    def read(_frame: np.ndarray) -> list[object]:
        return []


class _OneBadgeThenNone:
    def __init__(self) -> None:
        self.calls = 0

    def read(self, _frame: np.ndarray) -> list[Marker]:
        self.calls += 1
        if self.calls > 1:
            return []
        corners = np.array([[80, 170], [120, 170], [120, 210], [80, 210]], dtype=np.float32)
        return [Marker(101, corners, (100, 190), 0.98)]


def test_automatic_monitoring_reports_runtime_readiness(tmp_path) -> None:
    pipeline = EdgePipeline(Settings(camera_enabled=False, data_dir=tmp_path))
    initial_health = pipeline.state()["health"]
    assert initial_health["automaticMonitoring"] == "unavailable"
    assert initial_health["storage"] == "online"
    assert initial_health["storageError"] is None

    pipeline.settings.camera_enabled = True
    pipeline.detector = _OnePersonDetector()
    pipeline.camera_online = True
    pipeline.latest_jpeg = b"frame"
    pipeline.last_frame_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    pipeline.processed_fps = 9.4
    health = pipeline.state()["health"]
    assert health["automaticMonitoring"] == "active"
    assert "running automatically" in health["monitoringMessage"]

    pipeline.processed_fps = 4.5
    health = pipeline.state()["health"]
    assert health["automaticMonitoring"] == "attention"
    assert "below 6 FPS" in health["monitoringMessage"]


def test_badge_identity_remains_bound_to_track_during_short_occlusion(tmp_path) -> None:
    pipeline = EdgePipeline(
        Settings(camera_enabled=False, data_dir=tmp_path, identity_binding_seconds=5)
    )
    pipeline.detector = _OnePersonDetector()
    pipeline.marker_reader = _OneBadgeThenNone()

    pipeline._process(_frame())
    assert pipeline.state()["activeEmployee"]["displayName"] == "Demo Operator A"
    assert pipeline.state()["activeEmployee"]["badgeConfidence"] == 0.98

    pipeline._process(_frame())
    employee = pipeline.state()["activeEmployee"]
    assert employee["displayName"] == "Demo Operator A"
    assert employee["identityMethod"] == "aruco_badge"

    pipeline.track_employee_binding_seen[17] = time.monotonic() - 6
    pipeline._process(_frame())
    assert pipeline.state()["activeEmployee"]["displayName"] == "Unidentified staff member"


def test_staff_activity_uses_zone_and_active_process_without_inferring_intent(tmp_path) -> None:
    pipeline = EdgePipeline(Settings(camera_enabled=False, data_dir=tmp_path))
    assert pipeline._activity_context("Preparation") == (
        "Present in preparation area · no active tagged process"
    )

    pipeline.process_state["status"] = "running"
    assert pipeline._activity_context("Preparation") == "Chicken Washing · in progress"
    assert pipeline._activity_context("Inventory") == "Present in Inventory"


def test_ppe_monitoring_without_identity_creates_ordered_proof_and_recovery(tmp_path) -> None:
    settings = Settings(
        camera_enabled=False,
        data_dir=tmp_path,
        ppe_persistence_seconds=0,
        ppe_recovery_seconds=0,
        identity_persistence_seconds=0,
    )
    pipeline = EdgePipeline(settings)
    detector = _OnePersonDetector()
    pipeline.detector = detector
    pipeline.marker_reader = _NoMarkers()
    compliant = _compliant_frame(pipeline.ppe_detector, detector.person)

    for _ in range(12):
        pipeline._process(compliant.copy())
    subject = pipeline.state()["activeEmployee"]
    assert subject["employeeId"] is None
    assert subject["displayName"] == "Unidentified staff member"
    assert subject["ppe"]["mask"] is True
    assert subject["ppe"]["gloves"] is True
    detection = pipeline.state()["detection"]
    assert detection["status"] == "compliant"
    assert detection["identityStatus"]["state"] == "not_associated"
    assert detection["issues"] == []

    bare = _frame()
    for _ in range(14):
        pipeline._process(bare.copy())
    events = pipeline.store.list_events(limit=100)
    violations = sorted(
        (event for event in events if event["type"] == "ppe_violation"),
        key=lambda event: event["occurredAt"],
    )
    violation_titles = [event["title"] for event in violations]
    assert {"Mask not detected", "Left glove not detected", "Right glove not detected"} <= set(
        violation_titles
    )
    assert violation_titles[:3] == [
        "Mask not detected",
        "Left glove not detected",
        "Right glove not detected",
    ]
    mask_event = next(event for event in events if event["title"] == "Mask not detected")
    assert mask_event["employeeId"] is None
    assert mask_event["trackId"] == 17
    assert mask_event["evidenceUrl"] is not None
    assert mask_event["metadata"]["item"] == "mask"
    assert mask_event["metadata"]["visibility_confidence"] > 0.9
    assert mask_event["metadata"]["blue_ratio"] == 0
    assert mask_event["metadata"]["colour_profile"] == "blue"
    assert mask_event["metadata"]["colour_ratio"] == 0
    assert mask_event["metadata"]["brightness"] >= 55
    assert mask_event["metadata"]["roi"] is not None
    assert pipeline.state()["detection"]["issues"][0]["title"] == "Mask not detected"

    for _ in range(12):
        pipeline._process(compliant.copy())
    recovery_events = [
        event for event in pipeline.store.list_events() if event["type"] == "ppe_compliance_restored"
    ]
    assert {event["metadata"]["item"] for event in recovery_events} >= {
        "mask",
        "left_glove",
        "right_glove",
    }

    retained_event_ids = {event["id"] for event in pipeline.store.list_events()}
    reset_state = pipeline.reset_detection()
    assert detector.reset_called is True
    assert reset_state["status"] == "idle"
    assert reset_state["resetGeneration"] == 1
    assert {event["id"] for event in pipeline.store.list_events()} == retained_event_ids


def test_mask_and_gloves_define_demo_compliance_while_secondary_rules_are_monitor_only(
    tmp_path,
) -> None:
    pipeline = EdgePipeline(
        Settings(
            camera_enabled=False,
            data_dir=tmp_path,
            ppe_persistence_seconds=0,
            identity_persistence_seconds=99,
        )
    )
    detector = _OnePersonDetector()
    pipeline.detector = detector
    pipeline.marker_reader = _NoMarkers()
    frame = _frame()
    baseline = pipeline.ppe_detector.detect(frame, detector.person)
    for item in ("mask", "left_glove", "right_glove"):
        _paint(frame, baseline.items[item].roi, pipeline.ppe_detector.colours[item])

    for _ in range(12):
        pipeline._process(frame.copy())

    detection = pipeline.state()["detection"]
    assert detection["status"] == "compliant"
    assert detection["ppeItems"]["hairnet"]["state"] == "missing"
    assert detection["ppeItems"]["hairnet"]["required"] is False
    assert detection["ppeItems"]["apron"]["required"] is False
    assert not [
        event for event in pipeline.store.list_events() if event["type"] == "ppe_violation"
    ]


def test_attention_overlay_draws_red_box_x_and_landmark_regions(tmp_path) -> None:
    pipeline = EdgePipeline(Settings(camera_enabled=False, data_dir=tmp_path))
    pipeline.detector = _OnePersonDetector()
    pipeline.marker_reader = _NoMarkers()
    annotated = _frame()
    for _ in range(12):
        annotated = pipeline._process(_frame())

    red_pixels = (annotated[:, :, 2] > 180) & (annotated[:, :, 1] < 90)
    white_pixels = np.all(annotated > 220, axis=2)
    assert red_pixels.sum() > 500
    assert white_pixels[34:66, 150:180].sum() > 5
    assert len(pipeline.track_paths[17]) == 12


def test_stable_zone_movement_creates_one_evidence_backed_event(tmp_path) -> None:
    pipeline = EdgePipeline(Settings(camera_enabled=False, data_dir=tmp_path))
    person = _person()
    frame = _frame()
    subject_key = "track:17"
    pipeline.movement_zone[subject_key] = "Preparation"
    pipeline.movement_candidate[subject_key] = ("Process Complete", time.monotonic() - 2)

    pipeline._check_movement(None, person, "Process Complete", frame)
    pipeline._check_movement(None, person, "Process Complete", frame)

    movement_events = [event for event in pipeline.store.list_events() if event["type"] == "staff_movement"]
    assert len(movement_events) == 1
    assert movement_events[0]["metadata"]["from_zone"] == "Preparation"
    assert movement_events[0]["metadata"]["to_zone"] == "Process Complete"
    assert movement_events[0]["trackId"] == 17
    assert movement_events[0]["evidenceUrl"] is not None
