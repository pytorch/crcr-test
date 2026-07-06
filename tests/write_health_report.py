#!/usr/bin/env python3
"""Write a structured CRCR health probe result for a repository_dispatch run."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


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
    args = parser.parse_args()

    checks: dict[str, str] = {}
    for item in args.check:
        if "=" not in item:
            print(f"::error::invalid --check {item!r}, expected name=outcome", file=sys.stderr)
            return 2
        name, outcome = item.split("=", 1)
        checks[name] = outcome

    report = {
        "probe": args.probe,
        "trigger": "repository_dispatch",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "delivery_id": args.delivery_id,
        "run_id": args.run_id,
        "event_type": args.event_type,
        "pr_number": int(args.pr_number) if args.pr_number.isdigit() else None,
        "checks": checks,
        "healthy": bool(checks) and all(outcome == "success" for outcome in checks.values()),
        "hud_url": "https://hud.pytorch.org/crcr/pytorch/crcr-test",
    }

    output = Path(args.output)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))

    if not report["healthy"]:
        failed = [name for name, outcome in checks.items() if outcome != "success"]
        print(f"::error::CRCR health probe unhealthy: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
