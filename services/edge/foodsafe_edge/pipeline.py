from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import UTC, datetime
from typing import Any

import cv2
import numpy as np

from .camera import OpenCVCameraSource, camera_catalog, camera_id_for_settings
from .detector import PersonDetection, PersonDetector, create_detector
from .enterprise import EnterpriseStore
from .evidence import EvidenceBuffer
from .livekit_publisher import LiveKitPublisher
from .markers import EMPLOYEE_MARKERS, INVENTORY_MARKERS, TRAY_MARKERS, ArucoMarkerReader, Marker
from .ppe import (
    ITEM_ORDER,
    REQUIRED_ITEMS,
    LandmarkColourPPEDetector,
    PPEItemResult,
    PPEResult,
    PPEStabilizer,
)
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
        self.track_employee_binding_confidence: dict[int, float] = {}
        self.track_paths: dict[int, deque[tuple[int, int]]] = {}
        self.movement_zone: dict[str, str] = {}
        self.movement_candidate: dict[str, tuple[str, float]] = {}
        self.movement_last_event: dict[str, float] = {}
        self.identity_missing_since: dict[int, float] = {}
        self.identity_alerted: set[int] = set()
        self.ppe_missing_since: dict[tuple[str, str], float] = {}
        self.ppe_alerted: set[tuple[str, str]] = set()
        self.ppe_recovery_since: dict[tuple[str, str], float] = {}
        self.ppe_observed_at: dict[tuple[str, str], float] = {}
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

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        with self.camera_lock:
            self.camera.close()
        self.temperature_source.stop()
        self.sync.stop()
        self.livekit.stop()

    def cameras(self) -> dict[str, Any]:
        catalog = camera_catalog(self.settings)
        catalog.update(
            {
                "switchState": self.camera_switch_state,
                "message": self.camera_switch_message,
            }
        )
        return catalog

    def switch_camera(self, camera_id: str) -> dict[str, Any]:
        if not self.camera_switch_lock.acquire(blocking=False):
            raise CameraSwitchError("Another camera switch is already in progress.")
        candidate: OpenCVCameraSource | None = None
        try:
            self.camera_switch_state = "switching"
            self.camera_switch_message = "Checking the requested camera for fresh frames."
            catalog = camera_catalog(self.settings)
            option = next((item for item in catalog["options"] if item["id"] == camera_id), None)
            if not option:
                raise CameraSwitchError("The requested camera is not configured for this demo.")
            if option["active"]:
                self.camera_switch_state = "idle"
                self.camera_switch_message = f"{option['label']} is already active."
                return self.cameras()
            if not option["registered"] or option["source"] is None:
                raise CameraSwitchError(
                    f"{option['label']} is not available. Open its camera software or reconnect the device."
                )

            candidate_settings = self.settings.model_copy(
                update={
                    "camera_kind": option["kind"],
                    "camera_source": str(option["source"]),
                    "camera_label": option["label"],
                }
            )
            candidate = OpenCVCameraSource(candidate_settings)
            if not candidate.open():
                raise CameraSwitchError(
                    f"{option['label']} could not be opened. The current camera remains active."
                )
            frame_ok = False
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                ok, frame = candidate.read()
                if ok and frame is not None:
                    frame_ok = True
                    break
                time.sleep(0.1)
            if not frame_ok:
                raise CameraSwitchError(
                    f"{option['label']} did not provide a fresh frame. The current camera remains active."
                )

            with self.camera_lock:
                previous = self.camera
                self.camera = candidate
                self.settings.camera_kind = str(option["kind"])
                self.settings.camera_source = str(option["source"])
                self.settings.camera_label = str(option["label"])
                candidate = None
                previous.close()
            with self.frame_condition:
                self.latest_jpeg = None
                self.latest_bgr = None
                self.last_frame_at = None
                self.processed_fps = 0.0
                self._fps_frames = 0
                self._fps_started = time.monotonic()
                self.active_employee = None
                self.active_subject_last_seen = 0.0
                self.track_first_seen.clear()
                self.track_last_seen.clear()
                self.track_paths.clear()
                self.movement_zone.clear()
                self.movement_candidate.clear()
                self.movement_last_event.clear()
                self.identity_missing_since.clear()
                self.identity_alerted.clear()
                self.ppe_stabilizer.reset()
                self.ppe_missing_since.clear()
                self.ppe_alerted.clear()
                self.ppe_recovery_since.clear()
                self.ppe_observed_at.clear()
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
            if candidate is not None:
                candidate.close()
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

    def _process(self, frame: np.ndarray) -> np.ndarray:
        height, width = frame.shape[:2]
        people = self.detector.detect(frame) if self.detector else []
        markers = self.marker_reader.read(frame)
        employee_markers = [marker for marker in markers if marker.marker_id in EMPLOYEE_MARKERS]
        draw_zones(frame)
        self._handle_process_and_inventory(markers, frame)

        resolved_employee = False
        resolved_subject = False
        for person in people:
            matched = next(
                (marker for marker in employee_markers if _contains(person.xyxy, marker.centre)), None
            )
            ppe = self.ppe_stabilizer.update(
                person.track_id,
                self.ppe_detector.detect(frame, person),
            )
            if matched:
                employee = EMPLOYEE_MARKERS.get(matched.marker_id)
                if employee:
                    self.track_employee_binding[person.track_id] = employee
                    self.track_employee_binding_seen[person.track_id] = time.monotonic()
                    self.track_employee_binding_confidence[person.track_id] = matched.confidence
            else:
                binding_age = time.monotonic() - self.track_employee_binding_seen.get(
                    person.track_id, 0
                )
                employee = (
                    self.track_employee_binding.get(person.track_id)
                    if binding_age <= self.settings.identity_binding_seconds
                    else None
                )
            person_zone = zone_for(_centre(person.xyxy), width, height)
            self._draw_person(frame, person, ppe, employee, person_zone)
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
                )
                self._check_ppe(employee, person, person_zone, ppe, frame)
                self._check_movement(employee, person, person_zone, frame)
            else:
                resolved_subject = True
                if not resolved_employee:
                    self._set_active_unidentified(person, person_zone, ppe)
                self._check_ppe(None, person, person_zone, ppe, frame)
                self._check_movement(None, person, person_zone, frame)

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
            if now - last_seen > 10:
                self.employee_first_seen.pop(employee_id, None)
                self.employee_last_seen.pop(employee_id, None)
        for track_id, last_seen in list(self.track_last_seen.items()):
            if now - last_seen > 10:
                self.track_first_seen.pop(track_id, None)
                self.track_last_seen.pop(track_id, None)
                self.track_paths.pop(track_id, None)
                self.track_employee_binding.pop(track_id, None)
                self.track_employee_binding_seen.pop(track_id, None)
                self.track_employee_binding_confidence.pop(track_id, None)
                subject_key = f"track:{track_id}"
                self.movement_zone.pop(subject_key, None)
                self.movement_candidate.pop(subject_key, None)
                self.movement_last_event.pop(subject_key, None)
                self.identity_missing_since.pop(track_id, None)
                self.identity_alerted.discard(track_id)
                self.ppe_stabilizer.clear_track(track_id)

        self._draw_markers(frame, markers)
        self._draw_header(frame)
        return frame

    def _set_active_employee(
        self,
        employee: dict[str, str],
        person: PersonDetection,
        badge_confidence: float,
        person_zone: str,
        ppe: PPEResult,
    ) -> None:
        employee_id = employee["employeeId"]
        entered = self.employee_first_seen.setdefault(employee_id, iso())
        self.employee_last_seen[employee_id] = time.monotonic()
        self.active_subject_last_seen = time.monotonic()
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
                self.ppe_recovery_since.pop(key, None)
                continue

            self.ppe_recovery_since.pop(key, None)
            if assessment.state != "missing":
                self.ppe_missing_since.pop(key, None)
                continue
            since = self.ppe_missing_since.setdefault(key, now)
            if now - since < self.settings.ppe_persistence_seconds or key in self.ppe_alerted:
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
            "detection": self._detection_state(),
            "process": process,
            "temperature": self.temperature,
            "inventory": self.store.inventory(),
            "recentEvents": events,
        }

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
                    "Resolved from an enrolled ArUco badge."
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
            self.track_employee_binding_confidence.clear()
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
            self.ppe_recovery_since.clear()
            self.ppe_observed_at.clear()
            self.detection_reset_generation += 1
            self.last_detection_reset_at = iso()
            return self._detection_state()

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
                        employee_name="Demo Operator A",
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
                        employee_name="Demo Operator A",
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
                        employee_name="Demo Operator B",
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
            self.ppe_recovery_since.clear()
            self.ppe_observed_at.clear()
            self.ppe_stabilizer.reset()
            self.active_employee = None
            self.active_subject_last_seen = 0.0
            self.track_first_seen.clear()
            self.track_last_seen.clear()
            self.track_employee_binding.clear()
            self.track_employee_binding_seen.clear()
            self.track_employee_binding_confidence.clear()
            return removed
