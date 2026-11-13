"""Regression for exact literal-only operational dispatch without eager package imports."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MEASURE = ROOT / "skeleton/ai/runtime/operational_ai/agent_fabric/assurance/measurements"
DOMAINS = ("context", "deployment", "evaluation", "learning", "model",
           "persistence", "planning", "queue", "retrieval", "security",
           "tooling", "transport")
FILES = [MEASURE / "__init__.py"] + [
    MEASURE / name / "__init__.py" for name in DOMAINS
] + [
    ROOT / "skeleton/ai/runtime/operational_ai/reliability_fabric/engine.py",
    ROOT / "skeleton/ai/runtime/operational_ai/trust_gates/engine.py",
    ROOT / "skeleton/perf_profiler/_stats.py",
]


class LiteralOperationalDispatchTests(unittest.TestCase):
    def test_all_repaired_sources_have_no_dynamic_import_calls(self):
        for path in FILES:
            with self.subTest(path=str(path.relative_to(ROOT))):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    func = node.func
                    self.assertFalse(
                        isinstance(func, ast.Name) and func.id in {"import_module", "__import__"}
                        or isinstance(func, ast.Attribute) and func.attr in {"import_module", "__import__"},
                        str(path),
                    )

    def test_measurements_preserve_lazy_literal_domain_dispatch(self):
        for path in FILES[:13]:
            with self.subTest(path=str(path.relative_to(ROOT))):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                dispatch = [node for node in ast.walk(tree)
                            if isinstance(node, ast.ImportFrom) and node.level == 1]
                self.assertEqual(len(dispatch), 12)
                self.assertTrue(all(len(node.names) == 1 for node in dispatch))

    def test_measurement_runtime_and_rejected_names(self):
        from skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements import measure
        result = measure("evaluation", "accuracy", {"correct": 3, "total": 4})
        self.assertEqual(result["value"], 0.75)
        with self.assertRaises(ValueError):
            measure("evaluation", "__import__", {})
        with self.assertRaises(ValueError):
            measure([], "accuracy", {})
        with self.assertRaises(ValueError):
            measure("evaluation", [], {})

    def test_reliability_and_trust_reject_unknown_names_before_dispatch(self):
        from skeleton.ai.runtime.operational_ai.reliability_fabric.engine import validate as reliability
        from skeleton.ai.runtime.operational_ai.trust_gates.engine import validate as trust
        with self.assertRaises(Exception):
            reliability("not_a_domain", {})
        with self.assertRaises(Exception):
            trust("not_a_gate", {})


if __name__ == "__main__":
    unittest.main()
