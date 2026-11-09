from pathlib import Path

import pytest

from skeleton.research.source_lineage import (
    CitationRelation,
    CitationSpec,
    HistoricalTechnique,
    ReplicationOutcome,
    ReplicationRecord,
    ResearchClaim,
    ResearchLineageError,
    RetractionRecord,
    ResearchSourceRegistry,
    SourceStatus,
    content_digest,
)


def _ingest(registry: ResearchSourceRegistry, source_id: str, content: str, *, citations=()):
    return registry.ingest(
        source_id=source_id,
        uri=f"https://example.invalid/{source_id}",
        content=content,
        rights_refs=("rights:research-test",),
        citations=citations,
        metadata={"method": "controlled-test"},
    )


def test_research_ingestion_is_content_bound_and_deterministic() -> None:
    registry = ResearchSourceRegistry()
    expected = content_digest("baseline result")

    first = registry.ingest(
        source_id="paper-a",
        uri="https://example.invalid/paper-a",
        content="baseline result",
        rights_refs=("rights:a",),
        expected_content_digest=expected,
        metadata={"method": "trial", "negative_result": False},
    )
    second = registry.ingest(
        source_id="paper-a",
        uri="https://example.invalid/paper-a",
        content="baseline result",
        rights_refs=("rights:a",),
        expected_content_digest=expected,
        metadata={"method": "trial", "negative_result": False},
    )

    assert first == second
    assert registry.source("paper-a").content_digest == expected
    assert len(registry.sources()) == 1
    assert registry.snapshot_digest() == registry.snapshot_digest()


def test_digest_mismatch_fails_before_registry_mutation() -> None:
    registry = ResearchSourceRegistry()

    with pytest.raises(ResearchLineageError, match="does not match expectation"):
        registry.ingest(
            source_id="paper-a",
            uri="https://example.invalid/paper-a",
            content="actual",
            rights_refs=("rights:a",),
            expected_content_digest="0" * 64,
        )

    assert registry.sources() == ()


def test_forward_citation_fails_atomically() -> None:
    registry = ResearchSourceRegistry()

    with pytest.raises(ResearchLineageError, match="citation target is not registered"):
        _ingest(
            registry,
            "paper-b",
            "dependent",
            citations=(CitationSpec("paper-a", CitationRelation.SUPPORTS),),
        )

    assert registry.sources() == ()
    assert registry.citation_edges() == ()


def test_ingestion_materializes_content_bound_citation_receipts() -> None:
    registry = ResearchSourceRegistry()
    _ingest(registry, "paper-a", "baseline")

    receipt = _ingest(
        registry,
        "paper-b",
        "replication",
        citations=(
            CitationSpec(
                "paper-a",
                CitationRelation.REPLICATES,
                "evidence:replication-1",
            ),
        ),
    )

    assert receipt.source_id == "paper-b"
    assert len(receipt.citation_edge_ids) == 1
    edge = registry.citation_edges()[0]
    assert edge.edge_id == receipt.citation_edge_ids[0]
    assert edge.source_id == "paper-b"
    assert edge.target_source_id == "paper-a"
    assert edge.relation is CitationRelation.REPLICATES
    assert edge.source_digest == registry.source("paper-b").content_digest
    assert edge.target_digest == registry.source("paper-a").content_digest
    assert registry.reconcile_citation_graph().healthy


def test_duplicate_citation_in_single_ingestion_is_rejected_without_mutation() -> None:
    registry = ResearchSourceRegistry()
    _ingest(registry, "paper-a", "baseline")
    spec = CitationSpec("paper-a", CitationRelation.CITES)

    with pytest.raises(ResearchLineageError, match="duplicate citation edge"):
        _ingest(
            registry,
            "paper-b",
            "dependent",
            citations=(spec, spec),
        )

    with pytest.raises(ResearchLineageError, match="unregistered research source: paper-b"):
        registry.source("paper-b")


def test_source_status_transition_is_monotonic_and_requires_evidence() -> None:
    registry = ResearchSourceRegistry()
    _ingest(registry, "paper-a", "baseline")

    with pytest.raises(ResearchLineageError, match="requires correction refs"):
        registry.transition_source_status(
            "paper-a",
            status=SourceStatus.RETRACTED,
            correction_refs=(),
        )

    retracted = registry.transition_source_status(
        "paper-a",
        status=SourceStatus.RETRACTED,
        correction_refs=("notice:retraction-1",),
    )
    assert retracted.status is SourceStatus.RETRACTED

    with pytest.raises(ResearchLineageError, match="cannot reactivate"):
        registry.transition_source_status(
            "paper-a",
            status=SourceStatus.ACTIVE,
            correction_refs=("notice:undo",),
        )


def test_superseding_source_requires_predecessor_to_be_non_active() -> None:
    registry = ResearchSourceRegistry()
    _ingest(registry, "paper-a-v1", "old")

    with pytest.raises(ResearchLineageError, match="must be corrected or retracted"):
        registry.ingest(
            source_id="paper-a-v2",
            uri="https://example.invalid/paper-a-v2",
            content="new",
            rights_refs=("rights:a",),
            supersedes=("paper-a-v1",),
        )

    registry.transition_source_status(
        "paper-a-v1",
        status=SourceStatus.CORRECTED,
        correction_refs=("notice:correction-1",),
    )
    receipt = registry.ingest(
        source_id="paper-a-v2",
        uri="https://example.invalid/paper-a-v2",
        content="new",
        rights_refs=("rights:a",),
        supersedes=("paper-a-v1",),
    )
    assert receipt.source_id == "paper-a-v2"


def test_retraction_propagates_through_cross_source_citation_graph() -> None:
    registry = ResearchSourceRegistry()
    _ingest(registry, "paper-a", "baseline")
    _ingest(
        registry,
        "paper-b",
        "analysis of a",
        citations=(CitationSpec("paper-a", CitationRelation.SUPPORTS),),
    )
    _ingest(
        registry,
        "paper-c",
        "survey of b",
        citations=(CitationSpec("paper-b", CitationRelation.CITES),),
    )
    registry.create_claim(
        claim_id="claim-c",
        statement="survey conclusion",
        source_ids=("paper-c",),
    )

    assert registry.reconcile_claim("claim-c")
    assert registry.reconcile_claim_with_graph("claim-c")

    registry.transition_source_status(
        "paper-a",
        status=SourceStatus.RETRACTED,
        correction_refs=("notice:retraction-a",),
    )

    report = registry.reconcile_citation_graph()
    assert not report.healthy
    assert report.total_edges == 2
    assert report.valid_edges == 1
    assert "paper-a" in report.invalid_source_ids
    assert "claim-c" in report.affected_claim_ids
    assert registry.reconcile_claim("claim-c")
    assert not registry.reconcile_claim_with_graph("claim-c")


def test_direct_claim_on_retracted_source_is_invalid() -> None:
    registry = ResearchSourceRegistry()
    _ingest(registry, "paper-a", "baseline")
    registry.create_claim(
        claim_id="claim-a",
        statement="baseline conclusion",
        source_ids=("paper-a",),
    )
    registry.transition_source_status(
        "paper-a",
        status=SourceStatus.RETRACTED,
        correction_refs=("notice:retraction-a",),
    )

    assert not registry.reconcile_claim("claim-a")
    assert "claim-a" in registry.reconcile_citation_graph().affected_claim_ids


def test_current_citations_cannot_point_to_non_active_sources() -> None:
    registry = ResearchSourceRegistry()
    _ingest(registry, "paper-a", "baseline")
    registry.transition_source_status(
        "paper-a",
        status=SourceStatus.RETRACTED,
        correction_refs=("notice:retraction-a",),
    )

    with pytest.raises(ResearchLineageError, match="non-active source"):
        _ingest(
            registry,
            "paper-b",
            "dependent",
            citations=(CitationSpec("paper-a"),),
        )


def test_source_identity_conflicts_fail_closed() -> None:
    registry = ResearchSourceRegistry()
    _ingest(registry, "paper-a", "baseline")

    with pytest.raises(ResearchLineageError, match="source identity conflict"):
        _ingest(registry, "paper-a", "different content")

    assert registry.source("paper-a").content_digest == content_digest("baseline")


def test_invalid_non_finite_metadata_is_rejected() -> None:
    registry = ResearchSourceRegistry()

    with pytest.raises(ResearchLineageError, match="deterministic JSON"):
        registry.ingest(
            source_id="paper-a",
            uri="https://example.invalid/paper-a",
            content="baseline",
            rights_refs=("rights:a",),
            metadata={"score": float("nan")},
        )


def test_source_metadata_is_deeply_detached_and_immutable() -> None:
    registry = ResearchSourceRegistry()
    metadata = {
        "method": "controlled-test",
        "nested": {"tags": ["alpha", "beta"]},
    }
    registry.ingest(
        source_id="paper-meta",
        uri="https://example.invalid/paper-meta",
        content="metadata integrity",
        rights_refs=("rights:meta",),
        metadata=metadata,
    )
    before = registry.snapshot_digest()

    metadata["nested"]["tags"].append("external-mutation")
    source = registry.source("paper-meta")
    assert source.metadata["nested"]["tags"] == ("alpha", "beta")

    with pytest.raises(TypeError):
        source.metadata["new"] = "forged"  # type: ignore[index]
    with pytest.raises(TypeError):
        source.metadata["nested"]["forged"] = True  # type: ignore[index]

    assert registry.snapshot_digest() == before


def test_metadata_rejects_non_text_object_keys() -> None:
    registry = ResearchSourceRegistry()
    with pytest.raises(ResearchLineageError, match="object keys must be text"):
        registry.ingest(
            source_id="paper-bad-meta",
            uri="https://example.invalid/paper-bad-meta",
            content="metadata integrity",
            rights_refs=("rights:meta",),
            metadata={1: "not-canonical"},  # type: ignore[dict-item]
        )


def test_correction_edge_binds_successor_without_poisoning_current_claim() -> None:
    registry = ResearchSourceRegistry()
    _ingest(registry, "paper-a-v1", "old result")
    registry.transition_source_status(
        "paper-a-v1",
        status=SourceStatus.CORRECTED,
        correction_refs=("notice:correction-a",),
    )

    receipt = registry.ingest(
        source_id="paper-a-v2",
        uri="https://example.invalid/paper-a-v2",
        content="corrected result",
        rights_refs=("rights:a",),
        supersedes=("paper-a-v1",),
        citations=(
            CitationSpec(
                "paper-a-v1",
                CitationRelation.CORRECTS,
                "notice:correction-a",
            ),
        ),
    )
    registry.create_claim(
        claim_id="claim-a-v2",
        statement="corrected conclusion",
        source_ids=("paper-a-v2",),
    )

    assert len(receipt.citation_edge_ids) == 1
    report = registry.reconcile_citation_graph()
    assert report.valid_edges == 1
    assert report.stale_edge_ids == ()
    assert "paper-a-v1" in report.invalid_source_ids
    assert "claim-a-v2" not in report.affected_claim_ids
    assert registry.reconcile_claim_with_graph("claim-a-v2")


def test_correction_edge_cannot_claim_unbound_predecessor() -> None:
    registry = ResearchSourceRegistry()
    _ingest(registry, "paper-a-v1", "old result")
    registry.transition_source_status(
        "paper-a-v1",
        status=SourceStatus.RETRACTED,
        correction_refs=("notice:retraction-a",),
    )

    with pytest.raises(
        ResearchLineageError,
        match="correction edge must target a source explicitly superseded",
    ):
        registry.ingest(
            source_id="paper-b",
            uri="https://example.invalid/paper-b",
            content="unrelated replacement",
            rights_refs=("rights:b",),
            citations=(
                CitationSpec(
                    "paper-a-v1",
                    CitationRelation.CORRECTS,
                    "notice:retraction-a",
                ),
            ),
        )

    with pytest.raises(ResearchLineageError, match="unregistered research source: paper-b"):
        registry.source("paper-b")


def test_contradiction_does_not_inherit_retracted_target_invalidity() -> None:
    registry = ResearchSourceRegistry()
    _ingest(registry, "paper-a", "claim under dispute")
    _ingest(
        registry,
        "paper-b",
        "independent contradictory result",
        citations=(
            CitationSpec(
                "paper-a",
                CitationRelation.CONTRADICTS,
                "evidence:contradiction-b",
            ),
        ),
    )
    registry.create_claim(
        claim_id="claim-b",
        statement="paper b contradicts the prior result",
        source_ids=("paper-b",),
    )

    registry.transition_source_status(
        "paper-a",
        status=SourceStatus.RETRACTED,
        correction_refs=("notice:retraction-a",),
    )

    report = registry.reconcile_citation_graph()
    assert report.valid_edges == 1
    assert report.stale_edge_ids == ()
    assert "paper-a" in report.invalid_source_ids
    assert "paper-b" not in report.invalid_source_ids
    assert "claim-b" not in report.affected_claim_ids
    assert registry.reconcile_claim_with_graph("claim-b")


def test_claim_tracks_method_result_limitations_and_negative_result_separately() -> None:
    registry = ResearchSourceRegistry()
    _ingest(registry, "paper-negative", "no measurable effect")

    claim = registry.create_claim(
        claim_id="claim-negative",
        statement="intervention did not improve the measured outcome",
        source_ids=("paper-negative",),
        method="double-blind controlled trial",
        result="no statistically meaningful improvement",
        limitations=("small cohort", "single site"),
        negative_result=True,
    )

    assert claim.method == "double-blind controlled trial"
    assert claim.result == "no statistically meaningful improvement"
    assert claim.limitations == ("small cohort", "single site")
    assert claim.negative_result is True
    assert registry.reconcile_claim("claim-negative")

    with pytest.raises(ResearchLineageError, match="requires explicit result text"):
        registry.create_claim(
            claim_id="claim-invalid-negative",
            statement="negative result without result evidence",
            source_ids=("paper-negative",),
            negative_result=True,
        )


def test_status_transition_emits_one_content_bound_retraction_record() -> None:
    registry = ResearchSourceRegistry()
    _ingest(registry, "paper-status", "superseded finding")

    first = registry.transition_source_status(
        "paper-status",
        status=SourceStatus.RETRACTED,
        correction_refs=("notice:retraction-status",),
    )
    second = registry.transition_source_status(
        "paper-status",
        status=SourceStatus.RETRACTED,
        correction_refs=("notice:retraction-status",),
    )

    assert first == second
    records = registry.status_records()
    assert len(records) == 1
    assert records[0].source_id == "paper-status"
    assert records[0].source_digest == content_digest("superseded finding")
    assert records[0].status is SourceStatus.RETRACTED
    assert records[0].evidence_refs == ("notice:retraction-status",)
    assert len(records[0].transition_digest) == 64


def test_failed_replication_is_negative_evidence_not_narrative_confidence() -> None:
    registry = ResearchSourceRegistry()
    _ingest(registry, "paper-original", "positive original result")
    _ingest(registry, "paper-replication", "failed replication result")

    record = registry.record_replication(
        replication_id="replication-1",
        source_id="paper-replication",
        target_source_id="paper-original",
        outcome=ReplicationOutcome.FAILED,
        method="preregistered independent replication",
        result="effect was not reproduced",
        limitations=("lower statistical power",),
    )
    replay = registry.record_replication(
        replication_id="replication-1",
        source_id="paper-replication",
        target_source_id="paper-original",
        outcome=ReplicationOutcome.FAILED,
        method="preregistered independent replication",
        result="effect was not reproduced",
        limitations=("lower statistical power",),
    )

    assert replay == record
    assert record.negative_result is True
    assert registry.reconcile_replication("replication-1")
    assert registry.replication_summary("paper-original") == {
        "replicated": 0,
        "failed": 1,
        "mixed": 0,
        "inconclusive": 0,
        "negative_results": 1,
        "total_current": 1,
    }

    registry.transition_source_status(
        "paper-replication",
        status=SourceStatus.RETRACTED,
        correction_refs=("notice:replication-retracted",),
    )
    assert not registry.reconcile_replication("replication-1")
    assert registry.replication_summary("paper-original")["total_current"] == 0


def test_replication_identity_conflict_fails_closed() -> None:
    registry = ResearchSourceRegistry()
    _ingest(registry, "paper-original", "positive original result")
    _ingest(registry, "paper-replication", "replication result")
    registry.record_replication(
        replication_id="replication-conflict",
        source_id="paper-replication",
        target_source_id="paper-original",
        outcome=ReplicationOutcome.REPLICATED,
        method="controlled replication",
        result="effect reproduced",
    )

    with pytest.raises(ResearchLineageError, match="replication identity conflict"):
        registry.record_replication(
            replication_id="replication-conflict",
            source_id="paper-replication",
            target_source_id="paper-original",
            outcome=ReplicationOutcome.FAILED,
            method="controlled replication",
            result="effect did not reproduce",
        )


def test_historical_technique_is_mechanism_bound_and_reconciles_source_status() -> None:
    registry = ResearchSourceRegistry()
    _ingest(registry, "history-source", "historical engineering record")

    technique = registry.register_historical_technique(
        technique_id="technique-legacy-cache",
        problem="reduce repeated expensive computation",
        mechanism="retain bounded reusable intermediate state",
        failure_modes=("stale state reuse", "unbounded retention"),
        modern_analogues=("content-addressed cache", "bounded memoization"),
        source_ids=("history-source",),
    )

    assert technique.problem == "reduce repeated expensive computation"
    assert technique.mechanism == "retain bounded reusable intermediate state"
    assert technique.failure_modes == ("stale state reuse", "unbounded retention")
    assert registry.reconcile_historical_technique(technique.technique_id)

    same = registry.register_historical_technique(
        technique_id="technique-legacy-cache",
        problem="reduce repeated expensive computation",
        mechanism="retain bounded reusable intermediate state",
        failure_modes=("stale state reuse", "unbounded retention"),
        modern_analogues=("content-addressed cache", "bounded memoization"),
        source_ids=("history-source",),
    )
    assert same == technique

    registry.transition_source_status(
        "history-source",
        status=SourceStatus.CORRECTED,
        correction_refs=("notice:history-correction",),
    )
    assert not registry.reconcile_historical_technique(technique.technique_id)


def test_historical_technique_requires_failure_and_modern_analogue_evidence() -> None:
    registry = ResearchSourceRegistry()
    _ingest(registry, "history-source", "historical engineering record")

    with pytest.raises(ResearchLineageError, match="requires failure modes"):
        registry.register_historical_technique(
            technique_id="technique-incomplete",
            problem="historical problem",
            mechanism="historical mechanism",
            failure_modes=(),
            modern_analogues=("modern system",),
            source_ids=("history-source",),
        )

    with pytest.raises(ResearchLineageError, match="requires modern analogues"):
        registry.register_historical_technique(
            technique_id="technique-incomplete-modern",
            problem="historical problem",
            mechanism="historical mechanism",
            failure_modes=("known failure",),
            modern_analogues=(),
            source_ids=("history-source",),
        )


def test_registry_capacity_fails_closed_but_allows_idempotent_replay() -> None:
    registry = ResearchSourceRegistry(
        max_sources=1,
        max_claims=1,
        max_edges=1,
        max_replications=1,
        max_historical_techniques=1,
    )
    first = _ingest(registry, "paper-a", "baseline")
    replay = _ingest(registry, "paper-a", "baseline")
    assert replay == first

    with pytest.raises(ResearchLineageError, match="source registry capacity exceeded"):
        _ingest(registry, "paper-b", "second source")
    assert tuple(source.source_id for source in registry.sources()) == ("paper-a",)


def test_ingestion_capacity_failure_is_atomic_for_source_and_edges() -> None:
    registry = ResearchSourceRegistry(max_sources=3, max_edges=1)
    _ingest(registry, "paper-a", "baseline")
    _ingest(registry, "paper-b", "supporting evidence")
    registry.add_citation(
        source_id="paper-b",
        target_source_id="paper-a",
        relation=CitationRelation.SUPPORTS,
    )

    with pytest.raises(ResearchLineageError, match="citation edge registry capacity exceeded"):
        registry.ingest(
            source_id="paper-c",
            uri="https://example.invalid/paper-c",
            content="would overflow edges",
            rights_refs=("rights:c",),
            citations=(CitationSpec("paper-b", CitationRelation.CITES),),
        )

    with pytest.raises(ResearchLineageError, match="unregistered research source: paper-c"):
        registry.source("paper-c")
    assert len(registry.citation_edges()) == 1


def test_claim_replication_and_historical_capacities_fail_closed() -> None:
    registry = ResearchSourceRegistry(
        max_sources=4,
        max_claims=1,
        max_replications=1,
        max_historical_techniques=1,
    )
    _ingest(registry, "paper-a", "baseline")
    _ingest(registry, "paper-b", "replication")
    registry.create_claim(
        claim_id="claim-a",
        statement="baseline claim",
        source_ids=("paper-a",),
    )
    with pytest.raises(ResearchLineageError, match="claim registry capacity exceeded"):
        registry.create_claim(
            claim_id="claim-b",
            statement="second claim",
            source_ids=("paper-b",),
        )

    registry.record_replication(
        replication_id="replication-a",
        source_id="paper-b",
        target_source_id="paper-a",
        outcome=ReplicationOutcome.REPLICATED,
        method="independent replication",
        result="reproduced",
    )
    with pytest.raises(ResearchLineageError, match="replication registry capacity exceeded"):
        registry.record_replication(
            replication_id="replication-b",
            source_id="paper-b",
            target_source_id="paper-a",
            outcome=ReplicationOutcome.MIXED,
            method="second replication",
            result="mixed",
        )

    registry.register_historical_technique(
        technique_id="technique-a",
        problem="avoid repeated work",
        mechanism="reuse validated state",
        failure_modes=("staleness",),
        modern_analogues=("content-addressed cache",),
        source_ids=("paper-a",),
    )
    with pytest.raises(
        ResearchLineageError,
        match="historical technique registry capacity exceeded",
    ):
        registry.register_historical_technique(
            technique_id="technique-b",
            problem="avoid repeated work differently",
            mechanism="memoize bounded results",
            failure_modes=("memory pressure",),
            modern_analogues=("bounded memoization",),
            source_ids=("paper-a",),
        )


def test_source_metadata_has_hard_serialized_size_bound() -> None:
    registry = ResearchSourceRegistry()
    with pytest.raises(ResearchLineageError, match="metadata exceeds size limit"):
        registry.ingest(
            source_id="paper-big-meta",
            uri="https://example.invalid/paper-big-meta",
            content="metadata bound",
            rights_refs=("rights:meta",),
            metadata={"blob": "x" * (70 * 1024)},
        )


def test_registry_capacity_configuration_rejects_boolean_zero_and_extreme_values() -> None:
    for value in (False, 0, 1_000_001):
        with pytest.raises(ResearchLineageError, match="max_sources"):
            ResearchSourceRegistry(max_sources=value)  # type: ignore[arg-type]


def test_public_lineage_contracts_fail_closed_when_constructed_directly() -> None:
    digest = "a" * 64
    lineage = "b" * 64

    with pytest.raises(ResearchLineageError, match="source digests must align"):
        ResearchClaim(
            claim_id="claim-direct",
            statement="direct claim",
            source_ids=("paper-a",),
            source_digests=(),
            lineage_digest=lineage,
        )

    with pytest.raises(
        ResearchLineageError,
        match="negative_result must match failed outcome",
    ):
        ReplicationRecord(
            replication_id="replication-direct",
            source_id="paper-b",
            source_digest=digest,
            target_source_id="paper-a",
            target_digest=digest,
            outcome=ReplicationOutcome.REPLICATED,
            method="replication method",
            result="replicated",
            limitations=(),
            negative_result=True,
            record_digest=lineage,
        )

    with pytest.raises(
        ResearchLineageError,
        match="status transition record cannot be active",
    ):
        RetractionRecord(
            source_id="paper-a",
            source_digest=digest,
            status=SourceStatus.ACTIVE,
            evidence_refs=("notice:not-a-transition",),
            transition_digest=lineage,
        )

    with pytest.raises(
        ResearchLineageError,
        match="source ids must be unique",
    ):
        HistoricalTechnique(
            technique_id="history-direct",
            problem="historical problem",
            mechanism="historical mechanism",
            failure_modes=("failure",),
            modern_analogues=("analogue",),
            source_ids=("paper-a", "paper-a"),
            source_digests=(digest, digest),
            lineage_digest=lineage,
        )


def test_public_research_package_exports_governed_contracts() -> None:
    from skeleton import research

    assert research.ResearchSourceRegistry is ResearchSourceRegistry
    assert research.ReplicationOutcome is ReplicationOutcome
    assert research.HistoricalTechnique is HistoricalTechnique
    assert research.RetractionRecord is RetractionRecord


def test_canonical_and_ai_research_lineage_implementations_are_byte_identical() -> None:
    root = Path(__file__).resolve().parents[2]
    canonical = root / "skeleton" / "research" / "source_lineage.py"
    ai_mirror = root / "skeleton" / "ai" / "research" / "source_lineage.py"

    assert canonical.read_bytes() == ai_mirror.read_bytes()

def test_qualification_snapshot_binds_cross_source_reconciliation_and_authority():
 registry=ResearchSourceRegistry()
 _ingest(registry,"paper-a","baseline")
 _ingest(registry,"paper-b","dependent",citations=(CitationSpec("paper-a",CitationRelation.SUPPORTS),))
 registry.create_claim(claim_id="claim-b",statement="supported",source_ids=("paper-b",))
 registry.record_replication(replication_id="rep-1",source_id="paper-b",target_source_id="paper-a",outcome=ReplicationOutcome.REPLICATED,method="independent",result="reproduced")
 registry.register_historical_technique(technique_id="hist-1",problem="p",mechanism="m",failure_modes=("f",),modern_analogues=("a",),source_ids=("paper-b",))
 q=registry.qualification_snapshot()
 assert q["citation_graph_healthy"] is True
 assert q["claim_results"]=={"claim-b":True}
 assert q["replication_results"]=={"rep-1":True}
 assert q["historical_results"]=={"hist-1":True}
 assert q["authority_scope"]=="research-evidence-only"
 assert len(q["qualification_digest"])==64
 assert q==registry.qualification_snapshot()

def test_qualification_snapshot_exposes_retraction_without_self_healing_evidence():
 registry=ResearchSourceRegistry()
 _ingest(registry,"paper-a","baseline")
 _ingest(registry,"paper-b","dependent",citations=(CitationSpec("paper-a",CitationRelation.SUPPORTS),))
 registry.create_claim(claim_id="claim-b",statement="supported",source_ids=("paper-b",))
 before=registry.qualification_snapshot()
 registry.transition_source_status("paper-a",status=SourceStatus.RETRACTED,correction_refs=("notice:r",))
 after=registry.qualification_snapshot()
 assert before["qualification_digest"]!=after["qualification_digest"]
 assert after["citation_graph_healthy"] is False
 assert after["claim_results"]["claim-b"] is False
 assert after["authority_scope"]=="research-evidence-only"
