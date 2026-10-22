"""Tests for vault path wiring."""
from pathlib import Path
import pytest
from skeleton.security.vault_path_wiring import vault_open, vault_list
from skeleton.security.path_url_hardener import PathHardeningError

def test_vault_open_ok(tmp_path: Path):
    root = tmp_path / "vault"
    root.mkdir()
    (root / "secret.txt").write_text("data")
    data = vault_open("secret.txt", root)
    assert data == b"data"

def test_vault_open_escape(tmp_path: Path):
    root = tmp_path / "vault"
    root.mkdir()
    with pytest.raises(PathHardeningError):
        vault_open("../../../etc/passwd", root)

def test_vault_list(tmp_path: Path):
    root = tmp_path / "vault"
    root.mkdir()
    (root / "a.txt").write_text("a")
    names = vault_list(root)
    assert "a.txt" in names
