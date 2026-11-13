from pathlib import Path

import pytest

from skeleton.provenance.shard_seal import (
    ShardSeal, ShardSealError, merkle_root, seal_tree, shard_names, verify_seal,
)


def _tree(tmp_path, n=5):
    names = shard_names(n)
    for i, name in enumerate(names):
        (tmp_path / name).write_text(f"x = {i}\n")
    return names


def test_names():
    assert shard_names(3) == ["shard_000.py", "shard_001.py", "shard_002.py"]
    assert shard_names(1500)[-1] == "shard_1499.py"
    with pytest.raises(ShardSealError):
        shard_names(0)


def test_merkle_root_order_and_domain():
    a = merkle_root([b"a", b"b", b"c"])
    assert a != merkle_root([b"b", b"a", b"c"])
    assert merkle_root([b"a"]) != merkle_root([b"a", b"a"])
    with pytest.raises(ShardSealError):
        merkle_root([])


def test_seal_roundtrip(tmp_path):
    names = _tree(tmp_path)
    dest = tmp_path / "out" / "seal.json"
    seal = seal_tree(tmp_path, names, dest)
    loaded = ShardSeal.from_json(dest.read_text())
    assert loaded == seal
    verify_seal(tmp_path, loaded)
    assert not list((tmp_path / "out").glob("*.tmp"))


def test_missing_fails_closed(tmp_path):
    names = _tree(tmp_path)
    (tmp_path / names[2]).unlink()
    with pytest.raises(ShardSealError, match="missing"):
        seal_tree(tmp_path, names, tmp_path / "seal.json")
    assert not (tmp_path / "seal.json").exists()


def test_tamper_detected(tmp_path):
    names = _tree(tmp_path)
    seal = seal_tree(tmp_path, names)
    (tmp_path / names[1]).write_text("x = 999\n")
    with pytest.raises(ShardSealError, match="changed"):
        verify_seal(tmp_path, seal)
    forged = ShardSeal(seal.expected, dict(seal.digests), "0" * 64)
    with pytest.raises(ShardSealError, match="root"):
        verify_seal(tmp_path, forged)


def test_malformed_and_duplicates(tmp_path):
    with pytest.raises(ShardSealError):
        ShardSeal.from_json("{}")
    names = _tree(tmp_path, 2)
    with pytest.raises(ShardSealError):
        seal_tree(tmp_path, names + names[:1])


def test_symlink_rejected(tmp_path):
    names = _tree(tmp_path, 2)
    (tmp_path / names[0]).unlink()
    (tmp_path / names[0]).symlink_to(tmp_path / names[1])
    with pytest.raises(ShardSealError):
        seal_tree(tmp_path, names)


def test_mirror_identical():
    root = Path(__file__).resolve().parents[1]
    assert (root / "provenance/shard_seal.py").read_bytes() == \
        (root / "ai/runtime/provenance/shard_seal.py").read_bytes()
