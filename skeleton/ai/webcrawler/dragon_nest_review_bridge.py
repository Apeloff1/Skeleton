"""Trusted Dragon nest handoff from *existing* reviewed knowledge authority.

No new crawler, rights authority or model-promotion ledger is invented here.
The authoritative ReviewedKnowledgeStore verifies the full source revision
graph and current independent evidence before a Dragon nest grows. Callers
must separately enforce real user idle state, source publication dates and
global resource reservations.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from skeleton.ai.game_builder.reviewed_knowledge import (
    KnowledgeBrief, KnowledgeHit, ReviewedKnowledgeStore,
)
from .dragon_nest_progression import AcquiredKnowledge, DragonNest
from .dragon_nest_store import DragonNestStore
from .dragon_mother_glean_ledger import MotherGleanLedger
from .dragon_mother_glean_matrix import HatchlingReceipt

VIDEO_HOSTS = frozenset({
    "youtube.com", "www.youtube.com", "youtu.be",
    "vimeo.com", "www.vimeo.com",
})


class DragonNestReviewBridge:
    def __init__(self, library: ReviewedKnowledgeStore, nest: DragonNestStore,
                 mother_ledger: MotherGleanLedger | None = None):
        if not isinstance(library, ReviewedKnowledgeStore) or not isinstance(nest, DragonNestStore):
            raise ValueError("canonical reviewed-library and durable nest authorities required")
        if mother_ledger is not None and not isinstance(mother_ledger, MotherGleanLedger):
            raise ValueError("mother knowledge authority must be a signed canonical ledger")
        self.library = library
        self.nest = nest
        self.mother_ledger = mother_ledger

    def _checked(
        self, owner: str, brief: KnowledgeBrief, source_id: str, *,
        authorized: bool,
    ) -> tuple[KnowledgeHit, tuple[KnowledgeHit, ...]]:
        if authorized is not True:
            raise PermissionError("trusted reviewed knowledge authority required")
        if (not isinstance(brief, KnowledgeBrief) or brief.owner != owner
                or brief.scope != "design_reference"
                or not brief.requires_human_decision
                or brief.conflicts or brief.independent_groups < 2):
            raise ValueError("independent conflict-free reviewed design brief required")
        # Recompute source revision lineage, evidence identity and rights scope
        # from the canonical store, never from a browser-supplied digest.
        self.library.require_fresh_brief(brief, authorized=True)
        candidates = tuple(hit for hit in brief.citations
                           if hit.source_id == source_id and hit.stance == "supports"
                           and hit.confidence_ppm >= 800000)
        if not candidates:
            raise ValueError("no high-confidence supported source evidence")
        identities = {(hit.revision, hit.revision_digest, hit.source_text_digest,
                       hit.source_url, hit.observed_at) for hit in candidates}
        if len(identities) != 1:
            raise ValueError("ambiguous source revision cannot confer growth")
        # The top hit is used only after all source revisions agree.
        return candidates[0], candidates

    def feed_parent(
        self, owner: str, brief: KnowledgeBrief, source_id: str, *,
        at: str, authorized: bool,
    ) -> DragonNest:
        hit, _ = self._checked(owner, brief, source_id, authorized=authorized)
        return self.nest.record_parent(
            owner, source_id, content_sha256=hit.source_text_digest,
            at=at, authorized=True, reviewed=True, lawful=True,
        )

    def feed_idle(
        self, owner: str, brief: KnowledgeBrief, source_id: str, *,
        lane: str, at: str, idle_since: str,
        consented: bool, background_allowed: bool, authorized: bool,
        published_at: str | None = None,
    ) -> DragonNest:
        hit, candidates = self._checked(owner, brief, source_id, authorized=authorized)
        host = (urlsplit(hit.source_url).hostname or "").lower()
        if lane == "video":
            if host not in VIDEO_HOSTS:
                raise ValueError("video hatchling requires verified reviewed video source")
        elif lane == "article":
            if host in VIDEO_HOSTS:
                raise ValueError("article hatchling cannot claim a video as an article")
        elif lane == "updates":
            # Fresh observation is not proof a source actually changed. Require
            # a newer *reviewed* canonical revision with changed source bytes.
            # Publication still needs separate independently attested dating.
            revisions = self.library.history(owner, source_id, authorized=True)
            if (len(revisions) < 2
                    or revisions[-1].revision != hit.revision
                    or revisions[-1].source_text_digest != hit.source_text_digest
                    or revisions[-2].source_text_digest == hit.source_text_digest):
                raise ValueError("updates require a changed reviewed source revision")
        else:
            raise ValueError("unknown hatchling specialist")
        previous = self.nest.read(owner, authorized=True)
        if previous is None or len(previous.children) != 3:
            raise ValueError("three hatchlings must be unlocked first")
        relevant = tuple(sorted({
            hit.mechanic for hit in candidates
            if hit.mechanic in (*previous.focus_tags, *previous.adjacent_tags)
        }))
        if not relevant:
            raise ValueError("no reviewed task/adjacent topic overlap")
        # The updates lane additionally requires an externally attested source
        # publication date; observation alone never proves publication recency.
        acquisition = AcquiredKnowledge(
            hit.source_id, hit.source_text_digest, hit.observed_at,
            relevant, True, True, min(x.confidence_ppm for x in candidates) / 1_000_000,
            published_at, lane,
        )
        updated = self.nest.record_idle(
            owner, lane, acquisition, at=at, idle_since=idle_since,
            consented=consented, background_allowed=background_allowed,
            authorized=True,
        )
        if self.mother_ledger is not None:
            # Run once for each approved child acquisition and retry on a
            # duplicate event. The signed mother ledger deduplicates by source
            # revision even after siblings grow. If gleaning fails after the
            # nest commit, a retry repeats this step without minting new XP.
            self.mother_ledger.run(
                self.library, updated,
                (HatchlingReceipt(
                    lane, hit.source_id, hit.source_text_digest,
                    hit.note_id, hit.observed_at,
                ),),
                at=at, idle_since=idle_since, owner_authorized=True,
                consented=consented, background_allowed=background_allowed,
            )
        return updated
