"""Fail-closed plagiarism, provenance and expressive-copying admission for games.

Plagiarism (misattribution) is not identical to copyright infringement. No
universal similarity percentage decides either. This module produces candidate
evidence for independent review; it never certifies legal non-infringement.

Hardware mechanics, algorithms, ordinary game rules and public facts are not
automatically treated as protected expression. Textual source/code/narrative
similarity is screened; music, graphics and audiovisual similarity need a
qualified modality-specific assessment, not a pretended text-only clean bill.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import re
import unicodedata

_SHA = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$")
_WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)?", re.UNICODE)
_MAX_TEXT = 128_000
_MAX_REFERENCES = 256
_MAX_TOKENS = 16_000
_SHINGLE = 6
_ASSET_CLASSES = frozenset({
    "source_code", "artwork", "music_audio", "characters", "story_dialogue",
    "level_maps", "interface_appearance", "marketing_brand",
})
_TEXT_CLASSES = frozenset({"source_code", "story_dialogue", "marketing_brand", "characters"})
_NON_TEXT_CLASSES = _ASSET_CLASSES - _TEXT_CLASSES


class OriginalityError(ValueError):
    """Missing evidence, inconsistent original authorship or malformed submission."""


class AttributionStatus(str, Enum):
    DOCUMENTED = "documented"
    NOT_REQUIRED = "not_required"
    MISSING = "missing"


class UseBasis(str, Enum):
    OWN_CREATION = "own_creation"
    LICENSED_REUSE = "licensed_reuse"
    VERIFIED_PUBLIC_DOMAIN = "verified_public_domain"
    FACTS_AND_MECHANICS = "facts_and_mechanics"
    UNKNOWN = "unknown"
    UNLICENSED_PROTECTED = "unlicensed_protected"


class AssetDisposition(str, Enum):
    INCLUDED = "included"
    NOT_USED = "not_used"


class OriginalityDisposition(str, Enum):
    DESIGN_ADMISSIBLE_NOT_LEGAL_CLEARANCE = "design_admissible_not_legal_clearance"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class AssetDeclaration:
    """One complete project media-class disclosure; hashes reference evidence."""
    modality: str
    disposition: AssetDisposition
    basis: UseBasis | None = None
    provenance_sha256: str | None = None
    author_identity: str | None = None
    rights_holder: str | None = None
    license_identifier: str | None = None
    proposed_use_licensed: bool = False
    public_domain_independently_checked: bool = False
    attribution: AttributionStatus = AttributionStatus.MISSING
    reviewer_evidence_sha256: str | None = None
    false_authorship_claim: bool = False
    comparable_media_screened: bool = False

    def __post_init__(self) -> None:
        if self.modality not in _ASSET_CLASSES or not isinstance(self.disposition, AssetDisposition):
            raise OriginalityError("invalid asset class or disclosure")
        for name in ("provenance_sha256", "reviewer_evidence_sha256"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not _SHA.fullmatch(value)):
                raise OriginalityError("evidence reference must be SHA-256")
        for name in ("proposed_use_licensed", "public_domain_independently_checked",
                     "false_authorship_claim", "comparable_media_screened"):
            if type(getattr(self, name)) is not bool:
                raise OriginalityError("asset flags must be explicit booleans")
        if not isinstance(self.attribution, AttributionStatus):
            raise OriginalityError("invalid attribution status")
        if self.disposition is AssetDisposition.NOT_USED:
            if self.basis is not None or self.false_authorship_claim:
                raise OriginalityError("unused asset cannot assert rights or authorship")
        elif not isinstance(self.basis, UseBasis):
            raise OriginalityError("included asset requires a named rights basis")
        for name in ("author_identity", "rights_holder", "license_identifier"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip() or len(value) > 256):
                raise OriginalityError("invalid author, rights-holder or license identity")


@dataclass(frozen=True, slots=True)
class ExpressionSample:
    """Local plain-text/independent-code excerpt, never embedded in output report."""
    work_id: str
    modality: str
    text: str
    evidence_sha256: str | None = None
    protected_reference: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.work_id, str) or not _ID.fullmatch(self.work_id):
            raise OriginalityError("invalid expression work identity")
        if self.modality not in _TEXT_CLASSES:
            raise OriginalityError("text fingerprinting cannot prove visual/audio originality")
        if not isinstance(self.text, str) or not 1 <= len(self.text) <= _MAX_TEXT:
            raise OriginalityError("expressive sample exceeds bounded text size")
        if self.evidence_sha256 is not None and (
            not isinstance(self.evidence_sha256, str) or not _SHA.fullmatch(self.evidence_sha256)
        ):
            raise OriginalityError("invalid reference provenance digest")
        if type(self.protected_reference) is not bool:
            raise OriginalityError("reference type must be explicit")

    @property
    def content_sha256(self) -> str:
        return sha256(self.text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ExpressiveOverlap:
    sample_id: str
    reference_id: str
    modality: str
    reference_sha256: str
    sample_sha256: str
    shared_word_shingles: int
    longest_consecutive_tokens: int
    candidate_shingle_share: float
    exact_normalized_match: bool
    triage_signal: str
    legal_infringement_determined: bool = False


@dataclass(frozen=True, slots=True)
class OriginalityReport:
    project_id: str
    artifact_sha256: str | None
    candidate_sha256: str
    reference_corpus_sha256: str
    screen_digest: str
    disposition: OriginalityDisposition
    overlap_findings: tuple[ExpressiveOverlap, ...]
    blockers: tuple[str, ...]
    review_issues: tuple[str, ...]
    class_coverage: tuple[str, ...]
    unexamined_external_media: tuple[str, ...]
    legal_originality_certified: bool = False
    release_permitted: bool = False
    independent_human_signoff_complete: bool = False

    @property
    def design_admissible(self) -> bool:
        return self.disposition is OriginalityDisposition.DESIGN_ADMISSIBLE_NOT_LEGAL_CLEARANCE

    def public_receipt(self) -> dict[str, object]:
        return {
            "schema": "skeleton.game_builder.originality.v1",
            "project_id": self.project_id,
            "artifact_sha256": self.artifact_sha256,
            "candidate_sha256": self.candidate_sha256,
            "reference_corpus_sha256": self.reference_corpus_sha256,
            "screen_digest": self.screen_digest,
            "disposition": self.disposition.value,
            "blockers": list(self.blockers),
            "review_issues": list(self.review_issues),
            "screened_asset_classes": list(self.class_coverage),
            "non_text_assets_needing_specialized_review": list(self.unexamined_external_media),
            "potential_expressive_matches": [
                {"sample_id": x.sample_id, "reference_id": x.reference_id,
                 "modality": x.modality,
                 "reference_sha256": x.reference_sha256,
                 "shared_word_shingles": x.shared_word_shingles,
                 "longest_consecutive_tokens": x.longest_consecutive_tokens,
                 "candidate_shingle_share": x.candidate_shingle_share,
                 "triage_signal": x.triage_signal,
                 "legal_infringement_determined": False}
                for x in self.overlap_findings
            ],
            "legal_originality_certified": False,
            "independent_human_signoff_complete": False,
            "release_permitted": False,
            "external_sources_exhaustively_searched": False,
            "legal_similarity_threshold_exists": False,
        }


def _tokens(text: str) -> tuple[str, ...]:
    norm = unicodedata.normalize("NFKC", text).casefold()
    found = _WORD.findall(norm)
    if len(found) > _MAX_TOKENS:
        raise OriginalityError("oversize expressive sample cannot be silently truncated")
    return tuple(found)


def _shingles(tokens: tuple[str, ...]) -> frozenset[tuple[str, ...]]:
    if len(tokens) < _SHINGLE:
        return frozenset()
    return frozenset(tuple(tokens[i:i + _SHINGLE]) for i in range(len(tokens) - _SHINGLE + 1))


def _longest_overlap(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    """Bounded longest contiguous token match; avoids quadratic pairwise DP."""
    if not left or not right:
        return 0
    positions: dict[tuple[str, ...], list[int]] = {}
    for j in range(max(0, len(right) - _SHINGLE + 1)):
        key = right[j:j + _SHINGLE]
        slot = positions.setdefault(key, [])
        if len(slot) < 32:
            slot.append(j)
    longest = 0
    for i in range(max(0, len(left) - _SHINGLE + 1)):
        for j in positions.get(left[i:i + _SHINGLE], ()):
            limit = min(len(left) - i, len(right) - j)
            if limit <= longest or left[i + longest] != right[j + longest]:
                continue
            k = max(_SHINGLE, longest)
            while k < limit and left[i + k] == right[j + k]:
                k += 1
            longest = max(longest, k)
    if not longest and len(left) < _SHINGLE and left == right:
        return len(left)
    return longest


def find_expression_overlap(
    submission: ExpressionSample, reference: ExpressionSample,
) -> ExpressiveOverlap | None:
    """Heuristic review signal. Neither the threshold nor a pass is legal proof."""
    if submission.modality != reference.modality:
        return None
    original = _tokens(submission.text)
    prior = _tokens(reference.text)
    if not original or not prior:
        return None
    sample_ngrams = _shingles(original)
    prior_ngrams = _shingles(prior)
    common = len(sample_ngrams & prior_ngrams)
    share = common / len(sample_ngrams) if sample_ngrams else 0.0
    longest = _longest_overlap(original, prior) if common else 0
    exact = original == prior and len(original) >= _SHINGLE
    # This is deliberately a *triage alert* rather than a legal percentage.
    # Short generic text and conventional code may be non-protectable.
    if exact and len(original) >= 8:
        signal = "IDENTICAL_NORMALIZED_EXPRESSION"
    elif longest >= 12:
        signal = "LONG_IDENTICAL_EXPRESSION_RUN"
    elif common >= 4 and share >= 0.30:
        signal = "SUBSTANTIAL_SHARED_PHRASE_STRUCTURE_FOR_REVIEW"
    else:
        return None
    return ExpressiveOverlap(
        sample_id=submission.work_id,
        reference_id=reference.work_id,
        modality=submission.modality,
        reference_sha256=reference.content_sha256,
        sample_sha256=submission.content_sha256,
        shared_word_shingles=common,
        longest_consecutive_tokens=longest,
        candidate_shingle_share=round(share, 5),
        exact_normalized_match=exact,
        triage_signal=signal,
    )


def audit_game_originality(
    project_id: str, *, assets: tuple[AssetDeclaration, ...],
    candidate_samples: tuple[ExpressionSample, ...],
    references: tuple[ExpressionSample, ...],
    reference_corpus_declared_complete: bool = False,
    artifact_sha256: str | None = None,
) -> OriginalityReport:
    """Fail closed on gaps and matches, but never mistake sparse references for clearance.

    Samples/references are voluntarily supplied by a rights-cleared review
    process; external copyrighted works must not be copied into our repository.
    """
    if not isinstance(project_id, str) or not _ID.fullmatch(project_id):
        raise OriginalityError("invalid project identity")
    if artifact_sha256 is not None and (not isinstance(artifact_sha256, str) or
        not _SHA.fullmatch(artifact_sha256)):
        raise OriginalityError("originality screen must bind to a valid artifact digest")
    if (not isinstance(assets, tuple) or len(assets) != len(_ASSET_CLASSES) or
        any(not isinstance(a, AssetDeclaration) for a in assets) or
        {a.modality for a in assets} != _ASSET_CLASSES):
        raise OriginalityError("all eight media classes must have a unique disclosure, including not_used")
    if not isinstance(candidate_samples, tuple) or not isinstance(references, tuple):
        raise OriginalityError("samples and references must be fixed tuples")
    if len(candidate_samples) > _MAX_REFERENCES or len(references) > _MAX_REFERENCES:
        raise OriginalityError("bounded originality batch exceeded")
    if any(not isinstance(s, ExpressionSample) for s in (*candidate_samples, *references)):
        raise OriginalityError("typed expression samples required")
    if len(candidate_samples) * len(references) > 4096:
        raise OriginalityError("comparison batch must be sharded into review cohorts")
    if sum(len(s.text) for s in (*candidate_samples, *references)) > 4_000_000:
        raise OriginalityError("aggregate review input exceeds memory budget")
    if len({x.work_id for x in candidate_samples}) != len(candidate_samples) or (
        len({x.work_id for x in references}) != len(references)
    ):
        raise OriginalityError("duplicate source ID in originality batch")
    if type(reference_corpus_declared_complete) is not bool:
        raise OriginalityError("reference completeness flag must be boolean")
    # No caller may self-assert that the global corpus covers the world.
    if reference_corpus_declared_complete:
        raise OriginalityError("external reference completeness cannot be self-certified")
    blockers: set[str] = set()
    review: set[str] = set()
    uncovered: set[str] = set()
    by_modality = {asset.modality: asset for asset in assets}
    for a in assets:
        if a.disposition is AssetDisposition.NOT_USED:
            continue
        if a.false_authorship_claim:
            blockers.add("DECEPTIVE_AUTHORSHIP_OR_ATTRIBUTION:" + a.modality)
        if a.basis is UseBasis.UNLICENSED_PROTECTED:
            blockers.add("PROTECTED_EXPRESSION_UNLICENSED:" + a.modality)
        elif a.basis is UseBasis.UNKNOWN:
            review.add("ASSET_ORIGIN_UNKNOWN:" + a.modality)
        elif a.basis is UseBasis.FACTS_AND_MECHANICS:
            # Facts/ideas are fine to study; but an actual expressive output
            # cannot claim it is *only* a free mechanic without further review.
            review.add("VERIFY_FACT_EXPRESSION_SEPARATION:" + a.modality)
        elif a.basis is UseBasis.OWN_CREATION:
            if not a.provenance_sha256 or not a.author_identity:
                review.add("AUTHORSHIP_HISTORY_UNDOCUMENTED:" + a.modality)
        elif a.basis is UseBasis.LICENSED_REUSE:
            if not (a.provenance_sha256 and a.license_identifier and a.rights_holder
                    and a.proposed_use_licensed):
                review.add("LICENSE_SCOPE_UNVERIFIED:" + a.modality)
        elif a.basis is UseBasis.VERIFIED_PUBLIC_DOMAIN:
            if not a.provenance_sha256 or not a.public_domain_independently_checked:
                review.add("PUBLIC_DOMAIN_STATUS_NOT_CONFIRMED:" + a.modality)
        if a.basis in (UseBasis.LICENSED_REUSE, UseBasis.VERIFIED_PUBLIC_DOMAIN):
            if a.attribution is AttributionStatus.MISSING:
                review.add("THIRD_PARTY_CREDIT_OR_ATTRIBUTION_MISSING:" + a.modality)
        if a.modality in _NON_TEXT_CLASSES and not (
            a.comparable_media_screened and a.reviewer_evidence_sha256
        ):
            uncovered.add(a.modality)
            review.add("NON_TEXT_SIMILARITY_NOT_INDEPENDENTLY_REVIEWED:" + a.modality)

    # Source isn't supplied? An author's claim and a SHA are still not a scan.
    for modality in _TEXT_CLASSES:
        if (by_modality[modality].disposition is AssetDisposition.INCLUDED and
            not any(s.modality == modality for s in candidate_samples)):
            review.add("EXPRESSIVE_TEXT_NOT_SUBMITTED_FOR_SCREEN:" + modality)
    for candidate in candidate_samples:
        asset = by_modality[candidate.modality]
        if asset.disposition is AssetDisposition.NOT_USED:
            raise OriginalityError("expressive sample supplied for a declared unused asset")
        if not asset.provenance_sha256 or candidate.evidence_sha256 != asset.provenance_sha256:
            review.add("EXPRESSION_NOT_BOUND_TO_AUTHORED_PROVENANCE:" + candidate.modality)
    if not references:
        review.add("NO_REFERENCE_CORPUS_PROVIDED")
    findings: list[ExpressiveOverlap] = []
    for cand in sorted(candidate_samples, key=lambda s: s.work_id):
        for prior in sorted(references, key=lambda s: s.work_id):
            found = find_expression_overlap(cand, prior)
            if found is None:
                continue
            findings.append(found)
            review.add("POTENTIAL_EXPRESSIVE_REUSE_REQUIRES_HUMAN_REVIEW:" + cand.work_id + ":" + prior.work_id)
    findings.sort(key=lambda x: (x.modality, x.sample_id, x.reference_id))
    # A clean hit list is never proof of non-plagiarism: the reference set may
    # miss obscure, licensed, localized, recently created or offline games.
    review.add("NONEXHAUSTIVE_SIMILARITY_CORPUS_AND_HUMAN_RELEASE_REVIEW_REQUIRED")
    disposition = (
        OriginalityDisposition.BLOCKED if blockers else
        OriginalityDisposition.HUMAN_REVIEW_REQUIRED
        if review - {"NONEXHAUSTIVE_SIMILARITY_CORPUS_AND_HUMAN_RELEASE_REVIEW_REQUIRED"} else
        OriginalityDisposition.DESIGN_ADMISSIBLE_NOT_LEGAL_CLEARANCE
    )
    # A release-specific verification process must independently certify actual
    # rights; no automated audit can emit a legal clearance certificate.
    cand_digest = sha256(json.dumps(
        [(s.work_id, s.modality, s.content_sha256, s.evidence_sha256) for s in
         sorted(candidate_samples, key=lambda x: x.work_id)], separators=(",", ":")
    ).encode()).hexdigest()
    ref_digest = sha256(json.dumps(
        [(s.work_id, s.modality, s.content_sha256) for s in
         sorted(references, key=lambda x: x.work_id)], separators=(",", ":")
    ).encode()).hexdigest()
    payload = {
        "project_id":project_id,"artifact_sha256":artifact_sha256,
        "assets":[{k:getattr(a,k).value if isinstance(getattr(a,k), Enum) else
                   getattr(a,k) for k in a.__dataclass_fields__}
                  for a in sorted(assets, key=lambda a:a.modality)],
        "candidate_sha256":cand_digest,"reference_corpus_sha256":ref_digest,
        "signals":[(f.sample_id,f.reference_id,f.modality,f.longest_consecutive_tokens,
                    f.shared_word_shingles,f.triage_signal) for f in findings],
        "blockers":sorted(blockers),"review":sorted(review),
    }
    digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False).encode()).hexdigest()
    return OriginalityReport(
        project_id=project_id, artifact_sha256=artifact_sha256, candidate_sha256=cand_digest,
        reference_corpus_sha256=ref_digest, screen_digest=digest,
        disposition=disposition, overlap_findings=tuple(findings),
        blockers=tuple(sorted(blockers)), review_issues=tuple(sorted(review)),
        class_coverage=tuple(sorted(_ASSET_CLASSES)),
        unexamined_external_media=tuple(sorted(uncovered)),
    )
