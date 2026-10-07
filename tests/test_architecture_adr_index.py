from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_architecture_adr_index",
    ROOT / "scripts" / "check_architecture_adr_index.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ArchitectureADRIndexTests(unittest.TestCase):
    def test_current_index_is_valid(self) -> None:
        result = MODULE.validate(ROOT)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["masterplan_binding"], "VOL-058")
        self.assertGreaterEqual(result["record_count"], 1)

    def _fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="adr-index-"))
        self.addCleanup(lambda: shutil.rmtree(temp, ignore_errors=True))
        for relative in (
            "machine/adr_index.json",
            "machine/ai_master_plan.json",
            "docs/adr",
        ):
            src = ROOT / relative
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
        return temp

    def test_rejects_unindexed_adr_document(self) -> None:
        root = self._fixture()
        (root / "docs/adr/ADR-9999-unindexed.md").write_text("# unindexed\n", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ADRIndexError, "coverage drift"):
            MODULE.validate(root)

    def test_rejects_governed_path_without_active_adr(self) -> None:
        root = self._fixture()
        path = root / "machine/adr_index.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["records"][0]["impacted_paths"].remove("machine/python_package_layers.json")
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ADRIndexError, "lack active ADR coverage"):
            MODULE.validate(root)

    def test_rejects_unknown_masterplan_reference(self) -> None:
        root = self._fixture()
        path = root / "machine/adr_index.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["records"][0]["masterplan_refs"].append("VOL-999")
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ADRIndexError, "unknown masterplan volumes"):
            MODULE.validate(root)

    def test_rejects_stale_masterplan_gap_binding(self) -> None:
        root = self._fixture()
        path = root / "machine/adr_index.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["masterplan_binding"]["required_gap_texts"][0] = "not a real gap"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ADRIndexError, "masterplan gap drift"):
            MODULE.validate(root)


if __name__ == "__main__":
    unittest.main()
