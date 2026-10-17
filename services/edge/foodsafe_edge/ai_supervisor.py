from __future__ import annotations

import base64
import hashlib
import json
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from .settings import Settings
from .store import EventStore, iso

# The generic public endpoint remains intentionally narrow. Operational
# actions are created only from records selected by OperationsSupervisor.
PUBLIC_OPERATIONS_ACTIONS = {"provider_smoke"}
SUPERVISOR_ACTIONS = {
    "explain_latest_alert",
    "interpret_process",
    "analyze_inventory",
    "review_cold_chain",
    "show_sop_guidance",
    "review_operations",
    "generate_shift_summary",
}
TERMINAL_JOB_STATES = {"completed", "needs_review", "unavailable", "failed"}


@dataclass(slots=True)
class ProviderResult:
    result: dict[str, Any]
    provider_request_id: str | None = None


@dataclass(slots=True)
class VisionJobRequest:
    images: list[bytes]
    regions: list[str]
    local_decisions: dict[str, str]
    source_record_ids: list[str]
    metadata: dict[str, Any]


class ProviderFailure(RuntimeError):
    def __init__(self, code: str, detail: str, *, job_state: str, retryable: bool = False):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.job_state = job_state
        self.retryable = retryable


class VisionVerifier(Protocol):
    model: str

    @property
    def configured(self) -> bool: ...

    def verify(
        self,
        *,
        images: list[bytes],
        regions: list[str],
        source_record_ids: list[str],
    ) -> ProviderResult: ...


class OperationsReasoner(Protocol):
    model: str

    @property
    def configured(self) -> bool: ...

    def reason(
        self,
        *,
        action: str,
        facts: dict[str, Any],
        source_record_ids: list[str],
    ) -> ProviderResult: ...


OPERATIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "outcome": {
            "type": "string",
            "enum": ["supported", "insufficient_evidence", "needs_review"],
        },
        "summary": {"type": "string", "maxLength": 1000},
        "rationale": {"type": "string", "maxLength": 2000},
        "source_record_ids": {
            "type": "array",
            "items": {"type": "string", "maxLength": 128},
            "maxItems": 20,
        },
    },
    "required": ["outcome", "summary", "rationale", "source_record_ids"],
    "additionalProperties": False,
}

VISION_SCHEMA = {
    "type": "object",
    "properties": {
        "regions": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "region": {"type": "string"},
                    "decision": {
                        "type": "string",
                        "enum": ["present", "missing", "uncertain"],
                    },
                    "image_quality": {"type": "string", "enum": ["adequate", "poor"]},
                    "reason": {"type": "string", "maxLength": 500},
                },
                "required": ["region", "decision", "image_quality", "reason"],
                "additionalProperties": False,
            },
        },
        "source_record_ids": {
            "type": "array",
            "items": {"type": "string", "maxLength": 128},
            "maxItems": 20,
        },
    },
    "required": ["regions", "source_record_ids"],
    "additionalProperties": False,
}


class OpenAIResponsesProvider(VisionVerifier, OperationsReasoner):
    """Stateless OpenAI Responses API adapter with strict structured outputs."""

    endpoint = "https://api.openai.com/v1/responses"

    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.model = settings.openai_model
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self._api_key())

    def reason(
        self,
        *,
        action: str,
        facts: dict[str, Any],
        source_record_ids: list[str],
    ) -> ProviderResult:
        prompt = json.dumps(
            {
                "action": action,
                "facts": facts,
                "source_record_ids": source_record_ids,
                "output_policy": (
                    "Explain only these exact facts. Do not introduce new people, measurements, "
                    "quantities, timestamps, causes, actions, or status. Use insufficient_evidence "
                    "when the facts do not support a conclusion. This output is advisory and cannot "
                    "change any operational record."
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        content = [{"type": "input_text", "text": prompt}]
        return self._request(content, OPERATIONS_SCHEMA, "operations_result")

    def verify(
        self,
        *,
        images: list[bytes],
        regions: list[str],
        source_record_ids: list[str],
    ) -> ProviderResult:
        if not images or len(images) != len(regions) or len(images) > 3:
            raise ProviderFailure(
                "invalid_vision_input",
                "Vision review requires one to three named image regions.",
                job_state="failed",
            )
        content: list[dict[str, Any]] = [
            {
                "type": "input_text",
                "text": json.dumps(
                    {
                        "task": (
                            "Review each three-frame contact sheet only for the named PPE region. "
                            "For lower_face, present means a blue protective mask visibly covers "
                            "the nose and mouth. For left_hand or right_hand, present means a red "
                            "protective glove visibly covers the hand. Return uncertain whenever "
                            "the region, coverage, lighting, or image quality is insufficient."
                        ),
                        "regions_in_image_order": regions,
                        "source_record_ids": source_record_ids,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
        ]
        for image in images:
            encoded = base64.b64encode(image).decode("ascii")
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:image/jpeg;base64,{encoded}",
                    "detail": "high",
                }
            )
        return self._request(content, VISION_SCHEMA, "ppe_review_result")

    def _api_key(self) -> str:
        return self.settings.openai_api_key.get_secret_value().strip()

    def _request(
        self,
        content: list[dict[str, Any]],
        schema: dict[str, Any],
        schema_name: str,
    ) -> ProviderResult:
        key = self._api_key()
        if not key:
            raise ProviderFailure(
                "missing_api_key",
                "OpenAI is not configured. Local monitoring continues.",
                job_state="unavailable",
            )
        payload = {
            "model": self.model,
            "store": False,
            "reasoning": {"effort": self.settings.openai_reasoning_effort},
            "max_output_tokens": self.settings.ai_max_output_tokens,
            "instructions": (
                "You are a read-only operations reviewer. Use only the supplied facts and source record IDs. "
                "Never infer identity, demographics, measurements, or actions. Return insufficient evidence "
                "when the supplied records do not support a conclusion."
            ),
            "input": [{"role": "user", "content": content}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        timeout = httpx.Timeout(self.settings.ai_timeout_seconds)
        attempts = self.settings.ai_retry_count + 1
        with httpx.Client(timeout=timeout, transport=self._transport) as client:
            for attempt in range(attempts):
                try:
                    response = client.post(
                        self.endpoint,
                        headers={
                            "authorization": f"Bearer {key}",
                            "content-type": "application/json",
                        },
                        json=payload,
                    )
                except httpx.TimeoutException as error:
                    if attempt + 1 < attempts:
                        continue
                    raise ProviderFailure(
                        "timeout",
                        "OpenAI did not respond within the configured timeout.",
                        job_state="unavailable",
                        retryable=True,
                    ) from error
                except httpx.NetworkError as error:
                    if attempt + 1 < attempts:
                        continue
                    raise ProviderFailure(
                        "network_error",
                        "OpenAI could not be reached. Local monitoring continues.",
                        job_state="unavailable",
                        retryable=True,
                    ) from error

                if response.status_code >= 500 and attempt + 1 < attempts:
                    continue
                if response.status_code >= 400:
                    raise self._http_failure(response)
                return self._parse_response(response, schema_name)
        raise ProviderFailure("provider_error", "OpenAI request failed.", job_state="failed")

    def _http_failure(self, response: httpx.Response) -> ProviderFailure:
        status = response.status_code
        if status in {401, 403}:
            return ProviderFailure(
                "invalid_api_key",
                "OpenAI credentials were rejected. Local monitoring continues.",
                job_state="unavailable",
            )
        if status == 404:
            return ProviderFailure(
                "unsupported_model",
                f"Configured model {self.model} is unavailable for this account.",
                job_state="unavailable",
            )
        if status == 429:
            return ProviderFailure(
                "rate_limited",
                "OpenAI rate limit or quota was reached. Local monitoring continues.",
                job_state="unavailable",
                retryable=True,
            )
        if status in {408, 409} or status >= 500:
            return ProviderFailure(
                "provider_unavailable",
                "OpenAI is temporarily unavailable. Local monitoring continues.",
                job_state="unavailable",
                retryable=True,
            )
        return ProviderFailure(
            "provider_rejected_request",
            "OpenAI rejected the bounded review request.",
            job_state="failed",
        )

    @classmethod
    def _parse_response(cls, response: httpx.Response, schema_name: str) -> ProviderResult:
        try:
            payload = response.json()
        except ValueError as error:
            raise ProviderFailure(
                "malformed_response",
                "OpenAI returned an unreadable response.",
                job_state="failed",
            ) from error
        for item in payload.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "refusal":
                    raise ProviderFailure(
                        "provider_refusal",
                        "OpenAI declined this review; human review is required.",
                        job_state="needs_review",
                    )
                if content.get("type") != "output_text":
                    continue
                try:
                    result = json.loads(content["text"])
                except (KeyError, TypeError, json.JSONDecodeError) as error:
                    raise ProviderFailure(
                        "malformed_response",
                        "OpenAI returned a response that did not match the required structure.",
                        job_state="failed",
                    ) from error
                if not isinstance(result, dict):
                    raise ProviderFailure(
                        "malformed_response",
                        "OpenAI returned a response that did not match the required structure.",
                        job_state="failed",
                    )
                cls._validate_structured_result(result, schema_name)
                return ProviderResult(result=result, provider_request_id=payload.get("id"))
        raise ProviderFailure(
            "malformed_response",
            "OpenAI returned no structured result.",
            job_state="failed",
        )

    @staticmethod
    def _validate_structured_result(result: dict[str, Any], schema_name: str) -> None:
        valid = False
        if schema_name == "operations_result":
            valid = (
                set(result) == {"outcome", "summary", "rationale", "source_record_ids"}
                and result.get("outcome")
                in {"supported", "insufficient_evidence", "needs_review"}
                and isinstance(result.get("summary"), str)
                and isinstance(result.get("rationale"), str)
                and isinstance(result.get("source_record_ids"), list)
                and all(isinstance(item, str) for item in result["source_record_ids"])
            )
        elif schema_name == "ppe_review_result":
            regions = result.get("regions")
            valid = (
                set(result) == {"regions", "source_record_ids"}
                and isinstance(regions, list)
                and isinstance(result.get("source_record_ids"), list)
                and all(isinstance(item, str) for item in result["source_record_ids"])
                and all(
                    isinstance(region, dict)
                    and set(region) == {"region", "decision", "image_quality", "reason"}
                    and isinstance(region.get("region"), str)
                    and region.get("decision") in {"present", "missing", "uncertain"}
                    and region.get("image_quality") in {"adequate", "poor"}
                    and isinstance(region.get("reason"), str)
                    for region in regions
                )
            )
        if not valid:
            raise ProviderFailure(
                "malformed_response",
                "OpenAI returned a response that did not match the required structure.",
                job_state="failed",
            )


class AIJobWorker:
    """Single bounded worker so cloud work never blocks the live camera pipeline."""

    def __init__(
        self,
        settings: Settings,
        store: EventStore,
        reasoner: OperationsReasoner | None = None,
        verifier: VisionVerifier | None = None,
    ):
        self.settings = settings
        self.store = store
        provider = OpenAIResponsesProvider(settings)
        self.reasoner = reasoner or provider
        self.verifier = verifier or (
            self.reasoner if hasattr(self.reasoner, "verify") else provider
        )
        self._queue: queue.Queue[str] = queue.Queue(maxsize=settings.ai_queue_capacity)
        self._vision_requests: dict[str, VisionJobRequest] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._accepted_at: deque[float] = deque()
        self._consecutive_failures = 0
        self._circuit_opened_at: float | None = None
        self._last_failure: dict[str, Any] | None = None
        self._last_success_at = self.store.latest_successful_ai_job_at()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.store.recover_incomplete_ai_jobs()
        with self._lock:
            self._vision_requests.clear()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="ai-supervisor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        with self._lock:
            self._vision_requests.clear()

    def create_job(
        self,
        *,
        action: str,
        source_record_ids: list[str],
        facts: dict[str, Any],
        dedupe_key: str | None = None,
    ) -> dict[str, Any]:
        if action not in PUBLIC_OPERATIONS_ACTIONS:
            raise ValueError("Unsupported AI action")
        return self._create_reasoning_job(
            action=action,
            source_record_ids=source_record_ids,
            facts=facts,
            dedupe_key=dedupe_key,
        )

    def create_operations_job(
        self,
        *,
        action: str,
        source_record_ids: list[str],
        facts: dict[str, Any],
        dedupe_key: str | None = None,
    ) -> dict[str, Any]:
        """Queue a trusted, server-grounded operational interpretation."""
        if action not in SUPERVISOR_ACTIONS:
            raise ValueError("Unsupported AI supervisor action")
        if not source_record_ids or not facts:
            return self.create_insufficient_evidence_job(
                action=action,
                detail="Insufficient operational evidence",
            )
        return self._create_reasoning_job(
            action=action,
            source_record_ids=source_record_ids,
            facts=facts,
            dedupe_key=dedupe_key,
        )

    def create_insufficient_evidence_job(
        self,
        *,
        action: str,
        detail: str = "Insufficient operational evidence",
    ) -> dict[str, Any]:
        if action not in SUPERVISOR_ACTIONS:
            raise ValueError("Unsupported AI supervisor action")
        fingerprint = hashlib.sha256(f"{action}:insufficient".encode()).hexdigest()
        existing = self.store.find_recent_ai_job(fingerprint, seconds=15)
        if existing:
            return existing
        job = self.store.create_ai_job(
            action=action,
            source_record_ids=[],
            model=self.reasoner.model,
            prompt_version=self.settings.ai_prompt_version,
            request_fingerprint=fingerprint,
        )
        return self.store.finish_ai_job(
            job["id"],
            status="completed",
            result={
                "outcome": "insufficient_evidence",
                "summary": detail,
                "rationale": "No qualifying local source record is available for this action.",
                "sourceRecordIds": [],
                "exactFacts": {},
                "aiAssisted": True,
                "advisoryOnly": True,
                "authoritativeSource": "local_operational_records",
            },
            latency_ms=0,
        )

    def _create_reasoning_job(
        self,
        *,
        action: str,
        source_record_ids: list[str],
        facts: dict[str, Any],
        dedupe_key: str | None = None,
    ) -> dict[str, Any]:
        fingerprint_payload = {
            "action": action,
            "source_record_ids": sorted(source_record_ids),
            "facts": facts,
            "dedupe_key": dedupe_key,
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        existing = self.store.find_recent_ai_job(fingerprint, seconds=60)
        if existing:
            return existing

        job = self.store.create_ai_job(
            action=action,
            source_record_ids=source_record_ids,
            model=self.reasoner.model,
            prompt_version=self.settings.ai_prompt_version,
            request_fingerprint=fingerprint,
        )
        if not self.reasoner.configured:
            return self.store.finish_ai_job(
                job["id"],
                status="unavailable",
                failure_code="missing_api_key",
                failure_detail="OpenAI is not configured. Local monitoring continues.",
            )
        if self._circuit_is_open():
            return self.store.finish_ai_job(
                job["id"],
                status="unavailable",
                failure_code="circuit_open",
                failure_detail="AI reviews are paused briefly after repeated provider failures.",
            )
        with self._lock:
            now = time.monotonic()
            while self._accepted_at and now - self._accepted_at[0] >= 60:
                self._accepted_at.popleft()
            if len(self._accepted_at) >= self.settings.ai_rate_limit_per_minute:
                return self.store.finish_ai_job(
                    job["id"],
                    status="unavailable",
                    failure_code="local_rate_limit",
                    failure_detail="The local AI review limit has been reached. Try again shortly.",
                )
            self.store.set_ai_job_request(job["id"], facts)
            try:
                self._queue.put_nowait(job["id"])
            except queue.Full:
                self.store.discard_ai_job_request(job["id"])
                return self.store.finish_ai_job(
                    job["id"],
                    status="unavailable",
                    failure_code="queue_full",
                    failure_detail="The AI review queue is full. Local monitoring continues.",
                )
            self._accepted_at.append(now)
        return self.store.get_ai_job(job["id"])

    def create_ppe_review_job(
        self,
        *,
        images: list[bytes],
        regions: list[str],
        local_decisions: dict[str, str],
        source_record_ids: list[str],
        metadata: dict[str, Any],
        dedupe_key: str,
    ) -> dict[str, Any]:
        if not images or len(images) != len(regions) or len(images) > 3:
            raise ValueError("PPE review requires one to three fresh named contact sheets")
        if any(region not in {"lower_face", "left_hand", "right_hand"} for region in regions):
            raise ValueError("Unsupported PPE review region")
        if set(local_decisions) != set(regions) or any(
            decision not in {"present", "missing"} for decision in local_decisions.values()
        ):
            raise ValueError("PPE review requires a stable local decision for every region")
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "action": "review_ppe",
                    "source_record_ids": sorted(source_record_ids),
                    "regions": regions,
                    "local_decisions": local_decisions,
                    "dedupe_key": dedupe_key,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        existing = self.store.find_recent_ai_job(fingerprint, seconds=60)
        if existing:
            return existing
        job = self.store.create_ai_job(
            action="review_ppe",
            source_record_ids=source_record_ids,
            model=self.verifier.model,
            prompt_version=self.settings.ai_prompt_version,
            request_fingerprint=fingerprint,
        )
        if not self.verifier.configured:
            return self.store.finish_ai_job(
                job["id"],
                status="unavailable",
                failure_code="missing_api_key",
                failure_detail="OpenAI is not configured. Local monitoring continues.",
            )
        if self._circuit_is_open():
            return self.store.finish_ai_job(
                job["id"],
                status="unavailable",
                failure_code="circuit_open",
                failure_detail="AI reviews are paused briefly after repeated provider failures.",
            )
        request = VisionJobRequest(
            images=list(images),
            regions=list(regions),
            local_decisions=dict(local_decisions),
            source_record_ids=list(source_record_ids),
            metadata=dict(metadata),
        )
        with self._lock:
            now = time.monotonic()
            while self._accepted_at and now - self._accepted_at[0] >= 60:
                self._accepted_at.popleft()
            if len(self._accepted_at) >= self.settings.ai_rate_limit_per_minute:
                return self.store.finish_ai_job(
                    job["id"],
                    status="unavailable",
                    failure_code="local_rate_limit",
                    failure_detail="The local AI review limit has been reached. Try again shortly.",
                )
            self._vision_requests[job["id"]] = request
            try:
                self._queue.put_nowait(job["id"])
            except queue.Full:
                self._vision_requests.pop(job["id"], None)
                return self.store.finish_ai_job(
                    job["id"],
                    status="unavailable",
                    failure_code="queue_full",
                    failure_detail="The AI review queue is full. Local monitoring continues.",
                )
            self._accepted_at.append(now)
        return self.store.get_ai_job(job["id"])

    def status(self) -> dict[str, Any]:
        circuit_open = self._circuit_is_open()
        retry_after = 0
        if circuit_open and self._circuit_opened_at is not None:
            retry_after = max(
                0,
                round(
                    self.settings.ai_circuit_recovery_seconds
                    - (time.monotonic() - self._circuit_opened_at)
                ),
            )
        configured = self.reasoner.configured and self.verifier.configured
        return {
            "provider": self.settings.ai_provider,
            "configured": configured,
            "available": configured and not circuit_open,
            "model": self.reasoner.model,
            "promptVersion": self.settings.ai_prompt_version,
            "queueDepth": self._queue.qsize(),
            "queueCapacity": self.settings.ai_queue_capacity,
            "lastSuccessfulJobAt": self._last_success_at,
            "lastFailure": self._last_failure,
            "circuit": {
                "state": "open" if circuit_open else "closed",
                "retryAfterSeconds": retry_after,
            },
            "localMonitoringUnaffected": True,
        }

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                job_id = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self._process(job_id)
            finally:
                self._queue.task_done()

    def _process(self, job_id: str) -> None:
        job = self.store.start_ai_job(job_id)
        started = time.monotonic()
        try:
            if job["action"] == "review_ppe":
                request = self._take_vision_request(job_id)
                provider_result = self.verifier.verify(
                    images=request.images,
                    regions=request.regions,
                    source_record_ids=job["sourceRecordIds"],
                )
                combined, needs_review = self._combine_ppe_result(
                    provider_result.result, request
                )
                result = ProviderResult(combined, provider_result.provider_request_id)
            else:
                exact_facts = self.store.take_ai_job_request(job_id)
                provider_result = self.reasoner.reason(
                    action=job["action"],
                    facts=exact_facts,
                    source_record_ids=job["sourceRecordIds"],
                )
                grounded_result = {
                    "outcome": provider_result.result["outcome"],
                    "summary": provider_result.result["summary"],
                    "rationale": provider_result.result["rationale"],
                    # Provenance is controlled by the edge service, never by the model.
                    "sourceRecordIds": job["sourceRecordIds"],
                    "exactFacts": exact_facts,
                    "aiAssisted": True,
                    "advisoryOnly": True,
                    "authoritativeSource": "local_operational_records",
                }
                result = ProviderResult(grounded_result, provider_result.provider_request_id)
                needs_review = grounded_result["outcome"] == "needs_review"
            elapsed_ms = round((time.monotonic() - started) * 1000)
            status = "needs_review" if needs_review else "completed"
            self.store.finish_ai_job(
                job_id,
                status=status,
                result=result.result,
                latency_ms=elapsed_ms,
                provider_request_id=result.provider_request_id,
            )
            if job["action"] == "review_ppe":
                for record_id in job["sourceRecordIds"]:
                    self.store.append_ai_review_reference(record_id, job_id)
            with self._lock:
                self._consecutive_failures = 0
                self._circuit_opened_at = None
                self._last_failure = None
                self._last_success_at = iso()
        except ProviderFailure as error:
            elapsed_ms = round((time.monotonic() - started) * 1000)
            self.store.finish_ai_job(
                job_id,
                status=error.job_state,
                latency_ms=elapsed_ms,
                failure_code=error.code,
                failure_detail=error.detail,
            )
            self._record_failure(error)
        except Exception:
            elapsed_ms = round((time.monotonic() - started) * 1000)
            self.store.finish_ai_job(
                job_id,
                status="failed",
                latency_ms=elapsed_ms,
                failure_code="unexpected_provider_error",
                failure_detail="The AI review failed safely. Local monitoring continues.",
            )
            self._record_failure(
                ProviderFailure(
                    "unexpected_provider_error",
                    "The AI review failed safely. Local monitoring continues.",
                    job_state="failed",
                )
            )
        finally:
            self.store.discard_ai_job_request(job_id)
            with self._lock:
                self._vision_requests.pop(job_id, None)

    def _take_vision_request(self, job_id: str) -> VisionJobRequest:
        with self._lock:
            request = self._vision_requests.pop(job_id, None)
        if request is None:
            raise ProviderFailure(
                "vision_evidence_expired",
                "The temporary PPE review evidence is no longer available.",
                job_state="unavailable",
            )
        return request

    @staticmethod
    def _combine_ppe_result(
        provider_result: dict[str, Any], request: VisionJobRequest
    ) -> tuple[dict[str, Any], bool]:
        returned = {region["region"]: region for region in provider_result["regions"]}
        comparisons: list[dict[str, Any]] = []
        needs_review = False
        for region in request.regions:
            cloud = returned.get(region)
            if cloud is None:
                cloud = {
                    "region": region,
                    "decision": "uncertain",
                    "image_quality": "poor",
                    "reason": "The provider did not return this requested region.",
                }
            local_decision = request.local_decisions[region]
            agreement = (
                cloud["decision"] == local_decision
                and cloud["decision"] != "uncertain"
                and cloud["image_quality"] == "adequate"
            )
            if not agreement:
                needs_review = True
            comparisons.append(
                {
                    "region": region,
                    "localDecision": local_decision,
                    "aiDecision": cloud["decision"],
                    "imageQuality": cloud["image_quality"],
                    "reason": cloud["reason"],
                    "agreement": agreement,
                }
            )
        return (
            {
                "assurance": "needs_human_review" if needs_review else "two_model_agreement",
                "regions": comparisons,
                "sourceRecordIds": request.source_record_ids,
                "evidence": request.metadata,
                "aiAssisted": True,
                "authoritativeSource": "local_edge",
            },
            needs_review,
        )

    def _record_failure(self, error: ProviderFailure) -> None:
        with self._lock:
            self._consecutive_failures += 1
            self._last_failure = {"code": error.code, "detail": error.detail, "at": iso()}
            if self._consecutive_failures >= self.settings.ai_circuit_failure_threshold:
                self._circuit_opened_at = time.monotonic()

    def _circuit_is_open(self) -> bool:
        with self._lock:
            if self._circuit_opened_at is None:
                return False
            if (
                time.monotonic() - self._circuit_opened_at
                >= self.settings.ai_circuit_recovery_seconds
            ):
                self._circuit_opened_at = None
                self._consecutive_failures = 0
                return False
            return True
