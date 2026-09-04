from types import SimpleNamespace

import numpy as np
import pytest

from foodsafe_edge import camera as camera_module
from foodsafe_edge import pipeline as pipeline_module
from foodsafe_edge.pipeline import CameraSwitchError, EdgePipeline
from foodsafe_edge.settings import Settings


def test_avfoundation_discovery_returns_video_devices_only(monkeypatch) -> None:
    output = """
[AVFoundation indev] AVFoundation video devices:
[AVFoundation indev] [0] FaceTime HD Camera
[AVFoundation indev] [1] Camo Camera
[AVFoundation indev] [2] Capture screen 0
[AVFoundation indev] AVFoundation audio devices:
[AVFoundation indev] [0] MacBook Pro Microphone
"""
    monkeypatch.setattr(camera_module.shutil, "which", lambda _name: "/opt/homebrew/bin/ffmpeg")
    monkeypatch.setattr(
        camera_module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stderr=output),
    )
    assert camera_module.discover_avfoundation_devices() == {
        "FaceTime HD Camera": "0",
        "Camo Camera": "1",
    }


def test_camera_catalog_uses_stable_label_when_indexes_reorder(monkeypatch) -> None:
    monkeypatch.setattr(
        camera_module,
        "discover_avfoundation_devices",
        lambda: {"Camo Camera": "0", "FaceTime HD Camera": "1"},
    )
    settings = Settings(
        camera_enabled=False,
        camera_kind="avfoundation",
        camera_source="1",
        camera_label="Camo Camera",
    )

    catalog = camera_module.camera_catalog(settings)

    assert catalog["activeId"] == "camo"
    active_option = next(option for option in catalog["options"] if option["active"])
    assert active_option["label"] == "Camo Camera"
    assert active_option["source"] == "0"


def test_camera_catalog_always_exposes_labelled_fallback_with_live_camera(monkeypatch) -> None:
    monkeypatch.setattr(
        camera_module,
        "discover_avfoundation_devices",
        lambda: {"FaceTime HD Camera": "0"},
    )
    settings = Settings(
        camera_enabled=False,
        camera_kind="avfoundation",
        camera_source="0",
        camera_label="FaceTime HD Camera",
    )

    catalog = camera_module.camera_catalog(settings)
    fallback = next(option for option in catalog["options"] if option["id"] == "fallback")

    assert catalog["activeId"] == "facetime"
    assert fallback["label"] == "Prerecorded local fallback"
    assert fallback["description"] == "Clearly labelled simulated presentation fallback"
    assert fallback["kind"] == "file"
    assert fallback["registered"] is True
    assert fallback["active"] is False


def test_camera_catalog_includes_every_discovered_camera(monkeypatch) -> None:
    monkeypatch.setattr(
        camera_module,
        "discover_avfoundation_devices",
        lambda: {
            "FaceTime HD Camera": "0",
            "Samsung SlimFit Camera": "1",
            "Camo Camera": "2",
            "USB Conference Camera": "3",
        },
    )
    settings = Settings(
        camera_enabled=False,
        camera_kind="file",
        camera_source="assets/fallback-demo.mp4",
        camera_label="Prerecorded local fallback",
    )

    catalog = camera_module.camera_catalog(settings)
    options = {option["label"]: option for option in catalog["options"]}

    assert set(options) == {
        "FaceTime HD Camera",
        "Samsung SlimFit Camera",
        "Camo Camera",
        "USB Conference Camera",
        "Prerecorded local fallback",
    }
    assert options["Samsung SlimFit Camera"]["id"].startswith("avf-samsung-slimfit-camera-")
    assert options["Samsung SlimFit Camera"]["description"] == "Monitor camera detected by macOS"
    assert options["USB Conference Camera"]["registered"] is True
    assert catalog["activeId"] == "fallback"


def test_dynamic_camera_id_is_stable_when_indexes_reorder(monkeypatch) -> None:
    settings = Settings(
        camera_enabled=False,
        camera_kind="avfoundation",
        camera_source="1",
        camera_label="Samsung SlimFit Camera",
    )
    monkeypatch.setattr(
        camera_module,
        "discover_avfoundation_devices",
        lambda: {"FaceTime HD Camera": "0", "Samsung SlimFit Camera": "1"},
    )
    first = camera_module.camera_catalog(settings)
    monkeypatch.setattr(
        camera_module,
        "discover_avfoundation_devices",
        lambda: {"Samsung SlimFit Camera": "0", "FaceTime HD Camera": "1"},
    )
    second = camera_module.camera_catalog(settings)

    assert first["activeId"] == second["activeId"]
    assert first["activeId"].startswith("avf-samsung-slimfit-camera-")
    assert next(option for option in second["options"] if option["active"])["source"] == "0"


class FakeCamera:
    fail_labels: set[str] = set()

    def __init__(self, settings: Settings):
        self.settings = settings
        self.closed = False

    def open(self) -> bool:
        return self.settings.camera_label not in self.fail_labels

    def read(self):
        if self.settings.camera_label in self.fail_labels:
            return False, None
        return True, np.zeros((720, 1280, 3), dtype=np.uint8)

    def close(self) -> None:
        self.closed = True


def fake_catalog(settings: Settings) -> dict[str, object]:
    active = "camo" if settings.camera_label == "Camo Camera" else "facetime"
    return {
        "activeId": active,
        "options": [
            {
                "id": "facetime",
                "label": "FaceTime HD Camera",
                "description": "Built-in MacBook camera",
                "kind": "avfoundation",
                "source": "0",
                "registered": True,
                "active": active == "facetime",
            },
            {
                "id": "camo",
                "label": "Camo Camera",
                "description": "iPhone through Camo Studio",
                "kind": "avfoundation",
                "source": "1",
                "registered": True,
                "active": active == "camo",
            },
        ],
    }


def test_switch_camera_commits_only_after_fresh_frame(monkeypatch, tmp_path) -> None:
    FakeCamera.fail_labels = set()
    monkeypatch.setattr(pipeline_module, "OpenCVCameraSource", FakeCamera)
    monkeypatch.setattr(pipeline_module, "camera_catalog", fake_catalog)
    pipeline = EdgePipeline(Settings(camera_enabled=False, data_dir=tmp_path))
    previous = pipeline.camera

    result = pipeline.switch_camera("camo")

    assert pipeline.settings.camera_label == "Camo Camera"
    assert pipeline.settings.camera_source == "1"
    assert previous.closed is True
    assert pipeline.camera.closed is False
    assert result["activeId"] == "camo"
    assert result["switchState"] == "idle"


def test_failed_switch_preserves_current_camera(monkeypatch, tmp_path) -> None:
    FakeCamera.fail_labels = {"Camo Camera"}
    monkeypatch.setattr(pipeline_module, "OpenCVCameraSource", FakeCamera)
    monkeypatch.setattr(pipeline_module, "camera_catalog", fake_catalog)
    pipeline = EdgePipeline(Settings(camera_enabled=False, data_dir=tmp_path))
    previous = pipeline.camera

    with pytest.raises(CameraSwitchError, match="could not be opened"):
        pipeline.switch_camera("camo")

    assert pipeline.camera is previous
    assert previous.closed is False
    assert pipeline.settings.camera_label == "FaceTime HD Camera"
    assert pipeline.camera_switch_state == "failed"
