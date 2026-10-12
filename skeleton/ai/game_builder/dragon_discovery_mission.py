"""Deterministic task-directed scouting over Dragon's unapproved source inventory.

Catalog headings and URL strings are *discovery metadata*. This module never
fetches content, grants rights, changes source priority in the durable scheduler,
makes a knowledge claim, or approves training. It offers a bounded, inspectable
proposal for an independently authorized policy-review worker.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from urllib.parse import urlsplit

from .contracts import canonical_digest
from .dragon_almanacs import DragonAlmanacs, _auth
from .dragon_source_catalog import canonical_source_url
from .reviewed_knowledge import _id, _integer


_WORDS = re.compile(r"[a-z0-9]+")
_SUSPICIOUS = frozenset({
    "rom", "roms", "bios", "firmware", "iso", "isos", "warez", "crack",
    "cracked", "pirated", "dump", "dumps", "torrent", "keygen",
})
_MAX_METADATA = 32768


def _tokens(value: str) -> frozenset[str]:
    return frozenset(_WORDS.findall(value.casefold().replace("_", " ")))


def _safe_phrase(value: str, label: str, *, maximum: int, required: bool) -> str:
    if not isinstance(value, str) or len(value) > maximum or (
            required and len(value.strip()) < 3):
        raise ValueError(f"invalid mission {label}")
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError(f"invalid mission {label}")
    return " ".join(value.split())


@dataclass(frozen=True, slots=True)
class SourceMission:
    goal: str
    platform: str = ""
    genre: str = ""
    era: str = ""
    prefer_video: bool = False
    limit: int = 25
    scan_budget: int = 2000

    def __post_init__(self) -> None:
        for field_name, max_length, required in (
            ("goal", 400, True), ("platform", 120, False),
            ("genre", 120, False), ("era", 80, False),
        ):
            object.__setattr__(self, field_name, _safe_phrase(
                getattr(self, field_name), field_name,
                maximum=max_length, required=required))
        if not _tokens(self.goal):
            raise ValueError("mission requires searchable text")
        if type(self.prefer_video) is not bool:
            raise ValueError("video preference must be boolean")
        _integer(self.limit, "scout limit", 1, 100)
        _integer(self.scan_budget, "scout scan budget", self.limit, 10_000)


class MissionSourceScout:
    """Bounded owner-scoped mission proposals with explicit coverage caveats."""

    def __init__(self, almanacs: DragonAlmanacs) -> None:
        if not isinstance(almanacs, DragonAlmanacs):
            raise TypeError("canonical DragonAlmanacs required")
        self.db = almanacs.db

    def propose(self, owner: str, mission: SourceMission, *, authorized: bool,
                topic: str | None = None) -> dict:
        _auth(owner, authorized)
        if not isinstance(mission, SourceMission):
            raise ValueError("typed mission required")
        if topic is not None:
            _id(topic, "mission topic")
            if not self.db.execute(
                    "SELECT 1 FROM dragon_almanac_topics WHERE owner=? AND topic=?",
                    (owner, topic)).fetchone():
                raise ValueError("unknown owner topic")
        condition = (
            "AND EXISTS(SELECT 1 FROM dragon_almanac_members m "
            "WHERE m.owner=s.owner AND m.source=s.source AND m.topic=?)"
            if topic is not None else ""
        )
        sql = (
            "SELECT s.source,s.body,s.digest,j.stage,j.state FROM dragon_almanac_sources s "
            "JOIN dragon_almanac_jobs j ON j.owner=s.owner AND j.source=s.source "
            "WHERE s.owner=? AND j.stage=0 AND j.state IN ('pending','blocked') "
            + condition + " ORDER BY s.source LIMIT ?"
        )
        params = [owner]
        if topic is not None:
            params.append(topic)
        params.append(mission.scan_budget + 1)
        rows = self.db.execute(sql, params).fetchall()
        truncated = len(rows) > mission.scan_budget
        goal_tokens = _tokens(mission.goal)
        platform_tokens = _tokens(mission.platform)
        genre_tokens = _tokens(mission.genre)
        era_tokens = _tokens(mission.era)
        found_terms = set()
        candidates = []
        for sid, raw, digest, stage, state in rows[:mission.scan_budget]:
            if not isinstance(raw, str) or len(raw) > _MAX_METADATA:
                raise ValueError("corrupt source metadata size")
            source = json.loads(raw)
            url = source.get("url")
            if (canonical_digest(source) != digest or
                    url != canonical_source_url(url) or
                    sid != "source-" + sha256(url.encode("utf-8")).hexdigest() or
                    source.get("source_id") != sid):
                raise ValueError("corrupt source identity")
            if state not in {"pending", "blocked"} or stage != 0:
                raise ValueError("invalid scout source stage")
            refs = self.db.execute(
                "SELECT body,digest FROM dragon_almanac_supplement_receipts_v2 "
                "WHERE owner=? AND normalized_source=? "
                "ORDER BY origin_source,supplement_digest LIMIT 65",
                (owner, sid)).fetchall()
            if len(refs) > 64:
                raise ValueError("scout provenance review budget exceeded")
            headings = set()
            repositories = set()
            for receipt_raw, receipt_digest in refs:
                if not isinstance(receipt_raw, str) or len(receipt_raw) > 262144:
                    raise ValueError("oversized catalog provenance")
                receipt = json.loads(receipt_raw)
                candidate = receipt.get("candidate")
                if (canonical_digest(receipt) != receipt_digest or
                        receipt.get("normalized_source_id") != sid or
                        receipt.get("normalized_url") != url or
                        receipt.get("authority") != "unreviewed_discovery_only" or
                        not isinstance(candidate, dict) or
                        canonical_source_url(candidate.get("url")) != url):
                    raise ValueError("invalid catalog provenance")
                for origin in candidate.get("discoveries", []):
                    if not isinstance(origin, dict):
                        raise ValueError("invalid provenance origin")
                    for heading in origin.get("headers", []):
                        if not isinstance(heading, str):
                            raise ValueError("invalid provenance heading")
                        headings.add(heading)
                    if isinstance(origin.get("repository"), str):
                        repositories.add(origin["repository"])
            for origin in source.get("discoveries", []):
                if not isinstance(origin, dict):
                    raise ValueError("invalid stored discovery")
                for heading in origin.get("headers", []):
                    if not isinstance(heading, str):
                        raise ValueError("invalid stored heading")
                    headings.add(heading)
                if isinstance(origin.get("catalog_id"), str):
                    repositories.add(origin["catalog_id"])
            label = " ".join(sorted(headings)) + " " + " ".join(sorted(repositories))
            # Text is metadata only: a matching title or heading is not a
            # verified article and cannot establish provenance independence.
            haystack = _tokens(label + " " + urlsplit(url).path.replace("/", " ") +
                               " " + urlsplit(url).hostname.replace(".", " "))
            found_terms.update(goal_tokens & haystack)
            def coverage(tokens: frozenset[str]) -> float:
                return len(haystack & tokens) / len(tokens) if tokens else 0.0
            factors = {
                "goal_overlap": round(coverage(goal_tokens), 6),
                "platform_overlap": round(coverage(platform_tokens), 6),
                "genre_overlap": round(coverage(genre_tokens), 6),
                "era_overlap": round(coverage(era_tokens), 6),
            }
            score = round(min(1.0, 0.58 * factors["goal_overlap"] +
                              0.22 * factors["platform_overlap"] +
                              0.12 * factors["genre_overlap"] +
                              0.08 * factors["era_overlap"] +
                              (0.03 if headings else 0) +
                              (0.03 if mission.prefer_video and
                               source.get("kind") == "video_candidate" else 0)), 6)
            if score <= 0:
                continue
            risk = sorted(_SUSPICIOUS & haystack)
            candidates.append({
                "source_id": sid, "url": url, "host": urlsplit(url).hostname,
                "kind": source.get("kind"), "score": score, "factors": factors,
                "matched_goal_terms": sorted(goal_tokens & haystack),
                "claimed_heading_count": len(headings),
                "claimed_catalog_count": len(repositories),
                "raw_provenance_receipts": len(refs),
                "policy_state": state,
                "needs_manual_rights_review": bool(risk),
                "rights_risk_tokens": risk,
                "network_authorized": False, "training_authorized": False,
            })
        candidates.sort(key=lambda entry: (-entry["score"], entry["url"]))
        # Host diversity is a recommendation display policy only; it is NOT an
        # assertion that different hosts supply independent original evidence.
        first_hosts = set()
        distinct = []
        later = []
        for entry in candidates:
            if entry["host"] not in first_hosts:
                first_hosts.add(entry["host"])
                distinct.append(entry)
            else:
                later.append(entry)
        selected = (distinct + later)[:mission.limit]
        return {
            "schema": "skeleton.dragon.discovery_mission_scout.v1",
            "owner": owner, "topic": topic,
            "mission": {"goal": mission.goal, "platform": mission.platform,
                        "genre": mission.genre, "era": mission.era,
                        "prefer_video": mission.prefer_video},
            "scanned": min(len(rows), mission.scan_budget),
            "eligible_metadata_matches": len(candidates),
            "scan_truncated": truncated,
            "selection": selected,
            "unmatched_goal_terms_in_scanned_corpus": sorted(goal_tokens - found_terms),
            "ranking_scope": "discovery_metadata_only_not_verified_content",
            "host_diversity_is_not_independence": True,
            "queue_modified": False,
            "crawler_authorized": False, "training_authorized": False,
            "policy_review_required": True,
        }
