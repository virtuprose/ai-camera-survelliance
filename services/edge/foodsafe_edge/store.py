from __future__ import annotations

import csv
import io
import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class EventInput:
    type: str
    title: str
    detail: str
    severity: str = "info"
    source_mode: str = "real"
    employee_id: str | None = None
    employee_name: str | None = None
    zone: str | None = None
    confidence: float | None = None
    evidence_url: str | None = None
    track_id: int | None = None
    device_id: str = "CAM-01"
    occurred_at: str | None = None


class EventStore:
    def __init__(self, database_path: Path):
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.connection = sqlite3.connect(database_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self._migrate()

    def _migrate(self) -> None:
        with self._lock, self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    occurred_at TEXT NOT NULL,
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    source_mode TEXT NOT NULL CHECK (source_mode IN ('real', 'simulated')),
                    status TEXT NOT NULL DEFAULT 'new',
                    employee_id TEXT,
                    employee_name TEXT,
                    zone TEXT,
                    confidence REAL,
                    evidence_url TEXT,
                    track_id INTEGER,
                    device_id TEXT NOT NULL,
                    retention_until TEXT NOT NULL,
                    sync_status TEXT NOT NULL DEFAULT 'pending',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_occurred_at ON events(occurred_at DESC);
                CREATE INDEX IF NOT EXISTS idx_events_sync_status ON events(sync_status);

                CREATE TABLE IF NOT EXISTS inventory (
                    sku TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    unit TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS process_runs (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    elapsed_seconds INTEGER,
                    source_mode TEXT NOT NULL,
                    retention_until TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS temperature_readings (
                    id TEXT PRIMARY KEY,
                    sensor_id TEXT NOT NULL,
                    value_c REAL NOT NULL,
                    min_c REAL NOT NULL,
                    max_c REAL NOT NULL,
                    status TEXT NOT NULL,
                    source_mode TEXT NOT NULL,
                    sampled_at TEXT NOT NULL,
                    retention_until TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_temperature_sampled_at
                ON temperature_readings(sampled_at DESC);
                CREATE TABLE IF NOT EXISTS inventory_transactions (
                    id TEXT PRIMARY KEY,
                    sku TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    employee_id TEXT,
                    confidence REAL,
                    source_mode TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    retention_until TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_inventory_transactions_time
                ON inventory_transactions(occurred_at DESC);
                CREATE TABLE IF NOT EXISTS runtime_health (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    checked_at TEXT NOT NULL
                );
                """
            )
            seeds = [
                ("SKU-001", "Product A", 5, "items"),
                ("SKU-002", "Product B", 8, "items"),
                ("SKU-003", "Product C", 3, "items"),
                ("SKU-004", "Product D", 6, "items"),
                ("SKU-005", "Product E", 4, "items"),
            ]
            self.connection.executemany(
                "INSERT OR IGNORE INTO inventory(sku,label,quantity,unit,updated_at) VALUES(?,?,?,?,?)",
                [(*row, iso()) for row in seeds],
            )

    def add_event(self, event: EventInput, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        event_id = str(uuid.uuid4())
        occurred_at = event.occurred_at or iso()
        retention_until = iso(
            datetime.fromisoformat(occurred_at.replace("Z", "+00:00")) + timedelta(days=365)
        )
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO events(
                    id,occurred_at,type,title,detail,severity,source_mode,status,employee_id,employee_name,
                    zone,confidence,evidence_url,track_id,device_id,retention_until,sync_status,metadata_json,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    event_id,
                    occurred_at,
                    event.type,
                    event.title,
                    event.detail,
                    event.severity,
                    event.source_mode,
                    "new",
                    event.employee_id,
                    event.employee_name,
                    event.zone,
                    event.confidence,
                    event.evidence_url,
                    event.track_id,
                    event.device_id,
                    retention_until,
                    "pending",
                    json.dumps(metadata or {}, separators=(",", ":")),
                    iso(),
                ),
            )
        return self.get_event(event_id)

    def get_event(self, event_id: str) -> dict[str, Any]:
        with self._lock:
            row = self.connection.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if row is None:
            raise KeyError(event_id)
        return self._row_to_event(row)

    def list_events(self, limit: int = 250) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT * FROM events ORDER BY occurred_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def update_status(self, event_id: str, status: str) -> dict[str, Any]:
        if status not in {"new", "acknowledged", "dismissed"}:
            raise ValueError("Unsupported review status")
        with self._lock, self.connection:
            cursor = self.connection.execute(
                "UPDATE events SET status=?,sync_status='pending',updated_at=? WHERE id=?",
                (status, iso(), event_id),
            )
        if cursor.rowcount == 0:
            raise KeyError(event_id)
        return self.get_event(event_id)

    def set_evidence(self, event_id: str, evidence_url: str) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                "UPDATE events SET evidence_url=?,sync_status='pending',updated_at=? WHERE id=?",
                (evidence_url, iso(), event_id),
            )

    def merge_metadata(self, event_id: str, updates: dict[str, Any]) -> None:
        """Atomically merge evidence/audit facts without replacing event provenance."""
        with self._lock, self.connection:
            row = self.connection.execute(
                "SELECT metadata_json FROM events WHERE id=?", (event_id,)
            ).fetchone()
            if row is None:
                raise KeyError(event_id)
            metadata = json.loads(row["metadata_json"] or "{}")
            metadata.update(updates)
            self.connection.execute(
                "UPDATE events SET metadata_json=?,sync_status='pending',updated_at=? WHERE id=?",
                (json.dumps(metadata, separators=(",", ":")), iso(), event_id),
            )

    def pending_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT * FROM events WHERE sync_status='pending' ORDER BY occurred_at LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def mark_synced(self, event_id: str) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                "UPDATE events SET sync_status='synced',updated_at=? WHERE id=?", (iso(), event_id)
            )

    def queue_depth(self) -> int:
        with self._lock:
            row = self.connection.execute(
                "SELECT COUNT(*) AS count FROM events WHERE sync_status='pending'"
            ).fetchone()
        return int(row["count"])

    def health_check(self) -> None:
        """Fail if the durable SQLite ledger cannot answer a read/write transaction."""
        with self._lock, self.connection:
            checked_at = iso()
            self.connection.execute(
                "INSERT INTO runtime_health(id,checked_at) VALUES(1,?) "
                "ON CONFLICT(id) DO UPDATE SET checked_at=excluded.checked_at",
                (checked_at,),
            )
            row = self.connection.execute(
                "SELECT checked_at FROM runtime_health WHERE id=1"
            ).fetchone()
        if row is None or row["checked_at"] != checked_at:
            raise RuntimeError("Local event ledger health check failed")

    def inventory(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT sku,label,quantity,unit FROM inventory ORDER BY sku"
            ).fetchall()
        return [dict(row) for row in rows]

    def move_inventory(self, sku: str, direction: str, quantity: int = 1) -> int:
        if direction not in {"in", "out"} or quantity < 1:
            raise ValueError("Invalid inventory movement")
        delta = quantity if direction == "in" else -quantity
        with self._lock, self.connection:
            row = self.connection.execute("SELECT quantity FROM inventory WHERE sku=?", (sku,)).fetchone()
            if row is None:
                raise KeyError(sku)
            new_quantity = max(0, int(row["quantity"]) + delta)
            self.connection.execute(
                "UPDATE inventory SET quantity=?,updated_at=? WHERE sku=?", (new_quantity, iso(), sku)
            )
        return new_quantity

    def start_process(self, label: str, source_mode: str) -> dict[str, Any]:
        run_id = str(uuid.uuid4())
        started_at = iso()
        retention = iso(utc_now() + timedelta(days=365))
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO process_runs(id,label,status,started_at,source_mode,retention_until)
                VALUES(?,?,?,?,?,?)
                """,
                (run_id, label, "running", started_at, source_mode, retention),
            )
        return {
            "id": run_id,
            "label": label,
            "status": "running",
            "startedAt": started_at,
            "elapsedSeconds": 0,
        }

    def complete_process(self, run_id: str) -> int:
        with self._lock, self.connection:
            row = self.connection.execute(
                "SELECT started_at FROM process_runs WHERE id=?", (run_id,)
            ).fetchone()
            if row is None:
                raise KeyError(run_id)
            completed_at = iso()
            elapsed = max(
                0,
                round(
                    (
                        datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
                        - datetime.fromisoformat(row["started_at"].replace("Z", "+00:00"))
                    ).total_seconds()
                ),
            )
            self.connection.execute(
                "UPDATE process_runs SET status='complete',completed_at=?,elapsed_seconds=? WHERE id=?",
                (completed_at, elapsed, run_id),
            )
        return elapsed

    def add_temperature_reading(
        self,
        sensor_id: str,
        value_c: float,
        min_c: float,
        max_c: float,
        status: str,
        source_mode: str,
        sampled_at: str,
    ) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO temperature_readings(
                    id,sensor_id,value_c,min_c,max_c,status,source_mode,sampled_at,retention_until
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    str(uuid.uuid4()),
                    sensor_id,
                    value_c,
                    min_c,
                    max_c,
                    status,
                    source_mode,
                    sampled_at,
                    iso(datetime.fromisoformat(sampled_at.replace("Z", "+00:00")) + timedelta(days=365)),
                ),
            )

    def temperature_readings(self, limit: int = 500) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT * FROM temperature_readings ORDER BY sampled_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def record_inventory_transaction(
        self,
        sku: str,
        direction: str,
        quantity: int,
        employee_id: str | None,
        confidence: float,
        source_mode: str,
    ) -> None:
        occurred_at = iso()
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO inventory_transactions(
                    id,sku,direction,quantity,employee_id,confidence,source_mode,occurred_at,retention_until
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    str(uuid.uuid4()),
                    sku,
                    direction,
                    quantity,
                    employee_id,
                    confidence,
                    source_mode,
                    occurred_at,
                    iso(datetime.fromisoformat(occurred_at.replace("Z", "+00:00")) + timedelta(days=365)),
                ),
            )

    def inventory_transactions(self, limit: int = 500) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT * FROM inventory_transactions ORDER BY occurred_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def csv_export(self) -> str:
        output = io.StringIO()
        fields = [
            "id",
            "deviceId",
            "trackId",
            "occurredAt",
            "type",
            "title",
            "severity",
            "sourceMode",
            "status",
            "employeeName",
            "zone",
            "confidence",
            "retentionUntil",
        ]
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(self.list_events(limit=10_000))
        return output.getvalue()

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "deviceId": row["device_id"],
            "trackId": row["track_id"],
            "occurredAt": row["occurred_at"],
            "type": row["type"],
            "title": row["title"],
            "detail": row["detail"],
            "severity": row["severity"],
            "sourceMode": row["source_mode"],
            "status": row["status"],
            "employeeId": row["employee_id"],
            "employeeName": row["employee_name"],
            "zone": row["zone"],
            "confidence": row["confidence"],
            "evidenceUrl": row["evidence_url"],
            "retentionUntil": row["retention_until"],
            "metadata": json.loads(row["metadata_json"]),
        }
