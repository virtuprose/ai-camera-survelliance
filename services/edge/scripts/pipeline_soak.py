from __future__ import annotations

import argparse
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx


def _age_seconds(value: str) -> float:
    sampled = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (datetime.now(UTC) - sampled).total_seconds()


def _evidence_exists(client: httpx.Client, base_url: str, event: dict[str, Any]) -> bool:
    snapshot = Path(str(event.get("evidenceUrl") or "")).name
    if not snapshot:
        return False
    return (
        client.get(f"{base_url}/api/evidence/{snapshot}").status_code == 200
        and client.get(f"{base_url}/api/evidence/{event['id']}.mp4").status_code == 200
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify the live camera and pose pipeline.")
    parser.add_argument("--minutes", type=float, default=10)
    parser.add_argument("--url", default="http://127.0.0.1:8787")
    args = parser.parse_args()
    duration = args.minutes * 60
    failures: list[str] = []
    fps_samples: list[float] = []
    tracks: list[int] = []
    checks = 0
    started = time.monotonic()
    next_heartbeat = 60.0

    with httpx.Client(timeout=5) as client:
        baseline = client.get(f"{args.url}/api/events")
        baseline.raise_for_status()
        baseline_ids = {event["id"] for event in baseline.json()["items"]}
        while (elapsed := time.monotonic() - started) < duration:
            response = client.get(f"{args.url}/api/state")
            response.raise_for_status()
            state = response.json()
            health = state["health"]
            if health["camera"] != "online":
                failures.append("camera offline")
            if health["stream"] != "online":
                failures.append("stream offline")
            last_frame = health.get("lastFrameAt")
            if not last_frame or _age_seconds(last_frame) > 2:
                failures.append("frame freshness exceeded two seconds")
            fps = float(health.get("processedFps") or 0)
            if elapsed >= 5:
                fps_samples.append(fps)
                if fps < 6:
                    failures.append(f"processed FPS below six ({fps:.1f})")
            track_id = state["detection"].get("trackId")
            if track_id is not None:
                tracks.append(int(track_id))
            checks += 1
            if elapsed >= next_heartbeat:
                print(
                    f"HEALTH: {elapsed / 60:.0f}m, {checks} checks, "
                    f"{len(failures)} failures, {fps:.1f} fps",
                    flush=True,
                )
                next_heartbeat += 60
            time.sleep(0.5)

        events_response = client.get(f"{args.url}/api/events")
        events_response.raise_for_status()
        new_ppe_events = [
            event
            for event in events_response.json()["items"]
            if event["id"] not in baseline_ids and event["type"] == "ppe_violation"
        ]
        duplicate_keys = Counter(
            (event.get("trackId"), (event.get("metadata") or {}).get("item"))
            for event in new_ppe_events
        )
        duplicates = [key for key, count in duplicate_keys.items() if count > 1]
        if duplicates:
            failures.append(f"duplicate sustained PPE events: {duplicates}")

        deadline = time.monotonic() + 4
        while new_ppe_events and time.monotonic() < deadline:
            if all(_evidence_exists(client, args.url, event) for event in new_ppe_events):
                break
            time.sleep(0.25)
        incomplete = [
            event["id"]
            for event in new_ppe_events
            if not _evidence_exists(client, args.url, event)
        ]
        if incomplete:
            failures.append(f"incomplete PPE evidence: {incomplete}")

    if failures:
        raise SystemExit("FAIL: " + "; ".join(sorted(set(failures))))
    minimum_fps = min(fps_samples) if fps_samples else 0
    maximum_fps = max(fps_samples) if fps_samples else 0
    print(
        f"PASS: {duration:.1f}s, {checks} health checks, {minimum_fps:.1f}-{maximum_fps:.1f} "
        f"processed fps, {len(set(tracks))} observed track IDs, {len(new_ppe_events)} new PPE events, "
        "zero stale frames, duplicates, or incomplete evidence",
        flush=True,
    )


if __name__ == "__main__":
    main()
