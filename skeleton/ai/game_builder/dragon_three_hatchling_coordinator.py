"""Mother Dragon: first-class ARTICLE, VIDEO and UPDATES hatchling coordination.

Three separate source-backed evidence inputs are always reported. A matching
word across three packets is a research question, NOT proof of source
independence, factual agreement, training utility or permission to crawl.
"""
from __future__ import annotations

from collections import Counter
import re

from skeleton.ai.webcrawler.dragon_nest_store import DragonNestStore

from .contracts import canonical_digest
from .dragon_evidence_disagreement import three_way_evidence_risks
from .dragon_almanacs import _auth
from .dragon_article_hatchling import DragonArticleHatchling
from .dragon_source_delta_ledger import DragonSourceDeltaLedger
from .dragon_research_source_picker import DragonResearchSourcePicker
from .dragon_video_transcript_ledger import DragonVideoTranscriptLedger
from .reviewed_knowledge import _integer

_WORDS = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "the and for from with this that what when which into upon they them were "
    "have been will would game games video article update changed research "
    "evidence source system your their where above below after before".split()
)
_MAX_MATCHES = 12
_MAX_TERMS = 12


def _vocabulary(text: str) -> set[str]:
    return {w for w in _WORDS.findall(text.lower())
            if len(w) >= 3 and w not in _STOP}


class DragonThreeHatchlingCoordinator:
    """Read-only three-lane child/parent research views."""

    def __init__(self, article: DragonArticleHatchling,
                 video: DragonVideoTranscriptLedger,
                 updates: DragonSourceDeltaLedger,
                 nest: DragonNestStore | None = None):
        if (not isinstance(article, DragonArticleHatchling)
            or not isinstance(video, DragonVideoTranscriptLedger)
            or not isinstance(updates, DragonSourceDeltaLedger)
            or article.captures.db is not updates.db
            or video.db is not updates.db):
            raise TypeError("same canonical owner and all three specialists required")
        if nest is not None and not isinstance(nest, DragonNestStore):
            raise TypeError("signed Dragon nest required for game progress")
        self.article = article
        self.video = video
        self.updates = updates
        self.nest = nest

    def source_catalog(self, owner: str, *, authorized: bool,
                       limit: int = 30, after_source: str | None = None) -> dict:
        """Discover validated owner-specific candidate identities, never crawl."""
        return DragonResearchSourcePicker(
            self.article,self.video,self.updates
        ).page(owner,authorized=authorized,limit=limit,
               after_source=after_source)

    def status(self, owner: str, *, article_source_id: str,
               video_source_id: str, update_source_id: str,
               authorized: bool) -> dict:
        """Review readiness of all three children; no child is skipped."""
        _auth(owner, authorized)
        if video_source_id in {article_source_id, update_source_id}:
            raise ValueError("video and web article source identities must differ")
        article = self.article.review_packet(
            owner, article_source_id, authorized=True)
        # A brand-new owner's egg does not yet have a signed nest snapshot.
        # Report zero real progression without creating a new nest. A present
        # but corrupted signature is still rejected by DragonNestStore.read.
        game = self.nest.read(owner, authorized=True) if self.nest else None
        children = {child.lane: child for child in game.children} if game else {}
        video = self.video.review_packet(
            owner, video_source_id, authorized=True, include_quotes=False)
        update = self.updates.review_packet(
            owner, update_source_id, authorized=True)
        article_ready = bool(article["candidate_capture_digest"])
        video_ready = video is not None
        update_ready = update is not None
        rows = [
            {
                "lane": "article", "source_id": article_source_id,
                "status": "review_ready" if article_ready else "awaiting_capture",
                "capture_digest": article["candidate_capture_digest"],
                "observed_at": article["candidate_observed_at"],
                "improvements": article["improvements"],
                "review_required": article_ready,
            },
            {
                "lane": "video", "source_id": video_source_id,
                "status": "review_ready" if video_ready else "awaiting_licensed_transcript",
                "capture_digest": video["capture_digest"] if video else None,
                "observed_at": video["observed_at"] if video else None,
                "improvements": [
                    "(timecoded independently signed transcript reference staged)"
                ] if video_ready else [],
                "review_required": video_ready,
            },
            {
                "lane": "updates", "source_id": update_source_id,
                "status": "review_ready" if update_ready else "awaiting_material_revision",
                "capture_digest": update["delta_receipt"] if update else None,
                "observed_at": update["observed_at"] if update else None,
                "improvements": [
                    "(changed source revisions prepared for independent review)"
                ] if update_ready else [],
                "review_required": update_ready,
            },
        ]
        for item in rows:
            child = children.get(item["lane"])
            item["growth"] = {
                "stage": child.stage if child else "locked",
                "level": child.level if child else 0,
                "accepted_evidence_count": len(child.evidence) if child else 0,
                "growth_from_pending_research": False,
            }
        return {
            "schema": "skeleton.dragon.three_hatchlings.v1",
            "owner": owner, "hatchlings": rows,
            "lane_count": 3,
            "mother_stage": game.stage if game else "not_initialized",
            "mother_level": game.level if game else None,
            "growth_requires_idle_and_reviewed_knowledge": True,
            "review_ready_count": sum(x["review_required"] for x in rows),
            "all_three_review_ready": all(x["review_required"] for x in rows),
            "distinct_source_count": len({
                article_source_id, video_source_id, update_source_id
            }),
            "independent_sources_verified": False,
            "mother_approval_required": True,
            "network_requests": 0, "xp_awarded": 0,
            "model_training_authorized": False,
        }

    def mother_review(self, owner: str, *, article_source_id: str,
                      video_source_id: str, update_source_id: str,
                      authorized: bool) -> dict:
        """Three-way source-exact lexical hypotheses with provenance and flags.

        Article+updates can use one source (often the natural layout). This
        MUST be explicitly recorded as only TWO distinct source identities.
        No term match can increase an independence or confidence score.
        """
        _auth(owner, authorized)
        status = self.status(
            owner, article_source_id=article_source_id,
            video_source_id=video_source_id,
            update_source_id=update_source_id, authorized=True)
        base = {
            "schema": "skeleton.dragon.mother_three_lane_review.v1",
            "owner": owner,
            "hatchling_status": status,
            "research_only": True,
            "source_independence_verified": False,
            "agreement_verified": False,
            "knowledge_approved": False,
            "shadow_weights_authorized": False,
            "training_authorized": False,
            "xp_awarded": 0,
            "network_requests": 0,
        }
        if not status["all_three_review_ready"]:
            return {**base, "status": "awaiting_three_reviewable_lanes",
                    "hypotheses": [], "review_questions": []}
        article = self.article.review_packet(
            owner, article_source_id, authorized=True, include_quotes=True)
        video = self.video.review_packet(
            owner, video_source_id, authorized=True, include_quotes=True)
        updates = self.updates.review_packet(
            owner, update_source_id, authorized=True)
        hypotheses = []
        corpus = Counter()
        for cue in video["timecoded_cues"][:32]:
            vt = _vocabulary(cue["text"])
            if not vt:
                continue
            for excerpt in article["passages"][:6]:
                article_quote = excerpt["exact_quote"]
                at = _vocabulary(article_quote)
                shared = vt & at
                if not shared:
                    continue
                for change in updates["candidate_changes"][:12]:
                    after = change.get("after")
                    if not after or not after.get("exact_quote"):
                        continue
                    three_way = sorted(shared & _vocabulary(after["exact_quote"]))
                    if not three_way:
                        continue
                    three_way = three_way[:_MAX_TERMS]
                    corpus.update(three_way)
                    hypothesis = {
                        "source_ids": {
                            "article": article_source_id,
                            "video": video_source_id,
                            "updates": update_source_id,
                        },
                        "video": {
                            "capture_digest": video["capture_digest"],
                            "start_ms": cue["start_ms"],
                            "end_ms": cue["end_ms"],
                            "exact_quote": cue["text"],
                        },
                        "article": {
                            "capture_digest": article["candidate_capture_digest"],
                            "start": excerpt["start"],
                            "end": excerpt["end"],
                            "exact_quote": article_quote,
                        },
                        "updates": {
                            "delta_receipt": updates["delta_receipt"],
                            "start": after["start"], "end": after["end"],
                            "exact_quote": after["exact_quote"],
                        },
                        "shared_terms": three_way,
                        "review_questions": [
                            "Do the three excerpts describe the same hardware, API, "
                            "version and game-building constraint?",
                            "Does the revision invalidate the article or transcript "
                            "claim, or simply use the same words?",
                            "Are the article and updates from the same publisher or "
                            "revision lineage rather than independent sources?",
                        ],
                        "source_agreement_verified": False,
                        "risk_lenses": three_way_evidence_risks(
                            article_quote, cue["text"], after["exact_quote"],
                            tuple(three_way),
                        ),
                        "requires_independent_wiki_review": True,
                    }
                    hypotheses.append({
                        **hypothesis,
                        "hypothesis_digest": canonical_digest(hypothesis),
                    })
                    if len(hypotheses) >= _MAX_MATCHES:
                        break
                if len(hypotheses) >= _MAX_MATCHES:
                    break
            if len(hypotheses) >= _MAX_MATCHES:
                break
        return {
            **base,
            "status": ("three_lane_research_questions" if hypotheses else
                       "no_three_way_exact_term_match"),
            "article_capture_digest": article["candidate_capture_digest"],
            "video_capture_digest": video["capture_digest"],
            "update_delta_receipt": updates["delta_receipt"],
            "three_way_shared_terms": dict(sorted(corpus.items())),
            "hypotheses": hypotheses,
            "review_questions": [
                "Check actual source independence, versions and permitted reuse.",
                "Adversarially test any actionable game-building interpretation "
                "before Wiki/HOAG approval.",
            ],
            "improvements": [
                "(all three hatchlings now supply individually traceable exact evidence)",
                "(mother review flags shared vocabulary without inventing corroboration)",
            ],
        }
