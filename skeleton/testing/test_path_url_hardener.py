"""Expanded regression tests for path_url_hardener and atlas starter."""
from pathlib import Path
import pytest

from skeleton.security.path_url_hardener import (
    harden_path, harden_url, PathHardeningError, URLHardeningError
)
from skeleton.forge.pipelines.commercial_asset_starter import emit_atlas, AssetPipelineError

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

def test_atlas_ok(tmp_path: Path):
    frame = bytes([255, 0, 0, 255] * 4)  # 2x2 opaque
    path, cov = emit_atlas([frame], 2, 2, tmp_path, "src-receipt")
    assert path.exists()
    assert 0.0 < cov <= 1.0
