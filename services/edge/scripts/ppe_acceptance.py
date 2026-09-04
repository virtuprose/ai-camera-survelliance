from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    instruction: str
    expected: dict[str, str]


SCENARIOS = (
    Scenario(
        "bare-face-hands-hidden",
        "Bare face visible; keep both hands outside the frame.",
        {"mask": "missing", "left_glove": "not_visible", "right_glove": "not_visible"},
    ),
    Scenario(
        "bare-face-bare-hands",
        "Bare face and both bare hands visible, with hands separated from the torso.",
        {"mask": "missing", "left_glove": "missing", "right_glove": "missing"},
    ),
    Scenario(
        "blue-mask-bare-hands",
        "Wear the blue mask; show both bare hands away from the torso.",
        {"mask": "detected", "left_glove": "missing", "right_glove": "missing"},
    ),
    Scenario(
        "blue-mask-red-gloves",
        "Wear the blue mask and both red gloves; show both hands away from the torso.",
        {"mask": "detected", "left_glove": "detected", "right_glove": "detected"},
    ),
    Scenario(
        "face-hidden-hands-visible",
        "Turn or cover the face so landmarks are unavailable; keep both bare hands visible.",
        {"mask": "not_visible", "left_glove": "missing", "right_glove": "missing"},
    ),
    Scenario(
        "face-visible-hands-hidden",
        "Keep the bare face visible and both hands outside the frame.",
        {"mask": "missing", "left_glove": "not_visible", "right_glove": "not_visible"},
    ),
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _event_item(event: dict[str, Any]) -> str | None:
    metadata = event.get("metadata") or {}
    return str(metadata.get("item")) if metadata.get("item") else None


def _evidence_ready(client: httpx.Client, base_url: str, event: dict[str, Any]) -> bool:
    evidence_url = event.get("evidenceUrl")
    if not evidence_url:
        return False
    snapshot_name = str(evidence_url).rsplit("/", 1)[-1]
    snapshot = client.get(f"{base_url}/api/evidence/{snapshot_name}")
    clip = client.get(f"{base_url}/api/evidence/{event['id']}.mp4")
    return snapshot.status_code == 200 and clip.status_code == 200


def _metadata_complete(event: dict[str, Any]) -> bool:
    metadata = event.get("metadata") or {}
    required = {
        "item",
        "visibility_confidence",
        "decision_confidence",
        "colour_profile",
        "colour_ratio",
        "threshold",
        "stable_for_ms",
        "brightness",
        "camera_label",
        "roi",
    }
    return (
        required <= set(metadata)
        and event.get("trackId") is not None
        and bool(event.get("retentionUntil"))
    )


def _wait_for_evidence(
    client: httpx.Client,
    base_url: str,
    events: list[dict[str, Any]],
    timeout: float = 4.0,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if all(_evidence_ready(client, base_url, event) for event in events):
            return True
        time.sleep(0.25)
    return all(_evidence_ready(client, base_url, event) for event in events)


def _run_once(
    client: httpx.Client,
    base_url: str,
    scenario: Scenario,
    duration: float,
) -> dict[str, Any]:
    reset = client.post(f"{base_url}/api/detection/reset")
    reset.raise_for_status()
    baseline_response = client.get(f"{base_url}/api/events")
    baseline_response.raise_for_status()
    baseline_ids = {event["id"] for event in baseline_response.json()["items"]}

    states: list[dict[str, str]] = []
    track_ids: list[int] = []
    health_failures: list[str] = []
    started = time.monotonic()
    while time.monotonic() - started < duration:
        response = client.get(f"{base_url}/api/state")
        response.raise_for_status()
        payload = response.json()
        health = payload["health"]
        if health["camera"] != "online":
            health_failures.append("camera offline")
        last_frame = health.get("lastFrameAt")
        if last_frame:
            sampled = datetime.fromisoformat(last_frame.replace("Z", "+00:00"))
            if (datetime.now(UTC) - sampled).total_seconds() > 2:
                health_failures.append("frame stale over two seconds")
        detection = payload["detection"]
        if detection.get("trackId") is not None:
            track_ids.append(int(detection["trackId"]))
        items = detection.get("ppeItems") or {}
        if all(item in items for item in scenario.expected):
            states.append({item: str(items[item]["state"]) for item in scenario.expected})
        time.sleep(0.25)

    state_response = client.get(f"{base_url}/api/state")
    state_response.raise_for_status()
    final_state = state_response.json()
    fps = float(final_state["health"].get("processedFps") or 0)
    final_samples = states[-4:]
    stable_match = len(final_samples) == 4 and all(
        sample == scenario.expected for sample in final_samples
    )

    event_response = client.get(f"{base_url}/api/events")
    event_response.raise_for_status()
    new_events = [
        event
        for event in event_response.json()["items"]
        if event["id"] not in baseline_ids and event["type"] == "ppe_violation"
    ]
    expected_missing = [item for item, state in scenario.expected.items() if state == "missing"]
    emitted = sorted(
        (event for event in new_events if _event_item(event) in expected_missing),
        key=lambda event: event["occurredAt"],
    )
    emitted_items = [_event_item(event) for event in emitted]
    expected_order = [
        item
        for item in ("mask", "left_glove", "right_glove")
        if item in expected_missing
    ]
    unexpected = [event for event in new_events if _event_item(event) not in expected_missing]
    metadata_ok = all(_metadata_complete(event) for event in emitted)
    evidence_ok = _wait_for_evidence(client, base_url, emitted) if emitted else True
    passed = all(
        (
            stable_match,
            fps >= 6,
            not health_failures,
            len(set(track_ids[-12:])) <= 1 and bool(track_ids),
            emitted_items == expected_order,
            not unexpected,
            metadata_ok,
            evidence_ok,
        )
    )
    return {
        "scenario": scenario.name,
        "passed": passed,
        "expected": scenario.expected,
        "finalSamples": final_samples,
        "processedFps": fps,
        "trackIds": sorted(set(track_ids)),
        "healthFailures": sorted(set(health_failures)),
        "expectedEventOrder": expected_order,
        "emittedEventOrder": emitted_items,
        "unexpectedEvents": [event["title"] for event in unexpected],
        "metadataComplete": metadata_ok,
        "evidenceComplete": evidence_ok,
        "checkedAt": _utc_now(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the 30-run controlled physical PPE gate.")
    parser.add_argument("--url", default="http://127.0.0.1:8787")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--seconds", type=float, default=8.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/client-demo/ppe-acceptance.json"),
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    print("ORVIA controlled PPE acceptance")
    print("Use bright front lighting, a plain background, and keep head, torso, and hands in frame.")
    print("This is a controlled demo gate, not a universal accuracy measurement.\n")
    results: list[dict[str, Any]] = []
    with httpx.Client(timeout=6) as client:
        health = client.get(f"{args.url}/health")
        health.raise_for_status()
        for scenario in SCENARIOS:
            for repeat in range(1, args.repeats + 1):
                prompt = (
                    f"[{scenario.name} {repeat}/{args.repeats}] {scenario.instruction}\n"
                    "Press Enter when ready: "
                )
                input(prompt)
                print(f"Observing for {args.seconds:.1f} seconds…", flush=True)
                result = _run_once(client, args.url, scenario, args.seconds)
                result["repeat"] = repeat
                results.append(result)
                args.output.write_text(
                    json.dumps({"startedAt": results[0]["checkedAt"], "runs": results}, indent=2),
                    encoding="utf-8",
                )
                print("PASS" if result["passed"] else "FAIL", json.dumps(result, indent=2))

    passed = sum(bool(result["passed"]) for result in results)
    report = {
        "completedAt": _utc_now(),
        "passed": passed,
        "total": len(results),
        "clientLiveGatePassed": passed == len(results) == len(SCENARIOS) * args.repeats,
        "runs": results,
    }
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not report["clientLiveGatePassed"]:
        raise SystemExit(f"FAIL: {passed}/{len(results)} controlled runs passed. Use the labelled fallback.")
    print(f"PASS: {passed}/{len(results)} controlled runs passed. Report: {args.output}")


if __name__ == "__main__":
    main()
