"""Dragon cross-source factual corroboration with distinct external trust anchors.

No excerpts, browsing, self-signed neural labels or promotion actions. Every
source-group witness signs an exact claim/revision; a separate adjudicator
signs the collection. A contradiction always blocks corroboration.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from skeleton.ai.game_builder.contracts import canonical_digest, canonical_json

HEX = re.compile(r"[0-9a-f]{64}\Z")
SOURCE = re.compile(r"source-[0-9a-f]{64}\Z")
IDENTITY = re.compile(r"[a-z0-9][a-z0-9._-]{1,79}\Z")
RELATIONS = frozenset(("supports", "contradicts", "uncertain"))
_MAX_CLAIMS = 64
_MAX_WITNESSES = 512


def _hash(value: str) -> str:
    if type(value) is not str or not HEX.fullmatch(value):
        raise ValueError("canonical SHA-256 digest required")
    return value


def _name(value: str) -> str:
    if type(value) is not str or not IDENTITY.fullmatch(value):
        raise ValueError("bounded canonical evidence identity required")
    return value


def _verify(pub: bytes, signature: str, payload: dict) -> None:
    if type(pub) is not bytes or len(pub) != 32:
        raise ValueError("provisioned external Ed25519 key required")
    try:
        raw = bytes.fromhex(signature)
        if len(raw) != 64:
            raise ValueError("Ed25519 signature length invalid")
        Ed25519PublicKey.from_public_bytes(pub).verify(
            raw, canonical_json(payload).encode("utf-8"))
    except (TypeError, ValueError, InvalidSignature) as exc:
        raise PermissionError("externally signed factual evidence invalid") from exc


@dataclass(frozen=True)
class ClaimSubject:
    claim_digest: str
    context_digest: str
    topic: str

    def body(self) -> dict:
        return {"claim_digest": _hash(self.claim_digest),
                "context_digest": _hash(self.context_digest),
                "topic": _name(self.topic)}


@dataclass(frozen=True)
class SourceWitness:
    owner: str
    knowledge_digest: str
    claim_digest: str
    context_digest: str
    source_id: str
    source_revision_digest: str
    publisher_group: str
    relation: str
    reviewer: str
    key_id: str
    observed_at: int
    expires_at: int
    signature_hex: str

    def body(self) -> dict:
        return {
            "schema": "skeleton.dragon.independent_source_witness.v1",
            "owner": self.owner, "knowledge_digest": self.knowledge_digest,
            "claim_digest": self.claim_digest,
            "context_digest": self.context_digest,
            "source_id": self.source_id,
            "source_revision_digest": self.source_revision_digest,
            "publisher_group": self.publisher_group, "relation": self.relation,
            "reviewer": self.reviewer, "key_id": self.key_id,
            "observed_at": self.observed_at, "expires_at": self.expires_at,
        }


@dataclass(frozen=True)
class SignedClaimAdjudication:
    owner: str
    knowledge_digest: str
    claim_digest: str
    context_digest: str
    witness_set_digest: str
    verdict: str
    reviewer: str
    key_id: str
    issued_at: int
    expires_at: int
    signature_hex: str

    def body(self) -> dict:
        return {
            "schema": "skeleton.dragon.fact_adjudication.v1",
            "owner": self.owner, "knowledge_digest": self.knowledge_digest,
            "claim_digest": self.claim_digest,
            "context_digest": self.context_digest,
            "witness_set_digest": self.witness_set_digest,
            "verdict": self.verdict, "reviewer": self.reviewer,
            "key_id": self.key_id, "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }


def witness_set_digest(witnesses: tuple[SourceWitness, ...]) -> str:
    """Canonical order-independent fingerprint of signed source observations."""
    if type(witnesses) is not tuple or len(witnesses) > _MAX_WITNESSES:
        raise ValueError("bounded immutable witness set required")
    return canonical_digest(sorted(
        ({"body": w.body(), "signature_hex": w.signature_hex}
         for w in witnesses),
        key=lambda r: (r["body"]["publisher_group"], r["body"]["source_id"],
                       r["body"]["source_revision_digest"]),
    ))


def verify_cross_source_claims(
    owner: str, knowledge_digest: str,
    claims: tuple[ClaimSubject, ...],
    witnesses: tuple[SourceWitness, ...],
    adjudications: tuple[SignedClaimAdjudication, ...], *,
    trusted_publisher_reviewers: dict[str, tuple[str, str, bytes]],
    adjudicator_public_key: bytes,
    adjudicator: str,
    adjudicator_key_id: str,
    now: int,
    min_independent_groups: int = 2,
) -> dict:
    """Require distinct signer keys for witnesses plus a separate adjudicator.

    Operator-provisioned trust anchors must not be taken from user input.
    Cryptographic signatures prove who asserted a fact, not its actual truth.
    """
    _name(owner)
    _hash(knowledge_digest)
    if (type(claims) is not tuple or not 1 <= len(claims) <= _MAX_CLAIMS
        or type(witnesses) is not tuple or len(witnesses) > _MAX_WITNESSES
        or type(adjudications) is not tuple or len(adjudications) > _MAX_CLAIMS
        or type(now) is not int or now < 0
        or type(min_independent_groups) is not int
        or not 2 <= min_independent_groups <= 5
        or type(trusted_publisher_reviewers) is not dict
        or not 2 <= len(trusted_publisher_reviewers) <= 50):
        raise ValueError("bounded independent fact-check policy required")
    _name(adjudicator)
    _name(adjudicator_key_id)
    if (type(adjudicator_public_key) is not bytes
        or len(adjudicator_public_key) != 32):
        raise ValueError("external adjudicator key required")
    pubkeys = set()
    for group, conf in trusted_publisher_reviewers.items():
        _name(group)
        if (type(conf) is not tuple or len(conf) != 3
            or type(conf[2]) is not bytes or len(conf[2]) != 32):
            raise ValueError("distinct trusted publisher reviewer keys required")
        _name(conf[0])
        _name(conf[1])
        if conf[2] in pubkeys or conf[2] == adjudicator_public_key:
            raise PermissionError("publisher group key reused or adjudicator not independent")
        pubkeys.add(conf[2])
    subjects = {}
    for subject in claims:
        if not isinstance(subject, ClaimSubject):
            raise TypeError("canonical claim subject required")
        body = subject.body()
        if body["claim_digest"] in subjects:
            raise ValueError("duplicate claim identity")
        subjects[body["claim_digest"]] = body
    if not subjects:
        raise ValueError("at least one claim required")
    grouped: dict[str, list[SourceWitness]] = {key: [] for key in subjects}
    unique_observations = set()
    for w in witnesses:
        if not isinstance(w, SourceWitness):
            raise TypeError("signed exact-revision witness required")
        if (w.owner != owner or w.knowledge_digest != knowledge_digest
            or w.claim_digest not in subjects
            or w.context_digest != subjects[w.claim_digest]["context_digest"]):
            raise PermissionError("cross-tenant or cross-claim factual witness")
        if (type(w.source_id) is not str or not SOURCE.fullmatch(w.source_id)
            or w.relation not in RELATIONS):
            raise ValueError("source identity or witness relation invalid")
        _hash(w.source_revision_digest)
        _name(w.reviewer)
        _name(w.key_id)
        trusted = trusted_publisher_reviewers.get(w.publisher_group)
        if trusted is None or (w.reviewer, w.key_id) != trusted[:2]:
            raise PermissionError("source witness reviewer outside trust map")
        if (type(w.observed_at) is not int or type(w.expires_at) is not int
            or not 0 <= w.observed_at <= now < w.expires_at
            or w.expires_at - w.observed_at > 90 * 86400):
            raise ValueError("source observation stale, future or unbounded")
        _verify(trusted[2], w.signature_hex, w.body())
        identity = (w.claim_digest, w.source_id)
        if identity in unique_observations:
            raise ValueError("duplicate source identity in independent witness set")
        unique_observations.add(identity)
        grouped[w.claim_digest].append(w)
    review_map = {}
    for review in adjudications:
        if not isinstance(review, SignedClaimAdjudication):
            raise TypeError("signed independent adjudication required")
        if (review.owner != owner or review.knowledge_digest != knowledge_digest
            or review.claim_digest not in subjects
            or review.context_digest != subjects[review.claim_digest]["context_digest"]
            or review.reviewer != adjudicator
            or review.key_id != adjudicator_key_id):
            raise PermissionError("wrong claim, tenant or adjudicator identity")
        if review.claim_digest in review_map:
            raise ValueError("duplicate signed final adjudication")
        if (type(review.issued_at) is not int or type(review.expires_at) is not int
            or not 0 <= review.issued_at <= now < review.expires_at
            or review.expires_at - review.issued_at > 30 * 86400
            or review.verdict not in ("accept", "reject", "needs_research")):
            raise ValueError("outdated or unrecognized adjudication")
        observed = witness_set_digest(tuple(grouped[review.claim_digest]))
        if review.witness_set_digest != observed:
            raise PermissionError("adjudication not bound to signed witness set")
        _verify(adjudicator_public_key, review.signature_hex, review.body())
        review_map[review.claim_digest] = review
    rows = []
    for subject in claims:
        evidence = grouped[subject.claim_digest]
        review = review_map.get(subject.claim_digest)
        supports = [w for w in evidence if w.relation == "supports"]
        contradicted = [w for w in evidence if w.relation == "contradicts"]
        uncertain = [w for w in evidence if w.relation == "uncertain"]
        groups = {w.publisher_group for w in supports}
        qualified = (
            review is not None and review.verdict == "accept"
            and not contradicted and not uncertain
            and len(groups) >= min_independent_groups
            and len({w.source_revision_digest for w in supports})
                >= min_independent_groups
        )
        rows.append({
            "claim_digest": subject.claim_digest,
            "context_digest": subject.context_digest,
            "topic": subject.topic,
            "witness_set_digest": witness_set_digest(tuple(evidence)),
            "supporting_source_count": len(supports),
            "distinct_reviewed_publisher_groups": len(groups),
            "contradicting_source_count": len(contradicted),
            "uncertain_source_count": len(uncertain),
            "adjudication": review.verdict if review else "missing",
            "corroboration_review_eligible": qualified,
            "source_independence_externally_attested_not_proved": True,
        })
    rows.sort(key=lambda r: r["claim_digest"])
    core = {
        "schema": "skeleton.dragon.signed_cross_source_fact_review.v1",
        "owner": owner, "knowledge_digest": knowledge_digest,
        "reviewer": adjudicator,
        "reviewer_key_id": adjudicator_key_id,
        "checked_at": now, "claim_count": len(rows),
        "corroborated_claim_count": sum(r["corroboration_review_eligible"]
                                       for r in rows),
        "all_claims_review_eligible": all(
            r["corroboration_review_eligible"] for r in rows),
        "claims": rows,
        "neural_training_authorized": False,
        "shadow_weight_promotion_authorized": False,
        "normal_weight_promotion_authorized": False,
        "hyperweight_promotion_authorized": False,
        "independent_source_rights_still_required": True,
    }
    return {**core, "report_digest": canonical_digest(core)}
