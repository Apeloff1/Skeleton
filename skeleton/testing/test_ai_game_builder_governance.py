from __future__ import annotations

import pytest

from skeleton.ai.game_builder.atomizer import ArtifactAtom, AtomGraph, AtomGraphError
from skeleton.ai.game_builder.canon import (
    CanonAssertion,
    CanonError,
    CanonLedger,
    CharacterKnowledge,
)
from skeleton.ai.game_builder.rights import (
    RightsLedger,
    RightsState,
    SimilarityFinding,
    SimilarityRisk,
    SourceRecord,
    UseKind,
)


def _digest(label: str) -> str:
    return (label + "-" + ("0" * 64))[:64]


def test_canon_blocks_accidental_same_branch_contradiction() -> None:
    ledger = CanonLedger()
    ledger.add_assertion(
        CanonAssertion(
            "a1", "hero", "alive", True, "root", 0,
            evidence_digests=(_digest("e1"),),
        )
    )
    with pytest.raises(CanonError, match="accidental canon contradiction"):
        ledger.add_assertion(
            CanonAssertion(
                "a2", "hero", "alive", False, "root", 5,
                evidence_digests=(_digest("e2"),),
            )
        )


def test_branch_divergence_isolated_and_effective_state_is_branch_local() -> None:
    ledger = CanonLedger()
    ledger.add_assertion(CanonAssertion("root-fact", "city", "status", "safe", "root", 0))
    ledger.add_branch("route-red", fork_tick=10)
    ledger.add_assertion(CanonAssertion("red-fact", "city", "status", "fallen", "route-red", 10))

    assert ledger.effective(subject="city", predicate="status", branch_id="root", tick=20).value == "safe"
    assert ledger.effective(subject="city", predicate="status", branch_id="route-red", tick=20).value == "fallen"
    assert ledger.contradictions() == ()


def test_character_cannot_know_fact_before_it_exists_or_across_unrelated_branch() -> None:
    ledger = CanonLedger()
    ledger.add_assertion(CanonAssertion("secret", "vault", "code", 4319, "root", 20))
    with pytest.raises(CanonError, match="before it exists"):
        ledger.add_knowledge(
            CharacterKnowledge("npc", "secret", "root", 10, "overheard")
        )

    ledger.add_branch("a", fork_tick=20)
    ledger.add_branch("b", fork_tick=20)
    ledger.add_assertion(CanonAssertion("branch-secret", "boss", "weakness", "ice", "a", 25))
    with pytest.raises(CanonError, match="unrelated branch"):
        ledger.add_knowledge(
            CharacterKnowledge("npc", "branch-secret", "b", 30, "impossible")
        )


def test_character_knowledge_is_explicit_and_time_bounded() -> None:
    ledger = CanonLedger()
    ledger.add_assertion(CanonAssertion("map", "gate", "location", "north", "root", 0))
    ledger.add_knowledge(CharacterKnowledge("guide", "map", "root", 12, "saw-map"))
    assert not ledger.character_knows(
        character_id="guide", assertion_id="map", branch_id="root", tick=11
    )
    assert ledger.character_knows(
        character_id="guide", assertion_id="map", branch_id="root", tick=12
    )


def test_unknown_rights_fail_closed_and_reference_only_cannot_supply_expression() -> None:
    ledger = RightsLedger()
    ledger.register_source(
        SourceRecord(
            "unknown",
            _digest("unknown"),
            RightsState.UNKNOWN_QUARANTINE,
            frozenset(),
            "web-reference",
        )
    )
    blocked = ledger.decide_incorporation(
        source_id="unknown",
        artifact_digest=_digest("artifact"),
        use_kind=UseKind.EXPRESSIVE_INCORPORATION,
    )
    assert blocked.allowed is False

    ledger.register_source(
        SourceRecord(
            "reference",
            _digest("reference"),
            RightsState.FACTS_IDEAS_REFERENCE_ONLY,
            frozenset({UseKind.FACTS_IDEAS_REFERENCE}),
            "design-postmortem",
        )
    )
    assert ledger.decide_incorporation(
        source_id="reference",
        artifact_digest=_digest("artifact"),
        use_kind=UseKind.FACTS_IDEAS_REFERENCE,
    ).allowed
    assert not ledger.decide_incorporation(
        source_id="reference",
        artifact_digest=_digest("artifact"),
        use_kind=UseKind.EXPRESSIVE_INCORPORATION,
    ).allowed


def test_unresolved_high_similarity_risk_blocks_release_until_reviewed() -> None:
    ledger = RightsLedger()
    source = SourceRecord(
        "owned",
        _digest("owned"),
        RightsState.PROJECT_OWNED,
        frozenset(
            {
                UseKind.EXPRESSIVE_INCORPORATION,
                UseKind.RELEASE_DISTRIBUTION,
            }
        ),
        "project-source",
    )
    ledger.register_source(source)
    artifact = _digest("artifact")
    decision = ledger.decide_incorporation(
        source_id="owned",
        artifact_digest=artifact,
        use_kind=UseKind.EXPRESSIVE_INCORPORATION,
    )
    ledger.record_similarity(
        SimilarityFinding(
            "sim-1",
            artifact,
            "owned",
            "image",
            SimilarityRisk.HIGH,
            _digest("similarity"),
        )
    )
    allowed, blockers = ledger.release_gate(
        artifact_digest=artifact,
        incorporation_decisions=(decision,),
    )
    assert not allowed
    assert any("human/legal review" in item for item in blockers)

    ledger.resolve_similarity("sim-1", resolution="independent review cleared false positive")
    allowed, blockers = ledger.release_gate(
        artifact_digest=artifact,
        incorporation_decisions=(decision,),
    )
    assert allowed
    assert blockers == ()


def test_atom_graph_preserves_pixel_to_scene_parent_context() -> None:
    graph = AtomGraph()
    graph.add(ArtifactAtom("scene", "scene", _digest("scene"), "scene-1", _digest("canon")))
    graph.add(
        ArtifactAtom(
            "sprite",
            "sprite",
            _digest("sprite"),
            "scene-1",
            _digest("canon"),
            parent_id="scene",
            source_ids=("owned-source",),
        )
    )
    graph.add(
        ArtifactAtom(
            "pixel-10-12",
            "pixel",
            _digest("pixel"),
            "scene-1",
            _digest("canon"),
            parent_id="sprite",
        )
    )
    graph.assert_parent_context("pixel-10-12")
    assert graph.trace_to_root("pixel-10-12") == ("scene", "sprite", "pixel-10-12")


def test_atom_dependency_blast_radius_reaches_derived_and_child_artifacts() -> None:
    graph = AtomGraph()
    graph.add(ArtifactAtom("palette", "palette", _digest("p"), "game", _digest("canon")))
    graph.add(
        ArtifactAtom(
            "sprite",
            "sprite",
            _digest("s"),
            "game",
            _digest("canon"),
            dependency_ids=("palette",),
        )
    )
    graph.add(
        ArtifactAtom(
            "pixel",
            "pixel",
            _digest("x"),
            "game",
            _digest("canon"),
            parent_id="sprite",
        )
    )
    assert graph.blast_radius(("palette",)) == ("palette", "pixel", "sprite")


def test_atom_graph_rejects_orphan_parent_and_dependency() -> None:
    graph = AtomGraph()
    with pytest.raises(AtomGraphError, match="parent atom does not exist"):
        graph.add(
            ArtifactAtom(
                "orphan", "pixel", _digest("o"), "scene", _digest("canon"),
                parent_id="missing",
            )
        )
    with pytest.raises(AtomGraphError, match="dependency atoms do not exist"):
        graph.add(
            ArtifactAtom(
                "dependent", "material", _digest("d"), "scene", _digest("canon"),
                dependency_ids=("missing",),
            )
        )


def test_child_branch_does_not_inherit_parent_events_after_fork() -> None:
    ledger = CanonLedger()
    ledger.add_assertion(CanonAssertion("pre", "door", "state", "closed", "root", 0))
    ledger.add_branch("child", fork_tick=10)
    ledger.add_assertion(CanonAssertion("post", "weather", "storm", True, "root", 15))
    ledger.add_knowledge(CharacterKnowledge("parent-npc", "post", "root", 15, "radio"))

    assert ledger.effective(
        subject="door", predicate="state", branch_id="child", tick=30
    ).value == "closed"
    assert ledger.effective(
        subject="weather", predicate="storm", branch_id="child", tick=30
    ) is None
    assert not ledger.character_knows(
        character_id="parent-npc", assertion_id="post", branch_id="child", tick=30
    )


def test_branch_cannot_be_queried_before_fork() -> None:
    ledger = CanonLedger()
    ledger.add_branch("future-route", fork_tick=20)
    with pytest.raises(CanonError, match="before its fork"):
        ledger.effective(
            subject="x", predicate="y", branch_id="future-route", tick=19
        )
