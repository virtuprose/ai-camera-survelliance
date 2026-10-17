from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import UTC, datetime
from typing import Any

import cv2
import numpy as np

from .ai_supervisor import AIJobWorker
from .camera import OpenCVCameraSource, camera_catalog, camera_id_for_settings
from .detector import PersonDetection, PersonDetector, create_detector
from .enterprise import EnterpriseStore
from .evidence import EvidenceBuffer
from .livekit_publisher import LiveKitPublisher
from .markers import EMPLOYEE_MARKERS, INVENTORY_MARKERS, TRAY_MARKERS, ArucoMarkerReader, Marker
from .operations_supervisor import ClientDemoPreflight, OperationsSupervisor
from .ppe import (
    ITEM_ORDER,
    REQUIRED_ITEMS,
    LandmarkColourPPEDetector,
    PPEItemResult,
    PPEResult,
    PPEStabilizer,
)
from .ppe_review import PPEReviewBuffer, PPEReviewUnavailable
from .settings import Settings
from .store import EventInput, EventStore, iso
from .sync import CloudSyncWorker
from .temperature import SimulatedTemperatureSource, TemperatureReading, create_temperature_source
from .zones import draw_zones, zone_for

logger = logging.getLogger(__name__)


class CameraSwitchError(RuntimeError):
    pass


def _centre(box: tuple[int, int, int, int]) -> tuple[int, int]:
    x1, y1, x2, y2 = box
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def _contains(box: tuple[int, int, int, int], point: tuple[int, int]) -> bool:
    x1, y1, x2, y2 = box
    return x1 <= point[0] <= x2 and y1 <= point[1] <= y2


PPE_LABELS = {
    "mask": "Mask",
    "left_glove": "Left glove",
    "right_glove": "Right glove",
    "hairnet": "Hairnet",
    "apron": "Apron",
}


def _item_payload(item: PPEItemResult, required: bool) -> dict[str, Any]:
    return {
        "state": item.state,
        "observationState": item.observation_state,
        "confidence": item.confidence,
        "visibilityConfidence": item.visibility_confidence,
        "blueRatio": item.blue_ratio,
        "colourProfile": item.expected_colour,
        "colourRatio": item.colour_ratio,
        "threshold": item.threshold,
        "stableForMs": item.stable_for_ms,
        "side": item.side,
        "roi": list(item.roi) if item.roi else None,
        "required": required,
        "verificationMethod": item.verification_method,
        "centreRatio": item.centre_ratio,
        "componentRatio": item.component_ratio,
        "horizontalSpanRatio": item.horizontal_span_ratio,
        "verticalSpanRatio": item.vertical_span_ratio,
        "centreOffsetRatio": item.centre_offset_ratio,
        "qualityScore": item.quality_score,
        "decisionReason": item.decision_reason,
    }


def _ppe_payload(ppe: PPEResult, required_items: tuple[str, ...] = REQUIRED_ITEMS) -> dict[str, Any]:
    return {
        "mask": ppe.mask,
        "gloves": ppe.gloves,
        "hairnet": ppe.hairnet,
        "apron": ppe.apron,
        "confidence": ppe.confidence,
        "assessmentAvailable": ppe.assessment_available,
        "items": {name: _item_payload(ppe.items[name], name in required_items) for name in ITEM_ORDER},
        "readiness": {
            "brightness": ppe.readiness.brightness,
            "lightingReady": ppe.readiness.lighting_ready,
            "faceVisible": ppe.readiness.face_visible,
            "leftHandVisible": ppe.readiness.left_hand_visible,
            "rightHandVisible": ppe.readiness.right_hand_visible,
            "torsoVisible": ppe.readiness.torso_visible,
            "framingReady": ppe.readiness.framing_ready,
            "guidance": ppe.readiness.guidance,
        },
    }


class EdgePipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = EventStore(settings.database_path)
        self.enterprise = EnterpriseStore(self.store)
        self.ai = AIJobWorker(settings, self.store)
        self.operations_supervisor = OperationsSupervisor(
            settings, self.store, self.enterprise, self.ai
        )
        self.client_preflight = ClientDemoPreflight(
            settings, self.store, self.operations_supervisor
        )
        self.ppe_review = PPEReviewBuffer(
            minimum_observations=settings.ai_ppe_min_observations,
            maximum_age_seconds=settings.ai_ppe_observation_max_age_seconds,
            minimum_visibility_confidence=settings.ai_ppe_min_visibility_confidence,
        )
        self.camera = OpenCVCameraSource(settings)
        self.detector: PersonDetector | None = None
        self.marker_reader = ArucoMarkerReader()
        self.ppe_detector = LandmarkColourPPEDetector(
            mask_threshold=settings.ppe_mask_colour_ratio,
            glove_threshold=settings.ppe_glove_colour_ratio,
            hairnet_threshold=settings.ppe_hairnet_colour_ratio,
            apron_threshold=settings.ppe_apron_colour_ratio,
            mask_colour=settings.ppe_mask_colour,
            glove_colour=settings.ppe_glove_colour,
            hairnet_colour=settings.ppe_hairnet_colour,
            apron_colour=settings.ppe_apron_colour,
            keypoint_confidence=settings.ppe_keypoint_confidence,
            minimum_brightness=settings.ppe_minimum_brightness,
        )
        self.ppe_self_test_passed, self.ppe_self_test_failures = (
            self.ppe_detector.startup_self_test()
        )
        if not self.ppe_self_test_passed:
            failure = "; ".join(self.ppe_self_test_failures)
            logger.error("PPE startup self-test failed: %s", failure)
            self.ppe_detector.disable(f"PPE verifier self-test failed: {failure}")
        self.ppe_stabilizer = PPEStabilizer()
        self.required_ppe_items = REQUIRED_ITEMS + (
            (("hairnet",) if settings.ppe_require_hairnet else ())
            + (("apron",) if settings.ppe_require_apron else ())
        )
        self.evidence = EvidenceBuffer(settings.evidence_dir, self.store, settings.camera_fps)
        self.storage_ready = False
        self.storage_error: str | None = None
        try:
            self.store.health_check()
            self.evidence.health_check()
            self.storage_ready = True
        except Exception as error:
            self.storage_error = str(error)
            logger.exception("Local storage startup self-test failed")
        self.sync = CloudSyncWorker(settings, self.store)
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.lock = threading.RLock()
        self.camera_lock = threading.RLock()
        self.camera_switch_lock = threading.Lock()
        self.frame_condition = threading.Condition(self.lock)
        self.latest_jpeg: bytes | None = None
        self.latest_bgr: np.ndarray | None = None
        self.camera_online = False
        self.last_frame_at: str | None = None
        self.processed_fps = 0.0
        self._fps_frames = 0
        self._fps_started = time.monotonic()
        self._last_temperature_sample = 0.0
        self.camera_switch_state = "idle"
        self.camera_switch_message: str | None = None
        self.active_employee: dict[str, Any] | None = None
        self.active_subject_last_seen = 0.0
        self.detection_reset_generation = 0
        self.last_detection_reset_at: str | None = None
        self.employee_first_seen: dict[str, str] = {}
        self.employee_last_seen: dict[str, float] = {}
        self.track_first_seen: dict[int, str] = {}
        self.track_last_seen: dict[int, float] = {}
        self.track_employee_binding: dict[int, dict[str, Any]] = {}
        self.track_employee_binding_seen: dict[int, float] = {}
        self.track_employee_binding_verified_at: dict[int, str] = {}
        self.track_employee_binding_confidence: dict[int, float] = {}
        self.track_identity_association: dict[int, str] = {}
        self.identity_sessions: dict[str, dict[str, Any]] = {}
        self.identity_reentry_candidates: dict[int, tuple[str, float]] = {}
        self.track_paths: dict[int, deque[tuple[int, int]]] = {}
        self.movement_zone: dict[str, str] = {}
        self.movement_candidate: dict[str, tuple[str, float]] = {}
        self.movement_last_event: dict[str, float] = {}
        self.identity_missing_since: dict[int, float] = {}
        self.identity_alerted: set[int] = set()
        self.ppe_missing_since: dict[tuple[str, str], float] = {}
        self.ppe_alerted: set[tuple[str, str]] = set()
        self.ppe_alert_event_by_track_item: dict[tuple[int, str], str] = {}
        self.ppe_recovery_since: dict[tuple[str, str], float] = {}
        self.ppe_observed_at: dict[tuple[str, str], float] = {}
        self.latest_ppe_review_job_id: str | None = None
        self._last_ai_review_signature: dict[int, tuple[tuple[str, str], ...]] = {}
        self.process_state: dict[str, Any] = {
            "id": None,
            "label": "Chicken Washing",
            "status": "idle",
            "startedAt": None,
            "elapsedSeconds": 0,
            "targetMinSeconds": 120,
            "targetMaxSeconds": 180,
        }
        self.last_tray_zone: str | None = None
        self.tray_zone_candidate: tuple[str, float] | None = None
        self.process_cooldown_until = 0.0
        self.inventory_positions: dict[int, float] = {}
        self.inventory_sides: dict[int, str] = {}
        self.inventory_side_candidates: dict[int, tuple[str, float]] = {}
        self.inventory_cooldown: dict[int, float] = {}
        self.temperature_source = create_temperature_source(settings)
        initial_temperature = TemperatureReading(
            settings.temperature_sensor_id,
            settings.temperature_label,
            settings.temperature_initial_c,
            settings.temperature_min_c,
            settings.temperature_max_c,
            self.temperature_source.source_mode,
            iso(),
        )
        self.temperature: dict[str, Any] = initial_temperature.payload()
        self.livekit = LiveKitPublisher(settings, self._livekit_frame)

    @property
    def vision_source_mode(self) -> str:
        """Prerecorded fallback footage is demo data, never a real-world observation."""
        return "simulated" if self.settings.camera_kind == "file" else "real"

    @property
    def vision_source_origin(self) -> str:
        return "prerecorded_fallback" if self.settings.camera_kind == "file" else "live_camera"

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        if self.settings.camera_enabled:
            self.detector = create_detector(self.settings)
            # AVFoundation permission must be requested from the process main thread on macOS.
            self.camera_online = self.camera.open()
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, name="camera-pipeline", daemon=True)
        self.thread.start()
        self.temperature_source.start()
        self.sync.start()
        self.livekit.start()
        self.ai.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        with self.camera_lock:
            self.camera.close()
        self.temperature_source.stop()
        self.sync.stop()
        self.livekit.stop()
        self.ai.stop()

    def cameras(self) -> dict[str, Any]:
        catalog = camera_catalog(self.settings)
        catalog.update(
            {
                "switchState": self.camera_switch_state,
                "message": self.camera_switch_message,
            }
        )
        return catalog

    @staticmethod
    def _camera_has_fresh_frames(camera: OpenCVCameraSource) -> bool:
        consecutive = 0
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            ok, frame = camera.read()
            consecutive = consecutive + 1 if ok and frame is not None else 0
            if consecutive >= 2:
                return True
            time.sleep(0.1)
        return False

    def switch_camera(self, camera_id: str) -> dict[str, Any]:
        if not self.camera_switch_lock.acquire(blocking=False):
            raise CameraSwitchError("Another camera switch is already in progress.")
        try:
            self.camera_switch_state = "switching"
            self.camera_switch_message = "Checking the requested camera for fresh frames."
            catalog = camera_catalog(self.settings)
            option = next((item for item in catalog["options"] if item["id"] == camera_id), None)
            if not option:
                raise CameraSwitchError("The requested camera is not configured for this demo.")
            if option["active"] and self.camera_online:
                self.camera_switch_state = "idle"
                self.camera_switch_message = f"{option['label']} is already active."
                return self.cameras()
            if not option["registered"] or option["source"] is None:
                raise CameraSwitchError(
                    f"{option['label']} is not available. Open its camera software or reconnect the device."
                )

            # AVFoundation can fail to deliver frames when two cameras are open
            # in this process. Release the old capture before testing the new one.
            candidate_settings = self.settings.model_copy(
                update={
                    "camera_kind": option["kind"],
                    "camera_source": str(option["source"]),
                    "camera_label": option["label"],
                }
            )
            with self.camera_lock:
                previous_settings = self.settings.model_copy()
                self.camera.close()
                self.camera_online = False
                with self.frame_condition:
                    self.latest_jpeg = None
                    self.latest_bgr = None
                    self.last_frame_at = None
                    self.processed_fps = 0.0
                    self.frame_condition.notify_all()

                candidate = OpenCVCameraSource(candidate_settings)
                try:
                    if not candidate.open():
                        raise CameraSwitchError(f"{option['label']} could not be opened.")
                    if not self._camera_has_fresh_frames(candidate):
                        raise CameraSwitchError(f"{option['label']} did not provide fresh frames.")
                except Exception as error:
                    candidate.close()
                    restored = OpenCVCameraSource(previous_settings)
                    try:
                        previous_ready = restored.open() and self._camera_has_fresh_frames(restored)
                    except Exception:
                        logger.exception("Previous camera could not be restored")
                        previous_ready = False
                    self.camera = restored
                    self.camera_online = previous_ready
                    self.settings.camera_source = previous_settings.camera_source
                    self.settings.camera_label = previous_settings.camera_label
                    if not previous_ready:
                        restored.close()
                    reason = (
                        str(error)
                        if isinstance(error, CameraSwitchError)
                        else "The selected camera failed."
                    )
                    recovery = (
                        f"{previous_settings.camera_label} was restored."
                        if previous_ready
                        else (
                            f"{previous_settings.camera_label} also has no live frames. "
                            "Check its connection and retry."
                        )
                    )
                    raise CameraSwitchError(f"{reason} {recovery}") from error

                self.camera = candidate
                self.settings.camera_kind = candidate_settings.camera_kind
                self.settings.camera_source = candidate_settings.camera_source
                self.settings.camera_label = candidate_settings.camera_label
            with self.frame_condition:
                self._fps_frames = 0
                self._fps_started = time.monotonic()
                self.active_employee = None
                self.active_subject_last_seen = 0.0
                self.track_first_seen.clear()
                self.track_last_seen.clear()
                self.track_employee_binding.clear()
                self.track_employee_binding_seen.clear()
                self.track_employee_binding_verified_at.clear()
                self.track_employee_binding_confidence.clear()
                self.track_identity_association.clear()
                self.identity_sessions.clear()
                self.identity_reentry_candidates.clear()
                self.track_paths.clear()
                self.movement_zone.clear()
                self.movement_candidate.clear()
                self.movement_last_event.clear()
                self.identity_missing_since.clear()
                self.identity_alerted.clear()
                self.ppe_stabilizer.reset()
                self.ppe_missing_since.clear()
                self.ppe_alerted.clear()
                self.ppe_alert_event_by_track_item.clear()
                self.ppe_recovery_since.clear()
                self.ppe_observed_at.clear()
                self.ppe_review.clear()
                self.latest_ppe_review_job_id = None
                self._last_ai_review_signature.clear()
                self.camera_online = True
                self.frame_condition.notify_all()
            self.camera_switch_state = "idle"
            self.camera_switch_message = f"Switched to {option['label']}."
            return self.cameras()
        except CameraSwitchError as error:
            self.camera_switch_state = "failed"
            self.camera_switch_message = str(error)
            raise
        except Exception as error:
            logger.exception("Unexpected camera switch failure")
            self.camera_switch_state = "failed"
            self.camera_switch_message = (
                "The camera could not be switched. The current source remains active."
            )
            raise CameraSwitchError(self.camera_switch_message) from error
        finally:
            self.camera_switch_lock.release()

    def _run(self) -> None:
        if not self.settings.camera_enabled:
            return
        period = 1.0 / max(1, self.settings.process_fps)
        while not self.stop_event.is_set():
            started = time.monotonic()
            with self.camera_lock:
                ok, frame = self.camera.read()
            self.camera_online = ok
            if not ok or frame is None:
                self.stop_event.wait(0.2)
                continue
            if frame.shape[1] != self.settings.camera_width or frame.shape[0] != self.settings.camera_height:
                frame = cv2.resize(frame, (self.settings.camera_width, self.settings.camera_height))
            try:
                with self.lock:
                    annotated = self._process(frame)
            except Exception:
                logger.exception("Frame processing failed")
                annotated = frame
                cv2.putText(
                    annotated,
                    "DETECTION PIPELINE DEGRADED",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (70, 90, 255),
                    2,
                )
            self.evidence.add_frame(annotated)
            if time.monotonic() - self._last_temperature_sample >= 5:
                self._sample_temperature()
            encoded, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 82])
            if encoded:
                with self.frame_condition:
                    self.latest_jpeg = jpeg.tobytes()
                    self.latest_bgr = annotated.copy()
                    self.last_frame_at = iso()
                    self.frame_condition.notify_all()
            self._update_fps()
            remaining = period - (time.monotonic() - started)
            if remaining > 0:
                self.stop_event.wait(remaining)

    def _update_fps(self) -> None:
        self._fps_frames += 1
        elapsed = time.monotonic() - self._fps_started
        if elapsed >= 2:
            self.processed_fps = self._fps_frames / elapsed
            self._fps_frames = 0
            self._fps_started = time.monotonic()

    @staticmethod
    def _assign_employee_markers(
        people: list[PersonDetection], markers: list[Marker]
    ) -> dict[int, Marker]:
        """Associate each badge with at most one containing person track."""
        candidates: list[tuple[float, float, int, int, Marker]] = []
        for person in people:
            person_x, person_y = _centre(person.xyxy)
            for marker_index, marker in enumerate(markers):
                if not _contains(person.xyxy, marker.centre):
                    continue
                distance = float(
                    np.hypot(person_x - marker.centre[0], person_y - marker.centre[1])
                )
                candidates.append(
                    (distance, -marker.confidence, person.track_id, marker_index, marker)
                )
        assignments: dict[int, Marker] = {}
        assigned_markers: set[int] = set()
        for _distance, _confidence, track_id, marker_index, marker in sorted(
            candidates, key=lambda candidate: candidate[:4]
        ):
            if track_id in assignments or marker_index in assigned_markers:
                continue
            assignments[track_id] = marker
            assigned_markers.add(marker_index)
        return assignments

    def _prune_identity_sessions(self, observed_at: float) -> None:
        expired = [
            employee_id
            for employee_id, session in self.identity_sessions.items()
            if observed_at - float(session["lastSeenMonotonic"])
            > self.settings.identity_reentry_seconds
        ]
        for employee_id in expired:
            self.identity_sessions.pop(employee_id, None)
        if expired:
            expired_ids = set(expired)
            for track_id, (employee_id, _started_at) in list(
                self.identity_reentry_candidates.items()
            ):
                if employee_id in expired_ids:
                    self.identity_reentry_candidates.pop(track_id, None)

    def _reentry_assignments(
        self,
        people: list[PersonDetection],
        employee_markers: list[Marker],
        marker_by_track: dict[int, Marker],
        observed_at: float,
    ) -> dict[int, dict[str, Any]]:
        """Return one conservative non-biometric session-to-track reassociation."""
        self._prune_identity_sessions(observed_at)
        unassigned = [
            person
            for person in people
            if person.track_id not in marker_by_track
            and person.track_id not in self.track_employee_binding
        ]
        if employee_markers or len(unassigned) != 1:
            self.identity_reentry_candidates.clear()
            return {}

        visible_track_ids = {person.track_id for person in people}
        visible_employee_ids = {
            employee["employeeId"]
            for track_id, employee in self.track_employee_binding.items()
            if track_id in visible_track_ids
        }
        camera_id = camera_id_for_settings(self.settings)
        eligible = [
            session
            for employee_id, session in self.identity_sessions.items()
            if employee_id not in visible_employee_ids
            and session["cameraId"] == camera_id
            and observed_at - float(session["lastSeenMonotonic"])
            <= self.settings.identity_reentry_seconds
        ]
        if len(eligible) != 1:
            self.identity_reentry_candidates.clear()
            return {}

        person = unassigned[0]
        session = eligible[0]
        employee_id = str(session["employee"]["employeeId"])
        candidate = self.identity_reentry_candidates.get(person.track_id)
        if candidate is None or candidate[0] != employee_id:
            self.identity_reentry_candidates = {
                person.track_id: (employee_id, observed_at)
            }
            return {}
        self.identity_reentry_candidates = {person.track_id: candidate}
        if observed_at - candidate[1] < self.settings.identity_reentry_stability_seconds:
            return {}
        self.identity_reentry_candidates.pop(person.track_id, None)
        return {person.track_id: session}

    def _process(self, frame: np.ndarray) -> np.ndarray:
        height, width = frame.shape[:2]
        people = self.detector.detect(frame) if self.detector else []
        markers = self.marker_reader.read(frame)
        employee_markers = [marker for marker in markers if marker.marker_id in EMPLOYEE_MARKERS]
        review_frame = frame.copy()
        draw_zones(frame)
        self._handle_process_and_inventory(markers, frame)
        employee_marker_by_track = self._assign_employee_markers(people, employee_markers)

        observed_at = time.monotonic()
        for person in people:
            previous_track_seen = self.track_last_seen.get(person.track_id)
            if (
                previous_track_seen is not None
                and observed_at - previous_track_seen > self.settings.identity_binding_seconds
            ):
                self._clear_track_identity(person.track_id)
        reentry_by_track = self._reentry_assignments(
            people,
            employee_markers,
            employee_marker_by_track,
            observed_at,
        )

        resolved_employee = False
        resolved_subject = False
        for person in people:
            reassociation_event_id: str | None = None
            self.track_first_seen.setdefault(person.track_id, iso())
            self.track_last_seen[person.track_id] = observed_at
            matched = employee_marker_by_track.get(person.track_id)
            ppe = self.ppe_stabilizer.update(
                person.track_id,
                self.ppe_detector.detect(frame, person),
            )
            self.ppe_review.add(review_frame, person.track_id, ppe)
            person_zone = zone_for(_centre(person.xyxy), width, height)
            if matched:
                employee = EMPLOYEE_MARKERS.get(matched.marker_id)
                if employee:
                    employee = self._bind_track_identity(
                        person.track_id, employee, matched, observed_at
                    )
                    if employee["badgeMarkerId"] != matched.marker_id:
                        matched = None
            elif person.track_id in reentry_by_track:
                employee, reassociation_event_id = self._reassociate_track_identity(
                    person.track_id,
                    reentry_by_track[person.track_id],
                    observed_at,
                    person_zone,
                )
            else:
                # A badge verifies the person track once. Keep that identity for the
                # complete visible track session; the configured timeout applies only
                # after the person track disappears, never to badge occlusion.
                employee = self.track_employee_binding.get(person.track_id)
            self._draw_person(frame, person, ppe, employee, person_zone)
            if reassociation_event_id is not None:
                self.evidence.capture(reassociation_event_id, frame)
            self._check_identity(employee, person, person_zone, frame)
            if employee:
                resolved_employee = True
                resolved_subject = True
                self._check_entry(employee, person_zone, person.track_id, frame)
                self._set_active_employee(
                    employee,
                    person,
                    matched.confidence
                    if matched
                    else self.track_employee_binding_confidence.get(person.track_id, 0.5),
                    person_zone,
                    ppe,
                    badge_visible=matched is not None,
                )
                self._check_ppe(employee, person, person_zone, ppe, frame)
                self._check_movement(employee, person, person_zone, frame)
            else:
                resolved_subject = True
                if not resolved_employee:
                    self._set_active_unidentified(person, person_zone, ppe)
                self._check_ppe(None, person, person_zone, ppe, frame)
                self._check_movement(None, person, person_zone, frame)
            self._maybe_auto_ppe_review(person.track_id, ppe)

        if not resolved_subject and employee_markers:
            marker = employee_markers[0]
            employee = EMPLOYEE_MARKERS[marker.marker_id]
            marker_zone = zone_for(marker.centre, width, height)
            self.active_employee = {
                "employeeId": employee["employeeId"],
                "displayName": employee["displayName"],
                "photoUrl": employee.get("photoUrl"),
                "badgeMarkerId": employee["badgeMarkerId"],
                "identityMethod": "aruco_badge",
                "identityAssociation": "badge_visible",
                "identityVerifiedAt": iso(),
                "trackId": None,
                "zone": marker_zone,
                "activity": "Badge visible · waiting for person track",
                "enteredAt": self.employee_first_seen.get(employee["employeeId"]),
                "timeInZoneSeconds": 0,
                "badgeConfidence": marker.confidence,
                "ppe": {"mask": None, "gloves": None, "hairnet": None, "apron": None, "confidence": None},
            }
            self._check_entry(employee, marker_zone, None, frame)
            self.active_subject_last_seen = time.monotonic()
            resolved_subject = True

        now = time.monotonic()
        if not resolved_subject and self.active_employee and now - self.active_subject_last_seen > 2:
            self.active_employee = None
        for employee_id, last_seen in list(self.employee_last_seen.items()):
            if now - last_seen > 10 and employee_id not in self.identity_sessions:
                self.employee_first_seen.pop(employee_id, None)
                self.employee_last_seen.pop(employee_id, None)
        for track_id, last_seen in list(self.track_last_seen.items()):
            track_absence = now - last_seen
            if track_absence > self.settings.identity_binding_seconds:
                self._clear_track_identity(track_id)
            if track_absence > max(10, self.settings.identity_binding_seconds):
                self.track_first_seen.pop(track_id, None)
                self.track_last_seen.pop(track_id, None)
                self.track_paths.pop(track_id, None)
                self.track_employee_binding.pop(track_id, None)
                self.track_employee_binding_seen.pop(track_id, None)
                self.track_employee_binding_verified_at.pop(track_id, None)
                self.track_employee_binding_confidence.pop(track_id, None)
                subject_key = f"track:{track_id}"
                self.movement_zone.pop(subject_key, None)
                self.movement_candidate.pop(subject_key, None)
                self.movement_last_event.pop(subject_key, None)
                self.identity_missing_since.pop(track_id, None)
                self.identity_alerted.discard(track_id)
                self.ppe_stabilizer.clear_track(track_id)
                self.ppe_review.clear_track(track_id)
                self._last_ai_review_signature.pop(track_id, None)

        self._draw_markers(frame, markers)
        self._draw_header(frame)
        return frame

    def _clear_track_identity(self, track_id: int) -> None:
        """Expire only the optional identity association for one person track."""
        self.track_employee_binding.pop(track_id, None)
        self.track_employee_binding_seen.pop(track_id, None)
        self.track_employee_binding_verified_at.pop(track_id, None)
        self.track_employee_binding_confidence.pop(track_id, None)
        self.track_identity_association.pop(track_id, None)
        self.identity_reentry_candidates.pop(track_id, None)

    def _promote_transient_subject_state(self, track_id: int, employee_id: str) -> None:
        anonymous_key = f"track:{track_id}"
        for state in (
            self.ppe_missing_since,
            self.ppe_recovery_since,
            self.ppe_observed_at,
        ):
            for item in ITEM_ORDER:
                anonymous_item = (anonymous_key, item)
                employee_item = (employee_id, item)
                if anonymous_item in state and employee_item not in state:
                    state[employee_item] = state[anonymous_item]
                state.pop(anonymous_item, None)
        for item in ITEM_ORDER:
            anonymous_item = (anonymous_key, item)
            if anonymous_item in self.ppe_alerted:
                self.ppe_alerted.add((employee_id, item))
                self.ppe_alerted.discard(anonymous_item)
        for state in (
            self.movement_zone,
            self.movement_candidate,
            self.movement_last_event,
        ):
            if anonymous_key in state and employee_id not in state:
                state[employee_id] = state[anonymous_key]
            state.pop(anonymous_key, None)

    def _demote_transient_subject_state(self, track_id: int, employee_id: str) -> None:
        anonymous_key = f"track:{track_id}"
        for state in (
            self.ppe_missing_since,
            self.ppe_recovery_since,
            self.ppe_observed_at,
        ):
            for item in ITEM_ORDER:
                employee_item = (employee_id, item)
                anonymous_item = (anonymous_key, item)
                if employee_item in state and anonymous_item not in state:
                    state[anonymous_item] = state[employee_item]
                state.pop(employee_item, None)
        for item in ITEM_ORDER:
            employee_item = (employee_id, item)
            if employee_item in self.ppe_alerted:
                self.ppe_alerted.add((anonymous_key, item))
                self.ppe_alerted.discard(employee_item)
        for state in (
            self.movement_zone,
            self.movement_candidate,
            self.movement_last_event,
        ):
            if employee_id in state and anonymous_key not in state:
                state[anonymous_key] = state[employee_id]
            state.pop(employee_id, None)

    def _associate_track_identity(
        self,
        track_id: int,
        employee: dict[str, Any],
        observed_at: float,
        *,
        verified_at: str,
        badge_confidence: float,
        association: str,
    ) -> tuple[dict[str, Any], str]:
        previous = self.track_employee_binding.get(track_id)
        if previous is not None and previous["employeeId"] != employee["employeeId"]:
            return previous
        if previous is None:
            self._promote_transient_subject_state(track_id, employee["employeeId"])
        self.track_employee_binding[track_id] = employee
        self.track_employee_binding_seen[track_id] = observed_at
        self.track_employee_binding_verified_at[track_id] = verified_at
        self.track_employee_binding_confidence[track_id] = badge_confidence
        self.track_identity_association[track_id] = association
        return employee

    def _bind_track_identity(
        self,
        track_id: int,
        employee: dict[str, Any],
        marker: Marker,
        observed_at: float,
    ) -> dict[str, Any]:
        """Verify a badge and preserve transient state while resolving its track."""
        previous = self.track_employee_binding.get(track_id)
        if previous is not None and previous["employeeId"] != employee["employeeId"]:
            # Never replace an active session identity with a conflicting badge in
            # the same track. A reset/expiry must establish a new session first.
            return previous
        verified_at = iso()
        associated = self._associate_track_identity(
            track_id,
            employee,
            observed_at,
            verified_at=verified_at,
            badge_confidence=marker.confidence,
            association="badge",
        )
        if associated["employeeId"] == employee["employeeId"]:
            self.identity_sessions[employee["employeeId"]] = {
                "employee": employee,
                "cameraId": camera_id_for_settings(self.settings),
                "verifiedAt": verified_at,
                "badgeConfidence": marker.confidence,
                "lastTrackId": track_id,
                "lastSeenMonotonic": observed_at,
                "lastSeenAt": verified_at,
                "previousTrackId": None,
                "reassociatedAt": None,
            }
        return associated

    def _reassociate_track_identity(
        self,
        track_id: int,
        session: dict[str, Any],
        observed_at: float,
        zone: str,
    ) -> dict[str, Any]:
        employee = session["employee"]
        employee_id = employee["employeeId"]
        previous_track_id = int(session["lastTrackId"])
        gap_seconds = max(0.0, observed_at - float(session["lastSeenMonotonic"]))
        for bound_track_id, bound_employee in list(self.track_employee_binding.items()):
            if bound_track_id != track_id and bound_employee["employeeId"] == employee_id:
                self._clear_track_identity(bound_track_id)
        associated = self._associate_track_identity(
            track_id,
            employee,
            observed_at,
            verified_at=str(session["verifiedAt"]),
            badge_confidence=float(session["badgeConfidence"]),
            association="session_reentry",
        )
        reassociated_at = iso()
        session.update(
            {
                "lastTrackId": track_id,
                "lastSeenMonotonic": observed_at,
                "lastSeenAt": reassociated_at,
                "previousTrackId": previous_track_id,
                "reassociatedAt": reassociated_at,
            }
        )
        event = self.store.add_event(
            EventInput(
                type="identity_session_reassociated",
                title=f"{employee['displayName']} session reassociated",
                detail=(
                    "One returning track was associated with the only eligible remembered "
                    "badge session on this camera; the badge is not currently visible."
                ),
                severity="info",
                source_mode=self.vision_source_mode,
                employee_id=employee_id,
                employee_name=employee["displayName"],
                zone=zone,
                confidence=None,
                track_id=track_id,
            ),
            metadata={
                "source_origin": self.vision_source_origin,
                "identity_method": "session_reentry",
                "badge_marker_id": employee["badgeMarkerId"],
                "badge_verified_at": session["verifiedAt"],
                "previous_track_id": previous_track_id,
                "new_track_id": track_id,
                "absence_seconds": round(gap_seconds, 3),
                "reentry_window_seconds": self.settings.identity_reentry_seconds,
                "camera_id": session["cameraId"],
                "biometric_matching": False,
            },
        )
        return associated, event["id"]

    def _set_active_employee(
        self,
        employee: dict[str, str],
        person: PersonDetection,
        badge_confidence: float,
        person_zone: str,
        ppe: PPEResult,
        *,
        badge_visible: bool,
    ) -> None:
        employee_id = employee["employeeId"]
        observed_at = time.monotonic()
        entered = self.employee_first_seen.setdefault(employee_id, iso())
        self.employee_last_seen[employee_id] = observed_at
        self.active_subject_last_seen = observed_at
        session = self.identity_sessions.get(employee_id)
        if session is not None:
            session["lastTrackId"] = person.track_id
            session["lastSeenMonotonic"] = observed_at
            session["lastSeenAt"] = iso()
        association = (
            "badge_visible"
            if badge_visible
            else "session_reentry"
            if self.track_identity_association.get(person.track_id) == "session_reentry"
            else "track_session"
        )
        elapsed = max(
            0,
            int((datetime.now(UTC) - datetime.fromisoformat(entered.replace("Z", "+00:00"))).total_seconds()),
        )
        self.active_employee = {
            "employeeId": employee_id,
            "displayName": employee["displayName"],
            "photoUrl": employee.get("photoUrl"),
            "badgeMarkerId": employee["badgeMarkerId"],
            "identityMethod": "aruco_badge",
            "identityAssociation": association,
            "identityVerifiedAt": self.track_employee_binding_verified_at.get(person.track_id),
            "identityReassociatedAt": session.get("reassociatedAt") if session else None,
            "identityPreviousTrackId": session.get("previousTrackId") if session else None,
            "identitySessionWindowSeconds": self.settings.identity_reentry_seconds,
            "identitySessionExpiresInSeconds": self.settings.identity_reentry_seconds,
            "trackId": person.track_id,
            "zone": person_zone,
            "activity": self._activity_context(person_zone),
            "enteredAt": entered,
            "timeInZoneSeconds": elapsed,
            "badgeConfidence": badge_confidence,
            "personConfidence": person.confidence,
            "ppe": _ppe_payload(ppe, self.required_ppe_items),
        }

    def _set_active_unidentified(
        self,
        person: PersonDetection,
        person_zone: str,
        ppe: PPEResult,
    ) -> None:
        """Expose PPE state for a person even when no identity source is available."""
        entered = self.track_first_seen.setdefault(person.track_id, iso())
        observed_at = time.monotonic()
        self.track_last_seen[person.track_id] = observed_at
        self.active_subject_last_seen = observed_at
        elapsed = max(
            0,
            int((datetime.now(UTC) - datetime.fromisoformat(entered.replace("Z", "+00:00"))).total_seconds()),
        )
        self.active_employee = {
            "employeeId": None,
            "displayName": "Unidentified staff member",
            "photoUrl": None,
            "badgeMarkerId": None,
            "identityAssociation": "not_associated",
            "identityVerifiedAt": None,
            "trackId": person.track_id,
            "zone": person_zone,
            "activity": self._activity_context(person_zone),
            "enteredAt": entered,
            "timeInZoneSeconds": elapsed,
            "badgeConfidence": None,
            "personConfidence": person.confidence,
            "ppe": _ppe_payload(ppe, self.required_ppe_items),
        }

    def _activity_context(self, person_zone: str) -> str:
        """Describe only operational context supported by zone and SOP state."""
        if self.process_state["status"] == "running" and person_zone in {
            "Preparation",
            "Process Start",
            "Process Complete",
        }:
            return f"{self.process_state['label']} · in progress"
        if self.process_state["status"] == "complete" and person_zone == "Process Complete":
            return f"{self.process_state['label']} · completed"
        if person_zone == "Preparation":
            return "Present in preparation area · no active tagged process"
        return f"Present in {person_zone}"

    def _check_entry(
        self,
        employee: dict[str, str],
        zone: str,
        track_id: int | None,
        frame: np.ndarray,
    ) -> None:
        employee_id = employee["employeeId"]
        first = employee_id not in self.employee_first_seen
        self.employee_first_seen.setdefault(employee_id, iso())
        self.employee_last_seen[employee_id] = time.monotonic()
        if first:
            event = self.store.add_event(
                EventInput(
                    type="employee_entry",
                    title=f"{employee['displayName']} identified",
                    detail=(
                        f"Demo employee identity resolved from ArUco badge {employee['badgeMarkerId']}; "
                        "no facial recognition was used."
                    ),
                    severity="info",
                    source_mode=self.vision_source_mode,
                    employee_id=employee_id,
                    employee_name=employee["displayName"],
                    zone=zone,
                    confidence=0.99,
                    track_id=track_id,
                ),
                metadata={
                    "source_origin": self.vision_source_origin,
                    "identity_method": "aruco_badge",
                    "badge_marker_id": employee["badgeMarkerId"],
                },
            )
            self.evidence.capture(event["id"], frame)

    def _check_ppe(
        self,
        employee: dict[str, str] | None,
        person: PersonDetection,
        zone: str,
        ppe: PPEResult,
        frame: np.ndarray,
    ) -> None:
        if zone not in {"Preparation", "Process Start", "Process Complete"}:
            return
        employee_id = employee["employeeId"] if employee else None
        display_name = employee["displayName"] if employee else "Unidentified staff member"
        subject_key = employee_id or f"track:{person.track_id}"
        now = time.monotonic()
        violation_created = False
        for item in ITEM_ORDER:
            assessment = ppe.items[item]
            key = (subject_key, item)
            if now - self.ppe_observed_at.get(key, 0) >= 30:
                observed_value = (
                    True
                    if assessment.state == "detected"
                    else False
                    if assessment.state == "missing"
                    else None
                )
                self.enterprise.record_ppe(
                    employee_id,
                    item,
                    observed_value,
                    assessment.confidence,
                    self.vision_source_mode,
                )
                self.ppe_observed_at[key] = now

            if item not in self.required_ppe_items:
                continue

            if assessment.state == "detected":
                self.ppe_missing_since.pop(key, None)
                if key not in self.ppe_alerted:
                    self.ppe_recovery_since.pop(key, None)
                    continue
                # A stabilized recovery may outlive a contrary frame. Retain
                # evidence only when the current observation also supports it.
                if assessment.observation_state not in {None, "detected"}:
                    continue
                recovered_since = self.ppe_recovery_since.setdefault(key, now)
                if now - recovered_since < self.settings.ppe_recovery_seconds:
                    continue
                event = self.store.add_event(
                    EventInput(
                        type="ppe_compliance_restored",
                        title=f"{PPE_LABELS[item]} compliance restored",
                        detail=(
                            f"{PPE_LABELS[item]} remained detected for "
                            f"{self.settings.ppe_recovery_seconds:.0f} seconds after a violation."
                        ),
                        severity="info",
                        source_mode=self.vision_source_mode,
                        employee_id=employee_id,
                        employee_name=display_name,
                        zone=zone,
                        confidence=assessment.confidence,
                        track_id=person.track_id,
                    ),
                    metadata=self._ppe_evidence_metadata(
                        item, assessment, ppe, True, employee_id is not None
                    ),
                )
                self.evidence.capture(event["id"], frame)
                self.ppe_alerted.discard(key)
                self.ppe_alert_event_by_track_item.pop((person.track_id, item), None)
                self.ppe_recovery_since.pop(key, None)
                continue

            self.ppe_recovery_since.pop(key, None)
            if assessment.state != "missing":
                self.ppe_missing_since.pop(key, None)
                continue
            since = self.ppe_missing_since.setdefault(key, now)
            if now - since < self.settings.ppe_persistence_seconds or key in self.ppe_alerted:
                continue
            # Rolling consensus intentionally resists one-frame changes, but a
            # retained snapshot and its measurements must support the alert.
            if assessment.observation_state not in {None, "missing"}:
                continue
            # Retain deterministic safety ordering even when several items become
            # stable in the same frame. The next item is emitted on the next frame.
            if violation_created:
                continue
            event = self.store.add_event(
                EventInput(
                    type="ppe_violation",
                    title=f"{PPE_LABELS[item]} not detected",
                    detail=(
                        f"Landmark-gated controlled-scene PPE vision did not detect "
                        f"{PPE_LABELS[item].lower()} for "
                        f"{self.settings.ppe_persistence_seconds:.0f} seconds."
                    ),
                    severity="critical",
                    source_mode=self.vision_source_mode,
                    employee_id=employee_id,
                    employee_name=display_name,
                    zone=zone,
                    confidence=assessment.confidence,
                    track_id=person.track_id,
                ),
                metadata=self._ppe_evidence_metadata(
                    item, assessment, ppe, False, employee_id is not None
                ),
            )
            self.evidence.capture(event["id"], frame)
            self.ppe_alerted.add(key)
            self.ppe_alert_event_by_track_item[(person.track_id, item)] = event["id"]
            violation_created = True

    def _ppe_evidence_metadata(
        self,
        item: str,
        assessment: PPEItemResult,
        ppe: PPEResult,
        recovered: bool,
        identity_resolved: bool,
    ) -> dict[str, Any]:
        return {
            "ppe_model": self.ppe_detector.label,
            "pose_model": self.settings.detector_model,
            "controlled_scene": True,
            "source_origin": self.vision_source_origin,
            "camera_label": self.settings.camera_label,
            "identity_resolved": identity_resolved,
            "item": item,
            "side": assessment.side,
            "state": "detected" if recovered else "missing",
            "observation_state": assessment.observation_state,
            "visibility_confidence": assessment.visibility_confidence,
            "decision_confidence": assessment.confidence,
            "blue_ratio": assessment.blue_ratio,
            "colour_profile": assessment.expected_colour,
            "colour_ratio": assessment.colour_ratio,
            "threshold": assessment.threshold,
            "verification_method": assessment.verification_method,
            "centre_ratio": assessment.centre_ratio,
            "component_ratio": assessment.component_ratio,
            "horizontal_span_ratio": assessment.horizontal_span_ratio,
            "vertical_span_ratio": assessment.vertical_span_ratio,
            "centre_offset_ratio": assessment.centre_offset_ratio,
            "quality_score": assessment.quality_score,
            "decision_reason": assessment.decision_reason,
            "stable_for_ms": assessment.stable_for_ms,
            "brightness": ppe.readiness.brightness,
            "framing_ready": ppe.readiness.framing_ready,
            "roi": list(assessment.roi) if assessment.roi else None,
        }

    def _check_identity(
        self,
        employee: dict[str, str] | None,
        person: PersonDetection,
        zone: str,
        frame: np.ndarray,
    ) -> None:
        """Retain one proof-backed unresolved-identity event after persistence.

        Identity remains optional for PPE evaluation; this event records the observation
        without blocking mask, glove, hairnet, or apron checks.
        """
        track_id = person.track_id
        if employee is not None:
            self.identity_missing_since.pop(track_id, None)
            self.identity_alerted.discard(track_id)
            return
        since = self.identity_missing_since.setdefault(track_id, time.monotonic())
        if (
            time.monotonic() - since < self.settings.identity_persistence_seconds
            or track_id in self.identity_alerted
        ):
            return
        event = self.store.add_event(
            EventInput(
                type="identity_unresolved",
                title="Person ID not detected",
                detail=(
                    "Person tracking and PPE evaluation continued without an associated employee "
                    f"identity for {self.settings.identity_persistence_seconds:.0f} seconds."
                ),
                severity="info",
                source_mode=self.vision_source_mode,
                employee_name="Unidentified staff member",
                zone=zone,
                confidence=person.confidence,
                track_id=track_id,
            ),
            metadata={
                "source_origin": self.vision_source_origin,
                "identity_resolved": False,
                "identity_required_for_ppe": False,
                "persistence_seconds": self.settings.identity_persistence_seconds,
            },
        )
        self.evidence.capture(event["id"], frame)
        self.identity_alerted.add(track_id)

    def _check_movement(
        self,
        employee: dict[str, str] | None,
        person: PersonDetection,
        zone: str,
        frame: np.ndarray,
    ) -> None:
        """Record stable zone transitions; frame-by-frame movement remains a visual trail."""
        subject_key = employee["employeeId"] if employee else f"track:{person.track_id}"
        current_zone = self.movement_zone.get(subject_key)
        now = time.monotonic()
        if current_zone is None:
            self.movement_zone[subject_key] = zone
            return
        if zone == current_zone:
            self.movement_candidate.pop(subject_key, None)
            return
        candidate = self.movement_candidate.get(subject_key)
        if candidate is None or candidate[0] != zone:
            self.movement_candidate[subject_key] = (zone, now)
            return
        if now - candidate[1] < 1.0 or now - self.movement_last_event.get(subject_key, 0) < 5:
            return

        display_name = employee["displayName"] if employee else "Unidentified staff member"
        employee_id = employee["employeeId"] if employee else None
        event = self.store.add_event(
            EventInput(
                type="staff_movement",
                title=f"{display_name} moved to {zone}",
                detail=f"Tracked movement from {current_zone} to {zone} was stable for 1 second.",
                severity="info",
                source_mode=self.vision_source_mode,
                employee_id=employee_id,
                employee_name=display_name,
                zone=zone,
                confidence=person.confidence,
                track_id=person.track_id,
            ),
            metadata={
                "source_origin": self.vision_source_origin,
                "from_zone": current_zone,
                "to_zone": zone,
                "identity_resolved": employee_id is not None,
                "movement_rule": "stable_zone_transition_1s",
            },
        )
        self.evidence.capture(event["id"], frame)
        self.movement_zone[subject_key] = zone
        self.movement_candidate.pop(subject_key, None)
        self.movement_last_event[subject_key] = now

    def _handle_process_and_inventory(self, markers: list[Marker], frame: np.ndarray) -> None:
        height, width = frame.shape[:2]
        now = time.monotonic()
        tray = next((marker for marker in markers if marker.marker_id in TRAY_MARKERS), None)
        if tray:
            tray_zone = zone_for(tray.centre, width, height, ("Process Start", "Process Complete"))
            if tray_zone not in {"Process Start", "Process Complete"} or tray_zone == self.last_tray_zone:
                self.tray_zone_candidate = None
            elif self.tray_zone_candidate is None or self.tray_zone_candidate[0] != tray_zone:
                self.tray_zone_candidate = (tray_zone, now)
            elif now - self.tray_zone_candidate[1] >= self.settings.process_marker_dwell_seconds:
                if tray_zone == "Process Start" and self.process_state["status"] != "running":
                    self._start_process(self.vision_source_mode, frame)
                elif tray_zone == "Process Complete" and self.process_state["status"] == "running":
                    self._complete_process(self.vision_source_mode, frame)
                self.last_tray_zone = tray_zone
                self.tray_zone_candidate = None
        else:
            self.tray_zone_candidate = None

        line = self.settings.inventory_line_position
        hysteresis = self.settings.inventory_line_hysteresis
        for marker in markers:
            if marker.marker_id not in INVENTORY_MARKERS:
                continue
            x_normalized = marker.centre[0] / width
            self.inventory_positions[marker.marker_id] = x_normalized
            observed_side = (
                "left"
                if x_normalized <= line - hysteresis
                else "right"
                if x_normalized >= line + hysteresis
                else None
            )
            if observed_side is None:
                self.inventory_side_candidates.pop(marker.marker_id, None)
                continue
            confirmed_side = self.inventory_sides.get(marker.marker_id)
            if confirmed_side is None:
                self.inventory_sides[marker.marker_id] = observed_side
                continue
            if observed_side == confirmed_side:
                self.inventory_side_candidates.pop(marker.marker_id, None)
                continue
            candidate = self.inventory_side_candidates.get(marker.marker_id)
            if candidate is None or candidate[0] != observed_side:
                self.inventory_side_candidates[marker.marker_id] = (observed_side, now)
                continue
            if (
                now - candidate[1] < self.settings.inventory_marker_dwell_seconds
                or now < self.inventory_cooldown.get(marker.marker_id, 0)
            ):
                continue
            direction = "in" if confirmed_side == "left" and observed_side == "right" else "out"
            self._inventory_movement(
                INVENTORY_MARKERS[marker.marker_id],
                direction,
                1,
                self.vision_source_mode,
                frame,
            )
            self.inventory_sides[marker.marker_id] = observed_side
            self.inventory_side_candidates.pop(marker.marker_id, None)
            cooldown = 30 if self.settings.camera_kind == "file" else 3
            self.inventory_cooldown[marker.marker_id] = now + cooldown

    def _start_process(
        self,
        source_mode: str,
        frame: np.ndarray | None = None,
        source_origin: str | None = None,
    ) -> None:
        origin = source_origin or (self.vision_source_origin if frame is not None else "demo_control")
        if self.process_state["status"] == "running":
            return
        if origin == "prerecorded_fallback" and time.monotonic() < self.process_cooldown_until:
            return
        run = self.store.start_process("Chicken Washing", source_mode)
        self.process_state.update(run)
        self.process_state.update({"targetMinSeconds": 120, "targetMaxSeconds": 180})
        event = self.store.add_event(
            EventInput(
                type="process_started",
                title="Chicken Washing started",
                detail=(
                    "Tagged tray TRAY-01 entered Process Start."
                    if origin == "live_camera"
                    else "Prerecorded fallback: tagged tray TRAY-01 entered Process Start."
                    if origin == "prerecorded_fallback"
                    else "Operator used the simulated process-start control."
                ),
                severity="info",
                source_mode=source_mode,
                employee_id=self.active_employee["employeeId"] if self.active_employee else None,
                employee_name=self.active_employee["displayName"] if self.active_employee else None,
                zone="Process Start",
                confidence=1.0 if origin == "demo_control" else 0.98,
            ),
            metadata={
                "run_id": run["id"],
                "label": run["label"],
                "source_origin": origin,
            },
        )
        if frame is not None:
            self.evidence.capture(event["id"], frame)

    def _complete_process(
        self,
        source_mode: str,
        frame: np.ndarray | None = None,
        source_origin: str | None = None,
    ) -> None:
        run_id = self.process_state.get("id")
        if not run_id:
            return
        origin = source_origin or (self.vision_source_origin if frame is not None else "demo_control")
        elapsed = self.store.complete_process(run_id)
        self.process_state.update({"status": "complete", "elapsedSeconds": elapsed})
        if origin == "prerecorded_fallback":
            self.process_cooldown_until = time.monotonic() + 120
        event = self.store.add_event(
            EventInput(
                type="process_complete",
                title="Chicken Washing completed",
                detail=f"Process completed in {elapsed} seconds.",
                severity="info",
                source_mode=source_mode,
                employee_id=self.active_employee["employeeId"] if self.active_employee else None,
                employee_name=self.active_employee["displayName"] if self.active_employee else None,
                zone="Process Complete",
                confidence=1.0 if origin == "demo_control" else 0.98,
            ),
            metadata={
                "run_id": run_id,
                "elapsed_seconds": elapsed,
                "source_origin": origin,
            },
        )
        if frame is not None:
            self.evidence.capture(event["id"], frame)

    def _inventory_movement(
        self,
        sku: str,
        direction: str,
        quantity: int,
        source_mode: str,
        frame: np.ndarray | None = None,
        source_origin: str | None = None,
    ) -> None:
        origin = source_origin or (self.vision_source_origin if frame is not None else "demo_control")
        new_quantity = self.store.move_inventory(sku, direction, quantity)
        confidence = 1.0 if origin == "demo_control" else 0.96
        self.store.record_inventory_transaction(
            sku,
            direction,
            quantity,
            self.active_employee["employeeId"] if self.active_employee else None,
            confidence,
            source_mode,
        )
        event = self.store.add_event(
            EventInput(
                type="inventory_movement",
                title=f"{sku} stock {direction}",
                detail=f"{quantity} item moved {direction}; recorded quantity is now {new_quantity}.",
                severity="info",
                source_mode=source_mode,
                employee_id=self.active_employee["employeeId"] if self.active_employee else None,
                employee_name=self.active_employee["displayName"] if self.active_employee else None,
                zone="Inventory",
                confidence=confidence,
            ),
            metadata={
                "sku": sku,
                "direction": direction,
                "quantity": quantity,
                "resulting_quantity": new_quantity,
                "source_origin": origin,
            },
        )
        if frame is not None:
            self.evidence.capture(event["id"], frame)

    def _draw_person(
        self,
        frame: np.ndarray,
        person: PersonDetection,
        ppe: PPEResult,
        employee: dict[str, str] | None,
        zone: str,
    ) -> None:
        x1, y1, x2, y2 = person.xyxy
        missing = [
            ppe.items[item]
            for item in self.required_ppe_items
            if ppe.items[item].state == "missing"
        ]
        required_compliant = all(
            ppe.items[item].state == "detected" for item in self.required_ppe_items
        )
        attention_required = bool(missing)
        observing = not attention_required and not required_compliant
        colour = (42, 42, 225) if attention_required else (44, 153, 224) if observing else (83, 180, 112)
        path = self.track_paths.setdefault(person.track_id, deque(maxlen=28))
        path.append(_centre(person.xyxy))
        if len(path) > 1:
            points = np.array(path, dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(frame, [points], False, colour, 2, cv2.LINE_AA)
        for point in list(path)[-5:]:
            cv2.circle(frame, point, 3, colour, -1, cv2.LINE_AA)
        cv2.rectangle(frame, (x1, y1), (x2, y2), colour, 3)
        identity = employee["displayName"] if employee else f"Unidentified staff | Track {person.track_id}"
        label_width = min(frame.shape[1] - x1, 320)
        cv2.rectangle(frame, (x1, max(0, y1 - 48)), (x1 + label_width, y1), (11, 18, 20), -1)
        cv2.rectangle(frame, (x1, max(0, y1 - 48)), (x1 + label_width, y1), colour, 1)
        cv2.putText(
            frame, identity, (x1 + 7, y1 - 28), cv2.FONT_HERSHEY_SIMPLEX, 0.48, colour, 1, cv2.LINE_AA
        )
        status = "ACTION REQUIRED" if attention_required else "ASSESSING PPE" if observing else "COMPLIANT"
        cv2.putText(
            frame,
            f"{status} | {zone} | person {person.confidence:.0%}",
            (x1 + 7, y1 - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.36,
            colour if attention_required else (190, 220, 199),
            1,
            cv2.LINE_AA,
        )
        if attention_required:
            badge_size = 30
            badge_left = max(x1, x2 - badge_size)
            badge_top = max(34, y1)
            badge_bottom = min(frame.shape[0] - 1, badge_top + badge_size)
            cv2.rectangle(frame, (badge_left, badge_top), (x2, badge_bottom), colour, -1)
            inset = 8
            cv2.line(
                frame,
                (badge_left + inset, badge_top + inset),
                (x2 - inset, badge_bottom - inset),
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            cv2.line(
                frame,
                (x2 - inset, badge_top + inset),
                (badge_left + inset, badge_bottom - inset),
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

        roi_colours = {
            "missing": (42, 42, 225),
            "detected": (83, 180, 112),
            "checking": (44, 153, 224),
        }
        for item_name in ITEM_ORDER:
            item = ppe.items[item_name]
            if item.roi is None or item.state not in roi_colours:
                continue
            rx1, ry1, rx2, ry2 = item.roi
            roi_colour = roi_colours[item.state]
            cv2.rectangle(frame, (rx1, ry1), (rx2, ry2), roi_colour, 2)
            cv2.putText(
                frame,
                f"{PPE_LABELS[item_name].upper()} {item.state.upper()}",
                (rx1, max(36, ry1 - 5)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.32,
                roi_colour,
                1,
                cv2.LINE_AA,
            )

    @staticmethod
    def _draw_markers(frame: np.ndarray, markers: list[Marker]) -> None:
        for marker in markers:
            points = marker.corners.astype(np.int32)
            cv2.polylines(frame, [points], True, (225, 200, 99), 2, cv2.LINE_AA)
            cv2.circle(frame, marker.centre, 3, (225, 200, 99), -1)
            cv2.putText(
                frame,
                f"TAG {marker.marker_id}",
                (marker.centre[0] + 6, marker.centre[1] - 6),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (225, 200, 99),
                1,
                cv2.LINE_AA,
            )

    def _draw_header(self, frame: np.ndarray) -> None:
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 32), (7, 11, 12), -1)
        detector_label = self.detector.label if self.detector else "DETECTOR OFF"
        label = f"ORVIA AI SURVEILLANCE - CAM-01 - {detector_label} - NO AUDIO"
        cv2.putText(frame, label, (12, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (203, 218, 213), 1, cv2.LINE_AA)

    def frames(self):
        last_frame = None
        while not self.stop_event.is_set():
            with self.frame_condition:
                if self.latest_jpeg is None or self.latest_jpeg is last_frame:
                    self.frame_condition.wait(timeout=2)
                frame = self.latest_jpeg
            if frame is None:
                continue
            last_frame = frame
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"

    def request_ppe_review(self) -> dict[str, Any]:
        """Queue an advisory review from fresh server-selected PPE observations."""
        with self.lock:
            track_id = self.active_employee.get("trackId") if self.active_employee else None
            if track_id is None:
                raise PPEReviewUnavailable(
                    "No tracked person is available. Stand in view and wait for PPE assessment."
                )
            return self._create_ppe_review(int(track_id), trigger="manual")

    def _create_ppe_review(self, track_id: int, *, trigger: str) -> dict[str, Any]:
        bundle = self.ppe_review.build(track_id)
        event_ids = [
            event_id
            for item in ("mask", "left_glove", "right_glove")
            if (event_id := self.ppe_alert_event_by_track_item.get((track_id, item)))
        ]
        source_record_ids = list(dict.fromkeys(event_ids))
        frame_reference = f"camera-state:{self.last_frame_at or iso()}"
        source_record_ids.append(frame_reference)
        signature = tuple(sorted(bundle.local_decisions.items()))
        job = self.ai.create_ppe_review_job(
            images=bundle.images,
            regions=bundle.regions,
            local_decisions=bundle.local_decisions,
            source_record_ids=source_record_ids,
            metadata={
                **bundle.metadata,
                "trigger": trigger,
                "cameraSource": self.settings.camera_label,
                "sourceMode": self.vision_source_mode,
                "frameReference": frame_reference,
            },
            dedupe_key=f"{track_id}:{signature}",
        )
        self.latest_ppe_review_job_id = str(job["id"])
        return job

    def _maybe_auto_ppe_review(self, track_id: int, ppe: PPEResult) -> None:
        if not self.settings.ai_ppe_auto_review_enabled or not self.ai.status()["available"]:
            return
        stable = tuple(
            (item, ppe.items[item].state)
            for item in ("mask", "left_glove", "right_glove")
            if ppe.items[item].state in {"detected", "missing"}
        )
        if not stable or self._last_ai_review_signature.get(track_id) == stable:
            return
        missing_items = [item for item, state in stable if state == "missing"]
        if any(
            (track_id, item) not in self.ppe_alert_event_by_track_item
            for item in missing_items
        ):
            return
        try:
            job = self._create_ppe_review(track_id, trigger="automatic")
        except PPEReviewUnavailable:
            return
        if job["status"] in {"queued", "analyzing", "completed", "needs_review"}:
            self._last_ai_review_signature[track_id] = stable

    def _ai_ppe_assurance_state(self) -> dict[str, Any]:
        track_id = self.active_employee.get("trackId") if self.active_employee else None
        readiness = self.ppe_review.readiness(int(track_id) if track_id is not None else None)
        job = None
        if self.latest_ppe_review_job_id:
            try:
                job = self.store.get_ai_job(self.latest_ppe_review_job_id)
            except KeyError:
                self.latest_ppe_review_job_id = None
        return {
            "provider": self.ai.status(),
            "readiness": readiness,
            "latestJob": job,
            "advisoryOnly": True,
            "localDecisionAuthoritative": True,
        }

    def state(self) -> dict[str, Any]:
        now = iso()
        monitoring_state, monitoring_message = self._automatic_monitoring_status()
        process = dict(self.process_state)
        if process["status"] == "running" and process["startedAt"]:
            process["elapsedSeconds"] = max(
                0,
                int(
                    (
                        datetime.now(UTC)
                        - datetime.fromisoformat(process["startedAt"].replace("Z", "+00:00"))
                    ).total_seconds()
                ),
            )
        detector_label = self.detector.label if self.detector else "Detector initializing"
        events = self.store.list_events(limit=8)
        cloud_state = "online" if self.sync.configured and self.sync.online else "degraded"
        return {
            "health": {
                "edge": "online",
                "camera": "online" if self.camera_online else "offline",
                "cloud": cloud_state,
                "livekit": (
                    "online" if self.livekit.online else "degraded" if self.livekit.configured else "offline"
                ),
                "stream": "online" if self.latest_jpeg else "offline",
                "sensor": "online" if self.temperature_source.online else "offline",
                "storage": "online" if self.storage_ready else "offline",
                "storageError": self.storage_error,
                "temperatureSource": {
                    "kind": self.settings.temperature_source,
                    "sourceMode": self.temperature_source.source_mode,
                    "error": self.temperature_source.error,
                },
                "cameraLabel": self.settings.camera_label,
                "cameraId": camera_id_for_settings(self.settings),
                "sourceType": self.settings.camera_kind,
                "cameraSwitchState": self.camera_switch_state,
                "cameraSwitchMessage": self.camera_switch_message,
                "modelLabel": f"{detector_label} · {self.ppe_detector.label}",
                "ppeVerifier": {
                    "status": "passed" if self.ppe_self_test_passed else "failed",
                    "automaticSelfTest": True,
                    "failures": self.ppe_self_test_failures,
                },
                "processedFps": round(self.processed_fps, 1),
                "automaticMonitoring": monitoring_state,
                "monitoringMessage": monitoring_message,
                "queueDepth": self.store.queue_depth(),
                "lastFrameAt": self.last_frame_at,
                "updatedAt": now,
            },
            "activeEmployee": self.active_employee,
            "identitySessions": self._identity_sessions_state(),
            "detection": self._detection_state(),
            "aiPpeAssurance": self._ai_ppe_assurance_state(),
            "process": process,
            "temperature": self.temperature,
            "inventory": self.store.inventory(),
            "recentEvents": events,
        }

    def run_ai_operation(self, action: str) -> dict[str, Any]:
        return self.operations_supervisor.run(action)

    def ai_feature_readiness(self) -> dict[str, Any]:
        return {
            "items": self.operations_supervisor.features(),
            "advisoryOnly": True,
            "localRecordsAuthoritative": True,
        }

    def client_demo_preflight(self) -> dict[str, Any]:
        return self.client_preflight.status(self.state())

    def _identity_sessions_state(self) -> list[dict[str, Any]]:
        observed_at = time.monotonic()
        sessions: list[dict[str, Any]] = []
        for employee_id, session in self.identity_sessions.items():
            elapsed = max(0.0, observed_at - float(session["lastSeenMonotonic"]))
            remaining = max(0, int(self.settings.identity_reentry_seconds - elapsed + 0.999))
            sessions.append(
                {
                    "employeeId": employee_id,
                    "displayName": session["employee"]["displayName"],
                    "badgeMarkerId": session["employee"]["badgeMarkerId"],
                    "cameraId": session["cameraId"],
                    "status": "active" if elapsed <= 2 else "dormant",
                    "lastTrackId": session["lastTrackId"],
                    "verifiedAt": session["verifiedAt"],
                    "lastSeenAt": session["lastSeenAt"],
                    "reassociatedAt": session.get("reassociatedAt"),
                    "expiresInSeconds": remaining,
                    "windowSeconds": int(self.settings.identity_reentry_seconds),
                    "association": self.track_identity_association.get(
                        int(session["lastTrackId"]), "remembered"
                    ),
                }
            )
        return sorted(sessions, key=lambda item: item["displayName"])

    def _automatic_monitoring_status(self) -> tuple[str, str]:
        """Report whether the always-on local detection loop can evaluate new frames."""
        if not self.settings.camera_enabled or self.detector is None:
            return "unavailable", "Automatic monitoring is unavailable because the detector is not running."
        if not self.ppe_self_test_passed:
            return (
                "attention",
                "Person tracking is available, but PPE assessment is disabled because its automatic "
                "startup self-test failed.",
            )
        if not self.camera_online:
            return "attention", "The camera is offline. Detection will resume automatically after recovery."
        if self.latest_jpeg is None or self.last_frame_at is None or self.processed_fps <= 0:
            return "warming_up", "The camera is warming up. Detection will begin automatically."
        try:
            last_frame = datetime.fromisoformat(self.last_frame_at.replace("Z", "+00:00"))
            frame_age = (datetime.now(UTC) - last_frame).total_seconds()
        except ValueError:
            frame_age = 999.0
        if frame_age > 2:
            return "attention", "The latest frame is stale. Detection will resume when fresh frames return."
        if self.processed_fps < 6:
            return (
                "attention",
                "Processing is below 6 FPS. Close heavy applications or select another camera.",
            )
        return "active", "Camera analysis and PPE monitoring are running automatically."

    def _detection_state(self) -> dict[str, Any]:
        subject = self.active_employee
        if not subject or subject.get("trackId") is None:
            return {
                "status": "idle",
                "trackId": None,
                "identityDetected": False,
                "identityStatus": {
                    "state": "not_associated",
                    "label": "Identity not associated",
                    "detail": "PPE monitoring does not require employee identity.",
                },
                "ppeDetected": False,
                "issues": [],
                "ppeItems": {},
                "readiness": None,
                "proof": None,
                "resetGeneration": self.detection_reset_generation,
                "lastResetAt": self.last_detection_reset_at,
                "updatedAt": self.last_frame_at,
            }

        ppe = subject["ppe"]
        items = ppe.get("items", {})
        identity_detected = subject.get("employeeId") is not None
        missing = [
            item
            for item in ITEM_ORDER
            if item in self.required_ppe_items and items.get(item, {}).get("state") == "missing"
        ]
        ppe_detected = all(
            items.get(item, {}).get("state") == "detected" for item in self.required_ppe_items
        )
        issues: list[dict[str, str]] = []
        for item in missing:
            issues.append(
                {
                    "code": f"{item}_missing",
                    "title": f"{PPE_LABELS[item]} not detected",
                    "detail": (
                        f"The {PPE_LABELS[item].lower()} region was visible, but no qualifying "
                        "central controlled-PPE shape remained verified."
                    ),
                }
            )
        status = "attention" if missing else "compliant" if ppe_detected else "observing"
        return {
            "status": status,
            "trackId": subject["trackId"],
            "identityDetected": identity_detected,
            "identityStatus": {
                "state": "associated" if identity_detected else "not_associated",
                "label": subject["displayName"] if identity_detected else "Identity not associated",
                "detail": (
                    "Badge is visible and verifies this active person track."
                    if subject.get("identityAssociation") == "badge_visible"
                    else (
                        "The only eligible remembered badge session was conservatively "
                        "reassociated after this person returned; no biometric matching was used."
                    )
                    if subject.get("identityAssociation") == "session_reentry"
                    else "Badge was verified earlier; identity remains bound to this active person track."
                    if identity_detected
                    else "Optional badge or access-control association; PPE monitoring remains active."
                ),
            },
            "ppeDetected": ppe_detected,
            "issues": issues,
            "ppeItems": items,
            "readiness": ppe.get("readiness"),
            "proof": {
                "zone": subject.get("zone", "Unassigned"),
                "activity": subject.get("activity", "Tracking active"),
                "personConfidence": subject.get("personConfidence"),
                "ppeConfidence": ppe.get("confidence"),
                "movementSamples": len(self.track_paths.get(subject["trackId"], ())),
                "evidencePolicy": "snapshot_and_clip_on_persistent_event",
                "brightness": ppe.get("readiness", {}).get("brightness"),
                "framingReady": ppe.get("readiness", {}).get("framingReady", False),
                "assessmentAvailable": ppe.get("assessmentAvailable", False),
            },
            "resetGeneration": self.detection_reset_generation,
            "lastResetAt": self.last_detection_reset_at,
            "updatedAt": self.last_frame_at,
        }

    def reset_detection(self) -> dict[str, Any]:
        """Start a new transient observation without deleting retained evidence or events."""
        with self.lock:
            reset = getattr(self.detector, "reset", None)
            if callable(reset):
                reset()
            self.active_employee = None
            self.active_subject_last_seen = 0.0
            self.employee_first_seen.clear()
            self.employee_last_seen.clear()
            self.track_first_seen.clear()
            self.track_last_seen.clear()
            self.track_employee_binding.clear()
            self.track_employee_binding_seen.clear()
            self.track_employee_binding_verified_at.clear()
            self.track_employee_binding_confidence.clear()
            self.track_identity_association.clear()
            self.identity_sessions.clear()
            self.identity_reentry_candidates.clear()
            self.track_paths.clear()
            self.movement_zone.clear()
            self.movement_candidate.clear()
            self.movement_last_event.clear()
            self.tray_zone_candidate = None
            self.inventory_positions.clear()
            self.inventory_sides.clear()
            self.inventory_side_candidates.clear()
            self.inventory_cooldown.clear()
            self.identity_missing_since.clear()
            self.identity_alerted.clear()
            self.ppe_stabilizer.reset()
            self.ppe_missing_since.clear()
            self.ppe_alerted.clear()
            self.ppe_alert_event_by_track_item.clear()
            self.ppe_recovery_since.clear()
            self.ppe_observed_at.clear()
            self.ppe_review.clear()
            self.latest_ppe_review_job_id = None
            self._last_ai_review_signature.clear()
            self.detection_reset_generation += 1
            self.last_detection_reset_at = iso()
            return self._detection_state()

    def clear_identity_sessions(self) -> dict[str, Any]:
        """Clear remembered identity only; retained events and live PPE state remain."""
        with self.lock:
            removed = len(self.identity_sessions)
            for track_id, employee in list(self.track_employee_binding.items()):
                self._demote_transient_subject_state(track_id, employee["employeeId"])
                self._clear_track_identity(track_id)
            self.identity_sessions.clear()
            self.identity_reentry_candidates.clear()
            self.employee_first_seen.clear()
            self.employee_last_seen.clear()
            self.identity_missing_since.clear()
            self.identity_alerted.clear()
            self.active_employee = None
            self.active_subject_last_seen = 0.0
            return {"clearedSessions": removed, "retainedEventsDeleted": 0}

    def _livekit_frame(self) -> np.ndarray | None:
        with self.lock:
            return self.latest_bgr.copy() if self.latest_bgr is not None else None

    def _sample_temperature(self, evidence_frame: np.ndarray | None = None) -> None:
        reading = self.temperature_source.read()
        if reading is None:
            self._last_temperature_sample = time.monotonic()
            return
        previous_status = self.temperature["status"]
        self.temperature = reading.payload()
        sampled_at = reading.sampled_at
        self.store.add_temperature_reading(
            reading.sensor_id,
            reading.value_c,
            reading.min_c,
            reading.max_c,
            reading.status,
            reading.source_mode,
            sampled_at,
        )
        self._last_temperature_sample = time.monotonic()
        if reading.status == previous_status:
            return
        critical = reading.status == "critical"
        event = self.store.add_event(
            EventInput(
                type="temperature_alert" if critical else "temperature_recovered",
                title="Temperature exceeded configured limit"
                if critical
                else "Temperature returned to configured range",
                detail=f"{reading.label} reading reached {reading.value_c:.1f}°C.",
                severity="critical" if critical else "info",
                source_mode=reading.source_mode,
                zone=reading.label,
                confidence=1.0 if reading.source_mode == "simulated" else None,
            ),
            metadata={
                "source_origin": f"{self.settings.temperature_source}_temperature_source",
                "sensor_id": reading.sensor_id,
                "value_c": reading.value_c,
                "min_c": reading.min_c,
                "max_c": reading.max_c,
                "status": reading.status,
            },
        )
        frame = evidence_frame if evidence_frame is not None else self.latest_bgr
        if frame is not None:
            self.evidence.capture(event["id"], frame)

    def demo_action(self, action: str, payload: dict[str, Any]) -> None:
        with self.lock:
            frame = self.latest_bgr.copy() if self.latest_bgr is not None else None
            if action == "process-start":
                self._start_process("simulated", frame, "demo_control")
            elif action == "process-complete":
                self._complete_process("simulated", frame, "demo_control")
            elif action == "ppe-violation":
                event = self.store.add_event(
                    EventInput(
                        type="ppe_violation",
                        title="Gloves not detected",
                        detail="Operator triggered a simulated controlled-scene glove violation.",
                        severity="critical",
                        source_mode="simulated",
                        employee_id="EMP-001",
                        employee_name="Ahmed Hassan",
                        zone="Preparation",
                        confidence=1.0,
                    ),
                    metadata={"source_origin": "demo_control"},
                )
                if frame is not None:
                    self.evidence.capture(event["id"], frame)
            elif action in {"temperature-high", "temperature-safe"}:
                high = action == "temperature-high"
                if not isinstance(self.temperature_source, SimulatedTemperatureSource):
                    raise ValueError("Temperature demo controls require the simulated sensor source")
                self.temperature_source.set_value(8.1 if high else 4.2)
                self._sample_temperature(frame)
            elif action == "inventory":
                self._inventory_movement(
                    str(payload.get("sku", "SKU-001")),
                    str(payload.get("direction", "in")),
                    int(payload.get("quantity", 1)),
                    "simulated",
                    frame,
                    "demo_control",
                )
            elif action == "process-overtime":
                event = self.store.add_event(
                    EventInput(
                        type="process_exception",
                        title="Process exceeded target time",
                        detail="Simulated Chicken Washing run exceeded the 180-second target.",
                        severity="warning",
                        source_mode="simulated",
                        employee_id="EMP-001",
                        employee_name="Ahmed Hassan",
                        zone="Process Complete",
                        confidence=1.0,
                    ),
                    metadata={"source_origin": "demo_control", "elapsed_seconds": 212},
                )
                if frame is not None:
                    self.evidence.capture(event["id"], frame)
            elif action == "inventory-variance":
                event = self.store.add_event(
                    EventInput(
                        type="inventory_variance",
                        title="Inventory count variance",
                        detail="Simulated camera count differs from the expected quantity for SKU-003.",
                        severity="warning",
                        source_mode="simulated",
                        employee_id="EMP-002",
                        employee_name="Muhammad Zaid",
                        zone="Inventory",
                        confidence=1.0,
                    ),
                    metadata={"source_origin": "demo_control", "sku": "SKU-003", "variance": -1},
                )
                if frame is not None:
                    self.evidence.capture(event["id"], frame)
            else:
                raise ValueError(f"Unknown demo action: {action}")

    def reset_demo_state(self) -> dict[str, int]:
        """Reset only simulated persisted and in-memory presentation state."""
        with self.lock:
            removed = self.enterprise.reset_simulated()
            self.process_state = {
                "id": None,
                "label": "Chicken Washing",
                "status": "idle",
                "startedAt": None,
                "elapsedSeconds": 0,
                "targetMinSeconds": 120,
                "targetMaxSeconds": 180,
            }
            self.last_tray_zone = None
            self.tray_zone_candidate = None
            self.process_cooldown_until = time.monotonic() + 120
            self.inventory_positions.clear()
            self.inventory_sides.clear()
            self.inventory_side_candidates.clear()
            self.inventory_cooldown = {
                marker_id: time.monotonic() + 120 for marker_id in INVENTORY_MARKERS
            }
            if isinstance(self.temperature_source, SimulatedTemperatureSource):
                self.temperature_source.set_value(self.settings.temperature_initial_c)
                self.temperature = self.temperature_source.read().payload()
            self.ppe_missing_since.clear()
            self.ppe_alerted.clear()
            self.ppe_alert_event_by_track_item.clear()
            self.ppe_recovery_since.clear()
            self.ppe_observed_at.clear()
            self.ppe_stabilizer.reset()
            self.ppe_review.clear()
            self.latest_ppe_review_job_id = None
            self._last_ai_review_signature.clear()
            self.active_employee = None
            self.active_subject_last_seen = 0.0
            self.track_first_seen.clear()
            self.track_last_seen.clear()
            self.track_employee_binding.clear()
            self.track_employee_binding_seen.clear()
            self.track_employee_binding_verified_at.clear()
            self.track_employee_binding_confidence.clear()
            self.track_identity_association.clear()
            self.identity_sessions.clear()
            self.identity_reentry_candidates.clear()
            return removed
