import json

import pytest

from core.epistemic_transparency import EpistemicTransparency
from core.transparency_finality import FinalityBlocked, FinalityIntegrityError, TransparencyFinality
from core.transparency_gossip import TransparencyGossip
from core.transparency_witness import (
    TransparencyWitnessLedger,
    TrustedWitness,
    WitnessRejected,
)


def _registry():
    return (
        TrustedWitness("witness-a", "operator-a"),
        TrustedWitness("witness-a2", "operator-a"),
        TrustedWitness("witness-b", "operator-b"),
        TrustedWitness("witness-c", "operator-c"),
    )


def _stack(tmp_path, *, groups=3):
    transparency = EpistemicTransparency(tmp_path / "transparency")
    gossip = TransparencyGossip(tmp_path / "gossip")
    witnesses = TransparencyWitnessLedger(tmp_path / "witnesses", trusted_witnesses=_registry(), required_groups=groups)
    finality = TransparencyFinality(tmp_path / "finality", transparency=transparency, gossip=gossip, witnesses=witnesses)
    return transparency, gossip, witnesses, finality


def _publish(transparency, authority="a", epistemic="b"):
    return transparency.publish(
        authority_root_sha256=authority * 64,
        epistemic_root_sha256=epistemic * 64,
    )


def _witness(witnesses, descriptor, witness_id):
    return witnesses.observe(
        log_id=descriptor["log_id"],
        tree_size=descriptor["tree_size"],
        root_sha256=descriptor["root_sha256"],
        witness_id=witness_id,
        transport_authenticated=True,
    )


def test_quorum_counts_independence_groups_not_raw_witness_count(tmp_path):
    transparency, _, witnesses, finality = _stack(tmp_path)
    descriptor = _publish(transparency)["transparency"]
    _witness(witnesses, descriptor, "witness-a")
    _witness(witnesses, descriptor, "witness-a2")
    _witness(witnesses, descriptor, "witness-b")

    quorum = witnesses.quorum(log_id=descriptor["log_id"], tree_size=descriptor["tree_size"], root_sha256=descriptor["root_sha256"])
    assert quorum.trusted_receipts == 3
    assert quorum.independent_groups == 2
    assert quorum.reached is False
    with pytest.raises(FinalityBlocked, match="quorum"):
        finality.finalize()

    _witness(witnesses, descriptor, "witness-c")
    quorum = witnesses.quorum(log_id=descriptor["log_id"], tree_size=descriptor["tree_size"], root_sha256=descriptor["root_sha256"])
    assert quorum.independent_groups == 3 and quorum.reached is True
    finalized = finality.finalize()
    assert finalized.tree_size == 1
    assert finalized.root_sha256 == descriptor["root_sha256"]
    assert finalized.witness_groups == ("operator-a", "operator-b", "operator-c")


def test_unknown_or_unauthenticated_witnesses_never_count(tmp_path):
    transparency, _, witnesses, _ = _stack(tmp_path)
    descriptor = _publish(transparency)["transparency"]
    with pytest.raises(WitnessRejected, match="trusted"):
        witnesses.observe(log_id=descriptor["log_id"], tree_size=1, root_sha256=descriptor["root_sha256"],
                          witness_id="unknown", transport_authenticated=True)
    with pytest.raises(WitnessRejected, match="authenticated"):
        witnesses.observe(log_id=descriptor["log_id"], tree_size=1, root_sha256=descriptor["root_sha256"],
                          witness_id="witness-a", transport_authenticated=False)
    assert witnesses.status()["receipts"] == 0


def test_equivocating_trusted_witness_freezes_finality(tmp_path):
    transparency, _, witnesses, finality = _stack(tmp_path)
    descriptor = _publish(transparency)["transparency"]
    _witness(witnesses, descriptor, "witness-a")
    _witness(witnesses, descriptor, "witness-b")
    _witness(witnesses, descriptor, "witness-c")
    assert finality.finalize().tree_size == 1

    with pytest.raises(WitnessRejected, match="equivocated"):
        witnesses.observe(log_id=descriptor["log_id"], tree_size=descriptor["tree_size"],
                          root_sha256="f" * 64, witness_id="witness-a", transport_authenticated=True)
    assert witnesses.status()["healthy"] is False
    quorum = witnesses.quorum(log_id=descriptor["log_id"], tree_size=descriptor["tree_size"], root_sha256=descriptor["root_sha256"])
    assert quorum.frozen is True and quorum.reached is False


def test_finality_chain_advances_only_on_larger_witnessed_tree(tmp_path):
    transparency, _, witnesses, finality = _stack(tmp_path)
    first = _publish(transparency, "1", "2")["transparency"]
    for wid in ("witness-a", "witness-b", "witness-c"):
        _witness(witnesses, first, wid)
    one = finality.finalize()

    second = transparency.publish(
        authority_root_sha256="3" * 64,
        epistemic_root_sha256="4" * 64,
    )["transparency"]
    for wid in ("witness-a", "witness-b", "witness-c"):
        _witness(witnesses, second, wid)
    two = finality.finalize()
    assert two.tree_size == 2 and two.sequence == 2
    assert two.previous_sha256 == one.sha256
    assert finality.latest() == two


def test_finality_ledger_tamper_is_detected(tmp_path):
    transparency, _, witnesses, finality = _stack(tmp_path)
    descriptor = _publish(transparency)["transparency"]
    for wid in ("witness-a", "witness-b", "witness-c"):
        _witness(witnesses, descriptor, wid)
    finality.finalize()

    rows = finality.path.read_text(encoding="utf-8").splitlines()
    raw = json.loads(rows[0]); raw["root_sha256"] = "9" * 64
    finality.path.write_text(json.dumps(raw, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(FinalityIntegrityError):
        TransparencyFinality(tmp_path / "finality", transparency=transparency,
                            gossip=TransparencyGossip(tmp_path / "gossip"), witnesses=witnesses)
