import pytest

from core.claim_dependency_graph import ClaimDependencyGraph
from core.evidence_registry import EvidenceRegistry
from core.source_independence import SourceIndependenceAnalyzer
from core.source_lineage import SourceLineageGraph, SourceLineageIntegrityError
from core.truth_verifier import EvidenceItem, EvidenceKind
from core.truth_watch import TruthWatchFeed
from core.verified_curiosity import VerifiedCuriosityEngine


def _item(source, group, *, replication=False):
    return EvidenceItem(
        source_id=source, locator=f"doi:{source}",
        kind=EvidenceKind.REPLICATION if replication else EvidenceKind.PRIMARY_EMPIRICAL,
        supports=True, independence_group=group, quality=1.0, reproducible=replication,
        peer_reviewed=True, primary=True, provenance_verified=True, preregistered=True,
        data_available=True, code_available=True, sample_size=500, uncertainty_reported=True,
    )


def _row(source, group, *, replication=False, parents=()):
    return {
        "source_id": source, "source": source, "locator": f"doi:{source}",
        "kind": "replication" if replication else "primary_empirical",
        "supports": True, "independence_group": group, "quality": 1.0,
        "reproducible": replication, "peer_reviewed": True, "primary": True,
        "provenance_verified": True, "preregistered": True, "data_available": True,
        "code_available": True, "sample_size": 500, "uncertainty_reported": True,
        "parent_source_ids": list(parents),
    }


def _promote(engine, claim, prefix, *, dependencies=()):
    engine.observe_prompt(f"{prefix} verification")
    inquiry = engine.next_inquiry(); assert inquiry is not None
    record = engine.accept_finding(inquiry, {
        "summary": "Independent primary and replication evidence.",
        "claims": [claim], "falsifiable": {claim: True},
        "claim_dependencies": {claim: list(dependencies)},
        "claim_evidence": {claim: [
            _row(f"{prefix}-primary", f"{prefix}-lab-a"),
            _row(f"{prefix}-replication", f"{prefix}-lab-b", replication=True),
        ]},
    })
    return record


def test_shared_upstream_dataset_collapses_nominally_independent_papers(tmp_path):
    lineage = SourceLineageGraph(tmp_path / "lineage")
    lineage.register("dataset", source_kind="official_data", locator="dataset:v1")
    lineage.register("paper-a", source_kind="primary_empirical", locator="doi:a", parent_ids=("dataset",))
    lineage.register("paper-b", source_kind="replication", locator="doi:b", parent_ids=("dataset",))
    analyzer = SourceIndependenceAnalyzer(lineage)
    collapsed, report = analyzer.collapse((_item("paper-a", "lab-a"), _item("paper-b", "lab-b", replication=True)))
    assert report.raw_sources == 2
    assert report.effective_independent_sources == 1
    assert collapsed[0].independence_group == collapsed[1].independence_group
    assert "shared_upstream_source" in report.clusters[0].reasons


def test_legacy_unknown_ancestry_cannot_manufacture_replication(tmp_path):
    registry = EvidenceRegistry(tmp_path / "evidence")
    claim = "System X decreases measured error rate by 5 percent."
    registry.register(claim, _item("legacy-a", "claimed-lab-a"))
    registry.register(claim, _item("legacy-b", "claimed-lab-b", replication=True))
    engine = VerifiedCuriosityEngine(tmp_path)
    result = engine.reverify_claim(claim)
    assert result["independence"]["raw_sources"] == 2
    assert result["independence"]["effective_independent_sources"] == 1
    assert set(result["independence"]["unresolved_sources"]) == {"legacy-a", "legacy-b"}
    assert result["authoritative"] is False
    assert result["state"] != "verified"


def test_explicit_provenance_resolves_legacy_placeholder_without_rewriting_history(tmp_path):
    lineage = SourceLineageGraph(tmp_path)
    lineage.register("legacy-paper", source_kind="legacy_unresolved:primary_empirical", locator="doi:paper")
    lineage.register("dataset", source_kind="official_data", locator="dataset:v2")
    assert lineage.stats()["unresolved_lineage"] == 1
    resolved = lineage.resolve_legacy("legacy-paper", source_kind="primary_empirical", locator="doi:paper", parent_ids=("dataset",))
    assert resolved.parent_ids == ("dataset",)
    assert lineage.stats()["unresolved_lineage"] == 0
    with pytest.raises(SourceLineageIntegrityError):
        lineage.resolve_legacy("legacy-paper", source_kind="replication", locator="doi:paper")


def test_claim_dependency_revocation_cascades_without_erasing_history(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path)
    premise = "Measured intervention A decreases latency by 8 percent."
    conclusion = "Because intervention A decreases latency, deployment B meets the latency threshold."
    assert _promote(engine, premise, "premise").claims == (premise,)
    child = _promote(engine, conclusion, "conclusion", dependencies=(premise,))
    assert child.claims == (conclusion,)
    assert engine.truth_ledger.authoritative(premise) is True
    assert engine.truth_ledger.authoritative(conclusion) is True
    result = engine.retract_source("premise-primary", "instrument calibration invalid")
    assert conclusion in result["dependent_claims_revoked"]
    assert engine.truth_ledger.authoritative(premise) is False
    assert engine.truth_ledger.authoritative(conclusion) is False
    assert conclusion in engine.fabric.get(child.id).claims


def test_dependency_gate_blocks_verified_evidence_when_premise_is_unknown(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path)
    child = "Derived claim C decreases measured cost by 4 percent."
    record = _promote(engine, child, "derived", dependencies=("Unknown premise P is measured true.",))
    assert record.claims == ()
    assert engine.truth_ledger.authoritative(child) is False
    assert any("UNVERIFIED" in question for question in record.questions)


def test_claim_dependency_cycles_fail_closed(tmp_path):
    graph = ClaimDependencyGraph(tmp_path)
    graph.register("Claim A is measured true.", ("Claim B is measured true.",))
    with pytest.raises(ValueError, match="cycle"):
        graph.register("Claim B is measured true.", ("Claim A is measured true.",))


def test_unverified_watch_retraction_is_held_without_side_effect(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path / "engine")
    claim = "System Y decreases measured latency by 6 percent."
    _promote(engine, claim, "watch")
    feed = TruthWatchFeed(tmp_path / "watch-feed")
    event = feed.ingest(kind="source_retracted", target="watch-primary", reason="untrusted alert",
                        provider="anonymous-feed", provider_cursor="1", provenance_verified=False, event_id="evt-1")
    duplicate = feed.ingest(kind="source_retracted", target="watch-primary", reason="untrusted alert",
                            provider="anonymous-feed", provider_cursor="1", provenance_verified=False, event_id="evt-1")
    assert duplicate.sequence == event.sequence
    report = feed.apply_pending(engine)
    assert report["held_unverified"] == ["evt-1"]
    assert engine.truth_ledger.authoritative(claim) is True


def test_verified_watch_retraction_revokes_authority_and_advances_checkpoint(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path / "engine")
    claim = "System Z decreases measured latency by 7 percent."
    _promote(engine, claim, "verified-watch")
    feed = TruthWatchFeed(tmp_path / "watch-feed")
    feed.ingest(kind="source_retracted", target="verified-watch-primary", reason="publisher retraction",
                provider="verified-publisher", provider_cursor="cursor-42", provenance_verified=True, event_id="evt-42")
    report = feed.apply_pending(engine)
    assert report["applied"] == ["evt-42"]
    assert engine.truth_ledger.authoritative(claim) is False
    stats = feed.stats()
    assert stats["checkpoints"]["verified-publisher"] == "cursor-42"
    assert stats["states"]["applied"] == 1
    restored = TruthWatchFeed(tmp_path / "watch-feed")
    assert restored.stats()["checkpoints"]["verified-publisher"] == "cursor-42"
    assert restored.snapshot()[0].disposition == "applied"
