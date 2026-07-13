#!/usr/bin/env python3
"""Unit tests for CRCR payload validators (runs locally without relay)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from validate_callback_payload import validate_callback_body
from validate_dispatch_payload import ValidationError, validate_dispatch_payload
from write_health_report import build_report, checks_to_test_results

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

    def test_push_tag_deleted_fixture(self) -> None:
        validate_dispatch_payload(_load("push_tag_deleted.json"))

    def test_rejects_non_deleted_push_with_null_after(self) -> None:
        payload = _load("push_ciflow_tag.json")
        payload["payload"]["after"] = "0" * 40
        with self.assertRaises(ValidationError):
            validate_dispatch_payload(payload)

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
            "name": "CRCR L2 Critical",
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
            "name": "CRCR L2 Critical",
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

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
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
            head = subprocess.run(
                ["git", "-C", tmp, "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            )
            matching_sha = head.stdout.strip()

            payload = _load("pull_request_opened.json")
            payload["payload"]["pull_request"]["head"]["sha"] = matching_sha
            payload_path = tmp_path / "payload.json"
            payload_path.write_text(json.dumps(payload))

            result = subprocess.run(
                [
                    "python3",
                    str(Path(__file__).parent / "validate_pytorch_checkout.py"),
                    "--payload",
                    str(payload_path),
                    "--pytorch-dir",
                    tmp,
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_checkout_mismatch_dispatch_sha(self) -> None:
        import subprocess

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


class TestHealthReport(unittest.TestCase):
    def test_checks_to_test_results(self) -> None:
        results = checks_to_test_results(
            {
                "a": "success",
                "b": "success",
                "c": "failure",
                "d": "skipped",
            }
        )
        self.assertEqual(results, {"passed": 2, "failed": 1, "skipped": 1, "total": 4})

    def test_build_report_includes_hud_fields(self) -> None:
        report = build_report(
            probe="l2-critical",
            checks={"validate_payload": "success", "in_progress_callback": "success"},
            delivery_id="d-1",
            run_id="99",
            event_type="pull_request",
            pr_number="123",
        )
        self.assertTrue(report["healthy"])
        self.assertEqual(report["conclusion"], "success")
        self.assertEqual(report["test_results"], {"passed": 2, "failed": 0, "skipped": 0, "total": 2})

    def test_healthy_report(self) -> None:
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.json"
            result = subprocess.run(
                [
                    "python3",
                    str(Path(__file__).parent / "write_health_report.py"),
                    "--probe",
                    "l1-critical",
                    "--output",
                    str(out),
                    "--check",
                    "validate_payload=success",
                    "--check",
                    "verify_checkout=success",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0)
            report = json.loads(out.read_text())
            self.assertTrue(report["healthy"])
            self.assertEqual(report["trigger"], "repository_dispatch")

    def test_unhealthy_report_without_strict(self) -> None:
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.json"
            result = subprocess.run(
                [
                    "python3",
                    str(Path(__file__).parent / "write_health_report.py"),
                    "--probe",
                    "l2-critical",
                    "--output",
                    str(out),
                    "--check",
                    "in_progress_callback=failure",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0)
            report = json.loads(out.read_text())
            self.assertFalse(report["healthy"])
            self.assertEqual(report["test_results"]["failed"], 1)

    def test_unhealthy_report_strict(self) -> None:
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.json"
            result = subprocess.run(
                [
                    "python3",
                    str(Path(__file__).parent / "write_health_report.py"),
                    "--probe",
                    "l2-critical",
                    "--output",
                    str(out),
                    "--check",
                    "in_progress_callback=failure",
                    "--strict",
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            report = json.loads(out.read_text())
            self.assertFalse(report["healthy"])


if __name__ == "__main__":
    unittest.main()
