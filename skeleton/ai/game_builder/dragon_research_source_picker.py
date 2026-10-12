"""Owner-scoped, bounded source selection for the Dragon three-child cockpit.

This is a read-only projection of CANONICAL registered sources, not an
acquisition queue or a rights authorization. The caller must already have
been authenticated by the Dragon Academy principal dependency.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

from .dragon_almanacs import _auth
from .dragon_article_hatchling import DragonArticleHatchling
from .dragon_video_transcript_ledger import DragonVideoTranscriptLedger
from .dragon_source_delta_ledger import DragonSourceDeltaLedger
from .reviewed_knowledge import _integer

_SOURCE = re.compile(r"source-[0-9a-f]{64}\Z")
_MAX_LIMIT = 60


class DragonResearchSourcePicker:
    """No network calls, no worker admissions, no rights or XP changes."""

    def __init__(self, article: DragonArticleHatchling,
                 video: DragonVideoTranscriptLedger,
                 updates: DragonSourceDeltaLedger):
        if (not isinstance(article, DragonArticleHatchling)
            or not isinstance(video, DragonVideoTranscriptLedger)
            or not isinstance(updates, DragonSourceDeltaLedger)
            or article.captures.db is not video.db
            or video.db is not updates.db):
            raise TypeError("canonical shared-owner research custody required")
        self.article = article
        self.video = video
        self.updates = updates
        self.db = updates.db

    def page(self, owner: str, *, authorized: bool,
             limit: int = 30, after_source: str | None = None) -> dict:
        _auth(owner, authorized)
        _integer(limit, "research selection page", 1, _MAX_LIMIT)
        if after_source is not None and (
            type(after_source) is not str
            or not _SOURCE.fullmatch(after_source)
        ):
            raise ValueError("canonical selection cursor required")
        rows = self.db.execute(
            "SELECT source,body,digest FROM dragon_almanac_sources "
            "WHERE owner=? AND source>? ORDER BY source LIMIT ?",
            (owner, after_source or "", limit+1),
        ).fetchall()
        more = len(rows) > limit
        entries = []
        for sid, _, _ in rows[:limit]:
            if not isinstance(sid,str) or not _SOURCE.fullmatch(sid):
                raise ValueError("source registry contains invalid source identity")
            # Validate metadata AND atlas provenance using original custodians.
            # A blocked video source is not a selectable research input.
            try:
                source, seed = self.article.captures._source(owner, sid)
            except ValueError as exc:
                # A video candidate is not an article in the curated atlas.
                # Validate it independently; never ignore a malformed article.
                raw = self.db.execute(
                    "SELECT body FROM dragon_almanac_sources "
                    "WHERE owner=? AND source=?", (owner,sid)
                ).fetchone()
                if not raw or json.loads(raw[0]).get("kind")!="video_candidate":
                    raise
                try:
                    url = self.video._source(owner, sid)
                except PermissionError:
                    # Blocked/absent video job: never advertise as available.
                    continue
                packet = self.video.review_packet(
                    owner,sid,authorized=True,include_quotes=False)
                entries.append({
                    "source_id":sid,"kind":"video",
                    "host":urlsplit(url).hostname,
                    "label":"Video reference",
                    "research_status":(
                        "review_ready" if packet else "awaiting_licensed_transcript"),
                    "capture_digest":packet["capture_digest"] if packet else None,
                    "observed_at":packet["observed_at"] if packet else None,
                    "is_rights_approval":False,
                })
                continue
            # Sources held by policy or missing an active workflow must
            # never be suggested as a ready research selection.
            job = self.db.execute(
                "SELECT state FROM dragon_almanac_jobs WHERE owner=? AND source=?",
                (owner,sid),
            ).fetchone()
            if job is None or job[0]=="blocked":
                continue
            # A valid curated source can be inspected before capture; this
            # alone does not imply the site grants acquisition rights.
            article = self.article.review_packet(
                owner,sid,authorized=True,include_quotes=False)
            entries.append({
                "source_id":sid,"kind":"article",
                "host":urlsplit(source["url"]).hostname,
                "label":seed["slug"],
                "research_status":article["status"],
                "capture_digest":article["candidate_capture_digest"],
                "observed_at":article["candidate_observed_at"],
                "is_rights_approval":False,
            })
        return {
            "schema":"skeleton.dragon.research_source_catalog.v1",
            "owner":owner,
            "entries":entries,
            "page_size":len(entries),
            "scanned_source_count":min(len(rows),limit),
            "has_more":more,
            "next_after_source":rows[limit-1][0] if more else None,
            "training_authorized":False,"xp_awarded":0,
            "read_only":True,"network_requests":0,
            "unreviewed_source_is_not_crawl_permission":True,
        }
