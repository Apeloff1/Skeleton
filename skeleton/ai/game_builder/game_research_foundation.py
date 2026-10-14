"""First-floor game research: bounded targets and attributed review digestion.

Commentary, observed play, popularity and empirical findings are distinct.
This adapter uses the existing rights ledger and creates no crawler authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from itertools import islice
from typing import Iterable

from .contracts import canonical_digest
from .reviewed_knowledge import _id, _source_url, _text, _digest, _integer
from .rights import RightsLedger, RightsState, UseKind


@dataclass(frozen=True, slots=True)
class DistillationTarget:
    target_id: str
    label: str
    evidence_role: str
    search_suffix: str
    required_context: tuple[str, ...]


TARGETS = (
    DistillationTarget("reviewer_peer_review", "Independent assessments of game reviewers", "source_quality",
        "reviewer methodology corrections disclosures independent critique", ("reviewer_identity", "ownership", "expertise", "corrections", "sponsorship")),
    DistillationTarget("game_review", "Game criticism", "critical_opinion", "review critique mechanics",
        ("game_version", "platform", "review_date", "review_copy_disclosure")),
    DistillationTarget("lets_play", "Let's Play analysis", "observed_play", "lets play full gameplay",
        ("game_version", "platform", "timecode", "cuts", "mods", "player_skill", "input_context")),
    DistillationTarget("angry_video_game_nerd", "Angry Video Game Nerd / Cinemassacre", "comedy_criticism",
        "Angry Video Game Nerd Cinemassacre review", ("official_creator_identity", "timecode", "satire", "staged_segments", "game_version")),
    DistillationTarget("nostalgia_critic", "Nostalgia Critic / Channel Awesome", "media_criticism",
        "Nostalgia Critic Channel Awesome review", ("official_creator_identity", "timecode", "satire", "medium", "game_relevance")),
    DistillationTarget("blog_review", "Blog criticism", "critical_opinion", "blog review analysis",
        ("author", "expertise", "corrections", "affiliate_disclosure", "publication_date")),
    DistillationTarget("news_review", "News analysis and reviews", "reported_claim", "news review developer interview",
        ("byline", "primary_citations", "corrections", "syndication", "publication_date")),
    DistillationTarget("news_engagement", "Engagement with news", "engagement_signal", "news audience engagement methodology",
        ("measurement_window", "denominator", "platform", "sampling", "bot_bias", "privacy")),
    DistillationTarget("homebrew", "Homebrew projects", "technical_reference", "homebrew source license documentation",
        ("code_license", "asset_licenses", "toolchain", "hardware", "build_revision")),
    DistillationTarget("abandonware", "Historically labelled abandonware", "historical_reference", "abandonware ownership history",
        ("current_owner", "rights_chain", "distribution_permission", "label_not_clearance")),
    DistillationTarget("unlicensed", "Unlicensed releases", "historical_reference", "unlicensed game developer rights history",
        ("platform_license", "copyright", "patents", "sdk_provenance", "distribution_permission")),
    DistillationTarget("closed_studio", "Closed or inactive studios and IP", "historical_reference", "studio closure IP acquisition assignment",
        ("corporate_record", "successor_owner", "assignments", "territory", "closure_not_expiry")),
    DistillationTarget("title_catalog", "Titles and licensed releases", "catalog_record", "game title release platform region catalog",
        ("canonical_title_id", "aliases", "region", "platform", "edition", "license_citations")),
    DistillationTarget("mechanic_catalog", "Mechanics and implementations", "technical_reference", "mechanic implementation paper benchmark",
        ("abstract_rule", "implementation_version", "measured_evidence", "patent_search", "limitations")),
    DistillationTarget("patent_watch", "Patent families and legal records", "rights_status", "patent claims family legal status register",
        ("publication_number", "jurisdiction", "family", "claims", "maintenance", "term_adjustment", "reinstatement")),
)
_TARGETS = {t.target_id: t for t in TARGETS}


def bounded(rows: Iterable, maximum: int, kind: type) -> tuple:
    values = tuple(islice(rows, maximum + 1))
    if len(values) > maximum or any(not isinstance(r, kind) for r in values):
        raise ValueError("bounded typed input required")
    return values


def acquisition_targets(title: str, *, limit: int = 15) -> dict:
    """Deterministic discovery intents, including explicitly requested creators."""
    _text(title, "title", 240)
    _integer(limit, "target limit", 1, len(TARGETS))
    targets = [{**asdict(t), "query": title + " " + t.search_suffix,
                "reputation": "not_preapproved", "permission_check_required": True,
                "acquisition_owner": "skeleton/ai/webcrawler"} for t in TARGETS[:limit]]
    body = {"schema": "skeleton.game_builder.foundation_targets.v1", "title": title,
            "targets": targets, "deferred_targets": len(TARGETS)-limit,
            "acquisition_authorized": False, "training_authorized": False,
            "coverage": "discovery_plan_not_acquired_dataset"}
    return {**body, "plan_digest": canonical_digest(body)}


@dataclass(frozen=True, slots=True)
class ReviewerAssessment:
    source_id: str
    source_digest: str
    source_url: str
    reviewer_id: str
    reviewer_group: str
    subject_group: str
    evidence_url: str
    evidence_digest: str
    domain: str
    expertise_documented: bool
    corrections_documented: bool
    sponsorship_disclosed: bool
    evidence_traceable: bool
    checked_at: int
    expires_at: int

    def __post_init__(self):
        for k in ("source_id", "reviewer_id", "reviewer_group", "subject_group", "domain"):
            _id(getattr(self, k), k)
        _digest(self.source_digest, "source digest")
        _digest(self.evidence_digest, "review evidence digest")
        _source_url(self.evidence_url)
        _source_url(self.source_url)
        for k in ("expertise_documented", "corrections_documented", "sponsorship_disclosed", "evidence_traceable"):
            if type(getattr(self, k)) is not bool:
                raise ValueError("review criteria must be explicit booleans")
        _integer(self.checked_at, "review time", 0, 10**12)
        _integer(self.expires_at, "expiry", self.checked_at + 1, 10**12)


def assess_reviewer(source_id: str, source_digest: str, domain: str,
                    assessments: Iterable[ReviewerAssessment], *, now: int) -> dict:
    """Require two externally authenticated independent review groups.

    The caller verifies ownership/group declarations and cited review evidence.
    This policy assessment is not academic peer review or proof of accuracy.
    """
    _id(source_id, "source")
    _digest(source_digest, "source digest")
    _id(domain, "domain")
    _integer(now, "now", 0, 10**12)
    rows = bounded(assessments, 32, ReviewerAssessment)
    if len({r.reviewer_id for r in rows}) != len(rows):
        raise ValueError("duplicate reviewer identity")
    if any((r.source_id, r.source_digest, r.domain) != (source_id, source_digest, domain) for r in rows):
        raise ValueError("review assessment belongs to another source revision or domain")
    if len({r.subject_group.casefold() for r in rows}) > 1:
        raise ValueError("conflicting subject ownership")
    if len({r.source_url for r in rows}) > 1:
        raise ValueError("conflicting reviewed source URL")
    good = [r for r in rows if r.checked_at <= now < r.expires_at
            and r.reviewer_group.casefold() != r.subject_group.casefold() and r.expertise_documented
            and r.corrections_documented and r.sponsorship_disclosed and r.evidence_traceable]
    # Reused review documents cannot supply a second independent assessment.
    parents = list(range(len(good)))
    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i
    labels = {}
    for i, r in enumerate(good):
        for label in (("group", r.reviewer_group.casefold()), ("document", r.evidence_digest)):
            if label in labels:
                parents[root(i)] = root(labels[label])
            else:
                labels[label] = i
    groups = {root(i) for i in range(len(good))}
    body = {"source_id": source_id, "source_digest": source_digest, "domain": domain,
            "checked_at": now, "independent_review_groups": len(groups),
            "accepted_for_attributed_analysis": len(groups) >= 2 and len(good) == len(rows),
            "reviews": [asdict(r) for r in sorted(rows, key=lambda r: r.reviewer_id)],
            "factual_truth_established": False}
    return {**body, "assessment_digest": canonical_digest(body)}


@dataclass(frozen=True, slots=True)
class ReviewObservation:
    observation_id: str
    target_id: str
    title_id: str
    source_id: str
    source_url: str
    source_text: str
    start: int
    end: int
    locator: str
    attributed_observation: str
    context: tuple[tuple[str, str], ...]

    def __post_init__(self):
        for k in ("observation_id", "title_id", "source_id"):
            _id(getattr(self, k), k)
        if self.target_id not in _TARGETS:
            raise ValueError("unknown distillation target")
        _source_url(self.source_url)
        _text(self.source_text, "source text", 100000)
        _integer(self.start, "start", 0, len(self.source_text)-1)
        _integer(self.end, "end", self.start+1, min(len(self.source_text), self.start+400))
        _text(self.locator, "citation locator", 256)
        _text(self.attributed_observation, "attributed observation", 1500)
        if not isinstance(self.context, tuple) or len(self.context) > 32:
            raise ValueError("bounded observation context required")
        for pair in self.context:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError("context key/value pair required")
            _id(pair[0], "context key")
            _text(pair[1], "context value", 512)
        if len(dict(self.context)) != len(self.context):
            raise ValueError("duplicate context key")


def distill_observation(observation: ReviewObservation, rights: RightsLedger,
                       assessments: Iterable[ReviewerAssessment], *, now: int,
                       authorized: bool) -> dict:
    if authorized is not True:
        raise PermissionError("authenticated review ingestion required")
    if not isinstance(observation, ReviewObservation) or not isinstance(rights, RightsLedger):
        raise ValueError("typed observation and canonical rights ledger required")
    row = observation
    target = _TARGETS[row.target_id]
    digest = sha256(row.source_text.encode()).hexdigest()
    source = rights.source(row.source_id)
    if source.content_digest != digest:
        raise ValueError("source body differs from rights custody")
    if (source.rights_state in {RightsState.UNKNOWN_QUARANTINE, RightsState.FORBIDDEN}
            or (source.rights_state not in {RightsState.FACTS_IDEAS_REFERENCE_ONLY, RightsState.RESTRICTED_REFERENCE_ONLY}
                and UseKind.FACTS_IDEAS_REFERENCE not in source.allowed_uses)):
        raise ValueError("reference analysis rights not established")
    if source.consent_required and not source.consent_digest:
        raise ValueError("reference consent missing")
    assessments = bounded(assessments, 32, ReviewerAssessment)
    if any(a.source_url != row.source_url for a in assessments):
        raise ValueError("citation URL differs from reviewed source")
    quality = assess_reviewer(row.source_id, digest, target.evidence_role, assessments, now=now)
    missing = sorted(set(target.required_context) - dict(row.context).keys())
    body = {"schema": "skeleton.game_builder.foundation_observation.v1",
            "observation_id": row.observation_id, "title_id": row.title_id,
            "target_id": row.target_id, "evidence_role": target.evidence_role,
            "source_id": row.source_id, "source_digest": digest,
            "citation": {"url": row.source_url, "locator": row.locator, "start": row.start, "end": row.end,
                         "exact_quote": row.source_text[row.start:row.end]},
            "attributed_observation": row.attributed_observation,
            "context": dict(row.context), "missing_context": missing,
            "source_quality": quality, "rights_binding": source.rights_binding_digest,
            "ready_for_distillation_review": quality["accepted_for_attributed_analysis"] and not missing,
            "empirical_fact": False, "memory_promotion_authorized": False,
            "training_authorized": False, "reuse_authorized": False}
    return {**body, "observation_digest": canonical_digest(body)}


def main() -> None:
    import argparse
    from .contracts import canonical_json
    parser = argparse.ArgumentParser(description="Inspect governed game-research targets")
    parser.add_argument("--title", required=True)
    args = parser.parse_args()
    print(canonical_json(acquisition_targets(args.title)))


if __name__ == "__main__":
    main()
