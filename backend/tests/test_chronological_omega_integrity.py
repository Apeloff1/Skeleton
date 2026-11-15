"""Chronological Omega repair: atomicity, lifecycle, proof and persistence truth."""
import asyncio
import math

import pytest

from gameforge.omega.conductor import (
    OmegaUltraConductor, MerkleTree, sha3, QueueOverflowError,
    ConsensusError, RepetitionError, ConductorRegistry,
)
from gameforge.omega.delta_memory import DeltaMemory
from gameforge.omega.integration import OmegaFabric
from gameforge.prood.quorum import QuorumConsensus


def reference_root(leaves):
    layer = list(leaves)
    while len(layer) > 1:
        layer = [sha3(layer[i] + layer[min(i + 1, len(layer) - 1)])
                 for i in range(0, len(layer), 2)]
    return layer[0]


def test_incremental_merkle_matches_reference_and_proves_membership():
    tree = MerkleTree()
    for i in range(65):
        tree.append(sha3(str(i)))
        assert tree.root == reference_root(tree.leaves)
        for idx in (0, i // 2, i):
            proof = tree.proof(idx)
            assert tree.verify_proof(proof, tree.root, i+1)
            assert not tree.verify_proof({**proof, "leaf": sha3("tamper")}, tree.root, i+1)


@pytest.mark.asyncio
async def test_rejected_admission_never_mutates_session(monkeypatch):
    cond = OmegaUltraConductor()
    await cond.begin(total=20)
    try:
        original = cond.snapshot()
        async def reject(*args, **kwargs):
            raise ConsensusError("denied")
        monkeypatch.setattr(cond.consensus, "agree", reject)
        with pytest.raises(ConsensusError):
            await cond.deliver_context("candidate")
        assert cond.global_seq == 0 and cond.merkle.root == original["merkle_root"]
        assert cond.clock.logical == 0 and not cond._seen
        assert cond.queues.q["audit"].empty()
        monkeypatch.undo()
        cond.queues.q["audit"] = asyncio.Queue(maxsize=1)
        await cond.deliver_context("candidate")
        with pytest.raises(QueueOverflowError):
            await cond.deliver_context("next")
        assert cond.global_seq == 1 and len(cond.dag.nodes) == 1
        await cond.drain("audit")
        assert (await cond.deliver_context("next"))["global_seq"] == 2
        with pytest.raises(RepetitionError):
            await cond.deliver_response("candidate")
        assert cond.global_seq == 2
    finally:
        await cond.end()


@pytest.mark.asyncio
async def test_restart_and_resume_are_distinct_and_guardian_is_reaped():
    cond = OmegaUltraConductor()
    await cond.begin(total=10)
    first = cond._tasks[0]
    await cond.deliver_context("first")
    with pytest.raises(ValueError):
        await cond.deliver_context("bad", progress=float("nan"))
    await cond.begin(total=10, fresh=False)
    assert cond._tasks[0] is first and cond.global_seq == 1
    await cond.begin(total=10)
    assert first.done() and cond.global_seq == 0
    assert cond.queues.q["audit"].empty()
    await cond.deliver_context("first")
    current = cond._tasks[0]
    await cond.end()
    assert current.done() and not cond._tasks


def test_quorum_is_bounded_and_refuses_over_budget_faults():
    with pytest.raises(ValueError):
        QuorumConsensus(n=100_000, f=2)
    with pytest.raises(ValueError):
        QuorumConsensus(n=7, f=-1)
    q = QuorumConsensus(n=10, f=2)
    assert q.quorum_needed == 7
    assert q.agree({"x": 1}, faulty={1, 2}).decided
    assert not q.agree({"x": 1}, faulty={1, 2, 3}).decided
    assert q.agree({"x": 2}).to_dict()["scope"] == "in_process_simulation"


def test_delta_snapshot_failure_is_atomic():
    memory = DeltaMemory(dim=16)
    memory.write("key", "value")
    saved = memory.to_persist()
    for patch in ({"dim": 8192}, {"writes": -1}, {"M": [[float("nan")]]}, {"labels": ["x"*257]}):
        with pytest.raises(ValueError):
            memory.load({**saved, **patch})
        assert memory.to_persist() == saved
    restored = DeltaMemory(dim=16)
    restored.load(saved)
    assert restored.to_persist() == saved


@pytest.mark.asyncio
async def test_concurrent_agent_registration_is_single_generation(monkeypatch):
    fabric = OmegaFabric()
    monkeypatch.setattr(fabric, "_persist_enabled", lambda: False)
    same = await asyncio.gather(*(fabric.register_agent("a") for _ in range(12)))
    try:
        assert all(a is same[0] for a in same)
        assert len(fabric.agents) == 1
        assert len(same[0]._tasks) == 1
        assert not fabric.overview()["persisted"]
        assert await fabric.retire_agent("a")
        assert not same[0]._active
    finally:
        await fabric.close()
