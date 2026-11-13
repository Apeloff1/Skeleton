"""Adversarial, exact-content integration tests for the ordered AI bundle."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_ai_ecosystem_bundle.py"
spec = importlib.util.spec_from_file_location("ai_ecosystem_bundle", SCRIPT)
assert spec and spec.loader
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def git(repo: Path, *args: str) -> None:
    proc = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True)
    if proc.returncode:
        raise RuntimeError(f"git {args}: {proc.stderr}")


class OrderedBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="ordered-ai-bundle-")
        self.base = Path(self.temp.name)
        self.repo = self.base / "repo"
        self.payload = self.base / "operator-approved"
        self.repo.mkdir()
        self.payload.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "test@example.invalid")
        git(self.repo, "config", "user.name", "Fixture")
        self.profile = {"schema_version": 1, "source_root": "skeleton/ai", "support_files": {},
            "minimum_archive_bytes": 1, "maximum_archive_bytes": 1_000_000,
            "minimum_source_bytes": 16,
            "wave_prefixes": {wave: [f"skeleton/ai/{wave}.py"] for wave in bundle.WAVES}}
        for wave in bundle.WAVES:
            path = self.repo / "skeleton" / "ai" / f"{wave}.py"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# test implementation {wave}\n", encoding="utf-8")
        write_json(self.repo / "machine/ai_ecosystem_bundle_v1.json", self.profile)
        write_json(self.repo / "machine/ai_master_build_sequence.json", {
            "schema_version": 1, "waves": [
                {"id": wave, "hard_dependencies": ([bundle.WAVES[i-1]] if i else []),
                 "work_packages": [f"WP-W{i:02}"]}
                for i, wave in enumerate(bundle.WAVES)]})
        (self.repo / "scripts").mkdir(exist_ok=True)
        (self.repo / "scripts/build_ai_ecosystem_bundle.py").write_bytes(SCRIPT.read_bytes())
        self.model = self.payload / "weights" / "approved.gguf"
        self.model.parent.mkdir()
        self.model.write_bytes(b"GGUF original operator-approved test model bytes\n")
        self.ledger = {"schema_version": 1, "artifacts": [{
            "file": "weights/approved.gguf", "destination": "models/approved.gguf",
            "wave": "MBW-02", "bytes": self.model.stat().st_size,
            "sha256": hashlib.sha256(self.model.read_bytes()).hexdigest(),
            "license": "test-license-only", "source": "generated:test-fixture",
            "rights_approved": True}]}
        write_json(self.payload / "approved_artifacts.json", self.ledger)
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "fixture")
        self.output = self.base / "artifact" / "bundle.tar"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def do_build(self) -> dict[str, object]:
        return bundle.build(self.repo, self.payload, "approved_artifacts.json",
                            "machine/ai_ecosystem_bundle_v1.json", self.output)

    def test_real_ordered_archive_and_streaming_verification(self) -> None:
        receipt = self.do_build()
        self.assertEqual(receipt["status"], "integrity-verified-not-release-certified")
        self.assertEqual(receipt["waves"], list(bundle.WAVES))
        with tarfile.open(self.output, "r") as tf:
            names = tf.getnames()
            self.assertEqual(names[-1], bundle.MANIFEST_NAME)
            self.assertEqual(len(names), 10)
            self.assertEqual(names[2], "bundle/stages/MBW-02/source/skeleton/ai/MBW-02.py")
            embedded = json.load(tf.extractfile(bundle.MANIFEST_NAME))
            self.assertEqual(embedded["status"], "content-only-no-release-attestation")
            self.assertTrue(any(x["kind"] == "approved_artifact" for x in embedded["entries"]))
        self.assertEqual(bundle.verify(self.output, minimum=1, maximum=1_000_000,
                                      required_source_bytes=16)["entries"], 9)

    def test_root_level_support_files_are_valid_archive_members(self) -> None:
        # The real profile includes README.md, pyproject.toml and other root
        # support paths. Their tar member is exactly five path segments.
        (self.repo / "README.md").write_text("actual root documentation\n", encoding="utf-8")
        (self.repo / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
        self.profile["support_files"] = {
            "MBW-00": ["pyproject.toml"], "MBW-07": ["README.md"],
        }
        write_json(self.repo / "machine/ai_ecosystem_bundle_v1.json", self.profile)
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "include root-level support contract")
        receipt = self.do_build()
        with tarfile.open(self.output, "r") as tar:
            names = tar.getnames()
        self.assertIn("bundle/stages/MBW-00/source/pyproject.toml", names)
        self.assertIn("bundle/stages/MBW-07/source/README.md", names)
        self.assertEqual(receipt["entries"], 11)
        self.assertEqual(bundle.verify(self.output, minimum=1, maximum=1_000_000,
                                      required_source_bytes=16)["entries"], 11)

    def test_archive_size_hold_is_no_publish(self) -> None:
        self.profile["minimum_archive_bytes"] = 1_000_000
        write_json(self.repo / "machine/ai_ecosystem_bundle_v1.json", self.profile)
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "make impossible target")
        with self.assertRaisesRegex(bundle.PackageError, "archive bytes"):
            self.do_build()
        self.assertFalse(self.output.exists())

    def test_model_hash_mismatch_is_no_publish(self) -> None:
        self.model.write_bytes(b"GGUF altered at rest".ljust(self.model.stat().st_size, b"X"))
        with self.assertRaisesRegex(bundle.PackageError, "sha256 mismatch"):
            self.do_build()
        self.assertFalse(self.output.exists())

    def test_artifact_symlink_to_outside_rejected(self) -> None:
        self.model.unlink()
        outside = self.base / "private.txt"
        outside.write_text("not authorized", encoding="utf-8")
        self.model.symlink_to(outside)
        with self.assertRaises(OSError):
            self.do_build()
        self.assertFalse(self.output.exists())

    def test_parent_directory_symlink_rejected(self) -> None:
        old = self.model.parent
        old.rename(self.payload / "trusted")
        old.symlink_to(self.payload / "trusted", target_is_directory=True)
        with self.assertRaises(OSError):
            self.do_build()
        self.assertFalse(self.output.exists())

    def test_traversal_rejected_before_read(self) -> None:
        self.ledger["artifacts"][0]["file"] = "../private.key"
        write_json(self.payload / "approved_artifacts.json", self.ledger)
        with self.assertRaisesRegex(bundle.PackageError, "unsafe relative path"):
            self.do_build()

    def test_rights_provenance_must_be_explicit(self) -> None:
        self.ledger["artifacts"][0]["rights_approved"] = False
        write_json(self.payload / "approved_artifacts.json", self.ledger)
        with self.assertRaisesRegex(bundle.PackageError, "rights"):
            self.do_build()

    def test_missing_or_incorrect_wave_is_rejected(self) -> None:
        self.profile["wave_prefixes"]["MBW-00"] = ["skeleton/ai/other.py"]
        write_json(self.repo / "machine/ai_ecosystem_bundle_v1.json", self.profile)
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "simulate unclassified source")
        with self.assertRaisesRegex(bundle.PackageError, "unclassified canonical AI path"):
            self.do_build()

    def test_dirty_source_is_rejected(self) -> None:
        (self.repo / "skeleton/ai/MBW-03.py").write_text("unsaved changes\n")
        with self.assertRaisesRegex(bundle.PackageError, "git diff"):
            self.do_build()

    def test_archive_cannot_publish_inside_git(self) -> None:
        with self.assertRaisesRegex(bundle.PackageError, "outside source"):
            bundle.build(self.repo, self.payload, "approved_artifacts.json",
                         "machine/ai_ecosystem_bundle_v1.json", self.repo / "dist/bundle.tar")

    def test_canonical_path_rejects_unicode_lookalike_traversal_and_backslash(self) -> None:
        for value in ("a//b", "a/../b", "/root", "a/./b", "a\\b", "a\x00b", "-suspicious"):
            with self.subTest(value=value), self.assertRaises(bundle.PackageError):
                bundle._safe_relative(value)

    def test_tampered_archive_bytes_fail_verification(self) -> None:
        self.do_build()
        with self.output.open("r+b") as f:
            f.seek(512)  # first file body, not its tar header
            f.write(b"X")
        with self.assertRaisesRegex(bundle.PackageError, "mismatch"):
            bundle.verify(self.output, minimum=1, maximum=1_000_000, required_source_bytes=16)

    def test_unsafe_tar_member_rejected_without_extraction(self) -> None:
        path = self.base / "evil.tar"
        with tarfile.open(path, "w") as tf:
            info = tarfile.TarInfo("bundle/stages/MBW-00/source/../../secret")
            raw = b"hello"
            info.size = len(raw)
            tf.addfile(info, io.BytesIO(raw))
        with self.assertRaises(bundle.PackageError):
            bundle.verify(path, minimum=1, maximum=1_000_000, required_source_bytes=1)

    def test_output_no_clobber(self) -> None:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_bytes(b"existing")
        with self.assertRaisesRegex(bundle.PackageError, "exists"):
            self.do_build()
        self.assertEqual(self.output.read_bytes(), b"existing")

    def test_wrong_model_wave_rejected(self) -> None:
        self.ledger["artifacts"][0]["wave"] = "MBW-06"
        write_json(self.payload / "approved_artifacts.json", self.ledger)
        with self.assertRaisesRegex(bundle.PackageError, "model placement"):
            self.do_build()

    def test_invalid_master_build_order_rejected(self) -> None:
        sequence = json.loads((self.repo / "machine/ai_master_build_sequence.json").read_text())
        sequence["waves"][0]["hard_dependencies"] = ["MBW-07"]
        write_json(self.repo / "machine/ai_master_build_sequence.json", sequence)
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "bad graph")
        with self.assertRaisesRegex(bundle.PackageError, "build dependency"):
            self.do_build()


if __name__ == "__main__":
    unittest.main()
