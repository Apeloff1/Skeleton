from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_artifact_policy.py"
SPEC = importlib.util.spec_from_file_location("check_artifact_policy", SCRIPT)
assert SPEC and SPEC.loader
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


class ArtifactPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write(self, relative: str, content: bytes) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def _validate(self, relative: str) -> list[str]:
        with mock.patch.object(policy, "REPO_ROOT", self.root):
            return policy.validate_path(Path(relative))

    def test_rejects_oversized_regular_git_blob(self) -> None:
        self._write("assets/huge.dat", b"x" * (policy.REGULAR_GIT_MAX_BYTES + 1))
        errors = self._validate("assets/huge.dat")
        self.assertTrue(any("10 MiB regular-Git limit" in error for error in errors))

    def test_requires_lfs_for_model_format(self) -> None:
        self._write("models/router.onnx", b"model")
        errors = self._validate("models/router.onnx")
        self.assertTrue(any("must use Git LFS" in error for error in errors))

    def test_allows_bounded_test_fixture_without_lfs(self) -> None:
        self._write("tests/fixtures/router.onnx", b"fixture")
        self.assertEqual(self._validate("tests/fixtures/router.onnx"), [])

    def test_rejects_build_archive_even_when_small(self) -> None:
        self._write("dist/app.zip", b"not-a-real-archive")
        errors = self._validate("dist/app.zip")
        self.assertTrue(any("CI/release artifacts" in error for error in errors))

    def test_lfs_asset_requires_matching_provenance(self) -> None:
        content = b"deterministic-model"
        self._write(".gitattributes", b"*.onnx filter=lfs diff=lfs merge=lfs -text\n")
        self._write("models/router.onnx", content)
        sidecar = {"sha256": hashlib.sha256(content).hexdigest(), "source": "generated:test-fixture", "license": "MIT"}
        self._write("models/router.onnx.artifact.json", json.dumps(sidecar, sort_keys=True).encode("utf-8"))
        self.assertEqual(self._validate("models/router.onnx"), [])

    def test_lfs_asset_rejects_checksum_mismatch(self) -> None:
        self._write(".gitattributes", b"*.onnx filter=lfs diff=lfs merge=lfs -text\n")
        self._write("models/router.onnx", b"actual")
        sidecar = {"sha256": "0" * 64, "source": "generated:test-fixture", "license": "MIT"}
        self._write("models/router.onnx.artifact.json", json.dumps(sidecar, sort_keys=True).encode("utf-8"))
        errors = self._validate("models/router.onnx")
        self.assertTrue(any("sha256 mismatch" in error for error in errors))

    def test_rejects_generated_vault_path(self) -> None:
        self._write("backend/data/build_artifacts/output.txt", b"generated")
        errors = self._validate("backend/data/build_artifacts/output.txt")
        self.assertTrue(any("generated/cache path" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
