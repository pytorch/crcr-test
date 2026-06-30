#!/usr/bin/env python3
"""Verify PyTorch checkout matches the SHA from a CRCR dispatch payload."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from validate_dispatch_payload import ValidationError, validate_dispatch_payload


def _head_sha(client_payload: dict) -> str:
    event_type = client_payload["event_type"]
    payload = client_payload["payload"]
    if event_type == "pull_request":
        return payload["pull_request"]["head"]["sha"]
    return payload["after"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", required=True, help="Path to client_payload JSON file")
    parser.add_argument("--pytorch-dir", required=True, help="Path to checked-out pytorch tree")
    args = parser.parse_args()

    client_payload = json.loads(Path(args.payload).read_text())
    try:
        validate_dispatch_payload(client_payload)
    except ValidationError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    expected = _head_sha(client_payload)
    pytorch_dir = Path(args.pytorch_dir)
    if not pytorch_dir.is_dir():
        print(f"::error::pytorch dir does not exist: {pytorch_dir}", file=sys.stderr)
        return 1

    result = subprocess.run(
        ["git", "-C", str(pytorch_dir), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"::error::git rev-parse failed: {result.stderr.strip()}", file=sys.stderr)
        return 1

    actual = result.stdout.strip()
    if actual != expected:
        print(
            f"::error::checkout SHA mismatch: expected {expected}, got {actual}",
            file=sys.stderr,
        )
        return 1

    print(f"PyTorch checkout matches dispatch SHA {expected}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
