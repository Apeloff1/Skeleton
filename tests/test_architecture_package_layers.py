from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_architecture_package_layers",
    ROOT / "scripts" / "check_architecture_package_layers.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PythonPackageLayerTests(unittest.TestCase):
    def test_current_layer_manifest_is_valid(self) -> None:
        result = MODULE.validate(ROOT)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["layer_count"], 5)
        self.assertEqual(result["masterplan_bindings"], ["VOL-052", "VOL-053"])

    def _fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="python-layers-"))
        self.addCleanup(lambda: shutil.rmtree(temp, ignore_errors=True))
        for relative in (
            "machine/python_package_layers.json",
            "machine/ai_master_plan.json",
            "skeleton/kernel",
            "skeleton/contracts",
            "skeleton/providers",
            "skeleton/context",
            "skeleton/persistence",
            "skeleton/retrieval",
            "skeleton/memory",
            "skeleton/intelligence",
            "skeleton/frontier",
            "skeleton/skills",
            "skeleton/agents",
            "skeleton/jeeves",
            "skeleton/forge",
            "skeleton/pipelines",
            "skeleton/automation",
            "skeleton/api",
            "skeleton/deploy",
            "skeleton/__main__.py",
        ):
            src = ROOT / relative
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
        return temp

    def test_rejects_upward_import(self) -> None:
        root = self._fixture()
        target = root / "skeleton/kernel/_p2_upward_probe.py"
        target.write_text("from skeleton.api import routes\n", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.PackageLayerError, "upward import"):
            MODULE.validate(root)

    def test_rejects_path_hack(self) -> None:
        root = self._fixture()
        target = root / "skeleton/context/_p2_path_probe.py"
        target.write_text("import sys\nsys.path.append('/tmp')\n", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.PackageLayerError, "sys.path/PYTHONPATH"):
            MODULE.validate(root)

    def test_longest_path_override_classifies_composition_module(self) -> None:
        result = MODULE.validate(ROOT)
        self.assertEqual(result["status"], "valid")
        manifest = json.loads(
            (ROOT / "machine/python_package_layers.json").read_text(encoding="utf-8")
        )
        l3 = next(layer for layer in manifest["layers"] if layer["id"] == "PY-L3")
        self.assertIn("skeleton/context/pipeline.py", l3["paths"])

    def test_rejects_layer_allowing_higher_layer(self) -> None:
        root = self._fixture()
        path = root / "machine/python_package_layers.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["layers"][0]["allowed_layer_ids"].append("PY-L4")
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.PackageLayerError, "allows upward dependencies"):
            MODULE.validate(root)

    def test_rejects_narrowed_masterplan_gap(self) -> None:
        root = self._fixture()
        path = root / "machine/python_package_layers.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["masterplan_bindings"][0]["required_gap_texts"].pop()
        path.write_text(json.dumps(data), encoding="utf-8")
        master_path = root / "machine/ai_master_plan.json"
        master = json.loads(master_path.read_text(encoding="utf-8"))
        volume = next(v for v in master["volumes"] if v["key"] == "VOL-052")
        volume["gaps"].append("unexpected future gap")
        master_path.write_text(json.dumps(master), encoding="utf-8")
        # Existing bound gaps still validate, but the manifest may not claim a different title/ref.
        data = json.loads(path.read_text(encoding="utf-8"))
        data["masterplan_bindings"][0]["title"] = "Wrong title"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.PackageLayerError, "title drift"):
            MODULE.validate(root)


if __name__ == "__main__":
    unittest.main()
