#!/usr/bin/env python3
"""Write CRCR health probe results and map them to HUD test_results."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def parse_checks(items: list[str]) -> dict[str, str]:
    checks: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"invalid --check {item!r}, expected name=outcome")
        name, outcome = item.split("=", 1)
        checks[name] = outcome
    return checks


def checks_to_test_results(checks: dict[str, str]) -> dict[str, int]:
    passed = sum(1 for outcome in checks.values() if outcome == "success")
    skipped = sum(1 for outcome in checks.values() if outcome == "skipped")
    failed = len(checks) - passed - skipped
    return {
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "total": len(checks),
    }


def build_report(
    *,
    probe: str,
    checks: dict[str, str],
    delivery_id: str = "",
    run_id: str = "",
    event_type: str = "",
    pr_number: str = "",
) -> dict:
    healthy = bool(checks) and all(outcome == "success" for outcome in checks.values())
    test_results = checks_to_test_results(checks)
    return {
        "probe": probe,
        "trigger": "repository_dispatch",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "delivery_id": delivery_id,
        "run_id": run_id,
        "event_type": event_type,
        "pr_number": int(pr_number) if pr_number.isdigit() else None,
        "checks": checks,
        "healthy": healthy,
        "conclusion": "success" if healthy else "failure",
        "test_results": test_results,
        "hud_url": "https://hud.pytorch.org/crcr/pytorch/crcr-test",
    }


def append_github_output(report: dict, github_output: str) -> None:
    with open(github_output, "a", encoding="utf-8") as handle:
        handle.write(f"healthy={str(report['healthy']).lower()}\n")
        handle.write(f"conclusion={report['conclusion']}\n")
        handle.write("test_results<<EOF\n")
        handle.write(json.dumps(report["test_results"]))
        handle.write("\nEOF\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", required=True, help="Probe name, e.g. l1-critical")
    parser.add_argument("--output", required=True, help="Path to write JSON report")
    parser.add_argument("--delivery-id", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--event-type", default="")
    parser.add_argument("--pr-number", default="")
    parser.add_argument(
        "--check",
        action="append",
        default=[],
        help="Check outcome as name=outcome (repeatable)",
    )
    parser.add_argument(
        "--github-output",
        default="",
        help="If set, append healthy/conclusion/test_results to this GITHUB_OUTPUT path",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Exit 1 when the probe is unhealthy (default: exit 0 after writing report)",
    )
    args = parser.parse_args()

    try:
        checks = parse_checks(args.check)
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 2

    report = build_report(
        probe=args.probe,
        checks=checks,
        delivery_id=args.delivery_id,
        run_id=args.run_id,
        event_type=args.event_type,
        pr_number=args.pr_number,
    )

    output = Path(args.output)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))

    if args.github_output:
        append_github_output(report, args.github_output)

    if args.strict and not report["healthy"]:
        failed = [name for name, outcome in checks.items() if outcome != "success"]
        print(f"::error::CRCR health probe unhealthy: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
