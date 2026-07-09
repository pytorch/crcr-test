#!/usr/bin/env python3
"""Validate CRCR L2 callback body shape (downstream -> relay wire format)."""

from __future__ import annotations

import json
import sys
from typing import Any

from validate_dispatch_payload import ValidationError, validate_dispatch_payload

ALLOWED_STATUSES = frozenset({"in_progress", "completed"})
ALLOWED_CONCLUSIONS = frozenset({"success", "failure", "cancelled", "timed_out"})


def validate_callback_body(body: dict[str, Any], *, expect_status: str) -> None:
    validate_dispatch_payload(body)

    workflow = body.get("workflow")
    if not isinstance(workflow, dict):
        raise ValidationError("workflow must be an object")

    status = workflow.get("status")
    if status != expect_status:
        raise ValidationError(f"workflow.status must be {expect_status!r}, got {status!r}")

    for field in ("schema_version", "name", "url", "job_name", "check_run_id", "run_id", "run_attempt"):
        if field not in workflow:
            raise ValidationError(f"workflow.{field} is required for L2 callbacks")

    if expect_status == "in_progress":
        if workflow.get("conclusion") is not None:
            raise ValidationError("in_progress callback must not set workflow.conclusion")
        if not workflow.get("started_at"):
            raise ValidationError("in_progress callback must set workflow.started_at")
    else:
        conclusion = workflow.get("conclusion")
        if conclusion not in ALLOWED_CONCLUSIONS:
            raise ValidationError(
                f"completed callback conclusion must be one of {sorted(ALLOWED_CONCLUSIONS)}, "
                f"got {conclusion!r}"
            )
        if not workflow.get("completed_at"):
            raise ValidationError("completed callback must set workflow.completed_at")


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: validate_callback_payload.py <in_progress|completed> <json-file>", file=sys.stderr)
        return 2

    expect_status = sys.argv[1]
    if expect_status not in ALLOWED_STATUSES:
        print("::error::status arg must be in_progress or completed", file=sys.stderr)
        return 2

    try:
        body = json.loads(open(sys.argv[2]).read())
        validate_callback_body(body, expect_status=expect_status)
    except (ValidationError, json.JSONDecodeError, OSError) as exc:
        print(f"::error::L2 callback validation failed: {exc}", file=sys.stderr)
        return 1

    print(f"L2 {expect_status} callback validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
