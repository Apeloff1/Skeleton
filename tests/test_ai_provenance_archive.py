from __future__ import annotations
from dataclasses import replace
from skeleton.ai.runtime.provenance.archive import genesis,reattest,verify_archive_chain
from skeleton.ai.runtime.provenance.attestation import Attestation,Subject
from skeleton.ai.runtime.provenance.commitments import Commitment

def _att()->Attestation:
    return Attestation((Subject("execution",Commitment.of({"request":"r","output":"o"})),),{"runtime":"native","policy":"p1"})

def test_archive_chain_preserves_predecessor_continuity() -> None:
    att=_att()
    g0=genesis(att,year=2026)
    g1=reattest(g0,att,year=2036,reason="scheduled cryptographic refresh")
    g2=reattest(g1,att,year=2046,reason="archive migration")
    assert verify_archive_chain((g0,g1,g2))
    assert g2.generation==2

def test_archive_chain_rejects_predecessor_substitution() -> None:
    att=_att(); g0=genesis(att,year=2026); g1=reattest(g0,att,year=2036,reason="refresh")
    forged=replace(g1,predecessor=Commitment.of({"wrong":True}))
    assert not verify_archive_chain((g0,forged))

def test_archive_chain_rejects_generation_skip() -> None:
    att=_att(); g0=genesis(att,year=2026); g1=reattest(g0,att,year=2036,reason="refresh")
    assert not verify_archive_chain((g0,replace(g1,generation=2)))
