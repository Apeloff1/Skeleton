"""Closed literal offline-cognition dispatch regression (no eager imports)."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

from skeleton.ai.runtime.operational_ai.offline_cognition.catalog import FAMILIES
from skeleton.ai.runtime.operational_ai.offline_cognition.core.profiles import _ALLOWED
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import CognitionError
from skeleton.ai.runtime.operational_ai.offline_cognition.core.testing import _MODULE_LOADERS, _module, exercise


class LiteralCognitionDispatchTests(unittest.TestCase):
    def test_exact_closed_family_operation_inventory(self):
        expected = {(family, operation) for family in FAMILIES for operation in _ALLOWED}
        self.assertEqual(len(FAMILIES), 64)
        self.assertEqual(len(_ALLOWED), 20)
        self.assertEqual(set(_MODULE_LOADERS), expected)
        with self.assertRaises(TypeError):
            _MODULE_LOADERS[("forged", "source")] = object()

    def test_imports_are_literal_and_lazy(self):
        path = Path(__file__).resolve().parents[1] / (
            "skeleton/ai/runtime/operational_ai/offline_cognition/core/testing.py"
        )
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"
        ]
        self.assertEqual(len(calls), len(FAMILIES) * len(_ALLOWED))
        for node in calls:
            self.assertIsInstance(node.args[0], ast.Constant)
            self.assertIsInstance(node.args[0].value, str)
            self.assertTrue(node.args[0].value.startswith(".families."))

    def test_unknown_and_malformed_selection_fails_closed(self):
        for family, operation in (
            ("unknown", "source"), ([], "source"), (None, "source"),
            ("tokenizer_bridge", "unknown"), ("tokenizer_bridge", []),
            ("tokenizer_bridge", None),
        ):
            with self.subTest(family=family, operation=operation):
                with self.assertRaises(CognitionError):
                    _module(family, operation)

    def test_representative_real_family_modules(self):
        for family, operation in (
            ("tokenizer_bridge", "source"),
            ("answer_grounding", "evaluate"),
            ("release_hold", "health"),
        ):
            with self.subTest(family=family, operation=operation):
                module = _module(family, operation)
                self.assertEqual(
                    module.__name__,
                    "skeleton.ai.runtime.operational_ai.offline_cognition."
                    f"families.{family}.{operation}",
                )

    def test_positive_and_adversarial_source_exercise(self):
        self.assertTrue(exercise("tokenizer_bridge", "source"))
        self.assertTrue(exercise("tokenizer_bridge", "source", attack=True))


if __name__ == "__main__":
    unittest.main()
