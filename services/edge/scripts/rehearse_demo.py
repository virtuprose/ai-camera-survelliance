from __future__ import annotations

import argparse
import time

import httpx


def post(client: httpx.Client, base_url: str, action: str, payload: dict[str, object] | None = None) -> float:
    started = time.monotonic()
    response = client.post(f"{base_url}/api/demo/{action}", json=payload or {})
    response.raise_for_status()
    return time.monotonic() - started


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an unattended local fallback rehearsal.")
    parser.add_argument("--minutes", type=float, default=8)
    parser.add_argument("--url", default="http://127.0.0.1:8787")
    args = parser.parse_args()

    duration = args.minutes * 60
    checks = 0
    health_failures = 0
    max_action_latency = 0.0
    started = time.monotonic()
    next_heartbeat = 60.0
    actions: list[tuple[float, str, dict[str, object] | None]] = [
        (duration * 0.03125, "ppe-violation", None),
        (duration * 0.0625, "temperature-high", None),
        (duration * 0.09375, "temperature-safe", None),
        (duration * 0.125, "inventory", {"sku": "SKU-003", "direction": "in", "quantity": 1}),
        (duration * 0.1875, "process-start", None),
        (duration * 0.21875, "process-complete", None),
    ]
    pending = list(actions)
    poll_interval = min(2.0, max(0.1, duration / 30))

    with httpx.Client(timeout=5) as client:
        baseline_response = client.get(f"{args.url}/api/events")
        baseline_response.raise_for_status()
        baseline_ids = {item["id"] for item in baseline_response.json()["items"]}

        while (elapsed := time.monotonic() - started) < duration:
            try:
                response = client.get(f"{args.url}/health")
                response.raise_for_status()
                payload = response.json()
                if payload.get("camera") != "online" or not payload.get("lastFrameAt"):
                    health_failures += 1
            except Exception:
                health_failures += 1
            checks += 1

            while pending and elapsed >= pending[0][0]:
                _, action, payload = pending.pop(0)
                latency = post(client, args.url, action, payload)
                max_action_latency = max(max_action_latency, latency)
                print(f"ACTION: {action} accepted in {latency:.3f}s", flush=True)

            if elapsed >= next_heartbeat:
                print(
                    f"HEALTH: {elapsed / 60:.0f}m, {checks} checks, {health_failures} failures",
                    flush=True,
                )
                next_heartbeat += 60
            time.sleep(poll_interval)

        events_response = client.get(f"{args.url}/api/events")
        events_response.raise_for_status()
        new_events = [item for item in events_response.json()["items"] if item["id"] not in baseline_ids]

    required = {
        "ppe_violation",
        "temperature_alert",
        "temperature_recovered",
        "inventory_movement",
        "process_complete",
        "process_started",
    }
    # Live camera detections can legitimately arrive while the scripted controls
    # are being rehearsed. Validate the simulated control events independently
    # so an unidentified real person does not make the fallback rehearsal fail.
    rehearsed_events = [item for item in new_events if item["sourceMode"] == "simulated"]
    event_types = {item["type"] for item in rehearsed_events}
    missing = sorted(required - event_types)
    invalid = [
        item["id"]
        for item in rehearsed_events
        if item["type"] in required
        and (
            item["sourceMode"] != "simulated"
            or not item["retentionUntil"]
            or not item["evidenceUrl"]
        )
    ]
    failures: list[str] = []
    if health_failures:
        failures.append(f"{health_failures} health checks failed")
    if missing:
        failures.append(f"missing event types: {', '.join(missing)}")
    if invalid:
        failures.append(f"events missing simulated/retention/evidence fields: {', '.join(invalid)}")
    if max_action_latency > 2:
        failures.append(f"maximum action latency was {max_action_latency:.3f}s")
    if failures:
        raise SystemExit("FAIL: " + "; ".join(failures))
    print(
        f"PASS: {duration:.0f}s uninterrupted, {checks} health checks, "
        f"{len(new_events)} new events, maximum action latency {max_action_latency:.3f}s",
        flush=True,
    )


if __name__ == "__main__":
    main()
