import json
from pathlib import Path

from skeleton.build.delivery.cli import main

ENV_DIR = Path(__file__).resolve().parents[1] / "build" / "delivery" / "envs"


def test_manifest_verify_plan(tmp_path, capsys):
    root = tmp_path / "dist"
    root.mkdir()
    (root / "skel.whl").write_bytes(b"wheel")
    assert main(["manifest", str(root), "--release-id", "skel-1", "--version", "1.0.0", "--commit", "a" * 40]) == 0
    manifest = tmp_path / "m.json"
    manifest.write_text(capsys.readouterr().out)
    assert main(["verify", str(manifest), str(root)]) == 0
    (root / "skel.whl").write_bytes(b"tampered")
    assert main(["verify", str(manifest), str(root)]) == 1
    capsys.readouterr()
    assert main(["plan", str(manifest), "--env", "production", "--dir", str(ENV_DIR)]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["strategy"] == "canary" and plan["steps"][0]["kind"] == "lock"


def test_env_and_errors(tmp_path, capsys):
    assert main(["env", "staging", "--dir", str(ENV_DIR)]) == 0
    assert json.loads(capsys.readouterr().out)["lineage"] == ["staging", "base"]
    assert main(["env", "nope", "--dir", str(ENV_DIR)]) == 2


def test_secrets_scan(tmp_path, capsys):
    clean, dirty = tmp_path / "a.txt", tmp_path / "b.txt"
    clean.write_text("hello\n")
    dirty.write_text("key=AKIA" + "Q" * 16 + "\n")
    assert main(["secrets", str(clean)]) == 0
    assert main(["secrets", str(clean), str(dirty)]) == 1


def test_rollback(tmp_path, capsys):
    from skeleton.build.delivery.release_history import ReleaseHistory

    h = ReleaseHistory("staging")
    for i, rid in enumerate(("r1", "r2")):
        h.record(release_id=rid, manifest_digest=str(i) * 64, config_digest="c" * 64, outcome="deployed", recorded_at=i)
    path = tmp_path / "h.json"
    path.write_text(json.dumps(h.to_list()))
    assert main(["rollback", str(path), "--env", "staging"]) == 0
    assert json.loads(capsys.readouterr().out)["to"] == "r1"

def test_delivery_tree_rejects_symlink_and_hardlink_sources(tmp_path):
    import os
    import pytest
    from skeleton.build.delivery.cli import _read_tree
    from skeleton.build.delivery._util import DeliveryError

    root = tmp_path / "dist"
    root.mkdir()
    (root / "good.whl").write_bytes(b"good")
    outside = tmp_path / "outside.whl"
    outside.write_bytes(b"private")
    (root / "linked.whl").symlink_to(outside)
    with pytest.raises(DeliveryError):
        _read_tree(root)
    (root / "linked.whl").unlink()
    os.link(outside, root / "linked.whl")
    with pytest.raises(DeliveryError, match="aliases external inode"):
        _read_tree(root)
    (root / "linked.whl").unlink()
    assert _read_tree(root) == {"good.whl": b"good"}
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(DeliveryError):
        _read_tree(alias)


def test_delivery_tree_enforces_aggregate_bound(tmp_path, monkeypatch):
    import pytest
    from skeleton.build.delivery import cli
    from skeleton.build.delivery._util import DeliveryError

    root = tmp_path / "dist"
    root.mkdir()
    (root / "a.whl").write_bytes(b"ab")
    (root / "b.whl").write_bytes(b"cd")
    monkeypatch.setattr(cli, "MAX_READ", 3)
    with pytest.raises(DeliveryError, match="byte limit"):
        cli._read_tree(root)
