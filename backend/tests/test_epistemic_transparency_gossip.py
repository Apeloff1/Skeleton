import pytest

from core.epistemic_transparency import EpistemicTransparency, EpistemicTransparencyError
from core.transparency_gossip import TransparencyGossip
from core.transparency_log import TransparencyLog


def test_epistemic_checkpoint_is_included_and_reconciles_across_restart(tmp_path):
    layer = EpistemicTransparency(tmp_path)
    first = layer.publish(authority_root_sha256="a" * 64, epistemic_root_sha256="b" * 64,
                          observed_at="2026-09-14T16:00:00+00:00")
    assert first["verified"] is True
    assert first["transparency"]["tree_size"] == 1
    inclusion = layer.inclusion_for_checkpoint(first["checkpoint"]["sha256"])
    assert inclusion["verified"] is True
    assert inclusion["root_sha256"] == first["transparency"]["root_sha256"]

    replay = layer.publish(authority_root_sha256="a" * 64, epistemic_root_sha256="b" * 64,
                           observed_at="2026-09-14T16:01:00+00:00")
    assert replay["transparency"]["tree_size"] == 1

    second = layer.publish(authority_root_sha256="c" * 64, epistemic_root_sha256="d" * 64,
                           observed_at="2026-09-14T16:02:00+00:00")
    assert second["transparency"]["tree_size"] == 2
    proof = layer.consistency_from(1)
    assert proof["verified"] is True

    restored = EpistemicTransparency(tmp_path)
    health = restored.health()
    assert health["verified"] is True
    assert health["prefix_aligned"] is True
    assert health["checkpoint_entries"] == 2
    assert health["transparency_entries"] == 2
    assert health["root_sha256"] == second["transparency"]["root_sha256"]


def test_reconciliation_refuses_log_ahead_of_checkpoint_ledger(tmp_path):
    layer = EpistemicTransparency(tmp_path)
    layer.log.append({"kind": "not-a-checkpoint", "sha256": "0" * 64})
    with pytest.raises(EpistemicTransparencyError):
        layer.reconcile()


def test_gossip_detects_split_view_for_same_tree_size(tmp_path):
    gossip = TransparencyGossip(tmp_path)
    first = gossip.observe(log_id="epistemic", tree_size=8, root_sha256="1" * 64, source="observer-a")
    assert first["disposition"] == "consistent"
    second = gossip.observe(log_id="epistemic", tree_size=8, root_sha256="2" * 64, source="observer-b")
    assert second["disposition"] == "split_view"
    assert second["split_view"] is True
    status = gossip.status()
    assert status["healthy"] is False
    assert status["split_views"] == 1


def test_gossip_detects_rollback(tmp_path):
    gossip = TransparencyGossip(tmp_path)
    gossip.observe(log_id="epistemic", tree_size=10, root_sha256="3" * 64, source="observer-a")
    result = gossip.observe(log_id="epistemic", tree_size=9, root_sha256="4" * 64, source="observer-b")
    assert result["disposition"] == "rollback"
    assert gossip.status()["rollbacks"] == 1


def test_gossip_accepts_only_proven_append_extension(tmp_path):
    log = TransparencyLog(tmp_path / "log", log_id="epistemic")
    gossip = TransparencyGossip(tmp_path / "gossip")
    for i in range(2): log.append({"i": i})
    old = log.descriptor()
    gossip.observe(log_id=old["log_id"], tree_size=old["tree_size"], root_sha256=old["root_sha256"], source="observer-a")

    for i in range(2, 6): log.append({"i": i})
    new = log.descriptor(); consistency = log.consistency(old["tree_size"])
    result = gossip.observe(log_id=new["log_id"], tree_size=new["tree_size"], root_sha256=new["root_sha256"],
                            source="observer-b", consistency=consistency)
    assert result["disposition"] == "verified_extension"
    assert gossip.status()["healthy"] is True


def test_larger_root_without_consistency_proof_is_not_silently_trusted(tmp_path):
    gossip = TransparencyGossip(tmp_path)
    gossip.observe(log_id="epistemic", tree_size=3, root_sha256="5" * 64, source="observer-a")
    result = gossip.observe(log_id="epistemic", tree_size=4, root_sha256="6" * 64, source="observer-b")
    assert result["disposition"] == "unproven_extension"
    assert result["split_view"] is False
