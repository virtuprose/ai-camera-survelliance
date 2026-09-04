import time

import numpy as np

from foodsafe_edge.markers import Marker
from foodsafe_edge.pipeline import EdgePipeline
from foodsafe_edge.settings import Settings


def _marker(marker_id: int, x: int, y: int) -> Marker:
    corners = np.array(
        [[x - 20, y - 20], [x + 20, y - 20], [x + 20, y + 20], [x - 20, y + 20]],
        dtype=np.float32,
    )
    return Marker(marker_id, corners, (x, y), 0.98)


def _frame() -> np.ndarray:
    return np.full((720, 1280, 3), 100, dtype=np.uint8)


def test_process_timer_requires_stable_start_and_complete_zone_dwell(tmp_path) -> None:
    pipeline = EdgePipeline(
        Settings(camera_enabled=False, data_dir=tmp_path, process_marker_dwell_seconds=0.5)
    )
    frame = _frame()
    start = _marker(201, int(1280 * 0.30), int(720 * 0.70))
    complete = _marker(201, int(1280 * 0.60), int(720 * 0.70))

    pipeline._handle_process_and_inventory([start], frame)
    assert pipeline.process_state["status"] == "idle"
    assert pipeline.tray_zone_candidate is not None
    pipeline.tray_zone_candidate = ("Process Start", time.monotonic() - 1)
    pipeline._handle_process_and_inventory([start], frame)
    assert pipeline.process_state["status"] == "running"

    pipeline._handle_process_and_inventory([complete], frame)
    assert pipeline.process_state["status"] == "running"
    pipeline.tray_zone_candidate = ("Process Complete", time.monotonic() - 1)
    pipeline._handle_process_and_inventory([complete], frame)
    assert pipeline.process_state["status"] == "complete"

    events = sorted(pipeline.store.list_events(), key=lambda event: event["occurredAt"])
    assert [event["type"] for event in events] == ["process_started", "process_complete"]
    assert events[0]["metadata"]["source_origin"] == "live_camera"
    assert events[1]["metadata"]["run_id"] == events[0]["metadata"]["run_id"]


def test_inventory_hysteresis_rejects_line_jitter_and_counts_one_stable_crossing(tmp_path) -> None:
    pipeline = EdgePipeline(
        Settings(
            camera_enabled=False,
            data_dir=tmp_path,
            inventory_line_position=0.81,
            inventory_line_hysteresis=0.025,
            inventory_marker_dwell_seconds=0.3,
        )
    )
    frame = _frame()
    left = _marker(301, int(1280 * 0.76), 300)
    deadband = _marker(301, int(1280 * 0.81), 300)
    right = _marker(301, int(1280 * 0.86), 300)

    pipeline._handle_process_and_inventory([left], frame)
    for _ in range(5):
        pipeline._handle_process_and_inventory([deadband], frame)
    assert pipeline.store.inventory_transactions() == []

    pipeline._handle_process_and_inventory([right], frame)
    assert pipeline.store.inventory_transactions() == []
    pipeline.inventory_side_candidates[301] = ("right", time.monotonic() - 1)
    pipeline._handle_process_and_inventory([right], frame)
    pipeline._handle_process_and_inventory([right], frame)

    transactions = pipeline.store.inventory_transactions()
    assert len(transactions) == 1
    assert transactions[0]["sku"] == "SKU-001"
    assert transactions[0]["direction"] == "in"
    assert next(item for item in pipeline.store.inventory() if item["sku"] == "SKU-001")[
        "quantity"
    ] == 6
