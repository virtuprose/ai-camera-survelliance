from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Any

from .store import EventStore, iso, utc_now

ORG_ID = "10000000-0000-0000-0000-000000000001"
MAIN_SITE_ID = "11000000-0000-0000-0000-000000000001"
SECONDARY_SITE_ID = "11000000-0000-0000-0000-000000000002"
KITCHEN_ID = "12000000-0000-0000-0000-000000000001"
RECEIVING_ID = "12000000-0000-0000-0000-000000000002"
COLD_STORAGE_ID = "12000000-0000-0000-0000-000000000003"
INVENTORY_ID = "12000000-0000-0000-0000-000000000004"
SHIFT_ID = "13000000-0000-0000-0000-000000000001"
SOP_ID = "14000000-0000-0000-0000-000000000001"

INCIDENT_STATUSES = {"open", "investigating", "action_required", "resolved", "closed"}
INCIDENT_PRIORITIES = {"low", "medium", "high", "critical"}
SLA_MINUTES = {"critical": 30, "high": 240, "medium": 1440, "low": 4320}


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def simple_pdf(lines: list[str]) -> bytes:
    """Create a dependency-free, valid one-page PDF for the local audit demo."""
    content = ["BT", "/F1 10 Tf", "44 790 Td", "14 TL"]
    for index, line in enumerate(lines[:48]):
        if index:
            content.append("T*")
        content.append(f"({_pdf_escape(line[:105])}) Tj")
    content.append("ET")
    stream = "\n".join(content).encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode())
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(output)


class EnterpriseStore:
    def __init__(self, event_store: EventStore):
        self.event_store = event_store
        self.connection = event_store.connection
        self.lock = event_store._lock
        self._migrate()
        self._seed()

    def _column_exists(self, table: str, column: str) -> bool:
        rows = self.connection.execute(f"PRAGMA table_info({table})").fetchall()
        return any(row["name"] == column for row in rows)

    def _migrate(self) -> None:
        with self.lock, self.connection:
            for table in ("events", "process_runs", "temperature_readings", "inventory_transactions"):
                for column, default in (
                    ("site_id", MAIN_SITE_ID),
                    ("department_id", KITCHEN_ID),
                    ("workspace_id", KITCHEN_ID),
                    ("shift_id", SHIFT_ID),
                ):
                    if not self._column_exists(table, column):
                        self.connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
                    self.connection.execute(
                        f"UPDATE {table} SET {column}=? WHERE {column} IS NULL", (default,)
                    )
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS enterprise_sites (
                    id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, code TEXT NOT NULL,
                    name TEXT NOT NULL, timezone TEXT NOT NULL, mode TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS enterprise_workspaces (
                    id TEXT PRIMARY KEY, site_id TEXT NOT NULL, code TEXT NOT NULL,
                    name TEXT NOT NULL, department_type TEXT NOT NULL, mode TEXT NOT NULL,
                    device_code TEXT
                );
                CREATE TABLE IF NOT EXISTS enterprise_shifts (
                    id TEXT PRIMARY KEY, site_id TEXT NOT NULL, name TEXT NOT NULL,
                    starts_at TEXT NOT NULL, ends_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ppe_observations (
                    id TEXT PRIMARY KEY, site_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
                    shift_id TEXT NOT NULL, employee_id TEXT, item TEXT NOT NULL,
                    result INTEGER, confidence REAL, source_mode TEXT NOT NULL,
                    observed_at TEXT NOT NULL, retention_until TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ppe_observed_at ON ppe_observations(observed_at DESC);
                CREATE TABLE IF NOT EXISTS sop_templates (
                    id TEXT PRIMARY KEY, site_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
                    code TEXT NOT NULL, name TEXT NOT NULL, version TEXT NOT NULL,
                    source_mode TEXT NOT NULL, active INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sop_stages (
                    id TEXT PRIMARY KEY, sop_id TEXT NOT NULL, sequence INTEGER NOT NULL,
                    name TEXT NOT NULL, trigger_name TEXT NOT NULL,
                    target_min_seconds INTEGER NOT NULL, target_max_seconds INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS incidents (
                    id TEXT PRIMARY KEY, source_event_id TEXT UNIQUE, site_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL, shift_id TEXT NOT NULL, title TEXT NOT NULL,
                    detail TEXT NOT NULL, priority TEXT NOT NULL, status TEXT NOT NULL,
                    source_mode TEXT NOT NULL, owner TEXT, due_at TEXT NOT NULL,
                    root_cause TEXT, corrective_action TEXT, resolution_note TEXT,
                    resolution_type TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    retention_until TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_incidents_status_due ON incidents(status, due_at);
                CREATE TABLE IF NOT EXISTS incident_activity (
                    id TEXT PRIMARY KEY, incident_id TEXT NOT NULL, actor TEXT NOT NULL,
                    action TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS alert_rules (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, event_type TEXT NOT NULL,
                    severity TEXT NOT NULL, browser_enabled INTEGER NOT NULL,
                    email_status TEXT NOT NULL, sms_status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
                    actor TEXT NOT NULL, action TEXT NOT NULL, detail_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, retention_until TEXT NOT NULL
                );
                """
            )

    def _seed(self) -> None:
        with self.lock, self.connection:
            self.connection.executemany(
                "INSERT OR IGNORE INTO enterprise_sites VALUES(?,?,?,?,?,?)",
                [
                    (MAIN_SITE_ID, ORG_ID, "SITE-01", "Main Production Facility", "Asia/Kuwait", "live"),
                    (SECONDARY_SITE_ID, ORG_ID, "SITE-02", "Secondary Facility", "Asia/Kuwait", "planned"),
                ],
            )
            self.connection.executemany(
                "INSERT OR IGNORE INTO enterprise_workspaces VALUES(?,?,?,?,?,?,?)",
                [
                    (KITCHEN_ID, MAIN_SITE_ID, "KIT-01", "Kitchen 01", "production", "live", "CAM-01"),
                    (RECEIVING_ID, MAIN_SITE_ID, "RCV-01", "Receiving", "receiving", "simulated", None),
                    (
                        COLD_STORAGE_ID,
                        MAIN_SITE_ID,
                        "CLD-01",
                        "Cold Storage",
                        "cold_chain",
                        "simulated",
                        None,
                    ),
                    (INVENTORY_ID, MAIN_SITE_ID, "INV-01", "Inventory Store", "inventory", "simulated", None),
                ],
            )
            self.connection.execute(
                "INSERT OR IGNORE INTO enterprise_shifts VALUES(?,?,?,?,?)",
                (SHIFT_ID, MAIN_SITE_ID, "Day Shift", "06:00", "18:00"),
            )
            self.connection.execute(
                "INSERT OR IGNORE INTO sop_templates VALUES(?,?,?,?,?,?,?,?)",
                (SOP_ID, MAIN_SITE_ID, KITCHEN_ID, "SOP-CHW-01", "Chicken Washing", "1.0", "simulated", 1),
            )
            stages = [
                (
                    "14100000-0000-0000-0000-000000000001",
                    SOP_ID,
                    1,
                    "Process start",
                    "Tray enters Process Start",
                    0,
                    15,
                ),
                (
                    "14100000-0000-0000-0000-000000000002",
                    SOP_ID,
                    2,
                    "Washing",
                    "Timed preparation activity",
                    120,
                    180,
                ),
                (
                    "14100000-0000-0000-0000-000000000003",
                    SOP_ID,
                    3,
                    "Process complete",
                    "Tray enters Process Complete",
                    0,
                    15,
                ),
            ]
            self.connection.executemany("INSERT OR IGNORE INTO sop_stages VALUES(?,?,?,?,?,?,?)", stages)
            rules = [
                (
                    "15000000-0000-0000-0000-000000000001",
                    "PPE critical violation",
                    "ppe_violation",
                    "critical",
                    1,
                    "not_configured",
                    "not_configured",
                ),
                (
                    "15000000-0000-0000-0000-000000000002",
                    "Temperature excursion",
                    "temperature_alert",
                    "critical",
                    1,
                    "not_configured",
                    "not_configured",
                ),
                (
                    "15000000-0000-0000-0000-000000000003",
                    "Process timing exception",
                    "process_exception",
                    "warning",
                    0,
                    "not_configured",
                    "not_configured",
                ),
            ]
            self.connection.executemany("INSERT OR IGNORE INTO alert_rules VALUES(?,?,?,?,?,?,?)", rules)
            if not self.connection.execute("SELECT 1 FROM ppe_observations LIMIT 1").fetchone():
                now = utc_now()
                rows = []
                results = [1] * 16 + [0, 0, None, None]
                for index, result in enumerate(results):
                    observed = now - timedelta(minutes=(len(results) - index) * 4)
                    rows.append(
                        (
                            str(uuid.uuid5(uuid.NAMESPACE_URL, f"orvia-ppe-seed-{index}")),
                            MAIN_SITE_ID,
                            KITCHEN_ID,
                            SHIFT_ID,
                            "EMP-001" if index % 2 == 0 else "EMP-002",
                            ("mask", "gloves", "hairnet", "apron")[index % 4],
                            result,
                            0.94 if result is not None else None,
                            "simulated",
                            iso(observed),
                            iso(observed + timedelta(days=365)),
                        )
                    )
                self.connection.executemany(
                    "INSERT OR IGNORE INTO ppe_observations VALUES(?,?,?,?,?,?,?,?,?,?,?)", rows
                )

    def context(self) -> dict[str, Any]:
        with self.lock:
            sites = [
                dict(row) for row in self.connection.execute("SELECT * FROM enterprise_sites ORDER BY code")
            ]
            workspaces = [
                dict(row)
                for row in self.connection.execute("SELECT * FROM enterprise_workspaces ORDER BY code")
            ]
            shift = dict(
                self.connection.execute("SELECT * FROM enterprise_shifts WHERE id=?", (SHIFT_ID,)).fetchone()
            )
        return {
            "organization": {"id": ORG_ID, "name": "ORVIA AI Surveillance Demo"},
            "sites": [self._site(row) for row in sites],
            "workspaces": [self._workspace(row) for row in workspaces],
            "activeShift": {
                "id": shift["id"],
                "name": shift["name"],
                "startsAt": shift["starts_at"],
                "endsAt": shift["ends_at"],
            },
            "personas": ["executive", "qa_supervisor", "operations", "it"],
            "updatedAt": iso(),
        }

    def ensure_incidents(self) -> None:
        qualifying = ("ppe_violation", "temperature_alert", "process_exception", "inventory_variance")
        placeholders = ",".join("?" for _ in qualifying)
        with self.lock, self.connection:
            events = self.connection.execute(
                f"SELECT * FROM events WHERE type IN ({placeholders}) ORDER BY occurred_at", qualifying
            ).fetchall()
            for event in events:
                if self.connection.execute(
                    "SELECT 1 FROM incidents WHERE source_event_id=?", (event["id"],)
                ).fetchone():
                    continue
                priority = "critical" if event["severity"] == "critical" else "high"
                created = event["occurred_at"]
                due = iso(_parse(created) + timedelta(minutes=SLA_MINUTES[priority]))
                workspace = self._workspace_for_event(event)
                incident_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"orvia-incident-{event['id']}"))
                self.connection.execute(
                    """INSERT INTO incidents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        incident_id,
                        event["id"],
                        event["site_id"] or MAIN_SITE_ID,
                        workspace,
                        event["shift_id"] or SHIFT_ID,
                        event["title"],
                        event["detail"],
                        priority,
                        "open",
                        event["source_mode"],
                        None,
                        due,
                        None,
                        None,
                        None,
                        None,
                        created,
                        created,
                        event["retention_until"],
                        1,
                    ),
                )
                self._activity(incident_id, "System", "created", "Incident created from a qualifying event.")

    def list_incidents(self, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        self.ensure_incidents()
        sql = (
            "SELECT i.*, e.evidence_url, e.employee_name, e.zone, e.confidence "
            "FROM incidents i LEFT JOIN events e ON e.id=i.source_event_id"
        )
        params: list[Any] = []
        if status:
            sql += " WHERE i.status=?"
            params.append(status)
        sql += (
            " ORDER BY CASE i.priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 "
            "WHEN 'medium' THEN 2 ELSE 3 END, i.due_at LIMIT ?"
        )
        params.append(max(1, min(limit, 250)))
        with self.lock:
            rows = self.connection.execute(sql, params).fetchall()
        return [self._incident(row) for row in rows]

    def get_incident(self, incident_id: str) -> dict[str, Any]:
        items = [item for item in self.list_incidents(limit=250) if item["id"] == incident_id]
        if not items:
            raise KeyError(incident_id)
        incident = items[0]
        with self.lock:
            activity = self.connection.execute(
                "SELECT * FROM incident_activity WHERE incident_id=? ORDER BY created_at", (incident_id,)
            ).fetchall()
        incident["activity"] = [
            {
                "id": row["id"],
                "actor": row["actor"],
                "action": row["action"],
                "detail": row["detail"],
                "createdAt": row["created_at"],
            }
            for row in activity
        ]
        return incident

    def update_incident(self, incident_id: str, changes: dict[str, Any], actor: str) -> dict[str, Any]:
        current = self.get_incident(incident_id)
        status = str(changes.get("status", current["status"]))
        priority = str(changes.get("priority", current["priority"]))
        owner = changes.get("owner", current["owner"])
        root_cause = changes.get("rootCause", current["rootCause"])
        corrective = changes.get("correctiveAction", current["correctiveAction"])
        resolution_note = changes.get("resolutionNote", current["resolutionNote"])
        resolution_type = changes.get("resolutionType", current["resolutionType"])
        if status not in INCIDENT_STATUSES or priority not in INCIDENT_PRIORITIES:
            raise ValueError("Unsupported incident status or priority")
        if status in {"investigating", "action_required"} and not owner:
            raise ValueError("Assign an owner before starting investigation")
        if status in {"resolved", "closed"} and not (root_cause and corrective):
            raise ValueError("Root cause and corrective action are required before resolution")
        now = iso()
        with self.lock, self.connection:
            self.connection.execute(
                """UPDATE incidents SET status=?,priority=?,owner=?,root_cause=?,corrective_action=?,
                resolution_note=?,resolution_type=?,updated_at=?,version=version+1 WHERE id=?""",
                (
                    status,
                    priority,
                    owner,
                    root_cause,
                    corrective,
                    resolution_note,
                    resolution_type,
                    now,
                    incident_id,
                ),
            )
            detail = f"Status {current['status']} to {status}; owner {owner or 'unassigned'}."
            self._activity(incident_id, actor, "updated", detail)
            self._audit("incident", incident_id, actor, "updated", {"from": current["status"], "to": status})
        return self.get_incident(incident_id)

    def add_activity(self, incident_id: str, actor: str, detail: str) -> dict[str, Any]:
        self.get_incident(incident_id)
        if not detail.strip():
            raise ValueError("Activity note cannot be empty")
        with self.lock, self.connection:
            self._activity(incident_id, actor, "note", detail.strip())
            self._audit("incident", incident_id, actor, "note", {"detail": detail.strip()})
        return self.get_incident(incident_id)

    def overview(self) -> dict[str, Any]:
        incidents = self.list_incidents(limit=250)
        active_incidents = [
            item for item in incidents if item["status"] not in {"resolved", "closed"}
        ]
        with self.lock:
            ppe = self.connection.execute("SELECT result FROM ppe_observations").fetchall()
            completed = self.connection.execute(
                "SELECT elapsed_seconds FROM process_runs "
                "WHERE status='complete' AND elapsed_seconds IS NOT NULL"
            ).fetchall()
            temperature_alerts = self.connection.execute(
                "SELECT COUNT(*) count FROM events WHERE type='temperature_alert' AND status='new'"
            ).fetchone()["count"]
        determinate = [row["result"] for row in ppe if row["result"] is not None]
        compliant = sum(1 for result in determinate if result == 1)
        on_time = sum(1 for row in completed if 120 <= row["elapsed_seconds"] <= 180)
        return {
            "metrics": {
                "openCriticalIncidents": sum(
                    1
                    for item in active_incidents
                    if item["priority"] == "critical"
                ),
                "ppeCompliance": round(compliant / len(determinate) * 100) if determinate else None,
                "ppeDeterminateChecks": len(determinate),
                "processOnTime": round(on_time / len(completed) * 100) if completed else None,
                "completedProcesses": len(completed),
                "activeTemperatureExcursions": int(temperature_alerts),
                "systemAvailability": 100,
            },
            "priorityIncidents": active_incidents[:5],
            "siteHealth": [
                {
                    "siteId": MAIN_SITE_ID,
                    "name": "Main Production Facility",
                    "mode": "live",
                    "status": "operational",
                    "openIncidents": sum(
                        1 for item in active_incidents
                    ),
                },
                {
                    "siteId": SECONDARY_SITE_ID,
                    "name": "Secondary Facility",
                    "mode": "planned",
                    "status": "planned",
                    "openIncidents": 0,
                },
            ],
            "updatedAt": iso(),
        }

    def sops(self) -> list[dict[str, Any]]:
        with self.lock:
            templates = self.connection.execute("SELECT * FROM sop_templates WHERE active=1").fetchall()
            stages = self.connection.execute("SELECT * FROM sop_stages ORDER BY sequence").fetchall()
        return [
            {
                "id": template["id"],
                "code": template["code"],
                "name": template["name"],
                "version": template["version"],
                "sourceMode": template["source_mode"],
                "siteId": template["site_id"],
                "workspaceId": template["workspace_id"],
                "stages": [
                    {
                        "id": stage["id"],
                        "sequence": stage["sequence"],
                        "name": stage["name"],
                        "trigger": stage["trigger_name"],
                        "targetMinSeconds": stage["target_min_seconds"],
                        "targetMaxSeconds": stage["target_max_seconds"],
                    }
                    for stage in stages
                    if stage["sop_id"] == template["id"]
                ],
            }
            for template in templates
        ]

    def process_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.connection.execute(
                "SELECT * FROM process_runs ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {
                "id": row["id"],
                "sopId": SOP_ID,
                "label": row["label"],
                "status": row["status"],
                "startedAt": row["started_at"],
                "completedAt": row["completed_at"],
                "elapsedSeconds": row["elapsed_seconds"],
                "targetMinSeconds": 120,
                "targetMaxSeconds": 180,
                "sourceMode": row["source_mode"],
                "siteId": row["site_id"],
                "workspaceId": row["workspace_id"],
                "shiftId": row["shift_id"],
            }
            for row in rows
        ]

    def report_summary(self) -> dict[str, Any]:
        overview = self.overview()
        events = self.event_store.list_events(limit=10_000)
        return {
            **overview,
            "eventCount": len(events),
            "realCount": sum(1 for event in events if event["sourceMode"] == "real"),
            "simulatedCount": sum(1 for event in events if event["sourceMode"] == "simulated"),
            "generatedAt": iso(),
        }

    def audit_pack(self) -> bytes:
        report = self.report_summary()
        metrics = report["metrics"]
        ppe_value = metrics["ppeCompliance"]
        process_value = metrics["processOnTime"]
        lines = [
            "ORVIA AI Surveillance - Enterprise Audit Pack",
            "Main Production Facility | Day Shift | Asia/Kuwait",
            f"Generated: {report['generatedAt']}",
            "",
            "Data boundary: Real and Simulated records remain separately identified.",
            (
                f"Loaded events: {report['eventCount']} | Real: {report['realCount']} | "
                f"Simulated: {report['simulatedCount']}"
            ),
            f"Open critical incidents: {metrics['openCriticalIncidents']}",
            (
                "PPE compliance: "
                f"{ppe_value if ppe_value is not None else 'Insufficient data'}% "
                f"({metrics['ppeDeterminateChecks']} determinate checks)"
            ),
            f"Process on-time: {process_value if process_value is not None else 'Insufficient data'}%",
            f"Active temperature excursions: {metrics['activeTemperatureExcursions']}",
            "",
            "Priority incidents",
        ]
        for incident in report["priorityIncidents"]:
            lines.append(
                f"{incident['priority'].upper()} | {incident['status']} | "
                f"{incident['title']} | {incident['sourceMode']}"
            )
        lines.extend(
            [
                "",
                "Retention: operational records include a minimum 365-day retention date.",
                "Oracle ERP: Not connected. Proposed mapping only.",
            ]
        )
        return simple_pdf(lines)

    def oracle_readiness(self) -> dict[str, Any]:
        return {
            "status": "not_connected",
            "sourceMode": "simulated",
            "message": (
                "Client Oracle product, version, APIs, and credentials are required before connection."
            ),
            "mappings": [
                {
                    "source": "employee.employee_code",
                    "target": "Worker / person number",
                    "status": "proposed",
                },
                {"source": "inventory_item.sku", "target": "Item number", "status": "proposed"},
                {"source": "inventory_transaction", "target": "Material transaction", "status": "proposed"},
                {"source": "process_run", "target": "Batch operation / work order", "status": "proposed"},
                {"source": "incident", "target": "Quality issue / nonconformance", "status": "proposed"},
            ],
            "samplePayload": {
                "source": "ORVIA",
                "recordType": "inventory_transaction",
                "sourceMode": "simulated",
                "sku": "SKU-001",
                "direction": "in",
                "quantity": 1,
            },
            "externalRequestsEnabled": False,
        }

    def audit_log(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.connection.execute(
                "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {
                "id": row["id"],
                "entityType": row["entity_type"],
                "entityId": row["entity_id"],
                "actor": row["actor"],
                "action": row["action"],
                "detail": json.loads(row["detail_json"]),
                "createdAt": row["created_at"],
            }
            for row in rows
        ]

    def reset_simulated(self) -> dict[str, int]:
        with self.lock, self.connection:
            event_ids = [
                row["id"]
                for row in self.connection.execute("SELECT id FROM events WHERE source_mode='simulated'")
            ]
            incident_ids = [
                row["id"]
                for row in self.connection.execute("SELECT id FROM incidents WHERE source_mode='simulated'")
            ]
            if incident_ids:
                placeholders = ",".join("?" for _ in incident_ids)
                self.connection.execute(
                    f"DELETE FROM incident_activity WHERE incident_id IN ({placeholders})", incident_ids
                )
            self.connection.execute("DELETE FROM incidents WHERE source_mode='simulated'")
            self.connection.execute("DELETE FROM events WHERE source_mode='simulated'")
            self.connection.execute("DELETE FROM process_runs WHERE source_mode='simulated'")
            self.connection.execute("DELETE FROM temperature_readings WHERE source_mode='simulated'")
            self.connection.execute("DELETE FROM inventory_transactions WHERE source_mode='simulated'")
            self.connection.execute("DELETE FROM audit_log WHERE actor LIKE '%Demo%'")
            self.connection.executemany(
                "UPDATE inventory SET quantity=?,updated_at=? WHERE sku=?",
                [
                    (5, iso(), "SKU-001"),
                    (8, iso(), "SKU-002"),
                    (3, iso(), "SKU-003"),
                    (6, iso(), "SKU-004"),
                    (4, iso(), "SKU-005"),
                ],
            )
            completed_at = utc_now()
            started_at = completed_at - timedelta(seconds=150)
            self.connection.execute(
                """INSERT INTO process_runs(
                id,label,status,started_at,completed_at,elapsed_seconds,source_mode,retention_until,
                site_id,department_id,workspace_id,shift_id
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    str(uuid.uuid5(uuid.NAMESPACE_URL, "orvia-baseline-process-run")),
                    "Chicken Washing",
                    "complete",
                    iso(started_at),
                    iso(completed_at),
                    150,
                    "simulated",
                    iso(completed_at + timedelta(days=365)),
                    MAIN_SITE_ID,
                    KITCHEN_ID,
                    KITCHEN_ID,
                    SHIFT_ID,
                ),
            )
        return {"events": len(event_ids), "incidents": len(incident_ids)}

    def record_ppe(
        self,
        employee_id: str | None,
        item: str,
        result: bool | None,
        confidence: float | None,
        source_mode: str,
    ) -> None:
        observed = utc_now()
        with self.lock, self.connection:
            self.connection.execute(
                "INSERT INTO ppe_observations VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()),
                    MAIN_SITE_ID,
                    KITCHEN_ID,
                    SHIFT_ID,
                    employee_id,
                    item,
                    None if result is None else int(result),
                    confidence,
                    source_mode,
                    iso(observed),
                    iso(observed + timedelta(days=365)),
                ),
            )

    def _activity(self, incident_id: str, actor: str, action: str, detail: str) -> None:
        self.connection.execute(
            "INSERT INTO incident_activity VALUES(?,?,?,?,?,?)",
            (str(uuid.uuid4()), incident_id, actor, action, detail, iso()),
        )

    def _audit(
        self, entity_type: str, entity_id: str, actor: str, action: str, detail: dict[str, Any]
    ) -> None:
        now = utc_now()
        self.connection.execute(
            "INSERT INTO audit_log VALUES(?,?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()),
                entity_type,
                entity_id,
                actor,
                action,
                json.dumps(detail, separators=(",", ":")),
                iso(now),
                iso(now + timedelta(days=365)),
            ),
        )

    @staticmethod
    def _site(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "code": row["code"],
            "name": row["name"],
            "timezone": row["timezone"],
            "mode": row["mode"],
        }

    @staticmethod
    def _workspace(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "siteId": row["site_id"],
            "code": row["code"],
            "name": row["name"],
            "departmentType": row["department_type"],
            "mode": row["mode"],
            "deviceCode": row["device_code"],
        }

    @staticmethod
    def _workspace_for_event(event: sqlite3.Row) -> str:
        if event["type"].startswith("temperature"):
            return COLD_STORAGE_ID
        if event["type"].startswith("inventory"):
            return INVENTORY_ID
        return event["workspace_id"] or KITCHEN_ID

    @staticmethod
    def _incident(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "sourceEventId": row["source_event_id"],
            "siteId": row["site_id"],
            "workspaceId": row["workspace_id"],
            "shiftId": row["shift_id"],
            "title": row["title"],
            "detail": row["detail"],
            "priority": row["priority"],
            "status": row["status"],
            "sourceMode": row["source_mode"],
            "owner": row["owner"],
            "dueAt": row["due_at"],
            "rootCause": row["root_cause"],
            "correctiveAction": row["corrective_action"],
            "resolutionNote": row["resolution_note"],
            "resolutionType": row["resolution_type"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "retentionUntil": row["retention_until"],
            "version": row["version"],
            "evidenceUrl": row["evidence_url"],
            "employeeName": row["employee_name"],
            "zone": row["zone"],
            "confidence": row["confidence"],
        }
