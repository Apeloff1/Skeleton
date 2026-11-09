from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_p2_documentation",
    ROOT / "scripts" / "check_p2_documentation.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class P2DocumentationTests(unittest.TestCase):
    def test_current_generated_documentation_is_clean(self) -> None:
        result = MODULE.validate(ROOT)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["masterplan_binding_count"], 2)
        self.assertEqual(result["generated_file_count"], 1)

    def _fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="p2-docs-"))
        self.addCleanup(lambda: shutil.rmtree(temp, ignore_errors=True))
        for relative in (
            "machine/generated_documentation.json",
            "machine/ai_master_plan.json",
            "machine/ai_p2_execution_map.json",
            "machine/ai_p2_task_backlog.json",
            "scripts/generate_p2_documentation.py",
            "docs/generated/P2_MACHINE_AUTHORITY.md",
        ):
            src = ROOT / relative
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return temp

    def test_rejects_manual_root_overlapping_generated_root(self) -> None:
        root = self._fixture()
        target = root / "machine/generated_documentation.json"
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload["boundary_policy"]["manual_roots"].append("docs/generated/manual")
        target.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.DocumentationControlError,
            "manual/generated documentation roots overlap",
        ):
            MODULE.validate(root)

    def test_rejects_duplicate_manual_roots(self) -> None:
        root = self._fixture()
        target = root / "machine/generated_documentation.json"
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload["boundary_policy"]["manual_roots"].append(
            payload["boundary_policy"]["manual_roots"][0]
        )
        target.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.DocumentationControlError,
            "manual_roots must be unique",
        ):
            MODULE.validate(root)

    def test_rejects_generated_output_symlink(self) -> None:
        root = self._fixture()
        target = root / "docs/generated/P2_MACHINE_AUTHORITY.md"
        outside = root / "outside.md"
        outside.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
        target.unlink()
        try:
            target.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are unavailable on this platform")
        with self.assertRaisesRegex(
            MODULE.DocumentationControlError,
            "generated output must not be a symlink|regeneration cleanliness failed",
        ):
            MODULE.validate(root)

    def test_rejects_manual_generated_edit(self) -> None:
        root = self._fixture()
        target = root / "docs/generated/P2_MACHINE_AUTHORITY.md"
        target.write_text(
            target.read_text(encoding="utf-8") + "\nmanual divergence\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            MODULE.DocumentationControlError,
            "regeneration cleanliness failed",
        ):
            MODULE.validate(root)

    def test_rejects_stale_source_projection(self) -> None:
        root = self._fixture()
        target = root / "machine/ai_p2_task_backlog.json"
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload["status"] = "mutated-test-source"
        target.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.DocumentationControlError,
            "regeneration cleanliness failed",
        ):
            MODULE.validate(root)

    def test_rejects_generated_output_outside_boundary(self) -> None:
        root = self._fixture()
        target = root / "machine/generated_documentation.json"
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload["generated_files"][0]["output"] = "docs/P2_MACHINE_AUTHORITY.md"
        target.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.DocumentationControlError,
            "escapes generated root",
        ):
            MODULE.validate(root)

    def test_rejects_undeclared_generated_file(self) -> None:
        root = self._fixture()
        extra = root / "docs/generated/UNDECLARED.md"
        extra.write_text("# stray generated output\n", encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.DocumentationControlError,
            "inventory drift",
        ):
            MODULE.validate(root)


if __name__ == "__main__":
    unittest.main()
