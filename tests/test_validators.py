#!/usr/bin/env python3
"""Unit tests for CRCR payload validators (runs locally without relay)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from validate_callback_payload import validate_callback_body
from validate_dispatch_payload import ValidationError, validate_dispatch_payload

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class TestDispatchPayload(unittest.TestCase):
    def test_pull_request_opened_fixture(self) -> None:
        validate_dispatch_payload(_load("pull_request_opened.json"))

    def test_pull_request_synchronize_fixture(self) -> None:
        validate_dispatch_payload(_load("pull_request_synchronize.json"))

    def test_pull_request_closed_fixture(self) -> None:
        validate_dispatch_payload(_load("pull_request_closed.json"))

    def test_push_ciflow_tag_fixture(self) -> None:
        validate_dispatch_payload(_load("push_ciflow_tag.json"))

    def test_rejects_missing_delivery_id(self) -> None:
        payload = _load("pull_request_opened.json")
        del payload["delivery_id"]
        with self.assertRaises(ValidationError):
            validate_dispatch_payload(payload)

    def test_rejects_wrong_upstream_repo(self) -> None:
        payload = _load("pull_request_opened.json")
        payload["payload"]["repository"]["full_name"] = "other/repo"
        with self.assertRaises(ValidationError):
            validate_dispatch_payload(payload)

    def test_rejects_invalid_sha(self) -> None:
        payload = _load("pull_request_opened.json")
        payload["payload"]["pull_request"]["head"]["sha"] = "not-a-sha"
        with self.assertRaises(ValidationError):
            validate_dispatch_payload(payload)


class TestCallbackPayload(unittest.TestCase):
    def _completed_body(self) -> dict:
        body = _load("pull_request_opened.json")
        body["workflow"] = {
            "schema_version": "1",
            "status": "completed",
            "conclusion": "success",
            "name": "OOT L2 Critical",
            "url": "https://github.com/pytorch/crcr-test/actions/runs/1",
            "run_attempt": "1",
            "job_name": "l2-critical",
            "check_run_id": "12345",
            "run_id": "1",
            "started_at": "2026-06-29T00:00:00Z",
            "completed_at": "2026-06-29T00:01:00Z",
            "test_results": {"passed": 3, "failed": 0, "skipped": 0},
            "artifact_url": "https://example.com/artifacts/1",
        }
        return body

    def test_in_progress_shape(self) -> None:
        body = _load("pull_request_opened.json")
        body["workflow"] = {
            "schema_version": "1",
            "status": "in_progress",
            "conclusion": None,
            "name": "OOT L2 Critical",
            "url": "https://github.com/pytorch/crcr-test/actions/runs/1",
            "run_attempt": "1",
            "job_name": "l2-critical",
            "check_run_id": "12345",
            "run_id": "1",
            "started_at": "2026-06-29T00:00:00Z",
            "completed_at": None,
        }
        validate_callback_body(body, expect_status="in_progress")

    def test_completed_shape(self) -> None:
        validate_callback_body(self._completed_body(), expect_status="completed")

    def test_completed_requires_conclusion(self) -> None:
        body = self._completed_body()
        body["workflow"]["conclusion"] = None
        with self.assertRaises(ValidationError):
            validate_callback_body(body, expect_status="completed")


class TestPytorchCheckout(unittest.TestCase):
    def test_checkout_matches_dispatch_sha(self) -> None:
        import subprocess

        from validate_pytorch_checkout import _head_sha

        payload = _load("pull_request_opened.json")
        expected = _head_sha(payload)
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", tmp], check=True, capture_output=True)
            subprocess.run(
                ["git", "-C", tmp, "commit", "--allow-empty", "-m", "init"],
                check=True,
                capture_output=True,
                env={
                    **__import__("os").environ,
                    "GIT_AUTHOR_NAME": "test",
                    "GIT_AUTHOR_EMAIL": "test@test.com",
                    "GIT_COMMITTER_NAME": "test",
                    "GIT_COMMITTER_EMAIL": "test@test.com",
                },
            )
            # Empty repo won't match arbitrary SHA; just verify script runs.
            result = subprocess.run(
                [
                    "python3",
                    str(Path(__file__).parent / "validate_pytorch_checkout.py"),
                    "--payload",
                    str(FIXTURES / "pull_request_opened.json"),
                    "--pytorch-dir",
                    tmp,
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("checkout SHA mismatch", result.stderr)


if __name__ == "__main__":
    unittest.main()
