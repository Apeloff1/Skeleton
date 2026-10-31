"""Combined adversarial tests for injected gap starters."""
from pathlib import Path
import pytest

from skeleton.security.path_url_hardener import harden_path, harden_url, PathHardeningError, URLHardeningError
from skeleton.forge.pipelines.commercial_asset_starter import emit_atlas, emit_godot_tres, AssetPipelineError
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority, MultiplayerError

def test_hardener_escape(tmp_path: Path):
    root = tmp_path / "safe"
    root.mkdir()
    with pytest.raises(PathHardeningError):
        harden_path("../../../etc/passwd", root=root)

def test_url_ok():
    assert "example.com" in harden_url("https://api.example.com")

def test_atlas_png(tmp_path: Path):
    frame = bytes([255, 0, 0, 255] * 4)
    path, cov = emit_atlas([frame], 2, 2, tmp_path, "src")
    assert path.suffix == ".png"
    assert path.read_bytes().startswith(b"\x89PNG")
    assert cov > 0

def test_tres(tmp_path: Path):
    frame = bytes([0, 255, 0, 255] * 4)
    atlas, _ = emit_atlas([frame], 2, 2, tmp_path, "src")
    tres = emit_godot_tres(atlas, 1, 2, 2, tmp_path)
    assert "SpriteFrames" in tres.read_text()

def test_multi_grant():
    auth = SessionAuthority("s1")
    g = auth.issue_grant("p1")
    assert auth.verify_grant("p1", g.digest)
    with pytest.raises(MultiplayerError):
        SessionAuthority("s2", max_players=0).issue_grant("x")
