from pathlib import Path

import pytest

from foodsafe_edge.enterprise import EnterpriseStore
from foodsafe_edge.store import EventInput, EventStore


def enterprise(tmp_path: Path) -> tuple[EventStore, EnterpriseStore]:
    event_store = EventStore(tmp_path / "enterprise.db")
    return event_store, EnterpriseStore(event_store)


def test_context_has_one_live_site_and_honest_workspace_modes(tmp_path: Path) -> None:
    _, store = enterprise(tmp_path)
    context = store.context()
    assert [site["mode"] for site in context["sites"]] == ["live", "planned"]
    assert [workspace["mode"] for workspace in context["workspaces"]] == [
        "simulated",
        "simulated",
        "live",
        "simulated",
    ]


def test_qualifying_event_creates_one_incident_and_audit_history(tmp_path: Path) -> None:
    events, store = enterprise(tmp_path)
    event = events.add_event(
        EventInput(
            type="ppe_violation",
            title="Gloves not detected",
            detail="Controlled test",
            severity="critical",
            source_mode="simulated",
        )
    )
    incidents = store.list_incidents()
    assert len(incidents) == 1
    assert incidents[0]["sourceEventId"] == event["id"]
    assert len(store.list_incidents()) == 1
    investigated = store.update_incident(
        incidents[0]["id"],
        {"status": "investigating", "owner": "QA Supervisor"},
        "QA Supervisor (Demo View)",
    )
    assert investigated["status"] == "investigating"
    assert len(investigated["activity"]) == 2


def test_resolution_requires_root_cause_and_corrective_action(tmp_path: Path) -> None:
    events, store = enterprise(tmp_path)
    events.add_event(
        EventInput(
            type="temperature_alert",
            title="Temperature exceeded limit",
            detail="Controlled test",
            severity="critical",
            source_mode="simulated",
        )
    )
    incident = store.list_incidents()[0]
    with pytest.raises(ValueError, match="Root cause"):
        store.update_incident(incident["id"], {"status": "resolved"}, "QA Supervisor")


def test_closed_incidents_are_not_returned_in_priority_queue(tmp_path: Path) -> None:
    events, store = enterprise(tmp_path)
    events.add_event(
        EventInput(
            type="ppe_violation",
            title="Preflight PPE event",
            detail="Controlled test",
            severity="critical",
            source_mode="real",
        )
    )
    incident = store.list_incidents()[0]
    store.update_incident(
        incident["id"],
        {
            "status": "closed",
            "rootCause": "Preflight verification",
            "correctiveAction": "Reviewed before handoff",
        },
        "QA Preflight",
    )
    overview = store.overview()
    assert overview["metrics"]["openCriticalIncidents"] == 0
    assert overview["priorityIncidents"] == []
    assert overview["siteHealth"][0]["openIncidents"] == 0


def test_report_excludes_unknown_ppe_and_generates_pdf(tmp_path: Path) -> None:
    _, store = enterprise(tmp_path)
    report = store.report_summary()
    assert report["metrics"]["ppeDeterminateChecks"] == 18
    assert report["metrics"]["ppeCompliance"] == 89
    assert store.audit_pack().startswith(b"%PDF-1.4")


def test_reset_removes_only_simulated_events(tmp_path: Path) -> None:
    events, store = enterprise(tmp_path)
    real = events.add_event(EventInput(type="employee_entry", title="Real", detail="Keep"))
    events.add_event(
        EventInput(type="ppe_violation", title="Simulated", detail="Remove", source_mode="simulated")
    )
    removed = store.reset_simulated()
    assert removed["events"] == 1
    assert events.get_event(real["id"])["title"] == "Real"
    report = store.report_summary()
    assert report["metrics"]["completedProcesses"] == 1
    assert report["metrics"]["processOnTime"] == 100


def test_oracle_boundary_is_mapping_only_and_sends_no_external_request(tmp_path: Path) -> None:
    _, store = enterprise(tmp_path)
    readiness = store.oracle_readiness()

    assert readiness["status"] == "not_connected"
    assert readiness["externalRequestsEnabled"] is False
    assert readiness["mappings"]
    assert all(mapping["status"] == "proposed" for mapping in readiness["mappings"])
