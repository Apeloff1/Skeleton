"""The operator script must not bypass the real installed GGUF acceptance.

No synthetic result in this file constitutes a native model or device test.
All canonical inference and SQLite effects are replaced by a spy.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest import mock
import json
import unittest

from scripts import run_ai_laptop_native_e2e as harness

BASE = (
    "--model-root", "/private/approved/model",
    "--state-dir", "/private/committed/sqlite",
    "--capacity-root", "/private/slots",
    "--tenant", "local",
    "--subject", "owner",
    "--prompt-stdin",
    "--approve-real-model-test",
)


def attempt(options=BASE, *, result=0, failure=None):
    output, error = StringIO(), StringIO()
    with (
        mock.patch.object(harness, "native_cli", side_effect=failure,
                          return_value=result) as canonical,
        redirect_stdout(output),
        redirect_stderr(error),
    ):
        code = harness.main(list(options))
    return code, output.getvalue(), error.getvalue(), canonical


class RealDeviceHarnessSourceCustodyTests(unittest.TestCase):
    def test_harness_can_only_invoke_real_source_bound_cold_reopen(self):
        code, out, err, native = attempt()
        self.assertEqual(code, 0, err)
        self.assertEqual(out, "")
        self.assertEqual(err, "")
        native.assert_called_once()
        passed = native.call_args.args[0]
        self.assertEqual(passed[:4], [
            "--mode", "cold-reopen", "--approve-real-acceptance", "--prompt-stdin",
        ])
        self.assertEqual(passed.count("--mode"), 1)
        self.assertEqual(passed.count("--approve-real-acceptance"), 1)
        self.assertNotIn("--approve-real-model-test", passed)
        for name, value in (
            ("--model-root", "/private/approved/model"),
            ("--state-dir", "/private/committed/sqlite"),
            ("--capacity-root", "/private/slots"),
            ("--tenant", "local"),
            ("--subject", "owner"),
        ):
            self.assertEqual(passed[passed.index(name) + 1], value)

    def test_operator_cannot_omit_explicit_approval_or_private_stdin(self):
        for missing in ("--approve-real-model-test", "--prompt-stdin"):
            options = list(BASE)
            options.remove(missing)
            with self.subTest(missing=missing):
                code, out, err, native = attempt(options)
                self.assertEqual(code, 2)
                self.assertFalse(out)
                native.assert_not_called()
                self.assertEqual(json.loads(err)["status"], "held")

    def test_unapproved_parallel_mode_or_secret_unknown_arg_denied(self):
        for extra in (
            ("--mode", "once"),
            ("--provider", "remote"),
            ("--unknown", "private-password-123"),
        ):
            with self.subTest(extra=extra):
                code, out, err, native = attempt(BASE + extra)
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                native.assert_not_called()
                self.assertNotIn(extra[-1], err)

    def test_full_native_resource_budget_preserves_operator_intent(self):
        options = BASE + (
            "--context", "4096",
            "--max-new-tokens", "512",
            "--threads", "3",
            "--gpu-layers", "7",
            "--inference-ms", "120000",
            "--capacity-slots", "1",
            "--capacity-budget-bytes", "5000000000",
        )
        code, out, err, native = attempt(options)
        self.assertEqual(code, 0, err)
        passed = native.call_args.args[0]
        for name, value in (
            ("--context", "4096"),
            ("--max-new-tokens", "512"),
            ("--threads", "3"),
            ("--gpu-layers", "7"),
            ("--inference-ms", "120000"),
            ("--capacity-slots", "1"),
            ("--capacity-budget-bytes", "5000000000"),
        ):
            self.assertEqual(passed[passed.index(name) + 1], value)

    def test_no_duplicate_private_stdin_read_or_prompt_normalization(self):
        class Unreadable:
            @property
            def buffer(self):
                raise AssertionError("only canonical native CLI may read stdin")

        with mock.patch.object(harness.sys, "stdin", Unreadable()):
            code, _, err, native = attempt()
        self.assertEqual(code, 0, err)
        native.assert_called_once()

    def test_falsey_untyped_or_failed_native_results_cannot_promote(self):
        for result in (None, False, True, "", 1, 2, -1):
            with self.subTest(result=repr(result)):
                code, out, err, native = attempt(result=result)
                self.assertEqual(code, 2)
                self.assertFalse(out)
                native.assert_called_once()

    def test_native_exception_never_discloses_prompt_path_or_stack(self):
        code, out, err, native = attempt(
            failure=RuntimeError("private /home/owner/model and prompt"),
        )
        self.assertEqual(code, 2)
        self.assertFalse(out)
        self.assertEqual(json.loads(err), {
            "status": "held", "error_class": "RuntimeError",
        })
        self.assertNotIn("/home/owner", err)

    def test_wrapper_does_not_publish_legacy_success_or_release_claim(self):
        code, out, err, native = attempt()
        self.assertEqual(code, 0, err)
        self.assertEqual(out, "")
        self.assertNotIn("release_certified", out)
        native.assert_called_once()


if __name__ == "__main__":
    unittest.main()
