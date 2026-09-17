from __future__ import annotations

from datetime import date
from typing import Optional

import pytest

from skeleton.jeeves.science import (
    ArtifactKind,
    ClaimEdge,
    ClaimRelation,
    ClaimStatus,
    EvidenceKind,
    ResearchArtifact,
    ScientificClaim,
    ScientificEvidenceLedger,
)


def _artifact(identifier: str, year: int, *, digest: Optional[str] = None) -> ResearchArtifact:
    return ResearchArtifact(
        artifact_id=identifier,
        title=identifier,
        published=date(year, 1, 1),
        kind=ArtifactKind.PAPER,
        citation=identifier + " citation",
        content_digest=digest or ("sha256:" + identifier),
        authors=("Researcher",),
        primary_source=True,
        peer_reviewed=True,
    )


def _claim(
    identifier: str,
    artifact: str,
    year: int,
    *,
    evidence: EvidenceKind,
    domain: str = "compiler",
) -> ScientificClaim:
    return ScientificClaim(
        claim_id=identifier,
        proposition=identifier + " proposition",
        domain=domain,
        artifact_id=artifact,
        evidence_kind=evidence,
        observed_on=date(year, 1, 2),
        environment="reference",
    )


def test_ledger_rejects_duplicate_content_under_new_identity() -> None:
    ledger = ScientificEvidenceLedger()
    ledger.add_artifact(_artifact("a", 2000, digest="same"))
    with pytest.raises(ValueError, match="duplicate artifact content"):
        ledger.add_artifact(_artifact("b", 2001, digest="same"))


def test_claim_cannot_predate_its_artifact() -> None:
    ledger = ScientificEvidenceLedger()
    ledger.add_artifact(_artifact("a", 2000))
    with pytest.raises(ValueError, match="predate"):
        ledger.add_claim(
            ScientificClaim(
                claim_id="c",
                proposition="claim",
                domain="compiler",
                artifact_id="a",
                evidence_kind=EvidenceKind.OBSERVATIONAL,
                observed_on=date(1999, 12, 31),
            )
        )


def test_historical_snapshot_does_not_leak_future_evidence() -> None:
    ledger = ScientificEvidenceLedger()
    ledger.add_artifact(_artifact("old", 1991))
    ledger.add_claim(_claim("old-c", "old", 1991, evidence=EvidenceKind.MATHEMATICAL_PROOF))
    ledger.add_artifact(_artifact("new", 2026))
    ledger.add_claim(_claim("new-c", "new", 2026, evidence=EvidenceKind.CONTROLLED_BENCHMARK))

    snapshot = ledger.snapshot(through=date(2000, 12, 31))
    assert set(snapshot.claims) == {"old-c"}
    assert "new" not in snapshot.artifacts


def test_contradiction_is_preserved_instead_of_erasing_old_claim() -> None:
    ledger = ScientificEvidenceLedger()
    ledger.add_artifact(_artifact("old", 2000))
    ledger.add_artifact(_artifact("challenge", 2005))
    ledger.add_claim(_claim("old-c", "old", 2000, evidence=EvidenceKind.CONTROLLED_BENCHMARK))
    ledger.add_claim(_claim("challenge-c", "challenge", 2005, evidence=EvidenceKind.REPLICATION))
    ledger.relate(
        ClaimEdge(
            source_claim_id="challenge-c",
            target_claim_id="old-c",
            relation=ClaimRelation.CONTRADICTS,
            artifact_id="challenge",
            rationale="replication produced incompatible result",
            created_on=date(2005, 1, 3),
        )
    )

    snapshot = ledger.snapshot(through=date(2005, 12, 31))
    assert snapshot.status("old-c") == ClaimStatus.CONTESTED
    assert "old-c" in snapshot.claims
    assert snapshot.profile("old-c").contradictions == 1


def test_explicit_supersession_not_recency_changes_status() -> None:
    ledger = ScientificEvidenceLedger()
    ledger.add_artifact(_artifact("old", 2000))
    ledger.add_artifact(_artifact("new", 2026))
    ledger.add_claim(_claim("old-c", "old", 2000, evidence=EvidenceKind.MATHEMATICAL_PROOF))
    ledger.add_claim(_claim("new-c", "new", 2026, evidence=EvidenceKind.MATHEMATICAL_PROOF))

    before_edge = ledger.snapshot(through=date(2026, 1, 2))
    assert before_edge.status("old-c") == ClaimStatus.ACTIVE

    ledger.relate(
        ClaimEdge(
            source_claim_id="new-c",
            target_claim_id="old-c",
            relation=ClaimRelation.SUPERSEDES,
            artifact_id="new",
            rationale="new theorem strictly generalizes the old theorem under its assumptions",
            created_on=date(2026, 1, 3),
        )
    )
    after_edge = ledger.snapshot(through=date(2026, 1, 4))
    assert after_edge.status("old-c") == ClaimStatus.SUPERSEDED


def test_simulation_only_evidence_is_not_counted_as_empirical_support() -> None:
    ledger = ScientificEvidenceLedger()
    ledger.add_artifact(_artifact("sim", 2025))
    ledger.add_claim(_claim("sim-c", "sim", 2025, evidence=EvidenceKind.SIMULATION))
    snapshot = ledger.snapshot(through=date(2025, 12, 31))
    profile = snapshot.profile("sim-c")
    assert profile.simulation_support == 1
    assert profile.empirical_support == 0
    assert snapshot.simulation_only("sim-c")


def test_retraction_removes_source_from_evidence_profile() -> None:
    ledger = ScientificEvidenceLedger()
    ledger.add_artifact(_artifact("root", 2000))
    ledger.add_artifact(_artifact("rep", 2001))
    ledger.add_claim(_claim("root-c", "root", 2000, evidence=EvidenceKind.CONTROLLED_BENCHMARK))
    ledger.add_claim(_claim("rep-c", "rep", 2001, evidence=EvidenceKind.REPLICATION))
    ledger.relate(
        ClaimEdge(
            source_claim_id="rep-c",
            target_claim_id="root-c",
            relation=ClaimRelation.REPLICATES,
            artifact_id="rep",
            rationale="independent replication",
            created_on=date(2001, 1, 3),
        )
    )
    assert ledger.snapshot(through=date(2001, 12, 31)).profile("root-c").replications == 1
    ledger.retract_artifact("rep")
    profile = ledger.snapshot(through=date(2001, 12, 31)).profile("root-c")
    assert profile.replications == 0


def test_frontier_uses_evidence_dimensions_not_publication_year() -> None:
    ledger = ScientificEvidenceLedger()
    ledger.add_artifact(_artifact("old", 2000))
    ledger.add_artifact(_artifact("new", 2026))
    ledger.add_claim(_claim("old-c", "old", 2000, evidence=EvidenceKind.MACHINE_CHECKED_PROOF))
    ledger.add_claim(_claim("new-c", "new", 2026, evidence=EvidenceKind.SIMULATION))

    frontier = ledger.snapshot(through=date(2026, 12, 31)).undominated_frontier(domain="compiler")
    ids = {entry.claim.claim_id for entry in frontier}
    # Formal proof and simulation occupy different evidentiary dimensions.  The
    # newer simulation does not erase the older proof merely by date.
    assert "old-c" in ids


def test_ledger_fingerprint_is_deterministic() -> None:
    def build() -> ScientificEvidenceLedger:
        ledger = ScientificEvidenceLedger()
        ledger.add_artifact(_artifact("a", 2000))
        ledger.add_claim(_claim("c", "a", 2000, evidence=EvidenceKind.OBSERVATIONAL))
        return ledger

    assert build().fingerprint == build().fingerprint
