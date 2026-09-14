from dataclasses import replace
import json

import pytest

from core.transparency_log import (
    TransparencyIntegrityError,
    TransparencyLog,
    merkle_root,
    verify_consistency,
    verify_inclusion,
)


def test_every_leaf_has_verifiable_inclusion_proof(tmp_path):
    log = TransparencyLog(tmp_path)
    entries = [log.append({"sequence": i, "value": f"v-{i}"}) for i in range(7)]
    descriptor = log.descriptor()
    assert descriptor["tree_size"] == 7
    assert descriptor["root_sha256"] == merkle_root([entry.leaf_sha256 for entry in entries])
    for index in range(7):
        proof = log.inclusion(index)
        assert verify_inclusion(proof) is True
        assert proof.root_sha256 == descriptor["root_sha256"]


def test_inclusion_proof_rejects_tampering(tmp_path):
    log = TransparencyLog(tmp_path)
    for i in range(4): log.append({"i": i})
    proof = log.inclusion(2)
    assert verify_inclusion(proof) is True
    siblings = list(proof.siblings)
    siblings[0] = "0" * 64
    assert verify_inclusion(replace(proof, siblings=tuple(siblings))) is False
    assert verify_inclusion(replace(proof, leaf_sha256="f" * 64)) is False


def test_old_pinned_root_verifies_append_only_extension(tmp_path):
    log = TransparencyLog(tmp_path)
    for i in range(3): log.append({"i": i})
    old = log.descriptor()
    for i in range(3, 9): log.append({"i": i})
    proof = log.consistency(old["tree_size"])
    assert proof.old_root_sha256 == old["root_sha256"]
    assert proof.new_size == 9
    assert verify_consistency(proof) is True
    altered = list(proof.appended_leaf_hashes); altered[-1] = "a" * 64
    assert verify_consistency(replace(proof, appended_leaf_hashes=tuple(altered))) is False


def test_zero_to_nonzero_consistency_is_verifiable(tmp_path):
    log = TransparencyLog(tmp_path)
    for i in range(3): log.append({"i": i})
    proof = log.consistency(0)
    assert proof.old_size == 0
    assert verify_consistency(proof) is True


def test_independent_log_instances_share_one_process_safe_history(tmp_path):
    first = TransparencyLog(tmp_path)
    second = TransparencyLog(tmp_path)
    first.append({"writer": "a", "n": 1})
    second.append({"writer": "b", "n": 2})
    first.append({"writer": "a", "n": 3})
    assert first.descriptor() == second.descriptor()
    assert [row.index for row in second.snapshot()] == [0, 1, 2]


def test_duplicate_payload_is_idempotent(tmp_path):
    log = TransparencyLog(tmp_path)
    first = log.append({"checkpoint": "same"})
    replay = log.append({"checkpoint": "same"})
    assert replay == first
    assert log.descriptor()["tree_size"] == 1


def test_disk_tampering_fails_closed(tmp_path):
    log = TransparencyLog(tmp_path)
    log.append({"truth": "original"})
    row = json.loads(log.path.read_text(encoding="utf-8"))
    row["payload"]["truth"] = "rewritten"
    log.path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(TransparencyIntegrityError):
        TransparencyLog(tmp_path)
