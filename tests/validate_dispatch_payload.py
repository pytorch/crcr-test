#!/usr/bin/env python3
"""Validate CRCR repository_dispatch client_payload structure (L1 integration)."""

from __future__ import annotations

import json
import re
import sys
from typing import Any

UPSTREAM_REPO = "pytorch/pytorch"
ALLOWED_EVENT_TYPES = frozenset({"pull_request", "push"})
ALLOWED_PR_ACTIONS = frozenset({"opened", "reopened", "synchronize", "closed"})
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
NULL_SHA = "0" * 40


class ValidationError(Exception):
    pass


def _require(obj: dict[str, Any], key: str, label: str) -> Any:
    if key not in obj:
        raise ValidationError(f"missing {label}.{key}")
    return obj[key]


def _require_sha(value: str, label: str) -> None:
    if not SHA_RE.match(value):
        raise ValidationError(f"{label} is not a 40-char hex SHA: {value!r}")


def validate_dispatch_payload(client_payload: dict[str, Any]) -> None:
    event_type = _require(client_payload, "event_type", "client_payload")
    if event_type not in ALLOWED_EVENT_TYPES:
        raise ValidationError(
            f"client_payload.event_type must be one of {sorted(ALLOWED_EVENT_TYPES)}, "
            f"got {event_type!r}"
        )

    delivery_id = _require(client_payload, "delivery_id", "client_payload")
    if not isinstance(delivery_id, str) or not delivery_id.strip():
        raise ValidationError("client_payload.delivery_id must be a non-empty string")

    payload = _require(client_payload, "payload", "client_payload")
    if not isinstance(payload, dict):
        raise ValidationError("client_payload.payload must be an object")

    repo = _require(payload, "repository", "client_payload.payload")
    if not isinstance(repo, dict):
        raise ValidationError("client_payload.payload.repository must be an object")
    full_name = _require(repo, "full_name", "client_payload.payload.repository")
    if full_name != UPSTREAM_REPO:
        raise ValidationError(
            f"upstream repo must be {UPSTREAM_REPO!r}, got {full_name!r}"
        )

    if event_type == "pull_request":
        action = _require(payload, "action", "client_payload.payload")
        if action not in ALLOWED_PR_ACTIONS:
            raise ValidationError(
                f"pull_request action must be one of {sorted(ALLOWED_PR_ACTIONS)}, "
                f"got {action!r}"
            )
        pr = _require(payload, "pull_request", "client_payload.payload")
        if not isinstance(pr, dict):
            raise ValidationError("client_payload.payload.pull_request must be an object")
        number = _require(pr, "number", "client_payload.payload.pull_request")
        if not isinstance(number, int) or number <= 0:
            raise ValidationError(f"pull_request.number must be a positive int, got {number!r}")
        head = _require(pr, "head", "client_payload.payload.pull_request")
        if not isinstance(head, dict):
            raise ValidationError("pull_request.head must be an object")
        head_sha = _require(head, "sha", "pull_request.head")
        _require_sha(head_sha, "pull_request.head.sha")
        head_repo = _require(head, "repo", "pull_request.head")
        if not isinstance(head_repo, dict):
            raise ValidationError("pull_request.head.repo must be an object")
        _require(head_repo, "full_name", "pull_request.head.repo")

    elif event_type == "push":
        ref = _require(payload, "ref", "client_payload.payload")
        if not isinstance(ref, str) or not ref.startswith("refs/"):
            raise ValidationError(f"push ref must start with refs/, got {ref!r}")
        deleted = payload.get("deleted", False)
        if deleted:
            after = payload.get("after", "")
            if after != NULL_SHA:
                raise ValidationError(
                    f"deleted push must have null after SHA {NULL_SHA!r}, got {after!r}"
                )
        else:
            after = _require(payload, "after", "client_payload.payload")
            _require_sha(after, "payload.after")
            if after == NULL_SHA:
                raise ValidationError(
                    "non-deleted push must not use the null after SHA; set deleted=true"
                )


def main() -> int:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"::error::client_payload is not valid JSON: {exc}", file=sys.stderr)
        return 1

    try:
        validate_dispatch_payload(data)
    except ValidationError as exc:
        print(f"::error::L1 dispatch payload validation failed: {exc}", file=sys.stderr)
        return 1

    print("L1 dispatch payload validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
