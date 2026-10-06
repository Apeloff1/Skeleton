from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _package(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    module.__package__ = name
    sys.modules[name] = module


def _load(name: str, relative: str) -> None:
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)


_package("skeleton", ROOT / "skeleton")
_package("skeleton.ai", ROOT / "skeleton" / "ai")
_package("skeleton.ai.game_builder", ROOT / "skeleton" / "ai" / "game_builder")
_load("skeleton.ai.game_builder.contracts", "skeleton/ai/game_builder/contracts.py")
_load("skeleton.ai.game_builder.atomizer", "skeleton/ai/game_builder/atomizer.py")
_load("skeleton.ai.game_builder.canon", "skeleton/ai/game_builder/canon.py")
_load("skeleton.ai.game_builder.rights", "skeleton/ai/game_builder/rights.py")

from skeleton.ai.game_builder.atomizer import (  # noqa: E402
    ArtifactAtom,
    AtomGraph,
    AtomGraphError,
    AtomSourceBinding,
)
from skeleton.ai.game_builder.contracts import (  # noqa: E402
    EvaluatorProvenance,
    canonical_digest,
)
from skeleton.ai.game_builder.canon import (  # noqa: E402
    CanonAssertion,
    CanonError,
    CanonLedger,
    CharacterKnowledge,
)
from skeleton.ai.game_builder.rights import (  # noqa: E402
    RightsError,
    RightsLedger,
    RightsState,
    SimilarityFinding,
    SimilarityRisk,
    SourceRecord,
    UseKind,
)


def _digest(label: str) -> str:
    return (label + "-" + ("0" * 64))[:64]


def _authority(
    authority_id: str,
    *evidence_refs: str,
) -> EvaluatorProvenance:
    return EvaluatorProvenance(
        evaluator_id=authority_id,
        operation_id=f"operation:{authority_id}",
        execution_id=f"execution:{authority_id}",
        execution_identity_digest=canonical_digest({"execution": authority_id}),
        finalization_intent_digest=canonical_digest({"finalization": authority_id}),
        authority_kind="deterministic_control",
        authority_identity_digest=canonical_digest({"authority": authority_id}),
        method_id="rights-review",
        source_revision=canonical_digest({"source": authority_id})[:40],
        output_evidence_refs=tuple(evidence_refs),
    )


def _canon_assertion(
    assertion_id: str,
    subject: str,
    predicate: str,
    value: object,
    branch_id: str,
    valid_from_tick: int,
    valid_to_tick: int | None = None,
    intentional_contradiction: bool = False,
    evidence_digests: tuple[str, ...] = (),
) -> CanonAssertion:
    evidence = evidence_digests or (_digest(f"canon-{assertion_id}"),)
    return CanonAssertion(
        assertion_id=assertion_id,
        subject=subject,
        predicate=predicate,
        value=value,
        branch_id=branch_id,
        valid_from_tick=valid_from_tick,
        valid_to_tick=valid_to_tick,
        evaluator_provenance=_authority(
            f"canon-{assertion_id}-authority",
            *evidence,
        ),
        intentional_contradiction=intentional_contradiction,
        evidence_digests=evidence,
    )


def _source_binding(source_id: str) -> AtomSourceBinding:
    evidence = _digest(f"lineage-{source_id}")
    return AtomSourceBinding(
        source_id=source_id,
        evidence_digest=evidence,
        authority_provenance=_authority(
            f"lineage-{source_id}-authority",
            evidence,
        ),
    )


def test_canon_blocks_accidental_same_branch_contradiction() -> None:
    ledger = CanonLedger()
    ledger.add_assertion(
        _canon_assertion(
            "a1", "hero", "alive", True, "root", 0,
            evidence_digests=(_digest("e1"),),
        )
    )
    with pytest.raises(CanonError, match="accidental canon contradiction"):
        ledger.add_assertion(
            _canon_assertion(
                "a2", "hero", "alive", False, "root", 5,
                evidence_digests=(_digest("e2"),),
            )
        )


def test_branch_divergence_isolated_and_effective_state_is_branch_local() -> None:
    ledger = CanonLedger()
    ledger.add_assertion(
        _canon_assertion("root-fact", "city", "status", "safe", "root", 0)
    )
    ledger.add_branch("route-red", fork_tick=10)
    ledger.add_assertion(
        _canon_assertion("red-fact", "city", "status", "fallen", "route-red", 10)
    )

    assert ledger.effective(
        subject="city", predicate="status", branch_id="root", tick=20
    ).value == "safe"
    assert ledger.effective(
        subject="city", predicate="status", branch_id="route-red", tick=20
    ).value == "fallen"
    assert ledger.contradictions() == ()


def test_character_cannot_know_fact_before_it_exists_or_across_unrelated_branch() -> None:
    ledger = CanonLedger()
    ledger.add_assertion(
        _canon_assertion("secret", "vault", "code", 4319, "root", 20)
    )
    with pytest.raises(CanonError, match="before it exists"):
        ledger.add_knowledge(
            CharacterKnowledge("npc", "secret", "root", 10, "overheard")
        )

    ledger.add_branch("a", fork_tick=20)
    ledger.add_branch("b", fork_tick=20)
    ledger.add_assertion(
        _canon_assertion("branch-secret", "boss", "weakness", "ice", "a", 25)
    )
    with pytest.raises(CanonError, match="unrelated branch"):
        ledger.add_knowledge(
            CharacterKnowledge("npc", "branch-secret", "b", 30, "impossible")
        )


def test_character_knowledge_is_explicit_and_time_bounded() -> None:
    ledger = CanonLedger()
    ledger.add_assertion(
        _canon_assertion("map", "gate", "location", "north", "root", 0)
    )
    ledger.add_knowledge(
        CharacterKnowledge("guide", "map", "root", 12, "saw-map")
    )
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
        frozenset({
            UseKind.EXPRESSIVE_INCORPORATION,
            UseKind.RELEASE_DISTRIBUTION,
        }),
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
            _authority("similarity-judge", _digest("similarity")),
        )
    )
    allowed, blockers = ledger.release_gate(
        artifact_digest=artifact,
        incorporation_decisions=(decision,),
    )
    assert not allowed
    assert any("human/legal review" in item for item in blockers)

    ledger.resolve_similarity(
        "sim-1",
        resolution="independent review cleared false positive",
        resolution_evidence_digest=_digest("resolution"),
        resolution_authority=_authority("rights-reviewer", _digest("resolution")),
    )
    allowed, blockers = ledger.release_gate(
        artifact_digest=artifact,
        incorporation_decisions=(decision,),
    )
    assert allowed
    assert blockers == ()


def test_similarity_finding_rejects_unattributed_detection_evidence() -> None:
    with pytest.raises(RightsError, match="similarity evidence must be referenced"):
        SimilarityFinding(
            "sim-unbound",
            _digest("artifact"),
            "owned",
            "image",
            SimilarityRisk.HIGH,
            _digest("similarity"),
            _authority("similarity-judge", _digest("different")),
        )


def test_similarity_resolution_requires_attributed_review_evidence() -> None:
    ledger = RightsLedger()
    ledger.register_source(
        SourceRecord(
            "owned",
            _digest("owned"),
            RightsState.PROJECT_OWNED,
            frozenset({UseKind.RELEASE_DISTRIBUTION}),
            "project-source",
        )
    )
    finding = SimilarityFinding(
        "sim-resolution",
        _digest("artifact"),
        "owned",
        "image",
        SimilarityRisk.HIGH,
        _digest("similarity"),
        _authority("similarity-judge", _digest("similarity")),
    )
    ledger.record_similarity(finding)
    with pytest.raises(RightsError, match="resolution evidence must be referenced"):
        ledger.resolve_similarity(
            "sim-resolution",
            resolution="cleared",
            resolution_evidence_digest=_digest("resolution"),
            resolution_authority=_authority(
                "rights-reviewer",
                _digest("different-resolution"),
            ),
        )


def test_high_risk_similarity_cannot_be_self_cleared_by_detector() -> None:
    ledger = RightsLedger()
    ledger.register_source(
        SourceRecord(
            "owned-self-review",
            _digest("owned-self-review"),
            RightsState.PROJECT_OWNED,
            frozenset({UseKind.RELEASE_DISTRIBUTION}),
            "project-source",
        )
    )
    finding = SimilarityFinding(
        "sim-self-review",
        _digest("artifact-self-review"),
        "owned-self-review",
        "image",
        SimilarityRisk.HIGH,
        _digest("similarity-self-review"),
        _authority("same-reviewer", _digest("similarity-self-review")),
    )
    ledger.record_similarity(finding)
    with pytest.raises(RightsError, match="requires independent authority"):
        ledger.resolve_similarity(
            "sim-self-review",
            resolution="self-cleared",
            resolution_evidence_digest=_digest("resolution-self-review"),
            resolution_authority=_authority(
                "same-reviewer",
                _digest("resolution-self-review"),
            ),
        )


def test_canon_assertion_rejects_unattributed_evidence() -> None:
    evidence = _digest("canon-unbound")
    with pytest.raises(CanonError, match="referenced by assertion authority"):
        CanonAssertion(
            assertion_id="canon-unbound",
            subject="hero",
            predicate="state",
            value="alive",
            branch_id="root",
            valid_from_tick=0,
            evaluator_provenance=_authority(
                "canon-wrong-authority",
                _digest("other-canon-evidence"),
            ),
            evidence_digests=(evidence,),
        )


def test_atom_source_requires_lineage_binding() -> None:
    with pytest.raises(AtomGraphError, match="requires exactly one lineage binding"):
        ArtifactAtom(
            "sprite-unbound",
            "sprite",
            _digest("sprite-unbound"),
            "scene-1",
            _digest("canon"),
            source_ids=("owned-source",),
        )


def test_atom_source_binding_rejects_unattributed_lineage_evidence() -> None:
    evidence = _digest("lineage-owned-source")
    with pytest.raises(AtomGraphError, match="referenced by lineage authority"):
        AtomSourceBinding(
            source_id="owned-source",
            evidence_digest=evidence,
            authority_provenance=_authority(
                "lineage-wrong-authority",
                _digest("other-lineage"),
            ),
        )


def test_atom_graph_preserves_pixel_to_scene_parent_context() -> None:
    graph = AtomGraph()
    graph.add(
        ArtifactAtom(
            "scene", "scene", _digest("scene"), "scene-1", _digest("canon")
        )
    )
    graph.add(
        ArtifactAtom(
            "sprite",
            "sprite",
            _digest("sprite"),
            "scene-1",
            _digest("canon"),
            parent_id="scene",
            source_ids=("owned-source",),
            source_bindings=(_source_binding("owned-source"),),
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
    assert graph.trace_to_root("pixel-10-12") == (
        "scene", "sprite", "pixel-10-12"
    )


def test_atom_dependency_blast_radius_reaches_derived_and_child_artifacts() -> None:
    graph = AtomGraph()
    graph.add(
        ArtifactAtom("palette", "palette", _digest("p"), "game", _digest("canon"))
    )
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
                "orphan",
                "pixel",
                _digest("o"),
                "scene",
                _digest("canon"),
                parent_id="missing",
            )
        )
    with pytest.raises(AtomGraphError, match="dependency atoms do not exist"):
        graph.add(
            ArtifactAtom(
                "dependent",
                "material",
                _digest("d"),
                "scene",
                _digest("canon"),
                dependency_ids=("missing",),
            )
        )


def test_child_branch_does_not_inherit_parent_events_after_fork() -> None:
    ledger = CanonLedger()
    ledger.add_assertion(
        _canon_assertion("pre", "door", "state", "closed", "root", 0)
    )
    ledger.add_branch("child", fork_tick=10)
    ledger.add_assertion(
        _canon_assertion("post", "weather", "storm", True, "root", 15)
    )
    ledger.add_knowledge(
        CharacterKnowledge("parent-npc", "post", "root", 15, "radio")
    )

    assert ledger.effective(
        subject="door", predicate="state", branch_id="child", tick=30
    ).value == "closed"
    assert ledger.effective(
        subject="weather", predicate="storm", branch_id="child", tick=30
    ) is None
    assert not ledger.character_knows(
        character_id="parent-npc",
        assertion_id="post",
        branch_id="child",
        tick=30,
    )


def test_branch_cannot_be_queried_before_fork() -> None:
    ledger = CanonLedger()
    ledger.add_branch("future-route", fork_tick=20)
    with pytest.raises(CanonError, match="before its fork"):
        ledger.effective(
            subject="x",
            predicate="y",
            branch_id="future-route",
            tick=19,
        )
