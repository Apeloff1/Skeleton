"""Pure operator preflight before any private task read or native model activation."""
from __future__ import annotations

from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest import mock
import unittest

from skeleton.jeeves.agent.native_operator_preflight import (
    NativeOperatorHold, OperatorAdmission, check_operator_admission,
)
from skeleton.jeeves.agent.native_cli import main as operator_main


def admit(**overrides):
    values = {
        "mode": "agent",
        "task_stdin": True,
        "session": None,
        "request_id": None,
        "source_root": None,
        "signed_source_manifest": None,
        "enable_source_tool": False,
        "max_sources": 4,
        "max_steps": 8,
        "max_model_calls": 8,
        "max_wall_seconds": 180.0,
    }
    values.update(overrides)
    return check_operator_admission(**values)


class TestNativeOperatorPreflight(unittest.TestCase):
    def test_minimal_explicit_agent_no_source_is_allowed(self):
        record = admit()
        self.assertIsInstance(record, OperatorAdmission)
        self.assertEqual(record.mode, "agent")
        self.assertFalse(record.source_material_enabled)
        self.assertFalse(record.enable_source_tool)
        self.assertEqual(record.tool_call_ceiling, 1)

    def test_agent_with_signed_sources_requires_operator_tool_grant(self):
        root = Path("/private/sources")
        manifest = Path("/private/operator/manifest.json")
        with self.assertRaises(NativeOperatorHold):
            admit(source_root=root, signed_source_manifest=manifest)
        granted = admit(
            source_root=root, signed_source_manifest=manifest,
            enable_source_tool=True,
        )
        self.assertTrue(granted.source_material_enabled)
        self.assertTrue(granted.enable_source_tool)
        self.assertEqual(granted.tool_call_ceiling, 3)

    def test_chat_accepts_owner_reopen_and_signed_source(self):
        value = admit(
            mode="chat",
            session="s_approved",
            request_id="r_same",
            source_root=Path("/private/sources"),
            signed_source_manifest=Path("/private/manifest.json"),
        )
        self.assertEqual(value.session, "s_approved")
        self.assertEqual(value.request_id, "r_same")
        self.assertFalse(value.enable_source_tool)

    def test_repl_requires_implicit_line_reader_not_task_stdin(self):
        value = admit(mode="repl", task_stdin=False, session="s_prior")
        self.assertEqual(value.mode, "repl")
        self.assertEqual(value.session, "s_prior")
        with self.assertRaises(NativeOperatorHold):
            admit(mode="repl", task_stdin=True)

    def test_repl_cannot_borrow_request_id(self):
        with self.assertRaises(NativeOperatorHold):
            admit(mode="repl", task_stdin=False, request_id="r_reuse")

    def test_agent_cannot_borrow_chat_session(self):
        with self.assertRaises(NativeOperatorHold):
            admit(session="s_existing")
        with self.assertRaises(NativeOperatorHold):
            admit(request_id="r_existing")

    def test_missing_stdin_for_one_shot_refused(self):
        with self.assertRaises(NativeOperatorHold):
            admit(task_stdin=False)
        with self.assertRaises(NativeOperatorHold):
            admit(mode="chat", task_stdin=False)

    def test_unrecognized_mode_refused(self):
        for mode in ("hosted", "shell", "remote", "", "AGENT", None):
            with self.subTest(mode=mode), self.assertRaises(NativeOperatorHold):
                admit(mode=mode)

    def test_invalid_boolean_flags_refused(self):
        for flag in ("yes", 1, None):
            with self.subTest(flag=flag), self.assertRaises(NativeOperatorHold):
                admit(task_stdin=flag)
            with self.subTest(flag=flag), self.assertRaises(NativeOperatorHold):
                admit(enable_source_tool=flag)

    def test_unpaired_signed_source_paths_refused(self):
        with self.assertRaises(NativeOperatorHold):
            admit(source_root=Path("/private/source"))
        with self.assertRaises(NativeOperatorHold):
            admit(signed_source_manifest=Path("/private/manifest"))

    def test_relative_paths_are_never_preflighted_for_source_access(self):
        with self.assertRaises(NativeOperatorHold):
            admit(
                source_root=Path("relative/sources"),
                signed_source_manifest=Path("/private/manifest"),
                enable_source_tool=True,
            )
        with self.assertRaises(NativeOperatorHold):
            admit(
                source_root=Path("/private/sources"),
                signed_source_manifest=Path("relative/manifest"),
                enable_source_tool=True,
            )

    def test_dotdot_in_private_path_refused_without_resolve(self):
        with self.assertRaises(NativeOperatorHold):
            admit(
                source_root=Path("/private/../sensitive"),
                signed_source_manifest=Path("/private/manifest"),
                enable_source_tool=True,
            )

    def test_non_path_objects_refused(self):
        with self.assertRaises(NativeOperatorHold):
            admit(
                source_root="/private/source",
                signed_source_manifest=Path("/private/manifest"),
                enable_source_tool=True,
            )

    def test_source_tool_cannot_be_enabled_for_chat_or_repl(self):
        for mode, stdin in (("chat", True), ("repl", False)):
            with self.subTest(mode=mode), self.assertRaises(NativeOperatorHold):
                admit(
                    mode=mode, task_stdin=stdin,
                    source_root=Path("/private/sources"),
                    signed_source_manifest=Path("/private/manifest"),
                    enable_source_tool=True,
                )

    def test_negative_and_boolean_counts_refused(self):
        for x in (0, -1, 7, True, 1.2):
            with self.subTest(x=x), self.assertRaises(NativeOperatorHold):
                admit(max_sources=x)
        for x in (0, -1, 10001, True, 1.2):
            with self.subTest(x=x), self.assertRaises(NativeOperatorHold):
                admit(max_steps=x)
            with self.subTest(x=x), self.assertRaises(NativeOperatorHold):
                admit(max_model_calls=x)

    def test_nonfinite_and_unbounded_wall_time_refused(self):
        for time in (-1, 0, float("nan"), float("inf"), True, 86401):
            with self.subTest(time=time), self.assertRaises(NativeOperatorHold):
                admit(max_wall_seconds=time)

    def test_public_admission_receipt_discloses_no_paths_or_session(self):
        value = admit(
            source_root=Path("/private/secret/source"),
            signed_source_manifest=Path("/private/secret/manifest"),
            enable_source_tool=True,
        )
        result = value.public_receipt()
        self.assertTrue(result["signed_source_required"])
        self.assertFalse(result["model_rights_verified"])
        self.assertFalse(result["device_qualified"])
        self.assertFalse(result["release_certified"])
        self.assertNotIn("/private", str(result))
        self.assertNotIn("signed_source_manifest", str(result))

    def test_cli_rejects_missing_stdin_before_any_model_activation(self):
        argv = [
            "--model-root", "/private/model",
            "--state-dir", "/private/state",
            "--tenant", "local",
            "--subject", "operator",
            "--mode", "agent",
        ]
        with mock.patch(
            "skeleton.jeeves.agent.native_cli.activate_checked",
            side_effect=AssertionError("MUST NOT ACTIVATE"),
        ) as activate, redirect_stderr(StringIO()) as err:
            self.assertEqual(operator_main(argv), 2)
        activate.assert_not_called()
        self.assertNotIn("MUST NOT ACTIVATE", err.getvalue())

    def test_cli_rejects_source_tool_without_sources_before_activation(self):
        argv = [
            "--model-root", "/private/model",
            "--state-dir", "/private/state",
            "--tenant", "local",
            "--subject", "operator",
            "--mode", "agent",
            "--task-stdin",
            "--enable-source-tool",
        ]
        with mock.patch(
            "skeleton.jeeves.agent.native_cli.activate_checked",
            side_effect=AssertionError("MUST NOT ACTIVATE"),
        ) as activate, redirect_stderr(StringIO()) as err:
            self.assertEqual(operator_main(argv), 2)
        activate.assert_not_called()
        self.assertNotIn("MUST NOT ACTIVATE", err.getvalue())


if __name__ == "__main__":
    unittest.main()
