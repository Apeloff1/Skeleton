"""Reproducible packaging manifest: build, serialize, tamper detection, verify."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from skeleton.deployment.manifest import (
    MANIFEST_KIND,
    FileEntry,
    ManifestError,
    PackageManifest,
    build_manifest,
    dockerfile_copy_sources,
    load_manifest,
    verify_manifest,
    write_manifest,
)
from skeleton.deployment.profile import get_profile

REPO_ROOT = Path(__file__).resolve().parents[2]


def make_tree(root: Path) -> Path:
    (root / "pkg" / "sub").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    (root / "pkg" / "sub" / "mod.py").write_text("y = 2\n", encoding="utf-8")
    (root / "pkg" / "__pycache__").mkdir()
    (root / "pkg" / "__pycache__" / "mod.cpython-313.pyc").write_bytes(b"\0\0")
    (root / "README.md").write_text("readme\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.2.3"\nrequires-python = ">=3.11"\ndependencies = ["a>=1", "b==2"]\n',
        encoding="utf-8",
    )
    (root / "Dockerfile").write_text(
        "FROM python\n# COPY ignored.txt /x\nCOPY --chown=a:a pyproject.toml README.md ./\nCOPY pkg ./pkg\n",
        encoding="utf-8",
    )
    return root


def test_dockerfile_copy_sources_parses_flags_continuations_and_json() -> None:
    text = """
FROM python AS build
COPY --chown=app:app pyproject.toml README.md ./
COPY --chown=app:app \\
     skeleton ./skeleton
COPY ["machine/a.json", "machine/b.json", "./machine/"]
COPY --from=build /out /app
ADD ./docs/x.md /docs/
ADD https://example.org/f.tgz /tmp/
# COPY commented /nope
COPY onlyone
"""
    assert dockerfile_copy_sources(text) == [
        "pyproject.toml", "README.md", "skeleton", "machine/a.json", "machine/b.json", "docs/x.md",
    ]


def test_repository_dockerfile_sources_include_runtime_package() -> None:
    dockerfile = REPO_ROOT / "Dockerfile"
    if not dockerfile.is_file():
        pytest.skip("no Dockerfile in this checkout")
    sources = dockerfile_copy_sources(dockerfile.read_text(encoding="utf-8"))
    # A whole-context COPY (".") also ships the runtime package.
    assert "skeleton" in sources or "." in sources
    assert "pyproject.toml" in sources


def test_build_manifest_uses_dockerfile_sources_and_excludes_bytecode(tmp_path) -> None:
    manifest = build_manifest(make_tree(tmp_path))
    paths = [entry.path for entry in manifest.files]
    assert paths == ["pyproject.toml", "README.md", "pkg/__init__.py", "pkg/sub/mod.py"]
    assert manifest.sources == ["pyproject.toml", "README.md", "pkg"]
    assert (manifest.name, manifest.version, manifest.requires_python) == ("demo", "1.2.3", ">=3.11")
    assert manifest.dependencies == ["a>=1", "b==2"]
    assert manifest.file_count == 4
    assert manifest.total_bytes == sum(e.size for e in manifest.files)
    assert manifest.entrypoints["boot"][-2:] == ["deploy", "boot"]


def test_build_manifest_falls_back_without_dockerfile(tmp_path) -> None:
    (tmp_path / "skeleton").mkdir()
    (tmp_path / "skeleton" / "a.py").write_text("a", encoding="utf-8")
    manifest = build_manifest(tmp_path)
    assert manifest.sources == ["pyproject.toml", "README.md", "skeleton"]
    assert [e.path for e in manifest.files] == ["skeleton/a.py"]
    assert "pyproject.toml (missing)" in manifest.skipped
    assert manifest.name == "skeleton"


def test_root_digest_is_content_addressed_and_order_independent(tmp_path) -> None:
    first = build_manifest(make_tree(tmp_path / "a"))
    second = build_manifest(make_tree(tmp_path / "b"))
    assert first.root_digest == second.root_digest
    shuffled = PackageManifest.from_dict({**first.to_dict(), "files": list(reversed(first.to_dict()["files"]))})
    assert shuffled.root_digest == first.root_digest
    (tmp_path / "b" / "pkg" / "__init__.py").write_text("x = 2\n", encoding="utf-8")
    assert build_manifest(tmp_path / "b").root_digest != first.root_digest


def test_json_round_trip(tmp_path) -> None:
    manifest = build_manifest(make_tree(tmp_path), git_sha="abc123")
    target = write_manifest(manifest, tmp_path / "out" / "manifest.json")
    loaded = load_manifest(target)
    assert loaded.to_dict() == manifest.to_dict()
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["kind"] == MANIFEST_KIND
    assert payload["git_sha"] == "abc123"
    assert list(payload)[:3] == ["schema_version", "kind", "name"]


def test_summary_omits_files(tmp_path) -> None:
    summary = build_manifest(make_tree(tmp_path)).summary()
    assert "files" not in summary
    assert summary["file_count"] == 4


def test_manifest_embeds_redacted_profile(tmp_path) -> None:
    profile = get_profile("selfhost").with_overrides(service_token="s" * 40)
    manifest = build_manifest(make_tree(tmp_path), profile=profile)
    assert manifest.profile["fingerprint"] == profile.fingerprint()
    assert "s" * 40 not in manifest.to_json()


def test_verify_clean_tree(tmp_path) -> None:
    root = make_tree(tmp_path)
    diff = verify_manifest(build_manifest(root), root)
    assert diff.ok
    assert diff.expected_digest == diff.actual_digest
    assert diff.to_dict()["kind"] == "deployment_manifest_verification"


def test_verify_detects_missing_modified_unexpected_and_mode_changes(tmp_path) -> None:
    root = make_tree(tmp_path)
    manifest = build_manifest(root)
    (root / "pkg" / "sub" / "mod.py").unlink()
    (root / "pkg" / "__init__.py").write_text("tampered\n", encoding="utf-8")
    (root / "pkg" / "new.py").write_text("new\n", encoding="utf-8")
    if os.name == "posix":
        os.chmod(root / "README.md", 0o755)
    diff = verify_manifest(manifest, root)
    assert not diff.ok
    assert diff.missing == ["pkg/sub/mod.py"]
    assert diff.modified == ["pkg/__init__.py"]
    assert diff.unexpected == ["pkg/new.py"]
    if os.name == "posix":
        assert diff.mode_changed == ["README.md"]


def test_mode_change_alone_does_not_fail_verification(tmp_path) -> None:
    if os.name != "posix":
        pytest.skip("POSIX permissions")
    root = make_tree(tmp_path)
    manifest = build_manifest(root)
    os.chmod(root / "README.md", 0o755)
    diff = verify_manifest(manifest, root)
    assert diff.ok and diff.mode_changed == ["README.md"]


def test_symlinks_are_skipped_not_followed(tmp_path) -> None:
    if os.name != "posix":
        pytest.skip("symlinks")
    root = make_tree(tmp_path / "root")
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    (root / "pkg" / "link.txt").symlink_to(outside)
    manifest = build_manifest(root)
    assert "pkg/link.txt" not in [e.path for e in manifest.files]
    assert "pkg/link.txt (symlink)" in manifest.skipped


@pytest.mark.parametrize("path", ["/etc/passwd", "../up", "a/../b", "./a", "a\\b", "", "a//b", "a\x00b"])
def test_unsafe_paths_are_rejected(path: str) -> None:
    with pytest.raises(ManifestError, match="unsafe"):
        FileEntry.from_dict({"path": path, "size": 1, "sha256": "0" * 64})


def test_entry_validation() -> None:
    with pytest.raises(ManifestError, match="sha256"):
        FileEntry.from_dict({"path": "a", "size": 1, "sha256": "xyz"})
    with pytest.raises(ManifestError, match="size"):
        FileEntry.from_dict({"path": "a", "size": -1, "sha256": "0" * 64})
    with pytest.raises(ManifestError, match="size"):
        FileEntry.from_dict({"path": "a", "size": True, "sha256": "0" * 64})


def test_from_dict_rejects_tampering_and_bad_documents(tmp_path) -> None:
    payload = build_manifest(make_tree(tmp_path)).to_dict()
    tampered = json.loads(json.dumps(payload))
    tampered["files"][0]["sha256"] = "f" * 64
    with pytest.raises(ManifestError, match="root_digest"):
        PackageManifest.from_dict(tampered)
    truncated = {**payload, "files": payload["files"][1:]}
    with pytest.raises(ManifestError, match="root_digest"):
        PackageManifest.from_dict(truncated)
    duplicate = {**payload, "files": payload["files"] + payload["files"][:1]}
    duplicate.pop("root_digest")
    with pytest.raises(ManifestError, match="duplicate"):
        PackageManifest.from_dict(duplicate)
    with pytest.raises(ManifestError, match="not a"):
        PackageManifest.from_dict({**payload, "kind": "other"})
    with pytest.raises(ManifestError, match="schema_version"):
        PackageManifest.from_dict({**payload, "schema_version": 99})
    with pytest.raises(ManifestError, match="list"):
        PackageManifest.from_dict({**payload, "files": {}})


def test_load_manifest_errors(tmp_path) -> None:
    with pytest.raises(ManifestError, match="cannot read"):
        load_manifest(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    with pytest.raises(ManifestError, match="object"):
        load_manifest(bad)


def test_build_manifest_rejects_non_directory(tmp_path) -> None:
    with pytest.raises(ManifestError, match="not a directory"):
        build_manifest(tmp_path / "nope")


def test_build_manifest_rejects_escaping_sources(tmp_path) -> None:
    with pytest.raises(ManifestError, match="unsafe"):
        build_manifest(make_tree(tmp_path), sources=["../outside"])


def test_bad_pyproject_is_reported(tmp_path) -> None:
    root = make_tree(tmp_path)
    (root / "pyproject.toml").write_text("not = [valid", encoding="utf-8")
    with pytest.raises(ManifestError, match="cannot parse"):
        build_manifest(root)
