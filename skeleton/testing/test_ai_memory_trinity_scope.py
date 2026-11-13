from __future__ import annotations

import pytest

from skeleton.kernel.ids import UserId
from skeleton.memory.cag import CAGStore
from skeleton.memory.mag import MAGStore
from skeleton.memory.rag import InMemoryTFIDFStore
from skeleton.memory.trinity import MemoryTrinity
from skeleton.memory.types import MemoryChunk, MemoryQueryResult


def _trinity():
    user=UserId.new()
    rag=InMemoryTFIDFStore()
    rag.add(
        MemoryChunk(
            id="fact-allowed",
            text="alpha governed memory fact",
            metadata={"tenant_id":"tenant-a"},
            source_tier="rag",
        )
    )
    rag.add(
        MemoryChunk(
            id="fact-other",
            text="alpha other tenant fact",
            metadata={"tenant_id":"tenant-b"},
            source_tier="rag",
        )
    )
    cag=CAGStore()
    cag.create_persona("tutor","Tutor","patient alpha tutor")
    cag.add(
        MemoryChunk(
            id="persona-alpha",
            text="alpha persona guidance",
            metadata={"topic":"alpha","importance":1.0},
            source_tier="cag",
        )
    )
    mag=MAGStore(user_id=user)
    mag.add_episode("alpha personal history",tags={"alpha"})
    return MemoryTrinity(rag=rag,cag=cag,mag=mag),user


def test_scoped_trinity_enforces_each_memory_authority_before_fusion() -> None:
    trinity,user=_trinity()

    result=trinity.query_scoped(
        "alpha",
        rag_scope={"tenant_id":"tenant-a"},
        persona_id="tutor",
        user_id=str(user),
    )

    assert [item.chunk.id for item in result.facts]==["fact-allowed"]
    assert result.persona_frame
    assert result.personal_history
    assert all("fact-other" not in ref for ref in result.provenance_chain)


def test_scoped_trinity_rejects_wrong_persona_boundary() -> None:
    trinity,user=_trinity()

    with pytest.raises(ValueError,match="persona scope"):
        trinity.query_scoped(
            "alpha",
            rag_scope={"tenant_id":"tenant-a"},
            persona_id="other-persona",
            user_id=str(user),
        )


def test_scoped_trinity_wrong_user_yields_no_personal_history() -> None:
    trinity,_=_trinity()

    result=trinity.query_scoped(
        "alpha",
        rag_scope={"tenant_id":"tenant-a"},
        persona_id="tutor",
        user_id=str(UserId.new()),
    )

    assert result.personal_history==[]
    assert result.facts
    assert result.persona_frame


def test_trinity_fusion_tie_break_is_deterministic() -> None:
    trinity,_=_trinity()

    def tied_results() -> list[MemoryQueryResult]:
        # Fresh results avoid MAG's intentional access-count rehearsal updates.
        return [
            MemoryQueryResult(
                chunk=MemoryChunk(
                    id=chunk_id,
                    text=f"unique {chunk_id}",
                    metadata={},
                    source_tier="rag",
                ),
                score=1.0,
                rank=rank,
            )
            for rank,chunk_id in enumerate(("z","a"),start=1)
        ]

    first=trinity._compose("alpha",tied_results(),[],[],top_k_per_tier=3)
    second=trinity._compose("alpha",tied_results(),[],[],top_k_per_tier=3)

    assert first.provenance_chain==second.provenance_chain
    assert first.provenance_chain==[
        "rag:a(score=1.000)",
        "rag:z(score=1.000)",
    ]


def test_scoped_trinity_rehearsal_changes_score_not_authority() -> None:
    trinity,user=_trinity()

    first=trinity.query_scoped(
        "alpha",
        rag_scope={"tenant_id":"tenant-a"},
        persona_id="tutor",
        user_id=str(user),
    )
    second=trinity.query_scoped(
        "alpha",
        rag_scope={"tenant_id":"tenant-a"},
        persona_id="tutor",
        user_id=str(user),
    )

    # MAG intentionally increases recall score after each access. Provenance
    # order may change, but neither the memory identities nor scope may drift.
    def identities(provenance: list[str]) -> set[str]:
        return {ref.split("(score=",1)[0] for ref in provenance}

    assert identities(first.provenance_chain)==identities(second.provenance_chain)
    assert [item.chunk.id for item in first.facts]==["fact-allowed"]
    assert [item.chunk.id for item in second.facts]==["fact-allowed"]
    assert first.personal_history[0].chunk.id==second.personal_history[0].chunk.id
    assert second.personal_history[0].score>first.personal_history[0].score


def test_scoped_trinity_rejects_empty_authority_scope() -> None:
    trinity,user=_trinity()
    with pytest.raises(ValueError,match="rag_scope"):
        trinity.query_scoped(
            "alpha",
            rag_scope={},
            persona_id="tutor",
            user_id=str(user),
        )
