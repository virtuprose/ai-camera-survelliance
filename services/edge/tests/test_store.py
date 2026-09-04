from datetime import datetime, timedelta
from pathlib import Path

from foodsafe_edge.store import EventInput, EventStore


def test_event_has_one_year_retention_and_review(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "test.db")
    event = store.add_event(
        EventInput(type="test", title="Test event", detail="Controlled test", source_mode="simulated")
    )
    assert event["sourceMode"] == "simulated"
    occurred = datetime.fromisoformat(event["occurredAt"].replace("Z", "+00:00"))
    retained = datetime.fromisoformat(event["retentionUntil"].replace("Z", "+00:00"))
    assert retained - occurred >= timedelta(days=365)
    reviewed = store.update_status(event["id"], "acknowledged")
    assert reviewed["status"] == "acknowledged"


def test_offline_queue_reuses_event_uuid_and_requeues_review_changes(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "test.db")
    event = store.add_event(EventInput(type="test", title="Queued", detail="Offline proof"))

    assert store.queue_depth() == 1
    assert store.pending_events()[0]["id"] == event["id"]
    store.mark_synced(event["id"])
    assert store.queue_depth() == 0

    reviewed = store.update_status(event["id"], "acknowledged")
    assert reviewed["id"] == event["id"]
    assert store.pending_events()[0]["id"] == event["id"]


def test_inventory_never_becomes_negative(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "test.db")
    store.move_inventory("SKU-001", "out", 999)
    quantity = next(item["quantity"] for item in store.inventory() if item["sku"] == "SKU-001")
    assert quantity == 0


def test_temperature_and_inventory_history_are_retained(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "test.db")
    sampled_at = "2026-08-22T00:00:00Z"
    store.add_temperature_reading("TEMP-SIM-01", 8.1, 0, 5, "critical", "simulated", sampled_at)
    store.record_inventory_transaction("SKU-001", "in", 1, "EMP-001", 1.0, "simulated")
    temperature = store.temperature_readings()[0]
    transaction = store.inventory_transactions()[0]
    assert temperature["source_mode"] == "simulated"
    assert temperature["retention_until"] > temperature["sampled_at"]
    assert transaction["direction"] == "in"
    assert transaction["retention_until"] > transaction["occurred_at"]
