"""Source custody for merged replay checkpoint and provider-environment boundaries."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def test_replay_checkpoint_has_exact_canonical_mirror():
    source = ROOT / "skeleton/simulation/replay_checkpoint.py"
    mirror = ROOT / "skeleton/ai/simulation/replay_checkpoint.py"
    assert source.is_file() and not source.is_symlink()
    assert mirror.is_file() and not mirror.is_symlink()
    assert source.read_bytes() == mirror.read_bytes()


def test_provider_environment_is_explicitly_retained_with_owner_and_reason():
    source = ROOT / "skeleton/provider_environment.py"
    assert source.is_file() and not source.is_symlink()
    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    retained = [
        item for item in manifest["retained_outside_ai_tree"]
        if item.get("path") == "skeleton/provider_environment.py"
    ]
    assert len(retained) == 1
    assert retained[0]["owner"] and retained[0]["reason"]
    assert all(
        item.get("source") != "skeleton/provider_environment.py"
        for item in manifest["mappings"]
    )
