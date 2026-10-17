from __future__ import annotations

import time

import numpy as np
import pytest

from foodsafe_edge.ppe import CameraReadiness, PPEItemResult, PPEResult
from foodsafe_edge.ppe_review import PPEReviewBuffer, PPEReviewUnavailable


def ppe_result(
    *,
    mask: str = "detected",
    left: str = "detected",
    right: str = "not_visible",
    lighting_ready: bool = True,
) -> PPEResult:
    states = {
        "mask": (mask, (20, 20, 90, 80), None),
        "left_glove": (left, (15, 90, 70, 145), "left"),
        "right_glove": (right, None, "right"),
        "hairnet": ("not_visible", None, None),
        "apron": ("not_visible", None, None),
    }
    items = {
        item: PPEItemResult(
            item=item,
            state=state,  # type: ignore[arg-type]
            confidence=0.9 if state in {"detected", "missing"} else None,
            visibility_confidence=0.9 if roi else 0.0,
            blue_ratio=0.2 if state == "detected" else 0.0,
            threshold=0.05,
            side=side,
            roi=roi,
            observation_state=state,  # type: ignore[arg-type]
        )
        for item, (state, roi, side) in states.items()
    }
    readiness = CameraReadiness(
        brightness=120,
        lighting_ready=lighting_ready,
        face_visible=mask != "not_visible",
        left_hand_visible=left != "not_visible",
        right_hand_visible=right != "not_visible",
        torso_visible=True,
        framing_ready=True,
        guidance=[],
    )
    return PPEResult(
        mask=mask == "detected" if mask in {"detected", "missing"} else None,
        gloves=None,
        hairnet=None,
        apron=None,
        confidence=0.9,
        items=items,
        readiness=readiness,
        assessment_available=True,
    )


def test_builds_three_frame_contact_sheets_for_visible_stable_regions() -> None:
    buffer = PPEReviewBuffer(
        minimum_observations=3, maximum_age_seconds=4, capture_interval_seconds=0
    )
    frame = np.full((180, 120, 3), (120, 90, 60), dtype=np.uint8)
    for _ in range(3):
        buffer.add(frame, 7, ppe_result(mask="detected", left="missing"))

    readiness = buffer.readiness(7)
    bundle = buffer.build(7)

    assert readiness["ready"] is True
    assert readiness["regions"] == ["mask", "left_glove"]
    assert bundle.regions == ["lower_face", "left_hand"]
    assert bundle.local_decisions == {"lower_face": "present", "left_hand": "missing"}
    assert len(bundle.images) == 2
    assert all(image.startswith(b"\xff\xd8") for image in bundle.images)
    assert bundle.metadata["contactSheetsPersisted"] is False
    assert all(region["frameCount"] == 3 for region in bundle.metadata["regions"])


def test_hidden_or_poorly_lit_regions_are_never_submitted() -> None:
    buffer = PPEReviewBuffer(
        minimum_observations=3, maximum_age_seconds=4, capture_interval_seconds=0
    )
    frame = np.full((180, 120, 3), 100, dtype=np.uint8)
    for _ in range(3):
        buffer.add(
            frame,
            8,
            ppe_result(
                mask="not_visible",
                left="not_visible",
                right="not_visible",
                lighting_ready=False,
            ),
        )

    readiness = buffer.readiness(8)
    assert readiness["ready"] is False
    assert readiness["unavailableRegions"] == ["mask", "left_glove", "right_glove"]
    with pytest.raises(PPEReviewUnavailable):
        buffer.build(8)


def test_expired_observations_are_not_reviewable() -> None:
    buffer = PPEReviewBuffer(
        minimum_observations=3, maximum_age_seconds=0.01, capture_interval_seconds=0
    )
    frame = np.full((180, 120, 3), 100, dtype=np.uint8)
    for _ in range(3):
        buffer.add(frame, 9, ppe_result())
    time.sleep(0.02)

    assert buffer.readiness(9)["ready"] is False
    with pytest.raises(PPEReviewUnavailable):
        buffer.build(9)
