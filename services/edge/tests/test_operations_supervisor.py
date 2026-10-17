from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from foodsafe_edge.enterprise import EnterpriseStore
from foodsafe_edge.operations_supervisor import (
    FEATURES,
    ClientDemoPreflight,
    OperationsSupervisor,
)
from foodsafe_edge.settings import Settings
from foodsafe_edge.store import EventInput, EventStore, iso


class RecordingWorker:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create_operations_job(self, **payload: Any) -> dict[str, Any]:
        self.calls.append(payload)
        return {"id": "job-grounded", "status": "queued", **payload}

    def create_insufficient_evidence_job(self, **payload: Any) -> dict[str, Any]:
        self.calls.append(payload)
        return {
            "id": "job-insufficient",
            "status": "completed",
            "result": {"outcome": "insufficient_evidence", "sourceRecordIds": []},
        }


def build(
    tmp_path: Path,
) -> tuple[Settings, EventStore, EnterpriseStore, RecordingWorker, OperationsSupervisor]:
    settings = Settings(_env_file=None, data_dir=tmp_path, camera_enabled=False, openai_api_key="test")
    store = EventStore(settings.database_path)
    enterprise = EnterpriseStore(store)
    worker = RecordingWorker()
    supervisor = OperationsSupervisor(settings, store, enterprise, worker)  # type: ignore[arg-type]
    return settings, store, enterprise, worker, supervisor


def seed_records(store: EventStore, enterprise: EnterpriseStore, variant: int = 0) -> None:
    store.add_event(
        EventInput(
            type="ppe_violation",
            title="Mask not detected",
            detail=f"Visible lower-face region remained non-compliant. Fixture {variant}.",
            severity="critical",
            source_mode="real",
            zone="Preparation",
            confidence=round(0.81 + variant / 100, 2),
        ),
        {"item": "mask", "stable_duration_seconds": 3.2},
    )
    run = store.start_process("Chicken Washing", "simulated")
    store.complete_process(run["id"])
    store.record_inventory_transaction(
        "SKU-001", "in" if variant % 2 == 0 else "out", 1, None, 0.96, "simulated"
    )
    store.add_temperature_reading(
        "TEMP-SIM-01", round(5.5 + variant / 10, 1), 0, 5, "critical", "simulated", iso()
    )
    enterprise.ensure_incidents()


def mark_ready(store: EventStore, action: str) -> None:
    store.record_ai_feature_readiness(
        action,
        config_passed=True,
        automated_tests_passed=True,
        fixtures_passed=True,
        live_smoke_passed=True,
        detail="Verified fixture",
    )


@pytest.mark.parametrize(
    ("action", "variant"),
    [(action, variant) for action in FEATURES for variant in range(10)],
)
def test_each_action_uses_server_selected_grounded_fixture(tmp_path: Path, action: str, variant: int) -> None:
    _, store, enterprise, worker, supervisor = build(tmp_path)
    seed_records(store, enterprise, variant)
    mark_ready(store, action)

    job = supervisor.run(action)

    assert job["status"] == "queued"
    request = worker.calls[-1]
    assert request["action"] == action
    assert request["source_record_ids"]
    assert request["facts"]
    assert "api_key" not in str(request).lower()


def test_action_is_blocked_until_every_current_gate_passes(tmp_path: Path) -> None:
    _, store, enterprise, _, supervisor = build(tmp_path)
    seed_records(store, enterprise)

    with pytest.raises(PermissionError, match="readiness record"):
        supervisor.run("review_operations")

    mark_ready(store, "review_operations")
    store.set_ai_feature_enabled("review_operations", False)
    with pytest.raises(PermissionError, match="kill switch"):
        supervisor.run("review_operations")


def test_missing_operational_record_returns_insufficient_evidence(tmp_path: Path) -> None:
    _, store, _, worker, supervisor = build(tmp_path)
    mark_ready(store, "explain_latest_alert")

    job = supervisor.run("explain_latest_alert")

    assert job["result"]["outcome"] == "insufficient_evidence"
    assert worker.calls[-1]["action"] == "explain_latest_alert"


def test_shift_summary_counts_are_deterministic_database_facts(tmp_path: Path) -> None:
    _, store, enterprise, _, supervisor = build(tmp_path)
    seed_records(store, enterprise)

    facts, source_ids = supervisor.collect("generate_shift_summary")

    assert facts["exactCounts"]["events"] == 1
    assert facts["exactCounts"]["realEvents"] == 1
    assert facts["exactCounts"]["inventoryMovements"] == 1
    assert facts["exactCounts"]["temperatureReadings"] == 1
    assert source_ids


def test_preflight_fails_closed_when_physical_gates_are_not_recorded(tmp_path: Path) -> None:
    settings, store, enterprise, worker, supervisor = build(tmp_path)
    preflight = ClientDemoPreflight(settings, store, supervisor)
    runtime = {
        "health": {
            "camera": "offline",
            "cameraLabel": "FaceTime HD Camera",
            "lastFrameAt": None,
            "processedFps": 0,
            "ppeVerifier": {"status": "passed"},
            "storage": "online",
            "storageError": None,
        },
        "detection": {"readiness": None},
        "aiPpeAssurance": {
            "provider": {
                "configured": True,
                "available": True,
                "model": "test-model",
                "lastSuccessfulJobAt": None,
            }
        },
    }

    result = preflight.status(runtime)

    assert result["status"] == "blocked"
    assert result["summary"]["readyAiActions"] == 0
    assert next(item for item in result["checks"] if item["id"] == "camera_source")["status"] == "failed"
    assert next(item for item in result["checks"] if item["id"] == "ppe_acceptance")["status"] == "pending"


def test_preflight_does_not_treat_prerecorded_fallback_as_live_camera(tmp_path: Path) -> None:
    settings, store, _, _, supervisor = build(tmp_path)
    preflight = ClientDemoPreflight(settings, store, supervisor)
    runtime = {
        "health": {
            "camera": "online",
            "cameraLabel": "Prerecorded local fallback",
            "sourceType": "file",
            "lastFrameAt": "2026-09-21T21:00:00Z",
            "processedFps": 9.4,
            "ppeVerifier": {"status": "passed"},
            "storage": "online",
            "storageError": None,
        },
        "detection": {"readiness": None},
        "aiPpeAssurance": {
            "provider": {
                "configured": True,
                "available": True,
                "model": "test-model",
                "lastSuccessfulJobAt": None,
            }
        },
    }

    result = preflight.status(runtime)
    camera = next(item for item in result["checks"] if item["id"] == "camera_source")

    assert result["status"] == "blocked"
    assert camera["status"] == "failed"
    assert "prerecorded fallback" in camera["detail"]


def test_manual_preflight_records_explicit_evidence(tmp_path: Path) -> None:
    settings, store, _, _, supervisor = build(tmp_path)
    preflight = ClientDemoPreflight(settings, store, supervisor)

    record = preflight.record_manual("camera_soak", "passed", "10 minutes, no stale frame")

    assert record["status"] == "passed"
    assert record["current"] is True
    with pytest.raises(KeyError):
        preflight.record_manual("unknown", "passed", "not allowed")
