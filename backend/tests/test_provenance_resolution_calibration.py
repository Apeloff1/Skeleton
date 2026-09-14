from core.evidence_registry import EvidenceRegistry
from core.truth_verifier import EvidenceItem, EvidenceKind
from core.truth_watch import TruthWatchFeed
from core.verified_curiosity import VerifiedCuriosityEngine


def _item(source: str, group: str, *, replication: bool = False) -> EvidenceItem:
    return EvidenceItem(
        source_id=source,
        locator=f"doi:{source}#result",
        kind=EvidenceKind.REPLICATION if replication else EvidenceKind.PRIMARY_EMPIRICAL,
        supports=True,
        independence_group=group,
        quality=1.0,
        reproducible=replication,
        peer_reviewed=True,
        primary=True,
        provenance_verified=True,
        preregistered=True,
        data_available=True,
        code_available=True,
        sample_size=500,
        uncertainty_reported=True,
    )


def test_provenance_resolution_restores_independence_only_after_both_sources_resolved(tmp_path):
    claim = "System R decreases measured latency by 9 percent."
    registry = EvidenceRegistry(tmp_path / "evidence")
    registry.register(claim, _item("study-primary", "lab-a"))
    registry.register(claim, _item("study-replication", "lab-b", replication=True))

    engine = VerifiedCuriosityEngine(tmp_path)
    initial = engine.reverify_claim(claim)
    assert initial["independence"]["raw_sources"] == 2
    assert initial["independence"]["effective_independent_sources"] == 1
    assert engine.truth_ledger.authoritative(claim) is False

    forecast = engine.record_forecast(
        claim=claim,
        probability=0.75,
        forecaster="reasoner-a",
        forecast_id="forecast-r",
    )
    assert forecast["outcome"] is None

    watch = TruthWatchFeed(tmp_path / "watch")
    watch.ingest(
        kind="source_lineage_resolved",
        target="study-primary",
        reason="publisher metadata verified",
        provider="crossref-like-provider",
        provider_cursor="1",
        provenance_verified=True,
        event_id="resolve-primary",
        payload={
            "source_kind": "primary_empirical",
            "locator": "doi:study-primary#result",
            "content_sha256": "1" * 64,
            "parent_source_ids": [],
        },
    )
    assert watch.apply_pending(engine)["applied"] == ["resolve-primary"]
    after_one = engine.reverify_claim(claim)
    assert after_one["independence"]["effective_independent_sources"] == 1
    assert engine.truth_ledger.authoritative(claim) is False
    assert engine.calibration.snapshot()[0].outcome is None

    watch.ingest(
        kind="source_lineage_resolved",
        target="study-replication",
        reason="publisher metadata verified",
        provider="crossref-like-provider",
        provider_cursor="2",
        provenance_verified=True,
        event_id="resolve-replication",
        payload={
            "source_kind": "replication",
            "locator": "doi:study-replication#result",
            "content_sha256": "2" * 64,
            "parent_source_ids": [],
        },
    )
    assert watch.apply_pending(engine)["applied"] == ["resolve-replication"]
    final = engine.reverify_claim(claim)
    assert final["independence"]["effective_independent_sources"] == 2
    assert final["state"] == "verified"
    assert engine.truth_ledger.authoritative(claim) is True

    resolved = engine.calibration.snapshot()[0]
    assert resolved.outcome is True
    assert resolved.resolution_attestation_sha256 == final["verification_attestation_sha256"]
    metrics = engine.calibration.metrics()
    assert metrics["resolved"] == 1
    assert metrics["brier_score"] == 0.0625


def test_unverified_lineage_resolution_event_cannot_mutate_source_graph(tmp_path):
    claim = "System U decreases measured latency by 5 percent."
    registry = EvidenceRegistry(tmp_path / "evidence")
    registry.register(claim, _item("legacy-u", "lab-u"))
    engine = VerifiedCuriosityEngine(tmp_path)
    before = engine.source_lineage.get("legacy-u")
    assert before is not None and before.source_kind.startswith("legacy_unresolved:")

    watch = TruthWatchFeed(tmp_path / "watch")
    watch.ingest(
        kind="source_lineage_resolved",
        target="legacy-u",
        reason="anonymous metadata claim",
        provider="untrusted-feed",
        provider_cursor="1",
        provenance_verified=False,
        event_id="untrusted-resolution",
        payload={"source_kind": "primary_empirical", "locator": "doi:legacy-u"},
    )
    report = watch.apply_pending(engine)
    assert report["held_unverified"] == ["untrusted-resolution"]
    after = engine.source_lineage.get("legacy-u")
    assert after == before


def test_lineage_resolution_event_is_idempotent_via_event_identity(tmp_path):
    claim = "System I decreases measured latency by 4 percent."
    registry = EvidenceRegistry(tmp_path / "evidence")
    registry.register(claim, _item("legacy-i", "lab-i"))
    engine = VerifiedCuriosityEngine(tmp_path)
    watch = TruthWatchFeed(tmp_path / "watch")
    payload = {"source_kind": "primary_empirical", "locator": "doi:legacy-i", "content_sha256": "3" * 64}
    first = watch.ingest(kind="source_lineage_resolved", target="legacy-i", reason="verified metadata",
                         provider="provider", provider_cursor="9", provenance_verified=True,
                         event_id="same-event", payload=payload)
    replay = watch.ingest(kind="source_lineage_resolved", target="legacy-i", reason="verified metadata",
                          provider="provider", provider_cursor="9", provenance_verified=True,
                          event_id="same-event", payload=payload)
    assert replay.sequence == first.sequence
    applied = watch.apply_pending(engine)
    assert applied["applied"] == ["same-event"]
    assert watch.stats()["checkpoints"]["provider"] == "9"
