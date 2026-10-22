"""Adversarial regression tests for path_url_hardener and commercial_asset_starter.
Covers escape, geometry, PNG validity, tres structure, coverage, URL edges, length, empty.
"""
from pathlib import Path
import pytest

from skeleton.security.path_url_hardener import (
    harden_path, harden_url, PathHardeningError, URLHardeningError
)
from skeleton.forge.pipelines.commercial_asset_starter import (
    emit_atlas, emit_godot_tres, AssetPipelineError
)

def test_path_escape_rejected(tmp_path: Path):
    root = tmp_path / "safe"
    root.mkdir()
    with pytest.raises(PathHardeningError):
        harden_path("../../../etc/passwd", root=root)

def test_path_absolute_rejected(tmp_path: Path):
    root = tmp_path / "safe"
    root.mkdir()
    with pytest.raises(PathHardeningError):
        harden_path("/etc/passwd", root=root)

def test_path_empty_rejected(tmp_path: Path):
    root = tmp_path / "safe"
    root.mkdir()
    with pytest.raises(PathHardeningError):
        harden_path("", root=root)

def test_path_too_long(tmp_path: Path):
    root = tmp_path / "safe"
    root.mkdir()
    with pytest.raises(PathHardeningError):
        harden_path("a" * 5000, root=root)

def test_path_confined_ok(tmp_path: Path):
    root = tmp_path / "safe"
    root.mkdir()
    (root / "ok.txt").write_text("data")
    result = harden_path("ok.txt", root=root)
    assert result == (root / "ok.txt").resolve()

def test_url_bad_host():
    with pytest.raises(URLHardeningError):
        harden_url("https://evil.example.net/path")

def test_url_good_host():
    clean = harden_url("https://api.example.com/v1")
    assert "example.com" in clean

def test_url_localhost():
    clean = harden_url("http://localhost:8080/api")
    assert "localhost" in clean

def test_atlas_bad_geometry(tmp_path: Path):
    with pytest.raises(AssetPipelineError):
        emit_atlas([b"short"], 2, 2, tmp_path, "src")

def test_atlas_png_valid(tmp_path: Path):
    frame = bytes([255, 0, 0, 255] * 4)
    path, cov = emit_atlas([frame], 2, 2, tmp_path, "src-receipt")
    assert path.suffix == ".png"
    data = path.read_bytes()
    assert data.startswith(b"\x89PNG")
    assert 0.0 < cov <= 1.0

def test_tres_emitted(tmp_path: Path):
    frame = bytes([0, 255, 0, 255] * 4)
    atlas, _ = emit_atlas([frame], 2, 2, tmp_path, "src")
    tres = emit_godot_tres(atlas, 1, 2, 2, tmp_path)
    text = tres.read_text()
    assert "SpriteFrames" in text
    assert "AtlasTexture" in text

def test_coverage_bounds(tmp_path: Path):
    opaque = bytes([255] * 16)
    _, cov = emit_atlas([opaque], 2, 2, tmp_path, "src")
    assert cov == 1.0
