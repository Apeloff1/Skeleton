"""Unit tests for the shared ``skeleton dev`` console adapter."""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest import mock

from skeleton.developer import cli


def _console(result, printed=""):
    def fake(_argv):
        if printed:
            print(printed)
        return result

    out = io.StringIO()
    with mock.patch.object(cli, "run_dev_cli", side_effect=fake), contextlib.redirect_stdout(out):
        code = cli.run_dev_console([])
    return code, out.getvalue()


class AlreadyPrintedTests(unittest.TestCase):
    def test_exact_json_tail_matches(self):
        r = {"ok": 1, "kind": "k"}
        self.assertTrue(cli._already_printed_as_json(json.dumps(r, indent=2), r))

    def test_banner_then_json_matches(self):
        r = {"ok": 1}
        self.assertTrue(cli._already_printed_as_json("BANNER\n" + json.dumps(r, indent=2) + "\n", r))

    def test_summary_subset_does_not_match(self):
        r = {"ok": 1, "banner": "b", "extra": [1]}
        self.assertFalse(cli._already_printed_as_json(json.dumps({"ok": 1, "banner": "b"}), r))

    def test_plain_text_does_not_match(self):
        self.assertFalse(cli._already_printed_as_json("[Harness] ready\n", {"a": 1}))

    def test_empty_does_not_match(self):
        self.assertFalse(cli._already_printed_as_json("", {"a": 1}))

    def test_default_str_values_normalised(self):
        from pathlib import Path

        r = {"path": Path("/tmp/x")}
        self.assertTrue(cli._already_printed_as_json(json.dumps(r, default=str), r))


class ConsoleTests(unittest.TestCase):
    def test_prints_once_when_command_silent(self):
        code, out = _console({"ok": 1})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"ok": 1})

    def test_skips_when_command_printed_json(self):
        r = {"ok": 0, "kind": "x"}
        code, out = _console(r, json.dumps(r, indent=2))
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out), r)

    def test_help_prints_nothing_extra(self):
        code, out = _console({"status": "help_shown"}, "HELP TEXT")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "HELP TEXT")

    def test_log_lines_then_result(self):
        code, out = _console({"action": "snapshot"}, "[Harness] saved")
        self.assertTrue(out.startswith("[Harness] saved"))
        self.assertEqual(json.loads(out.split("\n", 1)[1]), {"action": "snapshot"})

    def test_non_dict_result_exit_one_no_print(self):
        code, out = _console(None)
        self.assertEqual((code, out), (1, ""))

    def test_stdout_restored_after_exception(self):
        import sys

        before = sys.stdout
        with mock.patch.object(cli, "run_dev_cli", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                cli.run_dev_console([])
        self.assertIs(sys.stdout, before)

    def test_main_delegates(self):
        with mock.patch.object(cli, "run_dev_console", return_value=7) as m:
            self.assertEqual(cli.main(["x"]), 7)
        m.assert_called_once_with(["x"])


if __name__ == "__main__":
    unittest.main()
