from __future__ import annotations

import json
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .store import iso

if TYPE_CHECKING:
    from .settings import Settings


@dataclass(frozen=True, slots=True)
class TemperatureReading:
    sensor_id: str
    label: str
    value_c: float
    min_c: float
    max_c: float
    source_mode: str
    sampled_at: str

    @property
    def status(self) -> str:
        return "safe" if self.min_c <= self.value_c <= self.max_c else "critical"

    def payload(self) -> dict[str, Any]:
        return {
            "sensorId": self.sensor_id,
            "label": self.label,
            "valueC": self.value_c,
            "minC": self.min_c,
            "maxC": self.max_c,
            "status": self.status,
            "sourceMode": self.source_mode,
            "sampledAt": self.sampled_at,
        }


class TemperatureSource(ABC):
    source_mode = "real"

    @property
    @abstractmethod
    def online(self) -> bool: ...

    @property
    def error(self) -> str | None:
        return None

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def read(self) -> TemperatureReading | None: ...


class SimulatedTemperatureSource(TemperatureSource):
    source_mode = "simulated"

    def __init__(
        self,
        sensor_id: str,
        label: str,
        value_c: float,
        min_c: float,
        max_c: float,
    ) -> None:
        self.sensor_id = sensor_id
        self.label = label
        self.value_c = value_c
        self.min_c = min_c
        self.max_c = max_c

    @property
    def online(self) -> bool:
        return True

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def set_value(self, value_c: float) -> None:
        self.value_c = float(value_c)

    def read(self) -> TemperatureReading:
        return TemperatureReading(
            self.sensor_id,
            self.label,
            self.value_c,
            self.min_c,
            self.max_c,
            self.source_mode,
            iso(),
        )


def parse_temperature_payload(payload: str | bytes) -> float:
    text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    text = text.strip()
    if not text:
        raise ValueError("Temperature payload is empty")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return float(text)
    if isinstance(parsed, int | float):
        return float(parsed)
    if isinstance(parsed, dict):
        for key in ("valueC", "temperatureC", "temperature", "value"):
            if key in parsed:
                return float(parsed[key])
    raise ValueError("Temperature payload must contain valueC, temperatureC, temperature, or value")


class SerialTemperatureSource(TemperatureSource):
    """Read newline-delimited Celsius values or JSON from a calibrated serial gateway."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.connection: Any | None = None
        self._error: str | None = None

    @property
    def online(self) -> bool:
        return bool(self.connection and getattr(self.connection, "is_open", False))

    @property
    def error(self) -> str | None:
        return self._error

    def start(self) -> None:
        try:
            import serial  # type: ignore[import-not-found]

            self.connection = serial.Serial(
                self.settings.temperature_serial_port,
                self.settings.temperature_serial_baud,
                timeout=0.1,
            )
            self._error = None
        except Exception as error:
            self.connection = None
            self._error = str(error)

    def stop(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def read(self) -> TemperatureReading | None:
        if not self.online:
            return None
        try:
            payload = self.connection.readline()
            if not payload:
                return None
            value = parse_temperature_payload(payload)
            self._error = None
            return _reading(self.settings, value, "real")
        except Exception as error:
            self._error = str(error)
            return None


class MqttTemperatureSource(TemperatureSource):
    """Hold the latest calibrated MQTT sample and reject stale readings."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client: Any | None = None
        self._latest: tuple[float, float] | None = None
        self._connected = False
        self._error: str | None = None
        self._lock = threading.RLock()

    @property
    def online(self) -> bool:
        with self._lock:
            return self._connected and self._latest is not None and (
                time.monotonic() - self._latest[1] <= self.settings.temperature_stale_seconds
            )

    @property
    def error(self) -> str | None:
        return self._error

    def start(self) -> None:
        try:
            import paho.mqtt.client as mqtt  # type: ignore[import-not-found]

            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            if self.settings.temperature_mqtt_username:
                self.client.username_pw_set(
                    self.settings.temperature_mqtt_username,
                    self.settings.temperature_mqtt_password,
                )

            def on_connect(client: Any, _userdata: Any, _flags: Any, reason_code: Any, _props: Any) -> None:
                with self._lock:
                    self._connected = int(reason_code) == 0
                if self._connected:
                    client.subscribe(self.settings.temperature_mqtt_topic, qos=1)

            def on_message(_client: Any, _userdata: Any, message: Any) -> None:
                try:
                    value = parse_temperature_payload(message.payload)
                    with self._lock:
                        self._latest = (value, time.monotonic())
                        self._error = None
                except Exception as error:
                    self._error = str(error)

            self.client.on_connect = on_connect
            self.client.on_message = on_message
            self.client.connect(
                self.settings.temperature_mqtt_host,
                self.settings.temperature_mqtt_port,
                keepalive=30,
            )
            self.client.loop_start()
        except Exception as error:
            self.client = None
            self._connected = False
            self._error = str(error)

    def stop(self) -> None:
        if self.client is not None:
            self.client.loop_stop()
            self.client.disconnect()
            self.client = None
        self._connected = False

    def read(self) -> TemperatureReading | None:
        with self._lock:
            latest = self._latest
        if not self.online or latest is None:
            return None
        return _reading(self.settings, latest[0], "real")


def _reading(settings: Settings, value_c: float, source_mode: str) -> TemperatureReading:
    return TemperatureReading(
        settings.temperature_sensor_id,
        settings.temperature_label,
        float(value_c),
        settings.temperature_min_c,
        settings.temperature_max_c,
        source_mode,
        iso(),
    )


def create_temperature_source(settings: Settings) -> TemperatureSource:
    if settings.temperature_source == "simulated":
        return SimulatedTemperatureSource(
            settings.temperature_sensor_id,
            settings.temperature_label,
            settings.temperature_initial_c,
            settings.temperature_min_c,
            settings.temperature_max_c,
        )
    if settings.temperature_source == "serial":
        return SerialTemperatureSource(settings)
    if settings.temperature_source == "mqtt":
        return MqttTemperatureSource(settings)
    raise ValueError(f"Unsupported temperature source: {settings.temperature_source}")
