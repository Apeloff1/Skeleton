"""End-to-end regression suite for ``skeleton dev`` (in-process).

Drives ``skeleton.developer.cli.run_dev_cli`` exactly as the console script
does and asserts on both the returned mapping and what is printed, covering
help, routing, ``--json`` contracts, fail-closed gates, ``--ci-bundle`` and the
snapshot / restore / snapshots persistence commands.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _cli_e2e_support import (  # noqa: E402
    FAIL_PREFIX,
    GATE_KEYS,
    PASS_BANNER,
    first_json,
    run_inprocess,
)
from skeleton.developer.cli import dev_exit_code, dev_help_text  # noqa: E402


class _Base(unittest.TestCase):
    def run_cli(self, *argv):
        result, out, err, code = run_inprocess(list(argv))
        self.assertIsNone(code, f"unexpected SystemExit({code}) for {argv}: {err}")
        return result, out, err

    def assert_gate_shape(self, result, kind):
        self.assertIsInstance(result, dict)
        self.assertTrue(GATE_KEYS.issubset(result), sorted(result))
        self.assertEqual(result["kind"], kind)
        verdict = result["verdict"]
        for key in ("banner", "blocking", "failed", "passed", "gates", "fingerprint", "ok"):
            self.assertIn(key, verdict)
        self.assertEqual(verdict["passed"] + verdict["failed"], len(verdict["gates"]))
        self.assertEqual(result["stored_prose"], 0)
        for gate in verdict["gates"]:
            self.assertIn(gate["severity"], ("info", "sev1", "sev2"))
            self.assertEqual(gate["passed"], gate["status"] == "passed")
            if gate["blocks"]:
                self.assertFalse(gate["passed"])

    def assert_passed(self, result):
        self.assertEqual(result["ok"], 1)
        self.assertEqual(result["banner"], PASS_BANNER)
        self.assertEqual(result["verdict"]["blocking"], [])
        self.assertEqual(dev_exit_code(result), 0)

    def assert_failed_closed(self, result, gate_name):
        self.assertEqual(result["ok"], 0)
        self.assertTrue(result["banner"].startswith(FAIL_PREFIX), result["banner"])
        self.assertIn(gate_name, result["verdict"]["blocking"])
        self.assertEqual(dev_exit_code(result), 1)


class HelpAndRoutingTests(_Base):
    def test_no_args_shows_help(self):
        result, out, _ = self.run_cli()
        self.assertEqual(result, {"status": "help_shown"})
        self.assertEqual(out.strip(), dev_help_text())

    def test_help_aliases_are_equivalent(self):
        outs = {flag: self.run_cli(flag)[1] for flag in ("-h", "--help", "help")}
        self.assertEqual(len(set(outs.values())), 1)

    def test_help_lists_every_registered_command(self):
        from skeleton.developer.commands import _dev_registry

        text = dev_help_text()
        for name in _dev_registry.commands:
            self.assertIn(f"skeleton dev {name}", text, name)

    def test_help_documents_json_and_ci_bundle(self):
        text = dev_help_text()
        self.assertIn("--ci-bundle", text)
        self.assertGreaterEqual(text.count("--json"), 4)
        for cmd in ("snapshot", "restore", "snapshots"):
            self.assertIn(f"skeleton dev {cmd}", text)

    def test_unknown_command_returns_error_on_stderr(self):
        result, out, err = self.run_cli("definitely-not-a-command")
        self.assertEqual(result, {"error": "Unknown dev command: definitely-not-a-command"})
        self.assertEqual(out, "")
        self.assertIn("Unknown dev command", err)
        self.assertEqual(dev_exit_code(result), 1)

    def test_bad_flag_is_argparse_exit_2(self):
        for cmd in ("doctor", "cockpit", "bridge", "regen", "stu-tools", "health", "snapshot"):
            _, _, err, code = run_inprocess([cmd, "--no-such-flag"])
            self.assertEqual(code, 2, cmd)
            self.assertIn("unrecognized arguments", err)

    def test_subcommand_help_exits_zero(self):
        for cmd in ("doctor", "cockpit", "bridge", "regen", "stu-tools", "snapshot", "restore", "snapshots"):
            _, out, _, code = run_inprocess([cmd, "--help"])
            self.assertEqual(code, 0, cmd)
            self.assertIn(f"skeleton dev {cmd}", out)

    def test_validate_requires_path(self):
        result, out, _ = self.run_cli("validate")
        self.assertEqual(result, {"error": "missing_path"})
        self.assertIn("Usage", out)

    def test_validate_missing_path(self):
        result, _, _ = self.run_cli("validate", "/nonexistent/skeleton/xyz")
        self.assertEqual(result, {"error": "path_not_found"})

    def test_docs_known_and_unknown_topics(self):
        for topic in ("overview", "genesis", "forge", "swarm", "api", "testing"):
            result, out, _ = self.run_cli("docs", topic)
            self.assertEqual(result["topic"], topic)
            self.assertNotIn("No documentation found", result["content"])
            self.assertEqual(out.strip(), result["content"])
        result, _, _ = self.run_cli("docs", "bogus")
        self.assertIn("No documentation found for 'bogus'", result["content"])
        self.assertEqual(self.run_cli("docs")[0]["topic"], "overview")

    def test_list_templates(self):
        result, out, _ = self.run_cli("list-templates")
        self.assertIn("minimal-agent", result["templates"])
        self.assertIn("Available templates:", out)


class JsonContractTests(_Base):
    """``--json`` must print exactly the returned mapping as one JSON document."""

    CASES = [
        (("doctor", "--json"), "stu-tools-doctor-report"),
        (("doctor", "--gates", "--json"), "stu-tools-doctor-gates"),
        (("cockpit", "--json"), "stu-tools-cockpit-report"),
        (("cockpit", "--gates", "--json"), "stu-tools-cockpit-gates"),
        (("health", "--deepen", "--json"), "stu-tools-health-report"),
        (("health", "--gates", "--json"), "stu-tools-health-gates"),
        (("stu-tools", "--json"), "stu-tools-pipeline"),
        (("stu-tools", "--ci-bundle", "--json"), "stu-tools-ci-bundle"),
    ]

    def test_json_stdout_round_trips_result(self):
        for argv, kind in self.CASES:
            with self.subTest(argv=argv):
                result, out, _ = self.run_cli(*argv)
                printed = json.loads(out)
                self.assertEqual(printed["kind"], kind)
                self.assertEqual(printed, json.loads(json.dumps(result, default=str)))

    def test_health_plain_json_summary(self):
        result, out, _ = self.run_cli("health", "--json")
        printed = json.loads(out)
        for key in ("overall", "total_subsystems", "phases_booted", "status_breakdown"):
            self.assertIn(key, printed)
        self.assertEqual(printed["total_subsystems"], result["total_subsystems"])
        self.assertEqual(sum(printed["status_breakdown"].values()), printed["total_subsystems"])

    def test_always_json_commands(self):
        for argv in (("bridge",), ("regen",), ("regen", "--allow-empty")):
            with self.subTest(argv=argv):
                result, out, _ = self.run_cli(*argv)
                self.assertEqual(json.loads(out)["kind"], result["kind"])

    def test_non_json_doctor_is_rendered_text(self):
        _, out, _ = self.run_cli("doctor")
        with self.assertRaises(ValueError):
            json.loads(out)
        self.assertTrue(out.strip())

    def test_gates_without_json_prints_banner_then_summary(self):
        for argv in (("doctor", "--gates"), ("visualize", "--blueprint", "e2e", "--gates")):
            with self.subTest(argv=argv):
                result, out, _ = self.run_cli(*argv)
                first_line = out.splitlines()[0]
                self.assertEqual(first_line, result["banner"])
                summary = first_json(out)
                self.assertEqual(summary["ok"], result["ok"])


class GateTests(_Base):
    def test_doctor_gates_pass(self):
        result, _, _ = self.run_cli("doctor", "--gates", "--json")
        self.assert_gate_shape(result, "stu-tools-doctor-gates")
        self.assert_passed(result)

    def test_cockpit_gates_pass_default_knobs(self):
        result, _, _ = self.run_cli("cockpit", "--gates")
        self.assert_gate_shape(result, "stu-tools-cockpit-gates")
        self.assert_passed(result)
        self.assertIn("applied_knobs", result)

    def test_cockpit_retune_implies_gates(self):
        result, _, _ = self.run_cli("cockpit", "--retune", "--knobs", json.dumps({"gravity": 99999}))
        self.assert_gate_shape(result, "stu-tools-cockpit-gates")
        self.assertIn(result["ok"], (0, 1))

    def test_cockpit_rejects_malformed_knobs_json(self):
        # JSONDecodeError is a ValueError, which run_dev_cli maps to an error result.
        result, _, err = self.run_cli("cockpit", "--knobs", "{not json")
        self.assertIn("error", result)
        self.assertTrue(err.strip())
        self.assertEqual(dev_exit_code(result), 1)

    def test_bridge_plan_and_apply(self):
        plan, _, _ = self.run_cli("bridge")
        self.assert_gate_shape(plan, "stu-tools-bridge-gates")
        self.assertIn("plan", plan)
        applied, _, _ = self.run_cli("bridge", "--apply")
        self.assert_gate_shape(applied, "stu-tools-bridge-gates")

    def test_regen_default_fails_closed_on_empty_plan(self):
        result, _, _ = self.run_cli("regen")
        self.assert_gate_shape(result, "stu-tools-regen-gates")
        self.assert_failed_closed(result, "regen.targets_nonempty")

    def test_regen_allow_empty_passes(self):
        result, _, _ = self.run_cli("regen", "--allow-empty")
        self.assert_passed(result)

    def test_regen_artefacts_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "artefacts.json"
            path.write_text(json.dumps({"stubs/ok.gd": "extends Node\n"}), encoding="utf-8")
            result, _, _ = self.run_cli("regen", "--artefacts", str(path), "--allow-empty")
            self.assert_gate_shape(result, "stu-tools-regen-gates")

    def test_regen_missing_artefacts_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            run_inprocess(["regen", "--artefacts", "/nonexistent/artefacts.json"])

    def test_doctor_card_file(self):
        base, _, _ = self.run_cli("doctor", "--json")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "card.json"
            path.write_text(json.dumps({}), encoding="utf-8")
            result, _, _ = self.run_cli("doctor", "--gates", "--json", "--card", str(path))
            self.assert_gate_shape(result, "stu-tools-doctor-gates")
        self.assertEqual(base["kind"], "stu-tools-doctor-report")

    def test_health_gates_pass(self):
        result, _, _ = self.run_cli("health", "--gates", "--json")
        self.assert_gate_shape(result, "stu-tools-health-gates")
        self.assert_passed(result)

    def test_visualize_gates_and_deepen(self):
        gates, _, _ = self.run_cli("visualize", "--blueprint", "e2e", "--gates")
        self.assert_gate_shape(gates, "stu-tools-visualize-gates")
        self.assert_passed(gates)
        deep, _, _ = self.run_cli("visualize", "--blueprint", "e2e", "--deepen")
        self.assertEqual(deep["kind"], "stu-tools-visualize-report")

    def test_visualize_requires_blueprint(self):
        result, _, _ = self.run_cli("visualize")
        self.assertIn("error", result)
        self.assertEqual(dev_exit_code(result), 1)

    def test_visualize_save_writes_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "vis.json"
            result, _, _ = self.run_cli("visualize", "--blueprint", "e2e", "--gates", "--save", str(dest))
            self.assertEqual(result["saved_to"], str(dest))
            self.assertEqual(json.loads(dest.read_text(encoding="utf-8"))["kind"], "stu-tools-visualize-gates")

    def test_visualize_plain_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "vis.txt"
            result, _, _ = self.run_cli("visualize", "--blueprint", "e2e", "--save", str(dest))
            self.assertEqual(result, {"saved_to": str(dest), "blueprint": "e2e"})
            self.assertTrue(dest.read_text(encoding="utf-8"))

    def test_visualize_plain_counts(self):
        result, _, _ = self.run_cli("visualize", "--blueprint", "e2e")
        self.assertEqual(result, {"blueprint": "e2e", "components": 3, "wires": 2})


class StuToolsPipelineTests(_Base):
    def test_default_pipeline_runs_all_paths(self):
        result, _, _ = self.run_cli("stu-tools", "--json")
        self.assert_gate_shape(result, "stu-tools-pipeline")
        self.assertEqual(result["paths"], ["health", "visualize", "doctor", "regen"])
        self.assertEqual(sorted(result["sections"]), ["doctor", "health", "regen", "visualize"])
        self.assert_passed(result)

    def test_single_path(self):
        for path in ("health", "visualize", "doctor", "regen"):
            with self.subTest(path=path):
                result, _, _ = self.run_cli("stu-tools", "--paths", path, "--json")
                self.assertEqual(result["paths"], [path])
                self.assertEqual(list(result["sections"]), [path])

    def test_paths_whitespace_and_empty_items_are_trimmed(self):
        result, _, _ = self.run_cli("stu-tools", "--paths", " health , ,doctor ", "--json")
        self.assertEqual(result["paths"], ["health", "doctor"])

    def test_unknown_path_fails_closed(self):
        result, _, _ = self.run_cli("stu-tools", "--paths", "bogus", "--json")
        self.assert_failed_closed(result, "suite.empty")

    def test_ci_bundle_shape(self):
        result, _, _ = self.run_cli("stu-tools", "--ci-bundle", "--json")
        self.assert_gate_shape(result, "stu-tools-ci-bundle")
        for key in ("pipeline", "cockpit", "bridge", "coverage", "merge_card"):
            self.assertIn(key, result)
        coverage = result["coverage"]
        for key in ("catalog_fp", "gate_count", "paths", "sev1", "sev2"):
            self.assertIn(key, coverage)
        card = result["merge_card"]
        self.assertEqual(card["ok"], result["ok"])
        self.assertEqual(card["catalog_fp"], coverage["catalog_fp"])
        self.assert_passed(result)

    def test_ci_bundle_with_paths(self):
        result, _, _ = self.run_cli("stu-tools", "--ci-bundle", "--paths", "health,doctor", "--json")
        self.assertEqual(result["kind"], "stu-tools-ci-bundle")

    def test_non_json_prints_gate_table_and_summary(self):
        result, out, _ = self.run_cli("stu-tools", "--paths", "health")
        summary = first_json(out[out.index("{\n  \"ok\""):])
        self.assertEqual(summary["ok"], result["ok"])
        self.assertEqual(summary["paths"], ["health"])

    def test_verdict_fingerprint_is_stable(self):
        a, _, _ = self.run_cli("stu-tools", "--paths", "doctor", "--json")
        b, _, _ = self.run_cli("stu-tools", "--paths", "doctor", "--json")
        self.assertEqual(a["verdict"]["fingerprint"], b["verdict"]["fingerprint"])
        self.assertEqual([g["name"] for g in a["verdict"]["gates"]], [g["name"] for g in b["verdict"]["gates"]])


class PersistenceCommandTests(_Base):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_snapshots_empty_root(self):
        result, out, _ = self.run_cli("snapshots", "--root", self.root)
        self.assertEqual(result, {"snapshots": [], "count": 0})
        self.assertIn("No snapshots found", out)

    def test_snapshot_restore_round_trip_with_ingest(self):
        doc = Path(self.root) / "lore.txt"
        doc.write_text("The forge remembers every era. Skeleton memory survives restarts.", encoding="utf-8")
        snap, out, _ = self.run_cli("snapshot", "--root", self.root, "--name", "e2e", "--ingest", str(doc))
        self.assertEqual(snap["action"], "snapshot")
        self.assertEqual(snap["name"], "e2e")
        self.assertGreaterEqual(snap["ingested_chunks"], 1)
        self.assertEqual(set(snap["planes"]), {"rag", "mag", "kag"})
        self.assertGreaterEqual(snap["planes"]["rag"], 1)
        self.assertIn("State snapshot saved", out)

        listed, out, _ = self.run_cli("snapshots", "--root", self.root)
        names = sorted(s["name"] for s in listed["snapshots"])
        self.assertEqual(listed["count"], len(names))
        self.assertTrue(all(n.startswith("e2e-") for n in names), names)
        self.assertIn("snapshot(s):", out)
        for entry in listed["snapshots"]:
            self.assertIsInstance(entry["saved_at"], (int, float))

        restored, _, _ = self.run_cli("restore", "--root", self.root, "--name", "e2e")
        self.assertEqual(restored["action"], "restore")
        self.assertEqual(restored["restored"], snap["planes"])
        self.assertEqual(restored["live"]["rag_docs"], snap["planes"]["rag"])
        self.assertEqual(dev_exit_code(restored), 0)

    def test_snapshot_without_ingest(self):
        snap, _, _ = self.run_cli("snapshot", "--root", self.root, "--name", "bare")
        self.assertEqual(snap["ingested_chunks"], 0)

    def test_snapshots_are_cumulative(self):
        doc = Path(self.root) / "a.txt"
        doc.write_text("first document about forge eras", encoding="utf-8")
        first, _, _ = self.run_cli("snapshot", "--root", self.root, "--name", "cum", "--ingest", str(doc))
        doc2 = Path(self.root) / "b.txt"
        doc2.write_text("second document about cockpit knobs", encoding="utf-8")
        second, _, _ = self.run_cli("snapshot", "--root", self.root, "--name", "cum", "--ingest", str(doc2))
        self.assertGreaterEqual(second["planes"]["rag"], first["planes"]["rag"])

    def test_named_snapshots_are_isolated(self):
        self.run_cli("snapshot", "--root", self.root, "--name", "alpha")
        self.run_cli("snapshot", "--root", self.root, "--name", "beta")
        names = {s["name"].rsplit("-", 1)[0] for s in self.run_cli("snapshots", "--root", self.root)[0]["snapshots"]}
        self.assertEqual(names, {"alpha", "beta"})

    def test_restore_missing_snapshot_is_empty(self):
        # Current contract: a missing name restores nothing rather than erroring.
        restored, _, _ = self.run_cli("restore", "--root", self.root, "--name", "missing")
        self.assertEqual(restored["restored"], {})
        self.assertEqual(restored["live"]["rag_docs"], 0)

    def test_ingest_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            run_inprocess(["snapshot", "--root", self.root, "--ingest", str(Path(self.root) / "nope.txt")])


class ExitCodeTests(unittest.TestCase):
    def test_mapping(self):
        cases = [
            ({"ok": 1}, 0),
            ({"ok": True}, 0),
            ({"ok": 0}, 1),
            ({"ok": False}, 1),
            ({"ok": "yes"}, 1),
            ({"error": "x"}, 1),
            ({"valid": False}, 1),
            ({"passed": False}, 1),
            ({"valid": True, "passed": True}, 0),
            ({}, 0),
            ({"status": "help_shown"}, 0),
            (None, 1),
            ([], 1),
            ("ok", 1),
        ]
        for result, expected in cases:
            with self.subTest(result=result):
                self.assertEqual(dev_exit_code(result), expected)


if __name__ == "__main__":
    unittest.main()
