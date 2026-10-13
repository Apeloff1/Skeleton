"""Bounded static capability, context, graph and duplicate regressions."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from skeleton.ai.game_builder.jeeves_appwide_fabric import (
    AppwideInventory, JeevesAppwideError, JeevesAppwideRuntime,
)
from skeleton.ai.game_builder.jeeves_capability_intelligence import (
    JeevesStaticIntelligence, MAX_PATHS,
)


EXAMPLE = """from math import sqrt

class Calculator:
    def compute(self, value):
        return sqrt(value)

def score(data, factor=3):
    count = 0
    for entry in data:
        if entry > 0:
            count += entry * factor
        elif entry < 0:
            count -= abs(entry)
        else:
            count += 1
    if count > 100:
        return count / 2
    if count > 50:
        return count - 5
    if count > 10:
        return count + 5
    if count % 2:
        return count ** 2
    return count
"""


class CapabilityIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base = "skeleton/ai/game_builder/"
        (self.root / self.base).mkdir(parents=True)
        self.put("math_tools.py", EXAMPLE)
        self.put("math_copy.py", EXAMPLE)
        self.put("math_variant.py", EXAMPLE.replace("Calculator", "MathEngine")
                 .replace("data", "values").replace("score", "ranking"))
        self.put("consumer.py",
                 "from skeleton.ai.game_builder.math_tools import score\n"
                 "def run():\n    return score([1, 2, 3])\n")
        self.put("invalid.py", "def ???\n")
        self.put("screen.tsx",
                 'import { Button } from "./widgets";\n'
                 "export function ScorePanel() {return <div onClick={() => {}} />;}\n")
        self.put("widgets.ts",
                 "export const Button = 1;\nexport class Editor {}\n")
        self.put("private_token.py", "DO_NOT_LEAK_SUPERSECRET\n")
        self.inventory = AppwideInventory(self.root)
        self.inventory.scan()
        self.intel = JeevesStaticIntelligence(self.inventory)
        self.runtime = JeevesAppwideRuntime(self.inventory)

    def put(self, suffix, text):
        path = self.root / self.base / suffix
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return self.base + suffix

    def paths(self, *names):
        return [self.base + n for n in names]

    def test_static_contracts_are_read_only_and_runtime_not_inferred(self):
        page = self.intel.contracts(self.paths("math_tools.py", "screen.tsx"))
        self.assertEqual(page["inspected_files"], 2)
        self.assertTrue(page["static_discovery_not_execution"])
        python = next(d for d in page["documents"] if d["language"] == ".py")
        self.assertEqual(python["status"], "parsed")
        self.assertIn("math.sqrt", python["static_imports"])
        self.assertIn("score", [d["name"] for d in python["declared_symbols"]])
        self.assertIn("compute", python["declared_symbols"][0]["methods"])
        self.assertFalse(python["callable_by_jeeves"])
        tsx = next(d for d in page["documents"] if d["language"] == ".tsx")
        self.assertEqual(tsx["status"], "heuristic_unverified")
        self.assertEqual(tsx["ui_event_handler_mentions"], 1)
        self.assertIn("ScorePanel", [d["name"] for d in tsx["declared_symbols"]])
        self.assertNotIn("DO_NOT_LEAK_SUPERSECRET", str(page))

    def test_registered_jeeves_actions_call_real_static_adapter(self):
        actions = {a["name"] for a in self.runtime.catalog()["registered_adapters"]}
        self.assertTrue({"ai.contracts", "ai.context", "ai.impact", "ai.duplicates"} <= actions)
        request = {"paths": self.paths("math_tools.py", "consumer.py")}
        receipt = self.runtime.invoke("ai.contracts", request)
        self.assertEqual(receipt["result"]["inspected_files"], 2)
        self.assertEqual(receipt["action"], "ai.contracts")
        self.assertFalse(receipt["operator_authorized"])
        self.assertEqual(len(receipt["digest"]), 64)

    def test_selected_dependency_graph_never_misstates_complete_coverage(self):
        graph = self.runtime.invoke("ai.impact", {
            "paths": self.paths("consumer.py", "math_tools.py"),
            "changed": self.base + "math_tools.py",
        })["result"]
        self.assertEqual(graph["direct_selected_dependents"],
                         [self.base + "consumer.py"])
        self.assertFalse(graph["graph_complete"])
        self.assertFalse(graph["refactor_safe_to_apply"])
        self.assertGreater(graph["unexamined_repository_files"], 0)

    def test_metadata_context_budget_is_stable_and_contains_no_source_body(self):
        request = {"paths": self.paths("math_tools.py", "screen.tsx", "consumer.py"),
                   "query": "math score", "budget_chars": 1200, "limit": 2}
        one = self.runtime.invoke("ai.context", request)["result"]
        two = self.runtime.invoke("ai.context", request)["result"]
        self.assertEqual(one, two)
        self.assertLessEqual(one["used_metadata_chars"], 1200)
        self.assertLessEqual(len(one["selected"]), 2)
        self.assertEqual(one["selected"][0]["path"], self.base + "math_tools.py")
        self.assertTrue(one["character_budget_is_not_token_budget"])
        self.assertNotIn("return count", str(one))
        self.assertNotIn("DO_NOT_LEAK_SUPERSECRET", str(one))

    def test_exact_duplicate_hash_and_review_only_near_duplicate(self):
        page = self.intel.duplicates(self.paths("math_tools.py", "math_copy.py",
                                                "math_variant.py", "consumer.py"))
        exact_paths = [item["paths"] for item in page["exact_groups"]]
        self.assertIn(self.paths("math_copy.py", "math_tools.py"), exact_paths)
        self.assertFalse(page["no_files_deleted"] is False)
        self.assertFalse(page["comparison_complete_for_entire_repo"])
        self.assertTrue(any(
            {p["left"], p["right"]} ==
            set(self.paths("math_variant.py", "math_tools.py"))
            for p in page["near_python_candidates"]
        ), page["near_python_candidates"])

    def test_private_scanned_paths_and_symlink_swaps_fail_closed(self):
        with self.assertRaises(JeevesAppwideError):
            self.intel.contracts(self.paths("private_token.py"))
        link = self.root / self.base / "math_tools.py"
        link.unlink()
        try:
            link.symlink_to(self.root / self.base / "consumer.py")
        except OSError:
            self.skipTest("symlinks not supported on this filesystem")
        with self.assertRaises(JeevesAppwideError):
            self.intel.contracts(self.paths("math_tools.py"))

    def test_stale_identity_rejected_even_on_equal_byte_length(self):
        path = self.base + "math_tools.py"
        one = self.intel.contracts([path])
        original = self.root / path
        original.write_text(EXAMPLE.replace("sqrt", "exp "), encoding="utf-8")
        # Even if inode/length/snapshot did not change, exact source digest pins.
        with self.assertRaises(JeevesAppwideError):
            self.intel.contracts([path], expected_sources={
                path: one["documents"][0]["source_sha256"]})

    def test_syntax_error_cannot_masquerade_as_export(self):
        page = self.intel.contracts(self.paths("invalid.py"))
        self.assertEqual(page["documents"][0]["status"], "parse_failed")
        self.assertEqual(page["documents"][0]["declared_symbols"], [])

    def test_rejects_unbounded_sets_bad_queries_and_forged_snapshot(self):
        many = [self.put(f"code_{i}.py", "def run():\n    return 1\n")
                for i in range(MAX_PATHS + 1)]
        self.inventory.scan()
        with self.assertRaises(JeevesAppwideError):
            self.intel.contracts(many)
        with self.assertRaises(JeevesAppwideError):
            self.intel.contracts(self.paths("math_tools.py", "math_tools.py"))
        with self.assertRaises(JeevesAppwideError):
            self.intel.context(self.paths("math_tools.py"), query="x",
                               budget_chars=200000)
        with self.assertRaises(JeevesAppwideError):
            self.intel.contracts(self.paths("math_tools.py"),
                                 expected_snapshot="0" * 64)
        with self.assertRaises(JeevesAppwideError):
            self.intel.duplicates(self.paths("math_tools.py"), threshold=0.1)

    def test_no_unknown_action_or_automatic_code_execution(self):
        with self.assertRaises(JeevesAppwideError):
            self.runtime.invoke("ai.eval", {"code": "open('/etc/passwd').read()"})
        with self.assertRaises(JeevesAppwideError):
            self.runtime.invoke("ai.contracts", {"paths": ["../../secrets.py"]})
        self.assertEqual((self.root / self.base / "math_tools.py").read_text(), EXAMPLE)


if __name__ == "__main__":
    unittest.main()
