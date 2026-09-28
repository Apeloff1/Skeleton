from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "restore_tracked_artifact.py"
SPEC = importlib.util.spec_from_file_location("restore_tracked_artifact", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
restore = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(restore)


class TrackedArtifactRestoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name) / "repo"
        self.root.mkdir()
        self._git("init")
        self._git("config", "user.email", "test@example.invalid")
        self._git("config", "user.name", "Artifact Test")

        self.payload = b"verified artifact payload\n"
        self.target = self.root / "deep" / "nested" / "artifact.bin"
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(self.payload)
        self._git("add", ".")
        self._git("commit", "-m", "seed artifact")
        self.source_commit = self._git("rev-parse", "HEAD")
        self.blob_oid = self._git("rev-parse", "HEAD:deep/nested/artifact.bin")

        self.target.unlink()
        self.manifest = self.target.with_name(self.target.name + ".git-artifact.json")
        self._write_manifest()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _git(self, *args: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(self.root), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return completed.stdout.strip()

    def _manifest_payload(self) -> dict[str, object]:
        return {
            "schema": 1,
            "path": "deep/nested/artifact.bin",
            "source_commit": self.source_commit,
            "blob_oid": self.blob_oid,
            "size_bytes": len(self.payload),
            "kind": "test-fixture",
        }

    def _write_manifest(self, **overrides: object) -> None:
        payload = self._manifest_payload()
        payload.update(overrides)
        self.manifest.write_text(
            json.dumps(payload, sort_keys=True),
            encoding="utf-8",
        )

    def test_restore_round_trip_verifies_git_oid_and_size(self) -> None:
        restored = restore.restore_artifact(self.manifest)

        self.assertEqual(restored, self.target)
        self.assertEqual(restored.read_bytes(), self.payload)
        self.assertEqual(self._git("hash-object", str(restored)), self.blob_oid)

    def test_check_only_validates_without_materializing(self) -> None:
        payload = restore.check_artifact_manifest(self.manifest)

        self.assertEqual(payload["blob_oid"], self.blob_oid)
        self.assertEqual(payload["size_bytes"], len(self.payload))
        self.assertFalse(self.target.exists())

    def test_deep_manifest_discovers_repository_root(self) -> None:
        self.assertEqual(restore._discover_repo_root(self.manifest), self.root)

    def test_existing_destination_requires_explicit_overwrite(self) -> None:
        self.target.write_bytes(b"local modification")

        with self.assertRaisesRegex(restore.ArtifactRestoreError, "already exists"):
            restore.restore_artifact(self.manifest)

        restored = restore.restore_artifact(self.manifest, overwrite=True)
        self.assertEqual(restored.read_bytes(), self.payload)

    def test_manifest_path_must_be_repository_relative_and_normalized(self) -> None:
        bad_paths = (
            "../escape.bin",
            "/absolute.bin",
            "deep/../escape.bin",
            "deep\\escape.bin",
            "deep/artifact.bin\nother",
        )
        for path in bad_paths:
            with self.subTest(path=path):
                payload = self._manifest_payload()
                payload["path"] = path
                with self.assertRaises(restore.ArtifactRestoreError):
                    restore.validate_manifest(payload)

    def test_manifest_rejects_wrong_oid_and_size_shapes(self) -> None:
        payload = self._manifest_payload()
        payload["blob_oid"] = "ABC"
        with self.assertRaisesRegex(restore.ArtifactRestoreError, "blob_oid"):
            restore.validate_manifest(payload)

        payload = self._manifest_payload()
        payload["size_bytes"] = -1
        with self.assertRaisesRegex(restore.ArtifactRestoreError, "size_bytes"):
            restore.validate_manifest(payload)

    def test_wrong_manifest_size_fails_before_destination_replace(self) -> None:
        self._write_manifest(size_bytes=len(self.payload) + 1)

        with self.assertRaisesRegex(
            restore.ArtifactRestoreError,
            "object size mismatch",
        ):
            restore.restore_artifact(self.manifest)

        self.assertFalse(self.target.exists())

    def test_manifest_blob_must_match_exact_source_commit_path(self) -> None:
        other = self.root / "other.bin"
        other.write_bytes(b"different payload\n")
        self._git("add", "other.bin")
        self._git("commit", "-m", "add other blob")
        other_oid = self._git("rev-parse", "HEAD:other.bin")
        self.target.unlink(missing_ok=True)
        self._write_manifest(blob_oid=other_oid, size_bytes=other.stat().st_size)

        with self.assertRaisesRegex(
            restore.ArtifactRestoreError,
            "does not match source-commit path",
        ):
            restore.check_artifact_manifest(self.manifest)

    def test_unknown_manifest_fields_fail_closed(self) -> None:
        payload = self._manifest_payload()
        payload["url"] = "https://example.invalid/untrusted"

        with self.assertRaisesRegex(restore.ArtifactRestoreError, "keys mismatch"):
            restore.validate_manifest(payload)

    def test_cli_reports_failure_without_materializing_invalid_manifest(self) -> None:
        self._write_manifest(blob_oid="0" * 40)

        result = restore.main(
            [
                str(self.manifest),
                "--repo-root",
                str(self.root),
                "--remote",
                "no-such-remote",
            ]
        )

        self.assertEqual(result, 1)
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
