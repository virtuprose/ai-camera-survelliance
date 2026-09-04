from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    camera_source: str = "0"
    camera_kind: str = "avfoundation"
    camera_label: str = "FaceTime HD Camera"
    camera_width: int = 1280
    camera_height: int = 720
    camera_fps: int = 15
    process_fps: int = 10
    camera_enabled: bool = True

    detector_backend: str = "ultralytics"
    detector_model: str = "yolo11n-pose.pt"
    detector_device: str = "cpu"
    detector_image_size: int = 512
    person_confidence: float = 0.45
    ppe_persistence_seconds: float = 3.0
    ppe_recovery_seconds: float = 5.0
    identity_persistence_seconds: float = 3.0
    identity_binding_seconds: float = 5.0
    ppe_keypoint_confidence: float = 0.45
    ppe_minimum_brightness: float = 55.0
    ppe_mask_colour: Literal["blue", "red"] = "blue"
    ppe_glove_colour: Literal["blue", "red"] = "red"
    ppe_hairnet_colour: Literal["blue", "red"] = "blue"
    ppe_apron_colour: Literal["blue", "red"] = "blue"
    ppe_mask_colour_ratio: float = 0.055
    ppe_glove_colour_ratio: float = 0.045
    ppe_hairnet_colour_ratio: float = 0.055
    ppe_apron_colour_ratio: float = 0.055
    ppe_require_hairnet: bool = False
    ppe_require_apron: bool = False
    process_marker_dwell_seconds: float = 0.5
    inventory_line_position: float = 0.81
    inventory_line_hysteresis: float = 0.025
    inventory_marker_dwell_seconds: float = 0.3

    temperature_source: str = "simulated"
    temperature_sensor_id: str = "TEMP-SIM-01"
    temperature_label: str = "Cold Storage Demo"
    temperature_initial_c: float = 4.2
    temperature_min_c: float = 0.0
    temperature_max_c: float = 5.0
    temperature_stale_seconds: float = 15.0
    temperature_serial_port: str = ""
    temperature_serial_baud: int = 9600
    temperature_mqtt_host: str = ""
    temperature_mqtt_port: int = 1883
    temperature_mqtt_topic: str = "orvia/sensors/temperature"
    temperature_mqtt_username: str = ""
    temperature_mqtt_password: str = ""

    edge_host: str = "127.0.0.1"
    edge_port: int = 8787
    edge_device_token: str = ""

    supabase_url: str = ""
    supabase_ingest_url: str = ""
    supabase_evidence_url: str = ""
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    livekit_room: str = "foodsafe-kitchen-01"

    data_dir: Path = ROOT / "data"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "edge.db"

    @property
    def evidence_dir(self) -> Path:
        return self.data_dir / "evidence"
