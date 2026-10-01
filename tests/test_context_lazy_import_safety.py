from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTEXT_FACADES = (
    ROOT / "skeleton/context/__init__.py",
    ROOT / "skeleton/ai/runtime/context/__init__.py",
)
ALLOWED_LAZY_MODULES = {
    "skeleton.context.tensor",
    "skeleton.context.dodeca",
    "skeleton.context.oracle",
    "skeleton.context.cockpit",
    "skeleton.context.pipeline",
    "skeleton.context.questionnaire",
}


class ContextLazyImportSafetyTests(unittest.TestCase):
    def test_context_facades_remain_exact_mirrors(self) -> None:
        canonical, mirror = CONTEXT_FACADES
        self.assertEqual(canonical.read_bytes(), mirror.read_bytes())

    def test_lazy_import_targets_are_literal_and_allowlisted(self) -> None:
        for path in CONTEXT_FACADES:
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                targets: set[str] = set()
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    if not isinstance(node.func, ast.Name) or node.func.id != "import_module":
                        continue
                    self.assertEqual(len(node.args), 1)
                    self.assertIsInstance(node.args[0], ast.Constant)
                    self.assertIsInstance(node.args[0].value, str)
                    targets.add(node.args[0].value)
                self.assertEqual(targets, ALLOWED_LAZY_MODULES)

    def test_lazy_export_map_references_only_allowlisted_modules(self) -> None:
        tree = ast.parse(
            CONTEXT_FACADES[0].read_text(encoding="utf-8"),
            filename=str(CONTEXT_FACADES[0]),
        )
        assignment = next(
            node
            for node in tree.body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "_LAZY_EXPORTS"
        )
        assert assignment.value is not None
        exports = ast.literal_eval(assignment.value)
        referenced = {module_name for module_name, _attribute in exports.values()}
        self.assertEqual(referenced, ALLOWED_LAZY_MODULES)


if __name__ == "__main__":
    unittest.main()
