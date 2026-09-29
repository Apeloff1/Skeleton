"""Regression tests for immutable Git-history artifact references (#807 B006)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "artifact_reference.py"
SPEC = importlib.util.spec_from_file_location("artifact_reference", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
refs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(refs)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def _fixture(root: Path, *, executable: bool = False):
    repo = root / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Artifact Test")
    _git(repo, "config", "user.email", "artifact-test@example.invalid")

    target = repo / "satellites" / "branch-snapshots" / "demo" / "backend" / "blob.bin"
    target.parent.mkdir(parents=True)
    payload = b"artifact-reference-test\n" * 32
    target.write_bytes(payload)
    if executable:
        target.chmod(0o755)
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "add legacy artifact")
    source_commit = _git(repo, "rev-parse", "HEAD")
    blob_oid = _git(
        repo,
        "rev-parse",
        "HEAD:satellites/branch-snapshots/demo/backend/blob.bin",
    )

    _git(repo, "rm", "-q", "satellites/branch-snapshots/demo/backend/blob.bin")
    _git(repo, "commit", "-qm", "remove legacy artifact")

    manifest = {
        "schema": 1,
        "source_commit": source_commit,
        "artifacts": [
            {
                "id": "demo-blob",
                "target_path": "satellites/branch-snapshots/demo/backend/blob.bin",
                "source_path": "satellites/branch-snapshots/demo/backend/blob.bin",
                "git_blob_oid": blob_oid,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_bytes": len(payload),
                "mode": "100755" if executable else "100644",
                "license": "NOASSERTION",
                "redistribution_status": "test-only",
                "provenance_note": "Synthetic regression fixture.",
            }
        ],
    }
    manifest_path = repo / "satellites" / "ARTIFACT_REFERENCES.json"
    manifest_path.parent.mkdir(exist_ok=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return repo, manifest_path, manifest, payload


class ArtifactReferenceTests(unittest.TestCase):
    def test_reference_validates_against_git_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, manifest_path, _, _ = _fixture(Path(tmp))

            entries = refs.validate_file(manifest_path, repo_root=repo)

            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["id"], "demo-blob")
            self.assertEqual(entries[0]["source_commit"], _git(repo, "rev-parse", "HEAD^"))

    def test_materialize_restores_exact_blob_and_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, manifest_path, _, payload = _fixture(root, executable=True)
            output = root / "restored" / "godot"

            restored = refs.materialize(
                "demo-blob",
                output,
                manifest_path=manifest_path,
                repo_root=repo,
            )

            self.assertEqual(restored.read_bytes(), payload)
            self.assertTrue(restored.stat().st_mode & 0o111)
            expected = refs.validate_file(manifest_path, repo_root=repo)[0]["git_blob_oid"]
            self.assertEqual(_git(repo, "hash-object", str(restored)), expected)

    def test_materialize_rejects_sha256_mismatch_and_removes_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, manifest_path, manifest, _ = _fixture(root)
            manifest["artifacts"][0]["sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            output = root / "tampered.bin"

            with self.assertRaisesRegex(refs.ArtifactReferenceError, "SHA-256 mismatch"):
                refs.materialize(
                    "demo-blob",
                    output,
                    manifest_path=manifest_path,
                    repo_root=repo,
                )
            self.assertFalse(output.exists())

    def test_materialize_refuses_overwrite_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, manifest_path, _, _ = _fixture(root)
            output = root / "existing.bin"
            output.write_bytes(b"existing")

            with self.assertRaisesRegex(
                refs.ArtifactReferenceError,
                "refusing to overwrite",
            ):
                refs.materialize(
                    "demo-blob",
                    output,
                    manifest_path=manifest_path,
                    repo_root=repo,
                )

    def test_tracked_duplicate_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, manifest_path, manifest, _ = _fixture(Path(tmp))
            entry = manifest["artifacts"][0]
            target = repo / entry["target_path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"restored duplicate")
            _git(repo, "add", entry["target_path"])

            with self.assertRaisesRegex(
                refs.ArtifactReferenceError,
                "target remains tracked",
            ):
                refs.validate_file(manifest_path, repo_root=repo)

    def test_malformed_reference_fails_closed(self) -> None:
        cases = [
            ("git_blob_oid", "0" * 40, "resolves to"),
            ("sha256", "not-a-sha256", "64 lowercase hex"),
            ("size_bytes", 1, "blob size"),
            ("mode", "120000", "unsupported mode"),
            ("target_path", "../escape.bin", "invalid path segments"),
        ]
        for field, value, match in cases:
            with self.subTest(field=field):
                with tempfile.TemporaryDirectory() as tmp:
                    repo, manifest_path, manifest, _ = _fixture(Path(tmp))
                    manifest["artifacts"][0][field] = value
                    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

                    with self.assertRaisesRegex(refs.ArtifactReferenceError, match):
                        refs.validate_file(manifest_path, repo_root=repo)

    def test_duplicate_ids_and_unknown_keys_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, manifest_path, manifest, _ = _fixture(Path(tmp))
            manifest["artifacts"].append(dict(manifest["artifacts"][0]))
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(
                refs.ArtifactReferenceError,
                "duplicate artifact id",
            ):
                refs.validate_file(manifest_path, repo_root=repo)

        with tempfile.TemporaryDirectory() as tmp:
            repo, manifest_path, manifest, _ = _fixture(Path(tmp))
            manifest["artifacts"][0]["shell"] = "rm -rf /"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(refs.ArtifactReferenceError, "keys mismatch"):
                refs.validate_file(manifest_path, repo_root=repo)

    def test_duplicate_json_keys_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(
                '{"schema":1,"schema":1,"source_commit":"'
                + "0" * 40
                + '","artifacts":[]}',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                refs.ArtifactReferenceError,
                "duplicate JSON key",
            ):
                refs.load_manifest(path)


if __name__ == "__main__":
    unittest.main()
