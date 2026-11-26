"""Forge emitted-source manifests under per-file and ecosystem byte envelopes.

The source manifest is an inventory digest, not a native export, device pass,
Godot boot receipt, security approval, or authority to overwrite a project.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from skeleton.forge import projector
from skeleton.forge import source_manifest as source_module


SOURCE_FILES = {
    "project.godot": '[application]\nconfig/name="Review"\n',
    "scripts/controller.gd": "extends Node\nvar x = 1\n",
    "assets/description.txt": "prototype ✓\n",
}


def test_canonical_manifest_is_stable_and_compatible_with_existing_digest():
    expected = {
        name: hashlib.sha256(content.encode("utf-8")).hexdigest()
        for name, content in SOURCE_FILES.items()
    }
    legacy = hashlib.sha256(
        json.dumps(expected, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    report = source_module.source_manifest(SOURCE_FILES)
    assert report["sha256"] == legacy
    assert report["files"] == dict(sorted(expected.items()))
    assert report["file_count"] == len(SOURCE_FILES)
    assert report == source_module.source_manifest(dict(reversed(list(SOURCE_FILES.items()))))


def test_source_manifest_never_uses_monolithic_json_dumps():
    with patch.object(
        source_module.json, "dumps",
        side_effect=AssertionError("monolithic source index serialization forbidden"),
    ):
        report = source_module.source_manifest(SOURCE_FILES)
    assert len(report["sha256"]) == 64


def test_utf8_boundary_uses_real_bytes_not_character_count(monkeypatch):
    monkeypatch.setattr(source_module, "MAX_SOURCE_FILE_BYTES", 20)
    files = {"project.godot": "short", "source.gd": "✨" * 7}
    with pytest.raises(ValueError, match="file.*byte budget"):
        source_module.source_manifest(files)
    files["source.gd"] = "é" * 10
    report = source_module.source_manifest(files)
    assert report["file_count"] == 2


def test_many_small_files_cannot_escape_total_byte_budget(monkeypatch):
    monkeypatch.setattr(source_module, "MAX_SOURCE_TOTAL_BYTES", 32)
    files = {
        "project.godot": "t" * 12,
        "script1.gd": "a" * 11,
        "script2.gd": "b" * 11,
    }
    with pytest.raises(ValueError, match="tree exceeds byte budget"):
        source_module.source_manifest(files)


def test_project_file_count_rejected_before_materialization(monkeypatch):
    monkeypatch.setattr(projector, "MAX_PROJECT_FILES", 2)
    files = {
        "project.godot": "valid",
        "main.gd": "main",
        "scene.tscn": "scene",
    }
    with pytest.raises(ValueError, match="file count"):
        projector._validate(files)


def test_source_manifest_file_count_rejected_before_projector(monkeypatch):
    monkeypatch.setattr(source_module, "MAX_SOURCE_FILES", 2)
    files = {
        "project.godot": "valid",
        "main.gd": "main",
        "scene.tscn": "scene",
    }
    with patch.object(
        projector, "_validate",
        side_effect=AssertionError("must not inspect unbounded source mapping"),
    ):
        with pytest.raises(ValueError, match="file budget"):
            source_module.source_manifest(files)


def test_path_length_and_text_length_rejected_before_source_publication(monkeypatch):
    monkeypatch.setattr(projector, "MAX_PROJECT_PATH_CHARS", 16)
    with pytest.raises(ValueError, match="invalid generated source path"):
        projector._validate({"project.godot": "valid", "long-long-path-name.gd": "valid"})
    monkeypatch.setattr(projector, "MAX_PROJECT_TEXT_CHARS", 8)
    with pytest.raises(ValueError, match="text budget"):
        projector._validate({"project.godot": "x" * 9})


@pytest.mark.parametrize("name", [
    "../escape.gd", "a/../b.gd", "/etc/passwd", "C:/run.gd",
    "a\\b.gd", "CON.gd", "a//b.gd", "a/./b.gd",
])
def test_escape_and_platform_alias_paths_are_rejected(name):
    with pytest.raises(ValueError):
        source_module.source_manifest({
            "project.godot": "legitimate",
            name: "malicious",
        })


def test_writing_real_project_publishes_its_receipt_without_overwrite(tmp_path: Path):
    destination = tmp_path / "created-project"
    receipt = projector.write_project(
        destination, SOURCE_FILES, overwrite=False,
    )
    generated = json.loads(
        (destination / "FORGE_MANIFEST.json").read_text(encoding="utf-8")
    )
    expected = source_module.source_manifest(SOURCE_FILES)
    assert generated["source_sha256"] == expected["sha256"]
    assert receipt["source_sha256"] == expected["sha256"]
    for name, body in SOURCE_FILES.items():
        assert (destination / name).read_text(encoding="utf-8") == body
    with pytest.raises(projector.ProjectExistsError):
        projector.write_project(destination, SOURCE_FILES, overwrite=False)


def test_source_code_and_ai_mirrors_are_identical():
    root = Path(__file__).resolve().parents[1]
    for relative in ("source_manifest.py", "projector.py", "export.py"):
        assert (
            root / "skeleton/forge" / relative
        ).read_bytes() == (
            root / "skeleton/ai/forge" / relative
        ).read_bytes()


def test_zero_length_source_is_still_hashable():
    report = source_module.source_manifest({
        "project.godot": "",
        "scripts/empty.gd": "",
    })
    empty = hashlib.sha256(b"").hexdigest()
    assert report["files"]["project.godot"] == empty
    assert report["files"]["scripts/empty.gd"] == empty


def test_source_manifest_rejects_nontext_and_ambiguous_key_case():
    for bad in (
        {"project.godot": object()},
        {"project.godot": "legit", "Project.GODOT": "collision"},
    ):
        with pytest.raises(ValueError):
            source_module.source_manifest(bad)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
