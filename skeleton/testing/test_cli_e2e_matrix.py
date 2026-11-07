"""Table-driven regression matrix for ``skeleton dev`` commands.

Each row pins (argv -> kind, ok, exit code, required keys). Rows are run twice
to assert the verdict fingerprint and gate list are deterministic.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _cli_e2e_support import run_inprocess  # noqa: E402
from skeleton.developer.cli import dev_exit_code  # noqa: E402

KNOBS_LOW = json.dumps({"gravity": -99999})
KNOBS_HIGH = json.dumps({"gravity": 99999})
KNOBS_UNKNOWN = json.dumps({"no_such_knob": 1})

# (argv, kind, expected ok (None = no ok key), expected exit, required keys)
MATRIX = [
    (["doctor", "--json"], "stu-tools-doctor-report", None, 0, {"weakest", "recommendations", "snapshot"}),
    (["doctor", "--gates"], "stu-tools-doctor-gates", 1, 0, {"verdict", "report"}),
    (["doctor", "--gates", "--json"], "stu-tools-doctor-gates", 1, 0, {"verdict", "report"}),
    (["cockpit", "--json"], "stu-tools-cockpit-report", None, 0, {"weakest", "retune", "snapshot"}),
    (["cockpit", "--gates"], "stu-tools-cockpit-gates", 1, 0, {"applied_knobs", "verdict"}),
    (["cockpit", "--gates", "--knobs", KNOBS_UNKNOWN], "stu-tools-cockpit-gates", 1, 0, {"verdict"}),
    (["cockpit", "--retune"], "stu-tools-cockpit-gates", 1, 0, {"verdict"}),
    (["cockpit", "--retune", "--knobs", KNOBS_HIGH], "stu-tools-cockpit-gates", 1, 0, {"verdict"}),
    (["cockpit", "--retune", "--knobs", KNOBS_LOW], "stu-tools-cockpit-gates", 1, 0, {"verdict"}),
    (["bridge"], "stu-tools-bridge-gates", 1, 0, {"plan", "applied_knobs"}),
    (["bridge", "--json"], "stu-tools-bridge-gates", 1, 0, {"plan"}),
    (["bridge", "--apply"], "stu-tools-bridge-gates", 1, 0, {"plan"}),
    (["regen"], "stu-tools-regen-gates", 0, 1, {"result", "after_inventory"}),
    (["regen", "--json"], "stu-tools-regen-gates", 0, 1, {"result"}),
    (["regen", "--allow-empty"], "stu-tools-regen-gates", 1, 0, {"result"}),
    (["regen", "--apply", "--allow-empty"], "stu-tools-regen-gates", 1, 0, {"result"}),
    (["health", "--gates", "--json"], "stu-tools-health-gates", 1, 0, {"report"}),
    (["health", "--deepen", "--json"], "stu-tools-health-report", None, 0, set()),
    (["visualize", "--blueprint", "m", "--gates"], "stu-tools-visualize-gates", 1, 0, {"report"}),
    (["visualize", "--blueprint", "m", "--deepen"], "stu-tools-visualize-report", None, 0, set()),
    (["visualize", "--blueprint", "m", "--deepen", "--compact"], "stu-tools-visualize-report", None, 0, set()),
    (["stu-tools", "--json"], "stu-tools-pipeline", 1, 0, {"sections", "gate_table", "paths"}),
    (["stu-tools", "--paths", "health", "--json"], "stu-tools-pipeline", 1, 0, {"sections"}),
    (["stu-tools", "--paths", "visualize", "--json"], "stu-tools-pipeline", 1, 0, {"sections"}),
    (["stu-tools", "--paths", "doctor", "--json"], "stu-tools-pipeline", 1, 0, {"sections"}),
    (["stu-tools", "--paths", "regen", "--json"], "stu-tools-pipeline", 1, 0, {"sections"}),
    (["stu-tools", "--paths", "health,doctor", "--json"], "stu-tools-pipeline", 1, 0, {"sections"}),
    (["stu-tools", "--paths", "bogus", "--json"], "stu-tools-pipeline", 0, 1, {"sections"}),
    # An empty --paths falls back to the default four paths (current contract).
    (["stu-tools", "--paths", "", "--json"], "stu-tools-pipeline", 1, 0, {"sections"}),
    (["stu-tools", "--ci-bundle", "--json"], "stu-tools-ci-bundle", 1, 0, {"coverage", "merge_card", "bridge", "cockpit", "pipeline"}),
    (["stu-tools", "--ci-bundle", "--paths", "doctor", "--json"], "stu-tools-ci-bundle", None, None, {"coverage", "merge_card"}),
]


def _strip_volatile(obj):
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items() if k not in ("duration_ms",)}
    if isinstance(obj, list):
        return [_strip_volatile(v) for v in obj]
    return obj


class MatrixTests(unittest.TestCase):
    def _run(self, argv):
        result, _, err, code = run_inprocess(argv)
        self.assertIsNone(code, f"{argv}: {err}")
        return result

    def test_matrix(self):
        for argv, kind, ok, exit_code, keys in MATRIX:
            with self.subTest(argv=argv):
                result = self._run(argv)
                self.assertEqual(result["kind"], kind)
                if ok is None and exit_code is not None:
                    self.assertNotIn("ok", result)
                elif ok is not None:
                    self.assertEqual(result["ok"], ok)
                if exit_code is not None:
                    self.assertEqual(dev_exit_code(result), exit_code)
                missing = keys - set(result)
                self.assertFalse(missing, f"missing keys {missing}")
                self.assertEqual(result.get("stored_prose", 0), 0)

    def test_gate_verdicts_are_deterministic(self):
        for argv, _kind, ok, _exit, _keys in MATRIX:
            if ok is None:
                continue
            with self.subTest(argv=argv):
                a = self._run(argv)["verdict"]
                b = self._run(argv)["verdict"]
                self.assertEqual(a["fingerprint"], b["fingerprint"])
                self.assertEqual(_strip_volatile(a["gates"]), _strip_volatile(b["gates"]))
                self.assertEqual(a["blocking"], b["blocking"])

    def test_banner_agrees_with_ok(self):
        for argv, _kind, ok, _exit, _keys in MATRIX:
            if ok is None:
                continue
            with self.subTest(argv=argv):
                result = self._run(argv)
                if result["ok"]:
                    self.assertEqual(result["verdict"]["blocking"], [])
                    self.assertIn("PASSED", result["banner"])
                else:
                    self.assertTrue(result["verdict"]["blocking"])
                    self.assertIn("FAIL CLOSED", result["banner"])
                    for name in result["verdict"]["blocking"]:
                        self.assertIn(name, result["banner"])

    def test_blocking_gates_are_sev1_or_sev2(self):
        for argv, _kind, ok, _exit, _keys in MATRIX:
            if ok is None:
                continue
            with self.subTest(argv=argv):
                verdict = self._run(argv)["verdict"]
                by_name = {g["name"]: g for g in verdict["gates"]}
                for name in verdict["blocking"]:
                    if name in by_name:
                        self.assertIn(by_name[name]["severity"], ("sev1", "sev2"))
                        self.assertTrue(by_name[name]["blocks"])


if __name__ == "__main__":
    unittest.main()
