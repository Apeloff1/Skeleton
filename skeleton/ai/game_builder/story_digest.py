"""Reference-only narrative analysis and original homebrew premise composition.

Lexical overlap is a triage signal, never a legal non-infringement certificate.
This module does not rewrite copyrighted stories into disguised copies. It
extracts supplied abstract motifs and composes from project-owned ingredients.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
import unicodedata
from typing import Iterable

from .contracts import EvaluatorProvenance, canonical_digest
from .rights import RightsLedger, RightsState, UseKind


MOTIFS = frozenset({"exploration", "identity", "sacrifice", "renewal", "belonging",
    "discovery", "rivalry", "trade", "rescue", "transformation", "time_pressure", "stewardship"})
MOTIF_CUES = {
    "exploration": frozenset({"explore", "explores", "journey", "travel", "navigate", "navigator"}),
    "identity": frozenset({"identity", "self", "disguise", "heritage"}),
    "sacrifice": frozenset({"sacrifice", "sacrifices", "forsake", "renounce"}),
    "renewal": frozenset({"restore", "restores", "rebuild", "rebuilds", "renew"}),
    "belonging": frozenset({"community", "trust", "belonging", "friendship", "family"}),
    "discovery": frozenset({"discover", "discovers", "mystery", "reveal", "investigate"}),
    "rivalry": frozenset({"rival", "rivalry", "compete", "competition"}),
    "trade": frozenset({"trade", "market", "merchant", "exchange"}),
    "rescue": frozenset({"rescue", "rescues", "save", "saves", "liberate"}),
    "transformation": frozenset({"transform", "transforms", "change", "changes", "metamorphosis"}),
    "time_pressure": frozenset({"deadline", "countdown", "urgent", "timed"}),
    "stewardship": frozenset({"steward", "protect", "protects", "conserve", "repair", "repairs"}),
}
ERAS = {
    "renaissance": ("workshop guild", "printing press", "canal district", "civic patronage"),
    "pirate": ("harbor cooperative", "navigation chart", "island market", "crew trust"),
    "industrial": ("repair collective", "rail timetable", "factory quarter", "worker solidarity"),
    "space": ("habitat assembly", "survey instrument", "orbital garden", "resource stewardship"),
}


def _text(value: str, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError("bounded nonempty narrative text required")
    return value.strip()


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text).casefold(), re.UNICODE))


def analyze_story_reference(*, source_id: str, text: str, rights: RightsLedger,
                            artifact_digest: str) -> tuple[StoryReference, dict]:
    """Digest bounded source text into heuristic abstract motif observations.

    The algorithm is a transparent lexical baseline. Its output makes no
    claim to deep narrative understanding or non-infringement; the proposer
    can use these abstractions alongside reviewed source evidence.
    """
    from hashlib import sha256
    _text(text, 100_000)
    source_digest = sha256(text.encode()).hexdigest()
    record = rights.source(source_id)
    if record.content_digest != source_digest:
        raise ValueError("story reference custody mismatch")
    tokens = _tokens(text)
    hits = tuple((motif, sum(token in cues for token in tokens))
                 for motif, cues in sorted(MOTIF_CUES.items()))
    observed = tuple(motif for motif, count in hits if count > 0)
    if not observed:
        raise ValueError("no supported abstract motif found; requires reviewed annotation")
    reference = StoryReference(source_id, source_digest, text, observed)
    digest = digest_references((reference,), rights, artifact_digest=artifact_digest)
    body = {"schema": "skeleton.dragon.story_motif_observation.v1", "source_id": source_id,
        "source_digest": source_digest, "token_count": len(tokens),
        "motif_counts": {motif: count for motif, count in hits if count},
        "method": "lexical_cues_v1", "calibration": "heuristic_not_semantic_truth",
        "narrative_digest": digest.digest, "expressive_text_exported": False,
        "release_authority": False}
    return reference, {**body, "observation_digest": canonical_digest(body)}


@dataclass(frozen=True, slots=True)
class StoryReference:
    source_id: str
    source_digest: str
    text: str
    abstract_motifs: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.source_id, 192)
        _text(self.text, 100_000)
        if not self.abstract_motifs or len(self.abstract_motifs) != len(set(self.abstract_motifs)) or not set(self.abstract_motifs) <= MOTIFS:
            raise ValueError("use declared abstract motifs, not copied expressive summaries")


@dataclass(frozen=True, slots=True)
class NarrativeDigest:
    source_ids: tuple[str, ...]
    motifs: tuple[str, ...]
    rights_snapshot_digest: str
    reference_decision_digests: tuple[str, ...]

    @property
    def digest(self) -> str:
        return canonical_digest({"sources": self.source_ids, "motifs": self.motifs,
            "rights": self.rights_snapshot_digest, "decisions": self.reference_decision_digests})


def digest_references(references: Iterable[StoryReference], rights: RightsLedger, *,
                      artifact_digest: str) -> NarrativeDigest:
    from hashlib import sha256
    rows = tuple(references)
    if not 1 <= len(rows) <= 32 or len({r.source_id for r in rows}) != len(rows):
        raise ValueError("bounded unique story reference set required")
    # Preflight every source before making any ledger decision.
    for row in rows:
        if not isinstance(row, StoryReference):
            raise ValueError("typed story references required")
        source = rights.source(row.source_id)
        if source.content_digest != row.source_digest or sha256(row.text.encode()).hexdigest() != row.source_digest:
            raise ValueError("story reference custody mismatch")
        if source.rights_state in {RightsState.UNKNOWN_QUARANTINE, RightsState.FORBIDDEN}:
            raise ValueError("story reference rights are not cleared")
        if source.rights_state not in {RightsState.FACTS_IDEAS_REFERENCE_ONLY, RightsState.RESTRICTED_REFERENCE_ONLY} and UseKind.FACTS_IDEAS_REFERENCE not in source.allowed_uses:
            raise ValueError("story reference use is not allowed")
    decisions = tuple(rights.decide_incorporation(source_id=r.source_id,
        artifact_digest=artifact_digest, use_kind=UseKind.FACTS_IDEAS_REFERENCE) for r in rows)
    if not all(d.allowed for d in decisions):
        raise ValueError("reference-only narrative analysis refused")
    return NarrativeDigest(tuple(r.source_id for r in rows),
        tuple(sorted({m for r in rows for m in r.abstract_motifs})),
        rights.snapshot()["digest"], tuple(d.decision_digest for d in decisions))


@dataclass(frozen=True, slots=True)
class OriginalIngredients:
    protagonist: str
    community: str
    conflict: str
    resolution: str
    era: str
    mechanic: str
    authorship_evidence: str

    def __post_init__(self) -> None:
        for name in ("protagonist", "community", "conflict", "resolution", "mechanic"):
            _text(getattr(self, name), 512)
        if self.era not in ERAS:
            raise ValueError("unsupported narrative era")
        if not isinstance(self.authorship_evidence, str) or len(self.authorship_evidence) != 64 or any(c not in "0123456789abcdef" for c in self.authorship_evidence):
            raise ValueError("authorship evidence identity required")


@dataclass(frozen=True, slots=True)
class StoryTriage:
    exact_overlap_sources: tuple[str, ...]
    protected_term_sources: tuple[str, ...]
    needs_independent_review: bool
    claim_boundary: str = "lexical triage only; structure, characters, visuals, music and other rights require review"


def triage_story(text: str, references: Iterable[StoryReference], *,
                 protected_terms: Iterable[str] = (), window: int = 8) -> StoryTriage:
    _text(text, 100_000)
    if type(window) is not int or not 4 <= window <= 32:
        raise ValueError("bounded lexical window required")
    tokens = _tokens(text)
    shingles = {tokens[i:i+window] for i in range(max(0, len(tokens)-window+1))}
    overlaps = []
    rows = tuple(references)
    if len(rows) > 32:
        raise ValueError("too many story references")
    for row in rows:
        other = _tokens(row.text)
        if any(other[i:i+window] in shingles for i in range(max(0, len(other)-window+1))):
            overlaps.append(row.source_id)
    terms = tuple(_text(term, 128) for term in protected_terms)
    if len(terms) > 256:
        raise ValueError("protected-term budget exceeded")
    detected = tuple(sorted(term for term in terms if _contains(tokens, _tokens(term))))
    return StoryTriage(tuple(sorted(set(overlaps))), detected, bool(overlaps or detected))


def _contains(tokens: tuple[str, ...], phrase: tuple[str, ...]) -> bool:
    return bool(phrase) and any(tokens[i:i+len(phrase)] == phrase for i in range(len(tokens)-len(phrase)+1))


def compose_original_premise(ingredients: OriginalIngredients, digest: NarrativeDigest) -> dict:
    """Compose from independently authored fields, never from source text.

    This provides a design draft. Neither the authorship hash nor a changed
    era constitutes proof of ownership, originality or legal release approval.
    """
    institution, tool, place, theme = ERAS[ingredients.era]
    premise = (f"{ingredients.protagonist} serves {ingredients.community} near a {place}. "
        f"When {ingredients.conflict}, the community's {institution} must respond. "
        f"Using {ingredients.mechanic} and a {tool}, the player explores {theme}. "
        f"The adventure resolves when {ingredients.resolution}.")
    body = {"schema": "skeleton.dragon.original_story_draft.v1", "premise": premise,
        "era": ingredients.era, "motifs": list(digest.motifs), "research_digest": digest.digest,
        "authorship_evidence": ingredients.authorship_evidence,
        "requires_independent_originality_review": True, "release_authority": False}
    return {**body, "draft_digest": canonical_digest(body)}


@dataclass(frozen=True, slots=True)
class ProfitEvidence:
    product_id: str
    profit: str
    currency: str
    period: str
    accounting_basis: str
    evidence_digest: str
    provenance: EvaluatorProvenance

    def __post_init__(self) -> None:
        for value in (self.product_id, self.period, self.accounting_basis):
            _text(value, 192)
        if not isinstance(self.profit, str) or len(self.profit) > 64:
            raise ValueError("bounded decimal profit required")
        try:
            amount = Decimal(self.profit)
        except InvalidOperation as exc:
            raise ValueError("reported profit must be decimal") from exc
        if not amount.is_finite():
            raise ValueError("finite reported profit required")
        if not isinstance(self.currency, str) or not re.fullmatch(r"[A-Z]{3}", self.currency):
            raise ValueError("declared currency required")
        if not isinstance(self.provenance, EvaluatorProvenance) or self.evidence_digest not in self.provenance.output_evidence_refs:
            raise ValueError("profit needs independently sourced output evidence")


def rank_by_profit(rows: Iterable[ProfitEvidence]) -> tuple[ProfitEvidence, ...]:
    """Rank reported profit, never substitute revenue, units or estimates."""
    values = tuple(rows)
    if len(values) > 256 or any(not isinstance(r, ProfitEvidence) for r in values):
        raise ValueError("bounded typed profit observations required")
    if len({r.product_id for r in values}) != len(values):
        raise ValueError("one profit observation per product required")
    if len({(r.currency, r.period, r.accounting_basis) for r in values}) > 1:
        raise ValueError("incomparable currencies, periods or accounting bases")
    return tuple(sorted(values, key=lambda r: (-Decimal(r.profit), r.product_id)))
