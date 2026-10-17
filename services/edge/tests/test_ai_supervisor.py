from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from foodsafe_edge.ai_supervisor import (
    AIJobWorker,
    OpenAIResponsesProvider,
    ProviderFailure,
    ProviderResult,
)
from foodsafe_edge.settings import Settings
from foodsafe_edge.store import EventInput, EventStore


def settings_for(tmp_path: Path, **updates: Any) -> Settings:
    values = {
        "_env_file": None,
        "data_dir": tmp_path,
        "camera_enabled": False,
        "openai_api_key": "test-key",
        "ai_timeout_seconds": 0.05,
        "ai_retry_count": 1,
    }
    values.update(updates)
    return Settings(**values)


def response_payload(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "resp_test",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps(result)}],
            }
        ],
    }


def operations_result(outcome: str = "supported") -> dict[str, Any]:
    return {
        "outcome": outcome,
        "summary": "Grounded result",
        "rationale": "Supported by the supplied record.",
        "source_record_ids": ["event-1"],
    }


def wait_for_terminal(store: EventStore, job_id: str, timeout: float = 1.5) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = store.get_ai_job(job_id)
        if job["status"] in {"completed", "needs_review", "unavailable", "failed"}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"AI job {job_id} did not finish")


class StaticReasoner:
    model = "test-model"
    configured = True

    def __init__(self, *, failures: int = 0, outcome: str = "supported"):
        self.failures = failures
        self.outcome = outcome
        self.calls = 0

    def reason(
        self,
        *,
        action: str,
        facts: dict[str, Any],
        source_record_ids: list[str],
    ) -> ProviderResult:
        self.calls += 1
        if self.calls <= self.failures:
            raise ProviderFailure(
                "network_error",
                "Provider unavailable; local monitoring continues.",
                job_state="unavailable",
            )
        return ProviderResult(
            {
                "outcome": self.outcome,
                "summary": f"Reviewed {action}",
                "rationale": "Bounded fixture",
                "source_record_ids": source_record_ids,
            },
            "resp_fixture",
        )


class StaticVerifier:
    model = "test-vision-model"
    configured = True

    def __init__(self, decisions: dict[str, str]):
        self.decisions = decisions
        self.calls = 0

    def verify(
        self,
        *,
        images: list[bytes],
        regions: list[str],
        source_record_ids: list[str],
    ) -> ProviderResult:
        self.calls += 1
        return ProviderResult(
            {
                "regions": [
                    {
                        "region": region,
                        "decision": self.decisions.get(region, "uncertain"),
                        "image_quality": "adequate",
                        "reason": "Fixture review",
                    }
                    for region in regions
                ],
                "source_record_ids": source_record_ids,
            },
            "resp_vision_fixture",
        )


def test_provider_requires_key_without_network(tmp_path: Path) -> None:
    settings = settings_for(tmp_path, openai_api_key="")
    provider = OpenAIResponsesProvider(settings)

    with pytest.raises(ProviderFailure) as raised:
        provider.reason(action="provider_smoke", facts={}, source_record_ids=[])

    assert raised.value.code == "missing_api_key"
    assert raised.value.job_state == "unavailable"


@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [(401, "invalid_api_key"), (403, "invalid_api_key"), (404, "unsupported_model"), (429, "rate_limited")],
)
def test_provider_maps_safe_http_failures(
    tmp_path: Path, status_code: int, expected_code: str
) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(status_code, request=request, json={"error": {"message": "x"}})
    )
    provider = OpenAIResponsesProvider(settings_for(tmp_path), transport=transport)

    with pytest.raises(ProviderFailure) as raised:
        provider.reason(action="provider_smoke", facts={}, source_record_ids=[])

    assert raised.value.code == expected_code
    assert raised.value.job_state == "unavailable"


def test_provider_retries_timeout_once_then_fails_safely(tmp_path: Path) -> None:
    calls = 0

    def timeout(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("timed out", request=request)

    provider = OpenAIResponsesProvider(settings_for(tmp_path), transport=httpx.MockTransport(timeout))

    with pytest.raises(ProviderFailure) as raised:
        provider.reason(action="provider_smoke", facts={}, source_record_ids=[])

    assert calls == 2
    assert raised.value.code == "timeout"


def test_provider_rejects_malformed_structured_response(tmp_path: Path) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            request=request,
            json=response_payload({"outcome": "supported", "summary": "missing fields"}),
        )
    )
    provider = OpenAIResponsesProvider(settings_for(tmp_path), transport=transport)

    with pytest.raises(ProviderFailure) as raised:
        provider.reason(action="provider_smoke", facts={}, source_record_ids=[])

    assert raised.value.code == "malformed_response"
    assert raised.value.job_state == "failed"


def test_provider_refusal_requires_human_review(tmp_path: Path) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            request=request,
            json={
                "id": "resp_refusal",
                "output": [
                    {"type": "message", "content": [{"type": "refusal", "refusal": "No"}]}
                ],
            },
        )
    )
    provider = OpenAIResponsesProvider(settings_for(tmp_path), transport=transport)

    with pytest.raises(ProviderFailure) as raised:
        provider.reason(action="provider_smoke", facts={}, source_record_ids=[])

    assert raised.value.code == "provider_refusal"
    assert raised.value.job_state == "needs_review"


def test_provider_uses_store_false_strict_schema_and_never_exposes_key(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["authorization"]
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, request=request, json=response_payload(operations_result()))

    provider = OpenAIResponsesProvider(
        settings_for(tmp_path, openai_api_key="private-key"),
        transport=httpx.MockTransport(handle),
    )
    result = provider.reason(
        action="explain_event",
        facts={"severity": "critical"},
        source_record_ids=["event-1"],
    )

    assert result.result["outcome"] == "supported"
    assert captured["authorization"] == "Bearer private-key"
    assert captured["payload"]["store"] is False
    assert captured["payload"]["model"] == "gpt-5.6-terra"
    assert captured["payload"]["text"]["format"]["strict"] is True
    assert "private-key" not in json.dumps(result.result)


def test_vision_interface_uses_memory_only_and_does_not_write_crop(tmp_path: Path) -> None:
    captured_payload: dict[str, Any] = {}
    result = {
        "regions": [
            {
                "region": "lower_face",
                "decision": "uncertain",
                "image_quality": "poor",
                "reason": "Fixture",
            }
        ],
        "source_record_ids": ["event-1"],
    }

    def handle(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content))
        return httpx.Response(200, request=request, json=response_payload(result))

    provider = OpenAIResponsesProvider(settings_for(tmp_path), transport=httpx.MockTransport(handle))
    before = set(tmp_path.rglob("*"))
    provider.verify(images=[b"jpeg-fixture"], regions=["lower_face"], source_record_ids=["event-1"])
    after = set(tmp_path.rglob("*"))

    assert before == after
    image_input = captured_payload["input"][0]["content"][1]
    assert image_input["type"] == "input_image"
    assert image_input["detail"] == "high"
    assert image_input["image_url"].startswith("data:image/jpeg;base64,")


def test_job_worker_deduplicates_and_keeps_request_facts_ephemeral(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    store = EventStore(settings.database_path)
    reasoner = StaticReasoner()
    worker = AIJobWorker(settings, store, reasoner)
    worker.start()
    try:
        first = worker.create_job(
            action="provider_smoke",
            source_record_ids=["event-1"],
            facts={"private_demo_fact": "not persisted"},
        )
        finished = wait_for_terminal(store, first["id"])
        second = worker.create_job(
            action="provider_smoke",
            source_record_ids=["event-1"],
            facts={"private_demo_fact": "not persisted"},
        )
    finally:
        worker.stop()

    assert finished["status"] == "completed"
    assert second["id"] == first["id"]
    assert reasoner.calls == 1
    assert store._ai_job_requests == {}
    columns = {
        row["name"] for row in store.connection.execute("PRAGMA table_info(ai_jobs)").fetchall()
    }
    assert "request_json" not in columns
    assert "facts_json" not in columns


def test_queue_capacity_and_local_rate_limit_fail_safely(tmp_path: Path) -> None:
    settings = settings_for(tmp_path, ai_queue_capacity=1, ai_rate_limit_per_minute=1)
    store = EventStore(settings.database_path)
    worker = AIJobWorker(settings, store, StaticReasoner())

    first = worker.create_job(
        action="provider_smoke", source_record_ids=["event-1"], facts={"sequence": 1}
    )
    second = worker.create_job(
        action="provider_smoke", source_record_ids=["event-2"], facts={"sequence": 2}
    )

    assert first["status"] == "queued"
    assert second["status"] == "unavailable"
    assert second["failure"]["code"] == "local_rate_limit"

    queue_settings = settings_for(tmp_path / "queue", ai_queue_capacity=1, ai_rate_limit_per_minute=6)
    queue_store = EventStore(queue_settings.database_path)
    queue_worker = AIJobWorker(queue_settings, queue_store, StaticReasoner())
    queue_worker.create_job(
        action="provider_smoke", source_record_ids=["event-1"], facts={"sequence": 1}
    )
    overflow = queue_worker.create_job(
        action="provider_smoke", source_record_ids=["event-2"], facts={"sequence": 2}
    )
    assert overflow["status"] == "unavailable"
    assert overflow["failure"]["code"] == "queue_full"


def test_circuit_breaker_opens_and_recovers(tmp_path: Path) -> None:
    settings = settings_for(
        tmp_path,
        ai_circuit_failure_threshold=2,
        ai_circuit_recovery_seconds=0.05,
    )
    store = EventStore(settings.database_path)
    reasoner = StaticReasoner(failures=2)
    worker = AIJobWorker(settings, store, reasoner)
    worker.start()
    try:
        for sequence in (1, 2):
            job = worker.create_job(
                action="provider_smoke",
                source_record_ids=[f"event-{sequence}"],
                facts={"sequence": sequence},
            )
            assert wait_for_terminal(store, job["id"])["status"] == "unavailable"
        assert worker.status()["circuit"]["state"] == "open"
        blocked = worker.create_job(
            action="provider_smoke", source_record_ids=["event-3"], facts={"sequence": 3}
        )
        assert blocked["failure"]["code"] == "circuit_open"
        time.sleep(0.06)
        recovered = worker.create_job(
            action="provider_smoke", source_record_ids=["event-4"], facts={"sequence": 4}
        )
        recovered = wait_for_terminal(store, recovered["id"])
    finally:
        worker.stop()

    assert recovered["status"] == "completed"
    assert worker.status()["circuit"]["state"] == "closed"


def test_successful_provider_status_survives_worker_restart(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    store = EventStore(settings.database_path)
    first_worker = AIJobWorker(settings, store, StaticReasoner())
    first_worker.start()
    try:
        created = first_worker.create_job(
            action="provider_smoke",
            source_record_ids=["phase6-smoke"],
            facts={"purpose": "restart regression"},
        )
        completed = wait_for_terminal(store, created["id"])
    finally:
        first_worker.stop()

    assert completed["status"] == "completed"
    completed_at = completed["completedAt"]
    restarted_worker = AIJobWorker(settings, EventStore(settings.database_path), StaticReasoner())

    assert restarted_worker.status()["lastSuccessfulJobAt"] == completed_at


def test_missing_key_job_is_unavailable_without_starting_worker(tmp_path: Path) -> None:
    settings = settings_for(tmp_path, openai_api_key="")
    store = EventStore(settings.database_path)
    worker = AIJobWorker(settings, store)

    job = worker.create_job(
        action="provider_smoke", source_record_ids=[], facts={"check": "configuration"}
    )

    assert job["status"] == "unavailable"
    assert job["failure"]["code"] == "missing_api_key"
    status = worker.status()
    assert status["configured"] is False
    assert status["localMonitoringUnaffected"] is True


def test_ai_job_retention_and_unknown_action(tmp_path: Path) -> None:
    settings = settings_for(tmp_path, openai_api_key="")
    store = EventStore(settings.database_path)
    worker = AIJobWorker(settings, store)
    job = worker.create_job(
        action="provider_smoke", source_record_ids=["health-1"], facts={}
    )

    assert job["retentionUntil"] > job["createdAt"]
    with pytest.raises(ValueError, match="Unsupported AI action"):
        worker.create_job(action="control_equipment", source_record_ids=[], facts={})
    with pytest.raises(ValueError, match="Unsupported AI action"):
        worker.create_job(action="review_ppe", source_record_ids=[], facts={})


def test_ppe_review_keeps_local_and_ai_decisions_separate(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    store = EventStore(settings.database_path)
    event = store.add_event(
        EventInput(
            type="ppe_violation",
            title="Mask not detected",
            detail="Fixture",
        )
    )
    verifier = StaticVerifier({"lower_face": "present", "left_hand": "missing"})
    worker = AIJobWorker(settings, store, StaticReasoner(), verifier)
    worker.start()
    try:
        created = worker.create_ppe_review_job(
            images=[b"face-contact-sheet", b"left-hand-contact-sheet"],
            regions=["lower_face", "left_hand"],
            local_decisions={"lower_face": "missing", "left_hand": "missing"},
            source_record_ids=[event["id"]],
            metadata={"contactSheetsPersisted": False},
            dedupe_key="track-7-state-1",
        )
        job = wait_for_terminal(store, created["id"])
    finally:
        worker.stop()

    assert job["status"] == "needs_review"
    assert job["result"]["assurance"] == "needs_human_review"
    assert job["result"]["regions"][0] == {
        "region": "lower_face",
        "localDecision": "missing",
        "aiDecision": "present",
        "imageQuality": "adequate",
        "reason": "Fixture review",
        "agreement": False,
    }
    assert job["result"]["regions"][1]["agreement"] is True
    assert store.get_event(event["id"])["metadata"]["ai_review_job_ids"] == [job["id"]]
    assert worker._vision_requests == {}


def test_ppe_review_reports_two_model_agreement(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    store = EventStore(settings.database_path)
    verifier = StaticVerifier({"lower_face": "present"})
    worker = AIJobWorker(settings, store, StaticReasoner(), verifier)
    worker.start()
    try:
        created = worker.create_ppe_review_job(
            images=[b"face-contact-sheet"],
            regions=["lower_face"],
            local_decisions={"lower_face": "present"},
            source_record_ids=["camera-state:fixture"],
            metadata={"contactSheetsPersisted": False},
            dedupe_key="track-7-present",
        )
        job = wait_for_terminal(store, created["id"])
    finally:
        worker.stop()

    assert job["status"] == "completed"
    assert job["result"]["assurance"] == "two_model_agreement"


def test_ppe_review_deduplicates_by_track_item_and_state(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    store = EventStore(settings.database_path)
    verifier = StaticVerifier({"lower_face": "present"})
    worker = AIJobWorker(settings, store, StaticReasoner(), verifier)
    worker.start()
    try:
        first = worker.create_ppe_review_job(
            images=[b"contact-sheet-one"],
            regions=["lower_face"],
            local_decisions={"lower_face": "present"},
            source_record_ids=["camera-state:one"],
            metadata={"contactSheetsPersisted": False},
            dedupe_key="track-7:mask:present",
        )
        finished = wait_for_terminal(store, first["id"])
        second = worker.create_ppe_review_job(
            images=[b"contact-sheet-two"],
            regions=["lower_face"],
            local_decisions={"lower_face": "present"},
            source_record_ids=["camera-state:one"],
            metadata={"contactSheetsPersisted": False},
            dedupe_key="track-7:mask:present",
        )
    finally:
        worker.stop()

    assert finished["status"] == "completed"
    assert second["id"] == first["id"]
    assert verifier.calls == 1


def test_worker_start_recovers_interrupted_jobs_without_request_data(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    store = EventStore(settings.database_path)
    worker = AIJobWorker(settings, store, StaticReasoner())
    interrupted = worker.create_job(
        action="provider_smoke",
        source_record_ids=["event-1"],
        facts={"temporary": "memory only"},
    )

    recovered_count = store.recover_incomplete_ai_jobs()
    recovered = store.get_ai_job(interrupted["id"])

    assert recovered_count == 1
    assert recovered["status"] == "unavailable"
    assert recovered["failure"]["code"] == "worker_restarted"
    assert store._ai_job_requests == {}
