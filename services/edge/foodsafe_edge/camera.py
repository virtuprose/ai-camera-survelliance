from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .settings import Settings

logger = logging.getLogger(__name__)

MAC_CAMERA_DEFINITIONS = (
    {
        "id": "facetime",
        "label": "FaceTime HD Camera",
        "description": "Built-in MacBook camera",
    },
    {
        "id": "facetime",
        "label": "MacBook Pro Camera",
        "description": "Built-in MacBook camera",
    },
    {
        "id": "camo",
        "label": "Camo Camera",
        "description": "iPhone through Camo Studio",
    },
)

KNOWN_CAMERA_DEFINITIONS = {
    str(definition["label"]): definition for definition in MAC_CAMERA_DEFINITIONS
}
FALLBACK_ASSET = Path(__file__).resolve().parents[1] / "assets" / "fallback-demo.mp4"
NATIVE_CAMERA_HELPER_SOURCE = (
    Path(__file__).resolve().parents[1] / "scripts" / "list_avfoundation_cameras.swift"
)
NATIVE_CAMERA_HELPER_BINARY = (
    Path(tempfile.gettempdir()) / "orvia-avfoundation-camera-discovery-v1"
)


def camera_id_for_label(label: str) -> str:
    """Return a stable public ID without depending on AVFoundation's mutable index."""
    definition = KNOWN_CAMERA_DEFINITIONS.get(label)
    if definition:
        return str(definition["id"])
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "camera"
    digest = hashlib.sha256(label.encode("utf-8")).hexdigest()[:8]
    return f"avf-{slug[:32]}-{digest}"


def camera_id_for_settings(settings: Settings) -> str:
    if settings.camera_kind == "avfoundation":
        return camera_id_for_label(settings.camera_label)
    if settings.camera_kind == "file":
        return "fallback"
    return "custom"


def camera_description(label: str) -> str:
    definition = KNOWN_CAMERA_DEFINITIONS.get(label)
    if definition:
        return str(definition["description"])
    normalized = label.lower()
    if "iphone" in normalized or "continuity" in normalized:
        return "iPhone camera detected by macOS"
    if any(value in normalized for value in ("samsung", "monitor", "display", "slimfit")):
        return "Monitor camera detected by macOS"
    if any(value in normalized for value in ("obs", "virtual", "snap camera", "manycam")):
        return "Virtual camera detected by macOS"
    return "Connected camera detected by macOS"


def is_camera_device(label: str) -> bool:
    """AVFoundation also lists screen capture inputs; those are not camera choices."""
    return not label.lower().startswith("capture screen")


def _is_builtin_camera(label: str) -> bool:
    normalized = label.lower()
    return "facetime" in normalized or ("macbook" in normalized and "camera" in normalized)


def resolve_avfoundation_source(settings: Settings) -> None:
    """Refresh a configured camera's mutable AVFoundation index from its stable label."""
    if settings.camera_kind != "avfoundation":
        return
    devices = discover_avfoundation_devices()
    if not devices:
        return
    source = devices.get(settings.camera_label)
    resolved_label = settings.camera_label
    if source is None and _is_builtin_camera(settings.camera_label):
        builtin = next(
            ((label, index) for label, index in devices.items() if _is_builtin_camera(label)),
            None,
        )
        if builtin:
            resolved_label, source = builtin
    if source is not None:
        settings.camera_label = resolved_label
        settings.camera_source = source


def _parse_ffmpeg_devices(output: str) -> dict[str, str]:
    devices: dict[str, str] = {}
    in_video_section = False
    for line in output.splitlines():
        if "AVFoundation video devices:" in line:
            in_video_section = True
            continue
        if "AVFoundation audio devices:" in line:
            break
        if not in_video_section:
            continue
        match = re.search(r"\[(\d+)]\s+(.+?)\s*$", line)
        if match and is_camera_device(match.group(2)):
            devices[match.group(2)] = match.group(1)
    return devices


def _discover_with_ffmpeg() -> dict[str, str]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return {}
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.warning("FFmpeg camera discovery was unavailable", exc_info=True)
        return {}
    return _parse_ffmpeg_devices(result.stderr)


def _compile_native_camera_helper() -> Path | None:
    if sys.platform != "darwin" or not NATIVE_CAMERA_HELPER_SOURCE.is_file():
        return None
    try:
        if (
            NATIVE_CAMERA_HELPER_BINARY.is_file()
            and NATIVE_CAMERA_HELPER_BINARY.stat().st_mtime
            >= NATIVE_CAMERA_HELPER_SOURCE.stat().st_mtime
        ):
            return NATIVE_CAMERA_HELPER_BINARY
        temporary_binary = NATIVE_CAMERA_HELPER_BINARY.with_name(
            f"{NATIVE_CAMERA_HELPER_BINARY.name}.{os.getpid()}.tmp"
        )
        compile_result = subprocess.run(
            ["xcrun", "swiftc", str(NATIVE_CAMERA_HELPER_SOURCE), "-o", str(temporary_binary)],
            capture_output=True,
            check=False,
            text=True,
            timeout=20,
        )
        if compile_result.returncode != 0:
            logger.warning("Native camera discovery helper could not be compiled: %s", compile_result.stderr)
            temporary_binary.unlink(missing_ok=True)
            return None
        temporary_binary.chmod(0o700)
        os.replace(temporary_binary, NATIVE_CAMERA_HELPER_BINARY)
        return NATIVE_CAMERA_HELPER_BINARY
    except (OSError, subprocess.TimeoutExpired):
        logger.warning("Native camera discovery helper was unavailable", exc_info=True)
        return None


def _discover_with_native_avfoundation() -> dict[str, str]:
    helper = _compile_native_camera_helper()
    if helper is None:
        return {}
    try:
        result = subprocess.run(
            [str(helper)],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.warning("Native AVFoundation camera discovery failed", exc_info=True)
        return {}
    if result.returncode != 0:
        logger.warning("Native AVFoundation camera discovery returned an error: %s", result.stderr)
        return {}
    devices: dict[str, str] = {}
    for line in result.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 2 or not parts[0].isdigit():
            continue
        source, label = parts[0], parts[1].strip()
        if label and is_camera_device(label):
            devices[label] = source
    return devices


def _discover_with_system_profiler() -> dict[str, str]:
    """Last-resort inventory when native AVFoundation compilation is unavailable."""
    if sys.platform != "darwin":
        return {}
    try:
        result = subprocess.run(
            ["system_profiler", "SPCameraDataType", "-json"],
            capture_output=True,
            check=False,
            text=True,
            timeout=8,
        )
        payload = json.loads(result.stdout) if result.returncode == 0 else {}
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        logger.warning("macOS camera inventory was unavailable", exc_info=True)
        return {}
    devices: dict[str, str] = {}
    for index, item in enumerate(payload.get("SPCameraDataType", [])):
        label = str(item.get("_name", "")).strip()
        if label and is_camera_device(label):
            devices[label] = str(index)
    return devices


def discover_avfoundation_devices() -> dict[str, str]:
    """Return every macOS video device mapped to its current AVFoundation index."""
    devices = _discover_with_ffmpeg()
    if devices:
        return devices
    devices = _discover_with_native_avfoundation()
    if devices:
        return devices
    return _discover_with_system_profiler()


def camera_catalog(settings: Settings) -> dict[str, Any]:
    devices = discover_avfoundation_devices()
    options: list[dict[str, Any]] = []
    for label, source in devices.items():
        # AVFoundation indexes can be reordered as physical and virtual cameras
        # are opened or released. The configured label is the stable identity.
        active = (
            settings.camera_kind == "avfoundation"
            and settings.camera_label == label
        )
        options.append(
            {
                "id": camera_id_for_label(label),
                "label": label,
                "description": camera_description(label),
                "kind": "avfoundation",
                "source": source,
                "registered": True,
                "active": active,
            }
        )
    configured_source = Path(settings.camera_source)
    if not configured_source.is_absolute():
        configured_source = Path.cwd() / configured_source
    fallback_active = (
        settings.camera_kind == "file"
        and configured_source.resolve(strict=False) == FALLBACK_ASSET.resolve(strict=False)
    )
    options.append(
        {
            "id": "fallback",
            "label": "Prerecorded local fallback",
            "description": "Clearly labelled simulated presentation fallback",
            "kind": "file",
            "source": str(FALLBACK_ASSET),
            "registered": FALLBACK_ASSET.is_file(),
            "active": fallback_active,
        }
    )
    active_id = next((option["id"] for option in options if option["active"]), None)
    if active_id is None and settings.camera_kind == "avfoundation":
        active_id = camera_id_for_settings(settings)
        options.append(
            {
                "id": active_id,
                "label": settings.camera_label,
                "description": "Current camera source; reconnect the device to rediscover it",
                "kind": "avfoundation",
                "source": settings.camera_source,
                "registered": True,
                "active": True,
            }
        )
    if active_id is None:
        active_id = camera_id_for_settings(settings)
        options.append(
            {
                "id": active_id,
                "label": settings.camera_label,
                "description": "Current configured camera source",
                "kind": settings.camera_kind,
                "source": settings.camera_source,
                "registered": True,
                "active": True,
            }
        )
    return {"activeId": active_id, "options": options}


class CameraSource(ABC):
    @abstractmethod
    def open(self) -> bool: ...

    @abstractmethod
    def read(self) -> tuple[bool, np.ndarray | None]: ...

    @abstractmethod
    def close(self) -> None: ...


class OpenCVCameraSource(CameraSource):
    def __init__(self, settings: Settings):
        self.settings = settings
        self.capture: cv2.VideoCapture | None = None
        self.last_reconnect = 0.0

    def _source(self) -> int | str:
        if self.settings.camera_kind == "avfoundation":
            return int(self.settings.camera_source)
        return self.settings.camera_source

    def open(self) -> bool:
        self.close()
        resolve_avfoundation_source(self.settings)
        source = self._source()
        backend = cv2.CAP_AVFOUNDATION if self.settings.camera_kind == "avfoundation" else cv2.CAP_ANY
        self.capture = cv2.VideoCapture(source, backend)
        if not self.capture.isOpened():
            logger.error("Camera source could not be opened: kind=%s", self.settings.camera_kind)
            self.capture.release()
            self.capture = None
            return False
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.settings.camera_width)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.settings.camera_height)
        self.capture.set(cv2.CAP_PROP_FPS, self.settings.camera_fps)
        self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        logger.info("Camera opened: %s (%s)", self.settings.camera_label, self.settings.camera_kind)
        return True

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self.capture is None or not self.capture.isOpened():
            if time.monotonic() - self.last_reconnect > 3:
                self.last_reconnect = time.monotonic()
                self.open()
            return False, None
        ok, frame = self.capture.read()
        if not ok or frame is None:
            if self.settings.camera_kind == "file" and self.capture is not None:
                self.capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = self.capture.read()
                if ok and frame is not None:
                    return True, frame
            logger.warning("Camera frame read failed; reconnecting")
            self.close()
            return False, None
        return True, frame

    def close(self) -> None:
        if self.capture is not None:
            self.capture.release()
            self.capture = None
