"""Jeeves laptop registry imports are literal, lazy, mirrored and fail closed."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import DOMAINS, list_domains, registry_module


class TestJeevesLiteralRegistryDispatch(unittest.TestCase):
    def test_all_twenty_registry_modules_are_resolvable_without_device_claims(self):
        self.assertEqual(len(DOMAINS), 20)
        self.assertEqual(set(list_domains()), DOMAINS)
        for domain in list_domains():
            with self.subTest(domain=domain):
                module = registry_module(domain)
                self.assertEqual(len(module.STAGES), 8)
                self.assertTrue(module.__name__.endswith("." + domain + ".registry"))

    def test_untrusted_module_names_are_never_imported(self):
        for value in ("", "../bootstrap", "bootstrap.registry", "__class__", "other", None, True, 7):
            with self.subTest(value=value), self.assertRaises(LaptopGateHold):
                registry_module(value)

    def test_registry_imports_are_exact_literal_calls(self):
        root = Path(__file__).resolve().parents[1]
        runner = root / "jeeves/native_fabric/laptop_ops/runner.py"
        mirror = root / "ai/agents/jeeves/native_fabric/laptop_ops/runner.py"
        self.assertEqual(runner.read_bytes(), mirror.read_bytes())
        tree = ast.parse(runner.read_text(encoding="utf-8"))
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr == "import_module"]
        self.assertEqual(len(calls), 20)
        self.assertTrue(all(len(call.args) == 1 and isinstance(call.args[0], ast.Constant)
                            and isinstance(call.args[0].value, str) for call in calls))
        self.assertEqual({call.args[0].value for call in calls}, {
            "skeleton.jeeves.native_fabric.laptop_ops.domains." + domain + ".registry"
            for domain in DOMAINS
        })

    def test_batch_catalog_and_fixtures_match_mirrors(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("catalog.py", "fixtures.py"):
            with self.subTest(name=name):
                canonical = root / "jeeves/native_fabric/laptop_ops/batch" / name
                mirror = root / "ai/agents/jeeves/native_fabric/laptop_ops/batch" / name
                self.assertEqual(canonical.read_bytes(), mirror.read_bytes())


if __name__ == "__main__":
    unittest.main()
