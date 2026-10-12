"""Mother Dragon: cross-hatchling semantic glean matrix over reviewed knowledge.

The mother examines article, video and update hatchling receipts through distinct
meaning lenses and repeated canonical searches. Each proposed subtext is a
*testable hypothesis*, not an observed fact or neural weight. No URL is fetched,
no external model is run, and nothing here can authorize live memory promotion.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import re

from skeleton.ai.game_builder.contracts import canonical_digest
from skeleton.ai.game_builder.reviewed_knowledge import (
    KnowledgeHit, ReviewedKnowledgeStore,
)
from .dragon_nest_progression import (
    DragonNest, LANES, _id, _instant, _iso, verify_change_history,
)

_WORD = re.compile(r"[^\W_]+", re.UNICODE)
MAX_ACQUISITIONS = 6
MAX_LENSES = 12


@dataclass(frozen=True)
class MeaningLens:
    key: str
    cues: tuple[str, ...]
    probes: tuple[str, str, str]
    question: str
    concern: str

    def __post_init__(self) -> None:
        _id(self.key)
        if (not 2 <= len(self.cues) <= 20
                or any(not isinstance(x, str) or not _WORD.fullmatch(x)
                       for x in self.cues)
                or len(set(self.cues)) != len(self.cues)
                or len(self.probes) != 3
                or any(not isinstance(p, str) or not 1 <= len(p) <= 60
                       for p in self.probes)
                or not 1 <= len(self.question) <= 240
                or not 1 <= len(self.concern) <= 240):
            raise ValueError("bounded, distinct lens cues and searches required")


LENSES = (
    MeaningLens(
        "causal", ("because", "causes", "prevents", "drives", "enables"),
        ("cause effect", "because mechanism", "prevents outcome"),
        "Does the cited mechanism cause the effect, or merely correlate?",
        "Correlation cannot establish causation.",
    ),
    MeaningLens(
        "tradeoff", ("tradeoff", "latency", "memory", "budget", "performance", "cost"),
        ("performance cost", "latency memory", "resource tradeoff"),
        "What is sacrificed when this game-system benefit increases?",
        "A benefit may move costs into another subsystem.",
    ),
    MeaningLens(
        "failure", ("failure", "fails", "invalid", "rollback", "crash", "fallback"),
        ("failure boundary", "rollback recovery", "error fallback"),
        "Which adversarial edge case would invalidate the observed behavior?",
        "A successful demonstration is not proof of failure tolerance.",
    ),
    MeaningLens(
        "player_experience", ("player", "agency", "choice", "feedback", "readability", "fun"),
        ("player feedback", "player agency", "choice consequence"),
        "Can player choices and feedback make the mechanic more legible?",
        "Mechanic correctness does not establish player value.",
    ),
    MeaningLens(
        "accessibility", ("accessibility", "contrast", "reader", "input", "cognitive", "assistive"),
        ("accessibility input", "reader contrast", "cognitive assistive"),
        "Which users or control methods might this implementation exclude?",
        "A default-input success cannot establish accessible design.",
    ),
    MeaningLens(
        "platform", ("console", "hardware", "port", "mobile", "compatibility", "fps"),
        ("platform hardware", "console port", "compatibility fps"),
        "Would the mechanism still work under different hardware constraints?",
        "Portability requires independent platform-specific verification.",
    ),
    MeaningLens(
        "emergence", ("emergent", "interaction", "dynamic", "adaptive", "systemic", "cascade"),
        ("emergent interaction", "systemic cascade", "adaptive dynamic"),
        "Could interactions between mechanics create a new useful capability?",
        "Predicted system interactions are not experimentally confirmed.",
    ),
    MeaningLens(
        "time_change", ("updated", "deprecated", "revision", "regression", "obsolete", "changed"),
        ("updated revision", "deprecated changed", "regression obsolete"),
        "Has a newer source revision superseded the apparent best practice?",
        "Source observation time differs from source publication time.",
    ),
    MeaningLens(
        "rights", ("copyright", "license", "attribution", "permission", "original", "patent"),
        ("license permission", "copyright attribution", "original patent"),
        "What rights or provenance constraints would block product reuse?",
        "Research access does not grant redistribution or training rights.",
    ),
    MeaningLens(
        "adversarial", ("exploit", "unsafe", "attack", "spoof", "leak", "injection"),
        ("attack exploit", "spoof injection", "unsafe leak"),
        "How might malformed or adversarial inputs break this assumption?",
        "Untrusted source text can describe, not authorize, actions.",
    ),
    MeaningLens(
        "transfer", ("transfer", "adapt", "reuse", "generalize", "genre", "hybrid"),
        ("adapt reuse", "genre hybrid", "transfer generalize"),
        "Would a proven technique transfer into an adjacent game genre?",
        "Transfer benefits require a separate target-specific demonstration.",
    ),
    MeaningLens(
        "testing", ("test", "benchmark", "baseline", "measurement", "holdout", "replay"),
        ("benchmark baseline", "test holdout", "measurement replay"),
        "Which controlled experiment would disprove the alleged gain?",
        "Search overlap is not a valid independent usefulness benchmark.",
    ),
)


@dataclass(frozen=True)
class HatchlingReceipt:
    lane: str
    source_id: str
    source_text_digest: str
    note_id: str
    observed_at: str

    def __post_init__(self) -> None:
        if self.lane not in LANES:
            raise ValueError("unknown hatchling lane")
        _id(self.source_id)
        _id(self.note_id)
        if not re.fullmatch(r"[0-9a-f]{64}", self.source_text_digest):
            raise ValueError("source content digest required")
        _iso(self.observed_at)


@dataclass(frozen=True)
class LensProbe:
    lens: str
    query: str
    evidence_ids: tuple[str, ...]
    independent_groups: int
    conflicting: bool
    digest: str


@dataclass(frozen=True)
class MeaningHypothesis:
    hypothesis_id: str
    lane: str
    source_id: str
    note_id: str
    lens: str
    mechanic: str
    question: str
    subtext: str
    caveat: str
    evidence_ids: tuple[str, ...]
    independent_groups: int
    status: str = "shadow_hypothesis"
    empirically_validated: bool = False
    model_promotion_authorized: bool = False


@dataclass(frozen=True)
class SynergyHypothesis:
    """A bounded cross-lens extrapolation; never a discovered source fact."""
    hypothesis_id: str
    lane: str
    source_id: str
    note_id: str
    lenses: tuple[str, str]
    question: str
    evidence_ids: tuple[str, ...]
    status: str = "shadow_hypothesis"
    empirically_validated: bool = False
    model_promotion_authorized: bool = False


# Pairwise interactions make the mother more than twelve disconnected filters.
SYNERGIES = (
    ("causal", "failure", "Where might the causal mechanism break at the failure boundary?"),
    ("tradeoff", "platform", "Can this optimization retain benefits on another platform?"),
    ("player_experience", "accessibility", "Whose agency or understanding changes with accessibility constraints?"),
    ("emergence", "transfer", "Could two original mechanics combine into a new cross-genre system?"),
    ("time_change", "testing", "Would the latest revision still beat the old experimental baseline?"),
    ("rights", "transfer", "Is this cross-domain technique reusable without copying protected expression?"),
    ("adversarial", "failure", "Can an adversarial input exploit the known failure boundary?"),
)


@dataclass(frozen=True)
class MotherGleanReport:
    schema: str
    owner: str
    at: str
    knowledge_root: str
    nest_history_head: str
    acquisitions: tuple[HatchlingReceipt, ...]
    probes: tuple[LensProbe, ...]
    hypotheses: tuple[MeaningHypothesis, ...]
    synergies: tuple[SynergyHypothesis, ...]
    research_gaps: tuple[str, ...]
    conflict_ids: tuple[str, ...]
    improvement: str
    digest: str
    neural_weights_modified: bool = False
    promotion_authorized: bool = False


def _hit_id(hit: KnowledgeHit) -> str:
    # Include revision, note, polarity and span: identical mirrored articles
    # cannot pretend to be independent source documents.
    return canonical_digest((
        hit.owner, hit.source_id, hit.revision_digest, hit.note_id,
        hit.source_text_digest, hit.stance, hit.start, hit.end,
    ))


def _find_acquisition(library: ReviewedKnowledgeStore, owner: str,
                      acquisition: HatchlingReceipt) -> KnowledgeHit:
    rows = library._rows(owner)
    matching = [
        (source, entry["note"])
        for source in rows
        if source["source_id"] == acquisition.source_id
        and source["status"] == "active"
        and source["source_text_digest"] == acquisition.source_text_digest
        and "design_reference" in source["allowed_scopes"]
        for entry in source["notes"]
        if entry["note"]["note_id"] == acquisition.note_id
    ]
    if len(matching) != 1:
        raise ValueError("hatchling receipt is not an active reviewed source note")
    source, note = matching[0]
    if (note["stance"] != "supports" or note["confidence_ppm"] < 800000
            or _instant(source["observed_at"]) > _instant(acquisition.observed_at)):
        raise ValueError("hatchling evidence lacks current high-confidence review")
    # Search yields canonical KnowledgeHit values and checks the current owner
    # rights policy. No raw crawler text is accepted as new facts.
    candidates = library.search(
        owner, note["mechanic"], authorized=True, limit=library.policy.max_query_results,
        min_confidence_ppm=800000, diversify=False,
    )
    found = [hit for hit in candidates
             if hit.source_id == acquisition.source_id
             and hit.source_text_digest == acquisition.source_text_digest
             and hit.note_id == acquisition.note_id]
    if len(found) != 1:
        raise ValueError("hatchling note is not retrievable from reviewed library")
    return found[0]


def _queries(mechanic: str, lens: MeaningLens) -> tuple[str, str, str]:
    # Exactly three independent lookup attempts with different semantic probes,
    # *not* three independent sources merely because a source was reread.
    focus = " ".join(_WORD.findall(mechanic.casefold())[:8])
    if not focus:
        raise ValueError("lens requires a searchable mechanic")
    result = tuple((focus + " " + suffix)[:300] for suffix in lens.probes)
    if len(set(result)) != 3:
        raise ValueError("lens search queries not distinct")
    return result


def glean_mother_insights(
    library: ReviewedKnowledgeStore, nest: DragonNest,
    acquisitions: tuple[HatchlingReceipt, ...], *,
    at: str, idle_since: str, owner_authorized: bool,
    consented: bool, background_allowed: bool,
    lenses: tuple[MeaningLens, ...] = LENSES,
) -> MotherGleanReport:
    """Deterministic tri-pass lenses; discoveries remain unapproved hypotheses.

    Worker entry must also enforce actual resource lease and network limits.
    A returned research gap may be scheduled later through the child planner,
    never fetched or promoted by this method.
    """
    if owner_authorized is not True or consented is not True or background_allowed is not True:
        raise PermissionError("mother glean requires owner consent and idle worker admission")
    if not isinstance(nest, DragonNest) or not verify_change_history(nest):
        raise ValueError("signed owner nest lineage must be verified upstream")
    _id(nest.owner)
    now, since = _instant(at), _instant(idle_since)
    if since > now or (now - since).total_seconds() < 300:
        raise PermissionError("mother may glean only when the app is idle")
    if nest.stage != "adult" or tuple(child.lane for child in nest.children) != LANES:
        raise ValueError("mother's three hatchlings must be unlocked")
    if (not isinstance(acquisitions, tuple) or not 1 <= len(acquisitions) <= MAX_ACQUISITIONS
            or any(not isinstance(x, HatchlingReceipt) for x in acquisitions)
            or len({(x.lane, x.source_id, x.source_text_digest, x.note_id)
                    for x in acquisitions}) != len(acquisitions)):
        raise ValueError("bounded unique hatchling acquisitions required")
    if (not isinstance(lenses, tuple) or not 1 <= len(lenses) <= MAX_LENSES
            or any(not isinstance(x, MeaningLens) for x in lenses)
            or len({x.key for x in lenses}) != len(lenses)):
        raise ValueError("bounded unique mother lenses required")
    root = library.snapshot_root(nest.owner, authorized=True)
    witnesses: list[tuple[HatchlingReceipt, KnowledgeHit]] = []
    for acq in acquisitions:
        evidence = next((child.evidence for child in nest.children if child.lane == acq.lane), ())
        if not any(
            source == acq.source_id and digest == acq.source_text_digest
            and observed == _iso(acq.observed_at)
            for source, digest, observed in evidence
        ):
            raise ValueError("mother acquisition does not appear in the hatchling's lineage")
        if _instant(acq.observed_at) > now:
            raise ValueError("future hatchling observation")
        witnesses.append((acq, _find_acquisition(library, nest.owner, acq)))
    probes: list[LensProbe] = []
    hypotheses: list[MeaningHypothesis] = []
    gaps: list[str] = []
    conflict_ids: set[str] = set()
    cached: dict[str, tuple[KnowledgeHit, ...]] = {}
    for acq, anchor in witnesses:
        for lens in lenses:
            signatures: dict[str, KnowledgeHit] = {}
            for query in _queries(anchor.mechanic, lens):
                if query not in cached:
                    cached[query] = library.search(
                        nest.owner, query, authorized=True,
                        limit=min(24, library.policy.max_query_results),
                        min_confidence_ppm=800000, diversify=False,
                    )
                matches = cached[query]
                for hit in matches:
                    if hit.mechanic != anchor.mechanic:
                        continue
                    signatures[_hit_id(hit)] = hit
                groups = {h.dependence_group for h in matches
                          if h.mechanic == anchor.mechanic}
                stances = {h.stance for h in matches if h.mechanic == anchor.mechanic}
                conflicting = "supports" in stances and "challenges" in stances
                ids = tuple(sorted(_hit_id(h) for h in matches
                                   if h.mechanic == anchor.mechanic))
                probes.append(LensProbe(
                    lens.key, query, ids, len(groups), conflicting,
                    canonical_digest((lens.key, query, ids)),
                ))
            relevant = [
                h for h in signatures.values()
                if set(_WORD.findall(h.statement.casefold())) & set(lens.cues)
            ]
            supporting = [h for h in relevant if h.stance == "supports"]
            challenging = [h for h in relevant if h.stance == "challenges"]
            support_groups = {h.dependence_group for h in supporting}
            # Explicitly disallow counting one source's repeated passes or
            # mirrored sources with a shared dependence group as corroboration.
            diverse_sources = {h.source_id for h in supporting}
            unresolved = bool(challenging) or any(p.conflicting for p in probes[-3:])
            if unresolved:
                conflict_ids.update(_hit_id(h) for h in challenging)
            if len(support_groups) < 2 or len(diverse_sources) < 2 or unresolved:
                gaps.extend(_queries(anchor.mechanic, lens)[:1])
                continue
            citations = tuple(sorted({_hit_id(h) for h in supporting}))
            hypothesis_id = canonical_digest((
                nest.owner, root, acq.lane, acq.source_id, acq.source_text_digest,
                anchor.mechanic, lens.key, citations,
            ))
            hypotheses.append(MeaningHypothesis(
                hypothesis_id, acq.lane, acq.source_id, acq.note_id,
                lens.key, anchor.mechanic,
                lens.question,
                "Potential cross-source implication for " + anchor.mechanic
                + " (" + lens.key.replace("_", " ") + "); verify with a controlled experiment.",
                lens.concern, citations, len(support_groups),
            ))
    # Do not publish a partial hypothesis set if the canonical knowledge
    # changes during the multi-lens searches.
    if library.snapshot_root(nest.owner, authorized=True) != root:
        raise ValueError("reviewed knowledge changed during mother glean")
    unique_hypotheses = tuple(dict.fromkeys(hypotheses))
    synergies = []
    for acq, _ in witnesses:
        by_lens = {
            h.lens: h for h in unique_hypotheses
            if h.lane == acq.lane and h.source_id == acq.source_id
            and h.note_id == acq.note_id
        }
        for first, second, question in SYNERGIES:
            if first not in by_lens or second not in by_lens:
                continue
            citations = tuple(sorted(
                set(by_lens[first].evidence_ids) | set(by_lens[second].evidence_ids)
            ))
            if len(citations) < 3:
                continue
            identity = canonical_digest((
                nest.owner, root, acq.source_id, acq.source_text_digest,
                acq.note_id, first, second, citations,
            ))
            synergies.append(SynergyHypothesis(
                identity, acq.lane, acq.source_id, acq.note_id,
                (first, second), question, citations,
            ))
    note = (f"(mother glean improved: {len(probes)} verified lens searches, "
            f"{len(unique_hypotheses)} testable subtext hypotheses, "
            f"{len(synergies)} cross-lens synergies, "
            f"{len(set(gaps))} unresolved research gaps; no automatic weight promotion)")
    fields = (
        "skeleton.dragon.mother_glean.v1", nest.owner, _iso(at), root, nest.head,
        tuple(asdict(x) for x in acquisitions),
        tuple(asdict(x) for x in probes),
        tuple(asdict(x) for x in unique_hypotheses),
        tuple(asdict(x) for x in synergies),
        tuple(sorted(set(gaps))), tuple(sorted(conflict_ids)), note,
    )
    return MotherGleanReport(
        fields[0], fields[1], fields[2], fields[3], fields[4], acquisitions,
        tuple(probes), unique_hypotheses, tuple(synergies),
        tuple(sorted(set(gaps))), tuple(sorted(conflict_ids)),
        note, canonical_digest(fields),
    )


def verify_mother_report(report: MotherGleanReport) -> bool:
    """Integrity of the derived report, not authority to modify model weights."""
    if not isinstance(report, MotherGleanReport):
        return False
    try:
        fields = (
            report.schema, report.owner, report.at, report.knowledge_root,
            report.nest_history_head,
            tuple(asdict(x) for x in report.acquisitions),
            tuple(asdict(x) for x in report.probes),
            tuple(asdict(x) for x in report.hypotheses),
            tuple(asdict(x) for x in report.synergies),
            report.research_gaps, report.conflict_ids, report.improvement,
        )
        return (report.schema == "skeleton.dragon.mother_glean.v1"
                and report.neural_weights_modified is False
                and report.promotion_authorized is False
                and report.improvement.startswith("(")
                and report.improvement.endswith(")")
                and report.digest == canonical_digest(fields))
    except (TypeError, ValueError, AttributeError):
        return False
