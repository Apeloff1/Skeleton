"""Claim-evidence matrix with explicit review and source-independence gates.

This is *not* factual verification, confidence calibration or automatic
promotion. A score is a deterministic triage signal derived from asserted
relevance, not a probability that the assertion is true.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable
import re

from .contracts import CampaignMandate, bounded_text, digest, exact_digest, finite, integer
from .evidence import CampaignPassage
from .references import CitationReport


_ID = re.compile(r"[a-z][a-z0-9_-]{2,63}\Z", re.ASCII)


@dataclass(frozen=True)
class ResearchClaim:
    claim_id: str
    statement: str
    objective_id: str
    version: int = 1

    def __post_init__(self):
        if not isinstance(self.claim_id, str) or not _ID.fullmatch(self.claim_id):
            raise ValueError("invalid research claim ID")
        bounded_text(self.statement, "research statement", 2048)
        if not isinstance(self.objective_id, str) or not _ID.fullmatch(self.objective_id):
            raise ValueError("invalid objective reference")
        integer(self.version, "claim version", 1, 2**31 - 1)


@dataclass(frozen=True)
class ClaimCitation:
    claim_id: str
    source_id: str
    passage_hash: str
    stance: str
    relevance: float
    rationale: str

    def __post_init__(self):
        if not isinstance(self.claim_id, str) or not _ID.fullmatch(self.claim_id):
            raise ValueError("invalid citation claim")
        exact_digest(self.source_id, "citation source ID")
        exact_digest(self.passage_hash, "citation passage")
        if self.stance not in ("supports", "refutes", "context", "uncertain"):
            raise ValueError("unknown evidence stance")
        finite(self.relevance, "assertion relevance", 0, 1)
        bounded_text(self.rationale, "citation rationale", 1024)


@dataclass(frozen=True)
class IndependenceAttestation:
    group_id: str
    source_ids: tuple[str, ...]
    operator_reference: str
    provenance_reviewed: bool

    def __post_init__(self):
        if not isinstance(self.group_id, str) or not _ID.fullmatch(self.group_id):
            raise ValueError("invalid independence group")
        if not isinstance(self.source_ids, tuple) or not 1 <= len(self.source_ids) <= 16:
            raise ValueError("invalid group size")
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("duplicate group member")
        for member in self.source_ids:
            exact_digest(member, "attested source")
        bounded_text(self.operator_reference, "review authority reference", 256)
        if type(self.provenance_reviewed) is not bool:
            raise ValueError("source independence review must be explicit")


@dataclass(frozen=True)
class ClaimAssessment:
    claim_id: str
    objective_id: str
    support_sources: tuple[str, ...]
    refute_sources: tuple[str, ...]
    context_sources: tuple[str, ...]
    unconfirmed_citations: int
    attested_support_groups: int
    attested_refute_groups: int
    conflicted: bool
    review_state: str
    support_triage_score: float
    refute_triage_score: float
    reasoning: tuple[str, ...]
    verified_fact: bool = False


@dataclass(frozen=True)
class ClaimReviewMatrix:
    mandate_digest: str
    claims: tuple[ClaimAssessment, ...]
    unbound_citations: int
    attestation_count: int
    matrix_digest: str
    authorized_for_model_training: bool = False
    authorized_for_publication: bool = False


def assess_claim_matrix(
    mandate: CampaignMandate,
    claims: Iterable[ResearchClaim],
    citations: Iterable[ClaimCitation],
    passages: Iterable[CampaignPassage],
    verification: CitationReport,
    attestations: Iterable[IndependenceAttestation] = (),
    *,
    now: float,
    authorized: bool,
) -> ClaimReviewMatrix:
    mandate.admit(now=now, authorized=authorized)
    claim_rows = tuple(claims)
    cite_rows = tuple(citations)
    passage_rows = tuple(passages)
    groups = tuple(attestations)
    if (
        not 1 <= len(claim_rows) <= 64
        or len(cite_rows) > 256
        or len(passage_rows) > 128
        or len(groups) > 64
    ):
        raise ValueError("claim-review capacity exceeded")
    if not isinstance(verification, CitationReport):
        raise TypeError("canonical source revalidation required")
    by_claim = {}
    for claim in claim_rows:
        if not isinstance(claim, ResearchClaim):
            raise TypeError("claim contract required")
        if claim.claim_id in by_claim:
            raise ValueError("duplicate claim")
        by_claim[claim.claim_id] = claim
    by_passage = {}
    for passage in passage_rows:
        if not isinstance(passage, CampaignPassage):
            raise TypeError("typed passage required")
        key = passage.source_id, passage.passage_hash
        if key in by_passage:
            raise ValueError("ambiguous passage hash at source")
        by_passage[key] = passage
    by_check = {}
    for check in verification.entries:
        key = check.source_id, check.passage_hash
        if key in by_check:
            raise ValueError("ambiguous current citation check")
        by_check[key] = check
    if set(by_check) != set(by_passage):
        raise PermissionError("current-source check not bound to exact passage set")
    for key, passage in by_passage.items():
        check = by_check[key]
        if check.source_revision != passage.source_content_hash:
            raise PermissionError("claim citation source revision not checked")
    membership: dict[str, str] = {}
    for group in groups:
        if not isinstance(group, IndependenceAttestation):
            raise TypeError("independence group required")
        if group.group_id in membership.values():
            # A group with several sources is fine; distinct groups must be
            # disjoint so mirrors cannot inflate independent corroboration.
            if any(member in membership for member in group.source_ids):
                raise ValueError("overlapping independence evidence groups")
        for member in group.source_ids:
            if member in membership:
                raise ValueError("source claimed by multiple independence groups")
            membership[member] = group.group_id if group.provenance_reviewed else ""
    seen = set()
    related: dict[str, list[tuple[ClaimCitation, bool]]] = {
        cid: [] for cid in by_claim
    }
    orphan = 0
    for cite in cite_rows:
        if not isinstance(cite, ClaimCitation):
            raise TypeError("typed citation required")
        if cite.claim_id not in related:
            raise ValueError("citation refers to unknown claim")
        identity = cite.claim_id, cite.source_id, cite.passage_hash, cite.stance
        if identity in seen:
            raise ValueError("duplicate claim evidence")
        seen.add(identity)
        key = cite.source_id, cite.passage_hash
        check = by_check.get(key)
        passage = by_passage.get(key)
        valid = bool(
            check and check.valid_for_review
            and passage and passage.eligible_for_review
        )
        if passage is None:
            orphan += 1
        related[cite.claim_id].append((cite, valid))
    output = []
    for claim in sorted(claim_rows, key=lambda c: c.claim_id):
        current = related[claim.claim_id]
        support = {x.source_id for x, valid in current if valid and x.stance == "supports"}
        refute = {x.source_id for x, valid in current if valid and x.stance == "refutes"}
        context = {x.source_id for x, valid in current if valid and x.stance in ("context", "uncertain")}
        # Opposing statements from one page are not independent corroboration.
        support_groups = {membership[x] for x in support if membership.get(x)}
        refute_groups = {membership[x] for x in refute if membership.get(x)}
        unconfirmed = sum(not valid for _, valid in current)
        conflicted = bool(support and refute)
        reasons = []
        if not current:
            reasons.append("no_claim_citations")
        if unconfirmed:
            reasons.append("uncurrent_or_unreviewable_citations")
        if not support_groups:
            reasons.append("no_attested_independent_support")
        if conflicted:
            reasons.append("contradictory_retained_evidence")
        if context:
            reasons.append("context_or_uncertainty_evidence")
        if orphan:
            reasons.append("unbound_evidence_references")
        def score(stance: str) -> float:
            vals = [
                c.relevance for c, valid in current
                if valid and c.stance == stance
            ]
            return round(sum(vals) / len(vals), 8) if vals else 0.0
        output.append(ClaimAssessment(
            claim_id=claim.claim_id,
            objective_id=claim.objective_id,
            support_sources=tuple(sorted(support)),
            refute_sources=tuple(sorted(refute)),
            context_sources=tuple(sorted(context)),
            unconfirmed_citations=unconfirmed,
            attested_support_groups=len(support_groups),
            attested_refute_groups=len(refute_groups),
            conflicted=conflicted,
            review_state=("conflict_human_review" if conflicted
                          else "source_review_pending" if support
                          else "insufficient_reviewable_support"),
            support_triage_score=score("supports"),
            refute_triage_score=score("refutes"),
            reasoning=tuple(sorted(set(reasons))),
        ))
    payload = {
        "mandate": mandate.fingerprint,
        "claim_ids": [asdict(c) for c in claim_rows],
        "citations": [asdict(c) for c in cite_rows],
        "attestations": [asdict(g) for g in groups],
        "checks": verification.report_digest,
        "assessments": [asdict(x) for x in output],
        "orphans": orphan,
    }
    return ClaimReviewMatrix(
        mandate_digest=mandate.fingerprint,
        claims=tuple(output),
        unbound_citations=orphan,
        attestation_count=len(groups),
        matrix_digest=digest(payload),
    )
