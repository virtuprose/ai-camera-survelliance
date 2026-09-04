from __future__ import annotations

import time
from collections import Counter, deque
from dataclasses import dataclass, replace
from typing import Literal

import cv2
import numpy as np

from .detector import Keypoint, PersonDetection

AssessmentState = Literal["not_visible", "checking", "detected", "missing", "unavailable"]
PPEColour = Literal["blue", "red"]

ITEM_ORDER = ("mask", "left_glove", "right_glove", "hairnet", "apron")
REQUIRED_ITEMS = ("mask", "left_glove", "right_glove")


@dataclass(slots=True)
class PPEItemResult:
    item: str
    state: AssessmentState
    confidence: float | None
    visibility_confidence: float
    blue_ratio: float | None
    threshold: float | None
    stable_for_ms: int = 0
    side: str | None = None
    roi: tuple[int, int, int, int] | None = None
    verification_method: str = "controlled_colour_shape"
    centre_ratio: float | None = None
    component_ratio: float | None = None
    horizontal_span_ratio: float | None = None
    vertical_span_ratio: float | None = None
    centre_offset_ratio: float | None = None
    quality_score: float | None = None
    decision_reason: str | None = None
    expected_colour: PPEColour = "blue"
    colour_ratio: float | None = None


@dataclass(slots=True)
class CameraReadiness:
    brightness: float
    lighting_ready: bool
    face_visible: bool
    left_hand_visible: bool
    right_hand_visible: bool
    torso_visible: bool
    framing_ready: bool
    guidance: list[str]


@dataclass(slots=True)
class PPEResult:
    mask: bool | None
    gloves: bool | None
    hairnet: bool | None
    apron: bool | None
    confidence: float | None
    items: dict[str, PPEItemResult]
    readiness: CameraReadiness
    assessment_available: bool


@dataclass(slots=True)
class ColourShapeEvidence:
    ratio: float
    centre_ratio: float
    component_ratio: float
    horizontal_span_ratio: float
    vertical_span_ratio: float
    centre_offset_ratio: float
    quality_score: float


def _derived_state(item: PPEItemResult) -> bool | None:
    if item.state == "detected":
        return True
    if item.state == "missing":
        return False
    return None


def _aggregate_result(
    items: dict[str, PPEItemResult], readiness: CameraReadiness, assessment_available: bool
) -> PPEResult:
    determinate = [item.confidence for item in items.values() if item.confidence is not None]
    left_glove = _derived_state(items["left_glove"])
    right_glove = _derived_state(items["right_glove"])
    gloves: bool | None
    if left_glove is False or right_glove is False:
        gloves = False
    elif left_glove is True and right_glove is True:
        gloves = True
    else:
        gloves = None
    return PPEResult(
        mask=_derived_state(items["mask"]),
        gloves=gloves,
        hairnet=_derived_state(items["hairnet"]),
        apron=_derived_state(items["apron"]),
        confidence=min(determinate) if determinate else None,
        items=items,
        readiness=readiness,
        assessment_available=assessment_available,
    )


class LandmarkColourPPEDetector:
    """Verify configured PPE colours using landmarks and connected-shape evidence.

    This remains a controlled-scene verifier, not a general-purpose PPE model.  A
    positive result requires a coherent component in the configured colour at the
    expected anatomical centre. Total colour pixels alone are deliberately
    insufficient because clothing, furniture, or a screen can overlap a
    landmark-derived rectangle.
    """

    def __init__(
        self,
        mask_threshold: float = 0.055,
        glove_threshold: float = 0.045,
        hairnet_threshold: float = 0.055,
        apron_threshold: float = 0.055,
        mask_colour: PPEColour = "blue",
        glove_colour: PPEColour = "red",
        hairnet_colour: PPEColour = "blue",
        apron_colour: PPEColour = "blue",
        keypoint_confidence: float = 0.45,
        minimum_brightness: float = 55.0,
    ) -> None:
        self.thresholds = {
            "mask": mask_threshold,
            "left_glove": glove_threshold,
            "right_glove": glove_threshold,
            "hairnet": hairnet_threshold,
            "apron": apron_threshold,
        }
        self.colours: dict[str, PPEColour] = {
            "mask": mask_colour,
            "left_glove": glove_colour,
            "right_glove": glove_colour,
            "hairnet": hairnet_colour,
            "apron": apron_colour,
        }
        self.label = (
            "Landmark-gated controlled PPE verifier v4 "
            f"({mask_colour} mask + {glove_colour} gloves)"
        )
        self.keypoint_confidence = keypoint_confidence
        self.minimum_brightness = minimum_brightness
        self.runtime_available = True
        self.runtime_failure_reason: str | None = None

    def disable(self, reason: str) -> None:
        self.runtime_available = False
        self.runtime_failure_reason = reason

    @staticmethod
    def _colour_mask(region: np.ndarray, colour: PPEColour) -> np.ndarray:
        if region.size == 0:
            return np.zeros((0, 0), dtype=np.uint8)
        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
        if colour == "blue":
            mask = cv2.inRange(hsv, np.array([85, 55, 35]), np.array([140, 255, 255]))
        elif colour == "red":
            lower_red = cv2.inRange(hsv, np.array([0, 120, 40]), np.array([10, 255, 255]))
            upper_red = cv2.inRange(hsv, np.array([170, 120, 40]), np.array([179, 255, 255]))
            mask = cv2.bitwise_or(lower_red, upper_red)

            # Hue alone can include warm skin tones. Require a strong red-channel
            # lead so a bare visible hand cannot satisfy the red-glove profile.
            blue_channel, green_channel, red_channel = cv2.split(region.astype(np.int16))
            red_dominant = (
                (red_channel >= 70)
                & ((red_channel - green_channel) >= 35)
                & ((red_channel - blue_channel) >= 45)
            )
            mask = cv2.bitwise_and(mask, (red_dominant.astype(np.uint8) * 255))
        else:  # pragma: no cover - PPEColour and Settings reject unsupported values.
            raise ValueError(f"Unsupported controlled PPE colour: {colour}")
        kernel = np.ones((3, 3), dtype=np.uint8)
        return cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    @classmethod
    def _colour_shape_evidence(
        cls, region: np.ndarray, item: str, colour: PPEColour
    ) -> ColourShapeEvidence:
        colour_mask = cls._colour_mask(region, colour)
        if colour_mask.size == 0:
            return ColourShapeEvidence(0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0)

        height, width = colour_mask.shape
        ratio = float(np.count_nonzero(colour_mask)) / float(colour_mask.size)
        centre = colour_mask[
            int(height * 0.10) : max(int(height * 0.85), 1),
            int(width * 0.25) : max(int(width * 0.75), 1),
        ]
        centre_ratio = (
            float(np.count_nonzero(centre)) / float(centre.size) if centre.size else 0.0
        )

        component_ratio = horizontal_span = vertical_span = 0.0
        centre_offset = 1.0
        component_count, _labels, stats, centroids = cv2.connectedComponentsWithStats(colour_mask)
        if component_count > 1:
            largest = max(
                range(1, component_count),
                key=lambda index: int(stats[index, cv2.CC_STAT_AREA]),
            )
            component_ratio = float(stats[largest, cv2.CC_STAT_AREA]) / float(colour_mask.size)
            horizontal_span = float(stats[largest, cv2.CC_STAT_WIDTH]) / float(width)
            vertical_span = float(stats[largest, cv2.CC_STAT_HEIGHT]) / float(height)
            component_x, component_y = centroids[largest]
            centre_offset = min(
                1.0,
                float(
                    np.hypot(
                        (component_x - width / 2) / max(width / 2, 1),
                        (component_y - height / 2) / max(height / 2, 1),
                    )
                ),
            )

        if item in {"mask", "hairnet"}:
            weights = (0.20, 0.35, 0.20, 0.15, 0.10)
            normalized = (
                min(1.0, ratio / 0.25),
                min(1.0, centre_ratio / 0.35),
                min(1.0, component_ratio / 0.25),
                min(1.0, horizontal_span / 0.65),
                max(0.0, 1.0 - centre_offset / 0.50),
            )
        else:
            weights = (0.25, 0.25, 0.20, 0.15, 0.15)
            normalized = (
                min(1.0, ratio / 0.35),
                min(1.0, centre_ratio / 0.40),
                min(1.0, component_ratio / 0.30),
                min(1.0, max(horizontal_span, vertical_span) / 0.60),
                max(0.0, 1.0 - centre_offset / 0.60),
            )
        quality_score = float(
            sum(weight * value for weight, value in zip(weights, normalized, strict=True))
        )
        return ColourShapeEvidence(
            ratio,
            centre_ratio,
            component_ratio,
            horizontal_span,
            vertical_span,
            centre_offset,
            quality_score,
        )

    @staticmethod
    def _shape_verified(item: str, evidence: ColourShapeEvidence, threshold: float) -> bool:
        if item == "mask":
            # Surgical masks sit below the eye/nose pose anchors and can extend
            # close to the lower edge of the derived face ROI. The previous
            # 0.38 centroid limit rejected a real, strongly segmented mask at
            # 0.389 despite high central/component coverage. Keep the coverage,
            # connected-component, span, and quality gates while allowing this
            # expected lower-face displacement. Peripheral/background colour
            # still fails the centre and horizontal-span requirements.
            return bool(
                evidence.ratio >= max(threshold, 0.08)
                and evidence.centre_ratio >= 0.14
                and evidence.component_ratio >= 0.07
                and evidence.horizontal_span_ratio >= 0.35
                and evidence.vertical_span_ratio >= 0.25
                and evidence.centre_offset_ratio <= 0.50
                and evidence.quality_score >= 0.58
            )
        if item == "hairnet":
            return bool(
                evidence.ratio >= max(threshold, 0.08)
                and evidence.centre_ratio >= 0.14
                and evidence.component_ratio >= 0.07
                and evidence.horizontal_span_ratio >= 0.35
                and evidence.centre_offset_ratio <= 0.38
                and evidence.quality_score >= 0.58
            )
        if item in {"left_glove", "right_glove"}:
            return bool(
                evidence.ratio >= max(threshold, 0.10)
                and evidence.centre_ratio >= 0.12
                and evidence.component_ratio >= 0.07
                and max(evidence.horizontal_span_ratio, evidence.vertical_span_ratio) >= 0.28
                and evidence.centre_offset_ratio <= 0.45
                and evidence.quality_score >= 0.52
            )
        return bool(
            evidence.ratio >= max(threshold, 0.10)
            and evidence.centre_ratio >= 0.12
            and evidence.component_ratio >= 0.08
            and evidence.quality_score >= 0.52
        )

    def _visible(self, point: Keypoint | None) -> bool:
        return bool(point and point.confidence >= self.keypoint_confidence and point.x > 0 and point.y > 0)

    @staticmethod
    def _clamp_roi(
        roi: tuple[float, float, float, float], width: int, height: int
    ) -> tuple[int, int, int, int] | None:
        x1, y1, x2, y2 = roi
        bounded = (
            max(0, min(width - 1, int(x1))),
            max(0, min(height - 1, int(y1))),
            max(0, min(width, int(x2))),
            max(0, min(height, int(y2))),
        )
        return bounded if bounded[2] - bounded[0] >= 4 and bounded[3] - bounded[1] >= 4 else None

    def _item(
        self,
        frame: np.ndarray,
        item: str,
        visible: bool,
        visibility_confidence: float,
        roi: tuple[int, int, int, int] | None,
        side: str | None = None,
    ) -> PPEItemResult:
        threshold = self.thresholds[item]
        expected_colour = self.colours[item]
        if not visible or roi is None:
            return PPEItemResult(
                item,
                "not_visible",
                None,
                visibility_confidence,
                None,
                threshold,
                side=side,
                decision_reason="Required anatomical region is not reliably visible",
                expected_colour=expected_colour,
            )
        x1, y1, x2, y2 = roi
        evidence = self._colour_shape_evidence(
            frame[y1:y2, x1:x2], item, expected_colour
        )
        detected = self._shape_verified(item, evidence, threshold)
        if detected:
            confidence = min(0.95, 0.55 + evidence.quality_score * 0.40)
            reason = f"Central connected {expected_colour} controlled-PPE shape verified"
        else:
            # This score describes the repeatability of the controlled-scene
            # decision.  It is not a probability of legal or safety compliance.
            confidence = min(0.95, 0.60 + visibility_confidence * 0.25 + (1 - evidence.quality_score) * 0.10)
            reason = (
                f"No qualifying central {expected_colour} controlled-PPE shape was verified"
            )
        return PPEItemResult(
            item,
            "detected" if detected else "missing",
            confidence,
            visibility_confidence,
            evidence.ratio if expected_colour == "blue" else None,
            threshold,
            side=side,
            roi=roi,
            centre_ratio=evidence.centre_ratio,
            component_ratio=evidence.component_ratio,
            horizontal_span_ratio=evidence.horizontal_span_ratio,
            vertical_span_ratio=evidence.vertical_span_ratio,
            centre_offset_ratio=evidence.centre_offset_ratio,
            quality_score=evidence.quality_score,
            decision_reason=reason,
            expected_colour=expected_colour,
            colour_ratio=evidence.ratio,
        )

    def detect(self, frame: np.ndarray, person: PersonDetection) -> PPEResult:
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = person.xyxy
        person_crop = frame[max(0, y1) : min(height, y2), max(0, x1) : min(width, x2)]
        brightness = (
            float(cv2.cvtColor(person_crop, cv2.COLOR_BGR2GRAY).mean()) if person_crop.size else 0.0
        )
        lighting_ready = brightness >= self.minimum_brightness
        keypoints = person.keypoints
        if not self.runtime_available or not keypoints:
            unavailable_reason = self.runtime_failure_reason or "PPE pose model unavailable"
            readiness = CameraReadiness(
                brightness,
                lighting_ready,
                False,
                False,
                False,
                False,
                False,
                [unavailable_reason],
            )
            items = {
                item: PPEItemResult(
                    item,
                    "unavailable",
                    None,
                    0.0,
                    None,
                    self.thresholds[item],
                    side="left" if item == "left_glove" else "right" if item == "right_glove" else None,
                    expected_colour=self.colours[item],
                )
                for item in ITEM_ORDER
            }
            return _aggregate_result(items, readiness, False)

        face_points = [
            keypoints.get(name)
            for name in ("nose", "left_eye", "right_eye", "left_ear", "right_ear")
        ]
        visible_face = [point for point in face_points if self._visible(point)]
        # Nose plus at least one eye is a stronger lower-face anchor than any two
        # face landmarks (for example, two ears inferred through an occlusion).
        face_visible = self._visible(keypoints.get("nose")) and any(
            self._visible(keypoints.get(name)) for name in ("left_eye", "right_eye")
        )
        left_wrist, right_wrist = keypoints.get("left_wrist"), keypoints.get("right_wrist")
        left_elbow, right_elbow = keypoints.get("left_elbow"), keypoints.get("right_elbow")
        # COCO pose has a wrist landmark but no finger landmarks. A confident
        # wrist is therefore the visibility gate; the elbow is optional context
        # used to project the hand ROI when it is also visible.
        left_hand_visible = self._visible(left_wrist)
        right_hand_visible = self._visible(right_wrist)
        shoulders = [keypoints.get("left_shoulder"), keypoints.get("right_shoulder")]
        hips = [keypoints.get("left_hip"), keypoints.get("right_hip")]
        torso_visible = all(self._visible(point) for point in shoulders + hips)
        shoulder_width = (
            abs(shoulders[1].x - shoulders[0].x)
            if all(self._visible(point) for point in shoulders)
            else max(30.0, (x2 - x1) * 0.35)
        )

        face_roi = hair_roi = None
        if face_visible:
            xs = [point.x for point in visible_face]
            ys = [point.y for point in visible_face]
            anchor_x = float(np.mean(xs))
            anchor_y = float(np.mean(ys))
            face_width = max(max(xs) - min(xs) if len(xs) > 1 else 0, shoulder_width * 0.42, 30.0)
            face_roi = self._clamp_roi(
                (
                    anchor_x - face_width * 0.58,
                    anchor_y,
                    anchor_x + face_width * 0.58,
                    anchor_y + face_width * 0.86,
                ),
                width,
                height,
            )
            hair_roi = self._clamp_roi(
                (
                    anchor_x - face_width * 0.64,
                    anchor_y - face_width * 0.80,
                    anchor_x + face_width * 0.64,
                    anchor_y,
                ),
                width,
                height,
            )

        def hand_roi(wrist: Keypoint | None, elbow: Keypoint | None) -> tuple[int, int, int, int] | None:
            if not wrist:
                return None
            dx, dy = (
                (wrist.x - elbow.x, wrist.y - elbow.y)
                if self._visible(elbow)
                else (0.0, 0.0)
            )
            # Project beyond the wrist toward the hand.  The previous 0.18
            # projection mostly measured cuffs/forearms and could miss a raised
            # palm entirely.
            centre_x, centre_y = wrist.x + dx * 0.48, wrist.y + dy * 0.48
            radius = max(22.0, min(56.0, shoulder_width * 0.20))
            return self._clamp_roi(
                (centre_x - radius, centre_y - radius, centre_x + radius, centre_y + radius),
                width,
                height,
            )

        left_hand_roi = hand_roi(left_wrist, left_elbow)
        right_hand_roi = hand_roi(right_wrist, right_elbow)
        apron_roi = None
        if torso_visible:
            apron_roi = self._clamp_roi(
                (
                    min(shoulders[0].x, shoulders[1].x),
                    max(shoulders[0].y, shoulders[1].y),
                    max(shoulders[0].x, shoulders[1].x),
                    max(hips[0].y, hips[1].y),
                ),
                width,
                height,
            )

        face_confidence = (
            float(np.mean([point.confidence for point in visible_face])) if visible_face else 0.0
        )
        left_visibility = left_wrist.confidence if left_hand_visible and left_wrist else 0.0
        right_visibility = right_wrist.confidence if right_hand_visible and right_wrist else 0.0
        torso_confidence = min(point.confidence for point in shoulders + hips) if torso_visible else 0.0
        items = {
            "mask": self._item(frame, "mask", face_visible and lighting_ready, face_confidence, face_roi),
            "left_glove": self._item(
                frame,
                "left_glove",
                left_hand_visible and lighting_ready,
                left_visibility,
                left_hand_roi,
                "left",
            ),
            "right_glove": self._item(
                frame,
                "right_glove",
                right_hand_visible and lighting_ready,
                right_visibility,
                right_hand_roi,
                "right",
            ),
            "hairnet": self._item(
                frame, "hairnet", face_visible and lighting_ready, face_confidence, hair_roi
            ),
            "apron": self._item(
                frame, "apron", torso_visible and lighting_ready, torso_confidence, apron_roi
            ),
        }
        guidance: list[str] = []
        if not lighting_ready:
            guidance.append("Increase front lighting")
        if not face_visible:
            guidance.append("Move back until your face is fully visible")
        if not torso_visible:
            guidance.append("Move back until head and torso are visible")
        if not left_hand_visible or not right_hand_visible:
            guidance.append("Raise both hands for glove assessment")
        readiness = CameraReadiness(
            brightness,
            lighting_ready,
            face_visible,
            left_hand_visible,
            right_hand_visible,
            torso_visible,
            lighting_ready and face_visible and left_hand_visible and right_hand_visible and torso_visible,
            list(dict.fromkeys(guidance)),
        )
        return _aggregate_result(items, readiness, True)

    def startup_self_test(self) -> tuple[bool, list[str]]:
        """Run deterministic fail-safe checks automatically at edge startup."""
        visible = 0.95
        person = PersonDetection(
            (20, 10, 180, 390),
            0.98,
            1,
            {
                "nose": Keypoint(100, 70, visible),
                "left_eye": Keypoint(90, 60, visible),
                "right_eye": Keypoint(110, 60, visible),
                "left_ear": Keypoint(75, 65, visible),
                "right_ear": Keypoint(125, 65, visible),
                "left_shoulder": Keypoint(65, 125, visible),
                "right_shoulder": Keypoint(135, 125, visible),
                "left_elbow": Keypoint(45, 190, visible),
                "right_elbow": Keypoint(155, 190, visible),
                "left_wrist": Keypoint(35, 250, visible),
                "right_wrist": Keypoint(165, 250, visible),
                "left_hip": Keypoint(75, 310, visible),
                "right_hip": Keypoint(125, 310, visible),
            },
        )
        frame = np.full((400, 200, 3), 100, dtype=np.uint8)
        baseline = self.detect(frame, person)
        failures: list[str] = []
        if baseline.items["mask"].state != "missing":
            failures.append("bare face did not resolve to missing")

        edge_leak = frame.copy()
        mask_roi = baseline.items["mask"].roi
        if mask_roi:
            x1, y1, x2, y2 = mask_roi
            strip = max(2, int((x2 - x1) * 0.18))
            edge_leak[y1:y2, x1 : x1 + strip] = (255, 100, 0)
            edge_leak[y1:y2, x2 - strip : x2] = (255, 100, 0)
        if self.detect(edge_leak, person).items["mask"].state != "missing":
            failures.append("peripheral blue background was accepted as a mask")

        compliant = frame.copy()
        synthetic_colours = {"blue": (255, 100, 0), "red": (0, 0, 255)}
        for item in ("mask", "left_glove", "right_glove"):
            roi = baseline.items[item].roi
            if roi:
                x1, y1, x2, y2 = roi
                compliant[y1:y2, x1:x2] = synthetic_colours[self.colours[item]]
        result = self.detect(compliant, person)
        for item in ("mask", "left_glove", "right_glove"):
            if result.items[item].state != "detected":
                failures.append(f"controlled {item} positive did not resolve to detected")

        wrong_glove_colour = frame.copy()
        for item in ("left_glove", "right_glove"):
            roi = baseline.items[item].roi
            if roi:
                x1, y1, x2, y2 = roi
                wrong_glove_colour[y1:y2, x1:x2] = synthetic_colours["blue"]
        wrong_result = self.detect(wrong_glove_colour, person)
        if any(
            wrong_result.items[item].state == "detected"
            for item in ("left_glove", "right_glove")
        ):
            failures.append("blue hand region was accepted by the red-glove profile")
        return not failures, failures


class PPEStabilizer:
    """Convert frame-level assessments into stable, non-flickering track state."""

    def __init__(self, window: int = 15, required_consensus: int = 12) -> None:
        self.window = window
        self.required_consensus = required_consensus
        self.history: dict[tuple[int, str], deque[AssessmentState]] = {}
        self.stable_state: dict[tuple[int, str], AssessmentState] = {}
        self.stable_since: dict[tuple[int, str], float] = {}

    def reset(self) -> None:
        self.history.clear()
        self.stable_state.clear()
        self.stable_since.clear()

    def clear_track(self, track_id: int) -> None:
        for mapping in (self.history, self.stable_state, self.stable_since):
            for key in [key for key in mapping if key[0] == track_id]:
                mapping.pop(key, None)

    def update(self, track_id: int, result: PPEResult, now: float | None = None) -> PPEResult:
        observed_at = now if now is not None else time.monotonic()
        stable_items: dict[str, PPEItemResult] = {}
        for item_name in ITEM_ORDER:
            item = result.items[item_name]
            key = (track_id, item_name)
            history = self.history.setdefault(key, deque(maxlen=self.window))
            # Visibility is a prerequisite, not a PPE decision. Once the anatomy
            # leaves view (or pose inference is unavailable), discard earlier
            # visible observations so they cannot be presented as a current miss.
            if item.state in {"not_visible", "unavailable"}:
                history.clear()
            history.append(item.state)
            counts = Counter(history)
            next_state: AssessmentState = "checking"
            if item.state in {"not_visible", "unavailable"}:
                next_state = item.state
            elif counts["detected"] >= self.required_consensus:
                next_state = "detected"
            elif counts["missing"] >= self.required_consensus:
                next_state = "missing"
            previous = self.stable_state.get(key)
            if next_state != previous:
                self.stable_state[key] = next_state
                self.stable_since[key] = observed_at
            # Confidence represents an actual PPE decision. Visibility states
            # intentionally remain unscored so the API never presents
            # `not_visible` or `unavailable` as a 100% PPE conclusion.
            consensus = (
                counts[next_state] / len(history)
                if history and next_state in {"detected", "missing"}
                else None
            )
            stable_items[item_name] = replace(
                item,
                state=next_state,
                confidence=consensus if consensus is not None else item.confidence,
                stable_for_ms=max(0, int((observed_at - self.stable_since.get(key, observed_at)) * 1000)),
            )
        return _aggregate_result(stable_items, result.readiness, result.assessment_available)


# Compatibility alias for imports outside the edge package.
ControlledColourPPEDetector = LandmarkColourPPEDetector
