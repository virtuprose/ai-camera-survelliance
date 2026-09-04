from __future__ import annotations

import logging
import threading
from pathlib import Path

import httpx

from .settings import Settings
from .store import EventStore

logger = logging.getLogger(__name__)


class CloudSyncWorker:
    """Idempotently upsert local events to Supabase when credentials are configured."""

    def __init__(self, settings: Settings, store: EventStore):
        self.settings = settings
        self.store = store
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.online = False

    @property
    def configured(self) -> bool:
        return bool(self.settings.supabase_ingest_url and self.settings.edge_device_token)

    def start(self) -> None:
        if not self.configured:
            return
        self.thread = threading.Thread(target=self._run, name="supabase-sync", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=3)

    def _run(self) -> None:
        endpoint = self.settings.supabase_ingest_url
        headers = {
            "content-type": "application/json",
            "x-device-token": self.settings.edge_device_token,
        }
        with httpx.Client(timeout=10) as client:
            while not self.stop_event.is_set():
                pending = self.store.pending_events()
                if not pending:
                    self.online = True
                    self.stop_event.wait(2)
                    continue
                for event in pending:
                    try:
                        response = client.post(endpoint, headers=headers, json=event)
                        response.raise_for_status()
                        if (
                            event["evidenceUrl"]
                            and self.settings.supabase_evidence_url
                            and not self._upload_evidence(client, headers, event)
                        ):
                            self.online = False
                            break
                        self.store.mark_synced(event["id"])
                        self.online = True
                    except Exception as error:
                        self.online = False
                        logger.warning("Cloud sync paused: %s", error)
                        break
                self.stop_event.wait(2 if self.online else 5)

    def _upload_evidence(
        self,
        client: httpx.Client,
        headers: dict[str, str],
        event: dict[str, object],
    ) -> bool:
        snapshot_name = Path(str(event["evidenceUrl"])).name
        snapshot = self.settings.evidence_dir / snapshot_name
        clip = self.settings.evidence_dir / f"{event['id']}.mp4"
        if not snapshot.is_file() or not clip.is_file():
            return False
        upload_headers = {"x-device-token": headers["x-device-token"]}
        for kind, path, content_type in (
            ("snapshot", snapshot, "image/jpeg"),
            ("clip", clip, "video/mp4"),
        ):
            with path.open("rb") as file_handle:
                response = client.post(
                    self.settings.supabase_evidence_url,
                    headers=upload_headers,
                    data={
                        "event_id": str(event["id"]),
                        "kind": kind,
                        "retention_until": str(event["retentionUntil"]),
                    },
                    files={"file": (path.name, file_handle, content_type)},
                )
            response.raise_for_status()
        return True
