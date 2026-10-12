"""Article hatchling: retain exact reviewable findings across unchanged recrawls.

The article hatchling's HTTP acquisition and fenced sequential almanac remain
in DragonTechnicalSources/DragonSourceCaptures. This module provides a bounded,
owner-scoped, read-only *specialist review surface* with the same first-class
status as video and updates. It never invents new content, rights or XP.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import re

from .dragon_almanacs import _auth
from .dragon_technical_source_captures import DragonSourceCaptures
from .dragon_technical_source_analysis import _LENSES
from .reviewed_knowledge import _integer

_WORDS = re.compile(r"[a-z0-9]+")
_MAX_PASSAGES = 6


class DragonArticleHatchling:
    def __init__(self, captures: DragonSourceCaptures):
        if not isinstance(captures, DragonSourceCaptures):
            raise TypeError("canonical article capture custody required")
        self.captures = captures

    def review_packet(self, owner: str, source_id: str, *,
                      authorized: bool, include_quotes: bool = False) -> dict:
        """Select latest MATERIAL revision, not necessarily latest observation.

        Reobservation with unchanged bytes MUST NOT discard the most recent
        article's unreviewed evidence. No claim about its acceptance by Wiki is
        inferred: this is only a candidate packet.
        """
        _auth(owner, authorized)
        if type(include_quotes) is not bool:
            raise ValueError("explicit quote visibility required")
        source, seed = self.captures._source(owner, source_id)
        chain = self.captures._history(owner, source_id)
        latest = chain[-1] if chain else None
        candidate = next(
            (r for r in reversed(chain) if r["change"] in {"new", "changed"}),
            None,
        )
        base = {
            "schema": "skeleton.dragon.article_hatchling_review.v1",
            "lane": "article", "owner": owner, "source_id": source_id,
            "source_url": source["url"],
            "catalog_family": seed["family"],
            "status": "review_candidate" if candidate else "not_yet_captured",
            "observation_count": len(chain),
            "latest_observation_digest": latest["digest"] if latest else None,
            "latest_observation_at": latest["observed_at"] if latest else None,
            "latest_observation_change": latest["change"] if latest else None,
            "candidate_capture_digest": candidate["digest"] if candidate else None,
            "candidate_content_sha256": candidate["content_sha256"] if candidate else None,
            "candidate_observed_at": candidate["observed_at"] if candidate else None,
            "unchanged_rechecks_after_candidate": (
                sum(r["change"] == "unchanged" for r in chain[candidate["sequence"]:])
                if candidate else 0
            ),
            "independent_review_required": bool(candidate),
            "acceptance_state_not_inferred": True,
            "knowledge_approved": False,
            "xp_awarded": 0,
            "training_authorized": False,
            "network_requests": 0,
            "worker_reservations": 0,
        }
        if candidate is None:
            return {**base, "passages": [], "lens_counts": {},
                    "improvements": []}
        text = candidate["document"]["text"]
        spans = candidate["evidence_candidates"][:_MAX_PASSAGES]
        passages = []
        lenses = Counter()
        for p in spans:
            start, end = p["start"], p["end"]
            quote = p["exact_quote"]
            if (type(start) is not int or type(end) is not int
                or text[start:end] != quote
                or p.get("review_required") is not True):
                raise ValueError("article exact-span custody invalid")
            tokens = set(_WORDS.findall(quote.lower()))
            hits = tuple(sorted(
                name for name, words in _LENSES.items()
                if tokens.intersection(words)
            ))
            lenses.update(hits)
            passages.append({
                "start": start, "end": end,
                "exact_quote": quote if include_quotes else None,
                "quote_sha256": sha256(quote.encode("utf-8")).hexdigest(),
                "lens_hints": hits,
                "rights_recheck_required": True,
                "independent_claim_verification_required": True,
            })
        improvement = (
            "(latest material article revision preserved despite unchanged rechecks)"
            if base["unchanged_rechecks_after_candidate"]
            else "(article evidence organized into exact citations and research lenses)"
        )
        return {**base, "passages": passages,
                "lens_counts": dict(sorted(lenses.items())),
                "improvements": [improvement]}

    def census(self, owner: str, *, authorized: bool,
               limit: int = 64, after_source: str | None = None) -> dict:
        """Deterministic, bounded article hatchling status across the owner."""
        _auth(owner, authorized)
        _integer(limit, "article census page", 1, 100)
        if after_source is not None and (
            not isinstance(after_source, str)
            or not re.fullmatch(r"source-[0-9a-f]{64}", after_source)
        ):
            raise ValueError("canonical article cursor required")
        rows = self.captures.db.execute(
            "SELECT DISTINCT source FROM dragon_technical_captures_v1 "
            "WHERE owner=? AND source>? ORDER BY source LIMIT ?",
            (owner, after_source or "", limit + 1)
        ).fetchall()
        more = len(rows) > limit
        ids = [r[0] for r in rows[:limit]]
        items = [
            self.review_packet(owner, sid, authorized=True)
            for sid in ids
        ]
        return {
            "schema": "skeleton.dragon.article_hatchling_census.v1",
            "owner": owner, "lane": "article",
            "items": items, "count_this_page": len(items),
            "has_more": more,
            "next_after_source": ids[-1] if more and ids else None,
            "read_only": True, "network_requests": 0,
            "training_authorized": False,
        }
