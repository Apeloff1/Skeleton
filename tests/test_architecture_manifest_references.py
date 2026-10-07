from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_architecture_manifest_references",
    ROOT / "scripts" / "check_architecture_manifest_references.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


class ArchitectureManifestReferenceTests(unittest.TestCase):
    def test_current_policy_is_valid(self) -> None:
        result = MODULE.validate(ROOT)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["masterplan_binding"], "VOL-054")
        self.assertGreaterEqual(result["checked_reference_count"], 1)
        self.assertEqual(result["doc_binding_count"], 7)

    def _fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="manifest-refs-"))
        self.addCleanup(lambda: shutil.rmtree(temp, ignore_errors=True))
        policy = json.loads(
            (ROOT / "machine/manifest_reference_policy.json").read_text(encoding="utf-8")
        )
        paths = {
            "machine/manifest_reference_policy.json",
            "machine/ai_master_plan.json",
        }
        for group in policy["reference_groups"]:
            paths.add(group["manifest"])
        for binding in policy["doc_bindings"]:
            paths.add(binding["source"])
            paths.add(binding["doc"])
        # Copy referenced targets as well.
        for group in policy["reference_groups"]:
            manifest = json.loads((ROOT / group["manifest"]).read_text(encoding="utf-8"))
            current = manifest
            for token in group["json_pointer"].split("/")[1:]:
                current = current[token]
            values = list(current.values()) if group["kind"] == "repo_path_map" else [current]
            paths.update(values)
        for relative in sorted(paths):
            src = ROOT / relative
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
        return temp

    def test_rejects_missing_manifest_reference(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_p2_execution_map.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["authority"]["validator"] = "scripts/does-not-exist.py"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ManifestReferenceError, "missing path"):
            MODULE.validate(root)

    def test_rejects_stale_doc_digest(self) -> None:
        root = self._fixture()
        source = root / "machine/python_package_layers.json"
        data = json.loads(source.read_text(encoding="utf-8"))
        data["manifest_version"] = "0.1.1"
        source.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ManifestReferenceError, "current digest marker"):
            MODULE.validate(root)

    def test_rejects_stale_masterplan_gap_binding(self) -> None:
        root = self._fixture()
        path = root / "machine/manifest_reference_policy.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["masterplan_binding"]["required_gap_texts"][0] = "not canonical"
        path.write_text(json.dumps(data), encoding="utf-8")
        # Refresh the policy's own doc marker so this test reaches the gap check first.
        doc = root / "docs/architecture/MANIFEST_REFERENCE_INTEGRITY.md"
        old = next(
            line for line in doc.read_text(encoding="utf-8").splitlines()
            if line.startswith("<!-- machine-git-blob: machine/manifest_reference_policy.json@")
        )
        new = (
            "<!-- machine-git-blob: machine/manifest_reference_policy.json@"
            + blob_sha(path)
            + " -->"
        )
        doc.write_text(doc.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ManifestReferenceError, "masterplan gap drift"):
            MODULE.validate(root)


if __name__ == "__main__":
    unittest.main()
