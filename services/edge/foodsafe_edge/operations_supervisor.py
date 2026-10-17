from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .ai_supervisor import SUPERVISOR_ACTIONS, AIJobWorker
from .enterprise import EnterpriseStore
from .settings import Settings
from .store import EventStore, iso

FEATURES: dict[str, dict[str, str]] = {
    "explain_latest_alert": {
        "label": "Explain latest alert",
        "description": "Explain the measurements and evidence behind the latest safety alert.",
    },
    "interpret_process": {
        "label": "Interpret process",
        "description": "Explain the latest preparation run against its approved timing window.",
    },
    "analyze_inventory": {
        "label": "Analyze inventory",
        "description": "Explain the latest tagged stock movement and resulting quantity.",
    },
    "review_cold_chain": {
        "label": "Review cold chain",
        "description": "Explain the latest reading, threshold, source, and recovery state.",
    },
    "show_sop_guidance": {
        "label": "Show SOP guidance",
        "description": "Return the next action from the active versioned SOP only.",
    },
    "review_operations": {
        "label": "Review operations",
        "description": "Correlate current safety, process, inventory, and platform facts.",
    },
    "generate_shift_summary": {
        "label": "Generate shift summary",
        "description": "Summarize exact ledger counts and unresolved incidents for the shift.",
    },
}

MANUAL_PREFLIGHT_CHECKS = {
    "backup_hotspot",
    "ppe_acceptance",
    "camera_soak",
    "demo_rehearsal",
    "recovery_package",
}


def _age_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, (datetime.now(UTC) - parsed).total_seconds())


class OperationsSupervisor:
    """Read-only AI actions grounded in exact local operational records."""

    def __init__(
        self,
        settings: Settings,
        store: EventStore,
        enterprise: EnterpriseStore,
        worker: AIJobWorker,
    ):
        self.settings = settings
        self.store = store
        self.enterprise = enterprise
        self.worker = worker
        self.store.ensure_ai_features(list(FEATURES))

    def features(self) -> list[dict[str, Any]]:
        rows = {item["action"]: item for item in self.store.list_ai_feature_readiness()}
        result: list[dict[str, Any]] = []
        for action, definition in FEATURES.items():
            row = rows[action]
            missing = [label for label, passed in row["gates"].items() if not passed]
            if not row["enabled"]:
                recovery = "This action is disabled by its independent kill switch."
            elif not row["current"]:
                recovery = "Run the action verification suite; the readiness record is missing or expired."
            elif missing:
                recovery = f"Complete the remaining readiness gates: {', '.join(missing)}."
            else:
                recovery = "Ready for a controlled client demonstration."
            result.append({**definition, **row, "recovery": recovery})
        return result

    def set_enabled(self, action: str, enabled: bool) -> dict[str, Any]:
        if action not in FEATURES:
            raise KeyError(action)
        self.store.set_ai_feature_enabled(action, enabled)
        return next(item for item in self.features() if item["action"] == action)

    def run(self, action: str) -> dict[str, Any]:
        if action not in SUPERVISOR_ACTIONS:
            raise KeyError(action)
        feature = next(item for item in self.features() if item["action"] == action)
        if not feature["ready"]:
            raise PermissionError(feature["recovery"])
        facts, source_ids = self.collect(action)
        if not source_ids:
            return self.worker.create_insufficient_evidence_job(action=action)
        snapshot = facts.get("snapshotAt", iso())
        return self.worker.create_operations_job(
            action=action,
            source_record_ids=source_ids[:20],
            facts=facts,
            dedupe_key=f"{action}:{snapshot}",
        )

    def collect(self, action: str) -> tuple[dict[str, Any], list[str]]:
        if action == "explain_latest_alert":
            return self._latest_alert()
        if action == "interpret_process":
            return self._process()
        if action == "analyze_inventory":
            return self._inventory()
        if action == "review_cold_chain":
            return self._cold_chain()
        if action == "show_sop_guidance":
            return self._sop()
        if action == "review_operations":
            return self._operations()
        if action == "generate_shift_summary":
            return self._shift_summary()
        raise KeyError(action)

    def _latest_alert(self) -> tuple[dict[str, Any], list[str]]:
        qualifying = {
            "ppe_violation",
            "temperature_alert",
            "process_exception",
            "inventory_variance",
        }
        event = next(
            (item for item in self.store.list_events(limit=250) if item["type"] in qualifying),
            None,
        )
        if not event:
            return {}, []
        facts = {
            "snapshotAt": iso(),
            "event": {
                key: event.get(key)
                for key in (
                    "id",
                    "occurredAt",
                    "type",
                    "title",
                    "detail",
                    "severity",
                    "sourceMode",
                    "status",
                    "employeeName",
                    "zone",
                    "confidence",
                    "evidenceUrl",
                    "retentionUntil",
                )
            },
            "measurements": event.get("metadata", {}),
        }
        return facts, [event["id"]]

    def _process(self) -> tuple[dict[str, Any], list[str]]:
        runs = self.enterprise.process_runs(limit=1)
        if not runs:
            return {}, []
        run = runs[0]
        elapsed = run["elapsedSeconds"]
        timing = "in_progress"
        if elapsed is not None:
            timing = (
                "below_target"
                if elapsed < run["targetMinSeconds"]
                else "above_target"
                if elapsed > run["targetMaxSeconds"]
                else "within_target"
            )
        return {
            "snapshotAt": iso(),
            "run": run,
            "timingAssessment": timing,
            "calculationAuthority": "edge timestamps",
        }, [run["id"]]

    def _inventory(self) -> tuple[dict[str, Any], list[str]]:
        transactions = self.store.inventory_transactions(limit=1)
        if not transactions:
            return {}, []
        transaction = transactions[0]
        item = next(
            (item for item in self.store.inventory() if item["sku"] == transaction["sku"]),
            None,
        )
        return {
            "snapshotAt": iso(),
            "transaction": transaction,
            "currentItem": item,
            "calculationAuthority": "inventory transaction ledger",
        }, [transaction["id"]]

    def _cold_chain(self) -> tuple[dict[str, Any], list[str]]:
        readings = self.store.temperature_readings(limit=10)
        if not readings:
            return {}, []
        latest = readings[0]
        prior = readings[1] if len(readings) > 1 else None
        return {
            "snapshotAt": iso(),
            "latestReading": latest,
            "previousReading": prior,
            "thresholdState": latest["status"],
            "sourceBoundary": latest["source_mode"],
            "calculationAuthority": "temperature sensor ledger",
        }, [reading["id"] for reading in readings[:10]]

    def _sop(self) -> tuple[dict[str, Any], list[str]]:
        templates = self.enterprise.sops()
        if not templates:
            return {}, []
        sop = templates[0]
        runs = self.enterprise.process_runs(limit=1)
        run = runs[0] if runs else None
        if not run:
            next_stage = sop["stages"][0]
        elif run["status"] == "running":
            next_stage = sop["stages"][1] if len(sop["stages"]) > 1 else sop["stages"][0]
        else:
            next_stage = sop["stages"][-1]
        source_ids = [sop["id"], next_stage["id"]]
        if run:
            source_ids.append(run["id"])
        return {
            "snapshotAt": iso(),
            "sop": {
                "id": sop["id"],
                "code": sop["code"],
                "name": sop["name"],
                "version": sop["version"],
                "sourceMode": sop["sourceMode"],
            },
            "currentRun": run,
            "nextApprovedStage": next_stage,
            "guidanceBoundary": "Only the active versioned SOP is authoritative.",
        }, source_ids

    def _operations(self) -> tuple[dict[str, Any], list[str]]:
        sections: dict[str, Any] = {"snapshotAt": iso()}
        sources: list[str] = []
        for key, collector in (
            ("latestAlert", self._latest_alert),
            ("process", self._process),
            ("inventory", self._inventory),
            ("coldChain", self._cold_chain),
        ):
            facts, ids = collector()
            if ids:
                sections[key] = facts
                sources.extend(ids)
        sections["boundaries"] = {
            "identity": "No face identification or demographic inference",
            "authority": "Local measurements and operator review remain authoritative",
            "oracle": "No external write is permitted",
        }
        return (sections, list(dict.fromkeys(sources))[:20]) if sources else ({}, [])

    def _shift_summary(self) -> tuple[dict[str, Any], list[str]]:
        events = self.store.list_events(limit=10_000)
        incidents = self.enterprise.list_incidents(limit=250)
        runs = self.enterprise.process_runs(limit=10_000)
        transactions = self.store.inventory_transactions(limit=10_000)
        readings = self.store.temperature_readings(limit=10_000)
        unresolved = [item for item in incidents if item["status"] not in {"resolved", "closed"}]
        sources = [item["id"] for item in events[:8]]
        sources += [item["id"] for item in runs[:4]]
        sources += [item["id"] for item in transactions[:4]]
        sources += [item["id"] for item in readings[:4]]
        if not sources:
            return {}, []
        facts = {
            "snapshotAt": iso(),
            "exactCounts": {
                "events": len(events),
                "realEvents": sum(item["sourceMode"] == "real" for item in events),
                "simulatedEvents": sum(item["sourceMode"] == "simulated" for item in events),
                "unresolvedIncidents": len(unresolved),
                "processRuns": len(runs),
                "inventoryMovements": len(transactions),
                "temperatureReadings": len(readings),
            },
            "unresolvedIncidents": [
                {
                    "id": item["id"],
                    "title": item["title"],
                    "priority": item["priority"],
                    "status": item["status"],
                    "sourceMode": item["sourceMode"],
                }
                for item in unresolved[:10]
            ],
            "sourceBoundary": "Counts are deterministic database totals; AI supplies narrative only.",
        }
        return facts, list(dict.fromkeys(sources))[:20]


class ClientDemoPreflight:
    """Single truthful readiness view for the exact controlled demonstration."""

    def __init__(self, settings: Settings, store: EventStore, supervisor: OperationsSupervisor):
        self.settings = settings
        self.store = store
        self.supervisor = supervisor

    @staticmethod
    def _check(
        check_id: str,
        label: str,
        status: str,
        detail: str,
        recovery: str,
        *,
        critical: bool = True,
    ) -> dict[str, Any]:
        return {
            "id": check_id,
            "label": label,
            "status": status,
            "detail": detail,
            "recovery": recovery,
            "critical": critical,
        }

    def status(self, runtime: dict[str, Any]) -> dict[str, Any]:
        health = runtime["health"]
        detection = runtime["detection"]
        provider = runtime["aiPpeAssurance"]["provider"]
        checks: list[dict[str, Any]] = []
        camera_ok = health["camera"] == "online"
        live_camera_ok = camera_ok and health.get("sourceType") != "file"
        if live_camera_ok:
            camera_detail = str(health["cameraLabel"])
        elif camera_ok:
            camera_detail = (
                f"{health['cameraLabel']} is the prerecorded fallback; select the live meeting camera."
            )
        else:
            camera_detail = "macOS is not delivering a camera frame."
        checks.append(
            self._check(
                "camera_source",
                "Camera permission and source",
                "passed" if live_camera_ok else "failed",
                camera_detail,
                "Close other camera apps, confirm macOS permission, and reselect the meeting camera.",
            )
        )
        frame_age = _age_seconds(health.get("lastFrameAt"))
        frame_ok = frame_age is not None and frame_age <= 2
        checks.append(
            self._check(
                "frame_freshness",
                "Frame freshness",
                "passed" if frame_ok else "failed",
                f"Latest frame age {frame_age:.1f} seconds."
                if frame_age is not None
                else "No frame timestamp is available.",
                "Restore the live camera until frame age remains below two seconds.",
            )
        )
        fps = float(health.get("processedFps") or 0)
        checks.append(
            self._check(
                "processed_fps",
                "Processed frame rate",
                "passed" if fps >= 6 else "failed",
                f"{fps:.1f} processed FPS.",
                "Close heavy applications or reduce camera resolution until at least 6 FPS is stable.",
            )
        )
        readiness = detection.get("readiness")
        framing_ok = bool(readiness and readiness.get("lightingReady") and readiness.get("framingReady"))
        checks.append(
            self._check(
                "lighting_framing",
                "Lighting and framing",
                "passed" if framing_ok else "pending",
                "Face, hands, and torso assessment region is ready."
                if framing_ok
                else "Stand in view to verify lighting and framing.",
                "Use even front lighting and position head, torso, and both hands inside the camera view.",
            )
        )
        ppe_ok = health.get("ppeVerifier", {}).get("status") == "passed"
        checks.append(
            self._check(
                "ppe_self_test",
                "PPE verifier self-test",
                "passed" if ppe_ok else "failed",
                "Startup regression checks passed."
                if ppe_ok
                else "The PPE verifier disabled itself after a failed check.",
                "Resolve the reported verifier failure before presenting live PPE.",
            )
        )
        storage_ok = health.get("storage") == "online"
        checks.append(
            self._check(
                "evidence_storage",
                "Evidence storage",
                "passed" if storage_ok else "failed",
                "Local event and evidence storage is writable."
                if storage_ok
                else str(health.get("storageError") or "Storage check failed."),
                "Restore write access to the client-demo data and evidence directories.",
            )
        )
        configured = bool(provider.get("configured"))
        checks.append(
            self._check(
                "openai_configuration",
                "AI provider configuration",
                "passed" if configured else "failed",
                f"{provider.get('model')} configured; credentials are never returned to the browser."
                if configured
                else "No usable provider credential is configured.",
                "Configure the rotated key in services/edge/.env and restart the edge service.",
            )
        )
        smoke_age = _age_seconds(provider.get("lastSuccessfulJobAt"))
        smoke_ok = smoke_age is not None and smoke_age <= 86_400 and provider.get("available")
        checks.append(
            self._check(
                "openai_live_smoke",
                "AI live smoke test",
                "passed" if smoke_ok else "pending",
                f"Last successful job {smoke_age / 60:.0f} minutes ago."
                if smoke_age is not None
                else "No current live smoke result is recorded.",
                "Run the approved live smoke suite on the meeting network.",
            )
        )
        checks.append(
            self._check(
                "alert_sound",
                "Browser alert sound",
                "pending",
                "This optional check is completed in the presenting browser.",
                "Enable sound once, use Test sound, then leave the preference in the required meeting state.",
                critical=False,
            )
        )
        with self.store._lock:
            simulated_events = int(
                self.store.connection.execute(
                    "SELECT COUNT(*) count FROM events WHERE source_mode='simulated'"
                ).fetchone()["count"]
            )
        checks.append(
            self._check(
                "clean_ledger",
                "Clean demonstration ledger",
                "passed" if simulated_events == 0 else "failed",
                f"{simulated_events} simulated event records are loaded.",
                "Use Platform > Reset simulated data immediately before the meeting.",
            )
        )
        for check_id, label in (
            ("backup_hotspot", "Backup hotspot"),
            ("ppe_acceptance", "PPE 30/30 acceptance"),
            ("camera_soak", "Ten-minute camera soak"),
            ("demo_rehearsal", "Full demonstration rehearsal"),
        ):
            record = self.store.get_demo_readiness(check_id)
            checks.append(
                self._check(
                    check_id,
                    label,
                    record["status"],
                    record["evidence"],
                    f"Complete and record the {label.lower()} check on the exact meeting setup.",
                )
            )
        edge_root = Path(__file__).resolve().parents[1]
        fallback = edge_root / "assets" / "fallback-demo.mp4"
        checks.append(
            self._check(
                "fallback_video",
                "Prerecorded fallback",
                "passed" if fallback.is_file() else "failed",
                "The labelled local fallback video is available."
                if fallback.is_file()
                else "The fallback video is missing.",
                "Restore services/edge/assets/fallback-demo.mp4 and verify playback.",
            )
        )
        recovery = self.store.get_demo_readiness("recovery_package")
        checks.append(
            self._check(
                "recovery_package",
                "Recovery package",
                recovery["status"],
                recovery["evidence"],
                "Verify each capability clip, screenshot, report, and recovery statement.",
            )
        )
        features = self.supervisor.features()
        critical_failed = [item for item in checks if item["critical"] and item["status"] != "passed"]
        return {
            "status": "ready"
            if not critical_failed and all(item["ready"] for item in features)
            else "blocked",
            "generatedAt": iso(),
            "checks": checks,
            "aiFeatures": features,
            "summary": {
                "passed": sum(item["status"] == "passed" for item in checks),
                "pending": sum(item["status"] == "pending" for item in checks),
                "failed": sum(item["status"] == "failed" for item in checks),
                "readyAiActions": sum(item["ready"] for item in features),
                "totalAiActions": len(features),
            },
            "clientBoundary": (
                "Local monitoring remains authoritative. AI is advisory, read-only, and unavailable "
                "actions stay disabled until every readiness gate is current."
            ),
        }

    def record_manual(self, check_id: str, status: str, evidence: str) -> dict[str, Any]:
        if check_id not in MANUAL_PREFLIGHT_CHECKS:
            raise KeyError(check_id)
        return self.store.record_demo_readiness(check_id, status, evidence)
