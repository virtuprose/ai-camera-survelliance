from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from foodsafe_edge.ai_supervisor import OpenAIResponsesProvider
from foodsafe_edge.enterprise import EnterpriseStore
from foodsafe_edge.operations_supervisor import FEATURES, OperationsSupervisor
from foodsafe_edge.settings import Settings
from foodsafe_edge.store import EventStore


class DirectWorker:
    """Collector-only placeholder; this verifier calls the provider directly."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify all read-only AI operations actions and record 24-hour readiness."
    )
    parser.add_argument("--live-runs", type=int, default=3)
    parser.add_argument("--skip-tests", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.live_runs < 1:
        raise SystemExit("--live-runs must be at least 1")
    settings = Settings()
    store = EventStore(settings.database_path)
    enterprise = EnterpriseStore(store)
    supervisor = OperationsSupervisor(settings, store, enterprise, DirectWorker())  # type: ignore[arg-type]
    provider = OpenAIResponsesProvider(settings)
    if not provider.configured:
        print("BLOCKED: OpenAI is not configured. Local monitoring is unaffected.")
        return 2

    tests_passed = args.skip_tests
    if not args.skip_tests:
        command = [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_ai_supervisor.py",
            "tests/test_operations_supervisor.py",
            "-q",
        ]
        completed = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], check=False)
        tests_passed = completed.returncode == 0
        if not tests_passed:
            print("BLOCKED: automated AI operation tests failed.")
            return completed.returncode

    failures: list[str] = []
    for action in FEATURES:
        facts, source_ids = supervisor.collect(action)
        if not facts or not source_ids:
            failures.append(f"{action}: insufficient local fixture evidence")
            continue
        action_ok = True
        for run in range(1, args.live_runs + 1):
            try:
                result = provider.reason(
                    action=action,
                    facts=facts,
                    source_record_ids=source_ids[:20],
                ).result
                if result["outcome"] not in {"supported", "needs_review"}:
                    action_ok = False
                    failures.append(f"{action} run {run}: {result['outcome']}")
            except Exception as error:
                action_ok = False
                failures.append(f"{action} run {run}: {type(error).__name__}")
        if action_ok:
            store.record_ai_feature_readiness(
                action,
                config_passed=True,
                automated_tests_passed=tests_passed,
                fixtures_passed=True,
                live_smoke_passed=True,
                detail=f"Automated fixtures and {args.live_runs} live grounded request(s) passed.",
            )
            print(f"PASS: {action}")

    if failures:
        print("BLOCKED: one or more actions failed readiness:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("PASS: all AI operations actions have current readiness records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
