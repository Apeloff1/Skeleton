"""Regression tests for path_url_hardener. Fail-closed coverage."""
from pathlib import Path
import pytest

from skeleton.security.path_url_hardener import harden_path, harden_url, PathHardeningError, URLHardeningError

def test_path_escape_rejected(tmp_path: Path):
    root = tmp_path / "safe"
    root.mkdir()
    with pytest.raises(PathHardeningError):
        harden_path("../../../etc/passwd", root=root)

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
