import pytest

from foodsafe_edge.pipeline import EdgePipeline
from foodsafe_edge.settings import Settings
from foodsafe_edge.temperature import (
    SimulatedTemperatureSource,
    create_temperature_source,
    parse_temperature_payload,
)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ("4.2", 4.2),
        ('{"valueC": 6.1}', 6.1),
        ('{"temperatureC": 1.5}', 1.5),
        ('{"temperature": -2}', -2.0),
        ('{"value": 8}', 8.0),
    ],
)
def test_temperature_payload_contract(payload: str, expected: float) -> None:
    assert parse_temperature_payload(payload) == expected


def test_temperature_payload_rejects_unknown_or_empty_values() -> None:
    with pytest.raises(ValueError, match="empty"):
        parse_temperature_payload("")
    with pytest.raises(ValueError, match="must contain"):
        parse_temperature_payload('{"humidity": 45}')


def test_simulated_source_is_explicit_and_uses_configured_thresholds() -> None:
    settings = Settings(camera_enabled=False)
    source = create_temperature_source(settings)
    assert isinstance(source, SimulatedTemperatureSource)
    assert source.read().status == "safe"
    assert source.read().source_mode == "simulated"

    source.set_value(8.1)
    assert source.read().status == "critical"


def test_temperature_transitions_emit_one_alert_and_one_recovery(tmp_path) -> None:
    pipeline = EdgePipeline(Settings(camera_enabled=False, data_dir=tmp_path))

    pipeline.demo_action("temperature-high", {})
    pipeline.demo_action("temperature-high", {})
    pipeline.demo_action("temperature-safe", {})
    pipeline.demo_action("temperature-safe", {})

    events = sorted(pipeline.store.list_events(), key=lambda event: event["occurredAt"])
    assert [event["type"] for event in events] == [
        "temperature_alert",
        "temperature_recovered",
    ]
    assert all(event["sourceMode"] == "simulated" for event in events)
    assert events[0]["metadata"]["sensor_id"] == "TEMP-SIM-01"
    assert events[0]["metadata"]["source_origin"] == "simulated_temperature_source"
    assert len(pipeline.store.temperature_readings()) == 4
