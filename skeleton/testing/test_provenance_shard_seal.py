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

def test_rejects_path_traversal_and_aliases(tmp_path):
    _tree(tmp_path, 2)
    for candidate in ("../outside", "/etc/passwd", "subdir/x", r"..\\escape", ".", "..", "", "bad" * 60):
        with pytest.raises(ShardSealError):
            seal_tree(tmp_path, [candidate])
    with pytest.raises(ShardSealError):
        seal_tree(tmp_path, ["shard_000.py", "shard_000.py"])
    with pytest.raises(ShardSealError):
        seal_tree(tmp_path, "shard_000.py")


def test_rejects_malicious_or_duplicate_seal_json(tmp_path):
    import json
    seal = seal_tree(tmp_path, _tree(tmp_path, 2))
    good = json.loads(seal.to_json())
    for bad in (
        '{"version":1,"version":1,"expected":2,"root":"' + seal.root + '","digests":{}}',
        '{"expected":1,"version":1,"root":"bad","digests":{"../escape":"bad"}}',
        '{"expected":true,"version":1,"root":"' + seal.root + '","digests":{}}',
    ):
        with pytest.raises(ShardSealError):
            ShardSeal.from_json(bad)
    good["digests"] = {"../secret": "0" * 64}
    good["expected"] = 1
    with pytest.raises(ShardSealError):
        ShardSeal.from_json(json.dumps(good))


def test_output_must_remain_inside_root(tmp_path):
    names = _tree(tmp_path, 2)
    with pytest.raises(ShardSealError):
        seal_tree(tmp_path, names, tmp_path.parent / "seal-outside.json")
    with pytest.raises(ShardSealError):
        seal_tree(tmp_path, names, tmp_path / names[0])
    assert (tmp_path / names[0]).read_text() == "x = 0\n"


def test_output_permissions_and_failure_cleanup(tmp_path):
    import os
    names = _tree(tmp_path, 2)
    target = tmp_path / "seal.json"
    seal_tree(tmp_path, names, target)
    if os.name == "posix":
        assert target.stat().st_mode & 0o077 == 0
    assert not list(tmp_path.glob(".shard-seal-*"))
    target.unlink()
    (tmp_path / names[0]).unlink()
    with pytest.raises(ShardSealError):
        seal_tree(tmp_path, names, target)
    assert not target.exists()
    assert not list(tmp_path.glob(".shard-seal-*"))


def test_seal_refuses_symlink_root_or_output_parent(tmp_path):
    names = _tree(tmp_path, 2)
    link = tmp_path.parent / (tmp_path.name + "-link")
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ShardSealError):
        seal_tree(link, names)
    other = tmp_path / "sub"
    other.mkdir()
    outlink = tmp_path / "sub-link"
    outlink.symlink_to(other, target_is_directory=True)
    with pytest.raises(ShardSealError):
        seal_tree(tmp_path, names, outlink / "seal.json")


def test_sparse_large_file_refused_before_read(tmp_path):
    from skeleton.provenance.shard_seal import MAX_SHARD_BYTES
    path = tmp_path / "shard_000.py"
    with path.open("wb") as stream:
        stream.truncate(MAX_SHARD_BYTES + 1)
    with pytest.raises(ShardSealError, match="large"):
        seal_tree(tmp_path, [path.name])


def test_shard_count_is_bounded():
    with pytest.raises(ShardSealError):
        shard_names(100001)
    with pytest.raises(ShardSealError):
        shard_names(True)
    with pytest.raises(ShardSealError):
        merkle_root([])
