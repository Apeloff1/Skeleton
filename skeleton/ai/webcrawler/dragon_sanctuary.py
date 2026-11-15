"""Current-consent, account-scoped Dragon habitat collection.

This is a finite read-time projection of already authorized source rows.
No extra data store, long-lived XP wallet, raw text export, source-use grant,
network operation, or background agent is created. The backend owns scope,
freshness, version fencing and the decision to admit each source to this view.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
import re
from urllib.parse import urlsplit

from .dragon_companion import _signature, _similarity, _lexical_quality, _medium
from .frontier_coverage import _unicode_terms

SCHEMA = "skeleton.dragon.sanctuary.v1"
MAX_EXPEDITIONS = 8
MAX_CANDIDATES = 128
MAX_SOURCE_BYTES = 24_000
_HEX = re.compile(r"[a-f0-9]{64}\Z")


@dataclass(frozen=True)
class SanctuarySource:
    session_id: str
    source_id: str
    content_hash: str
    fetched_url: str
    content_type: str
    text: str
    query: str
    fetched_at: float
    valid_until: float


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("ascii")).hexdigest()


def _check(row: SanctuarySource, *, as_of: float) -> None:
    if (not isinstance(row, SanctuarySource)
            or not isinstance(row.session_id, str) or not 1 <= len(row.session_id) <= 128
            or not isinstance(row.source_id, str) or not _HEX.fullmatch(row.source_id)
            or not isinstance(row.content_hash, str) or not _HEX.fullmatch(row.content_hash)
            or not isinstance(row.fetched_url, str) or len(row.fetched_url.encode("utf-8")) > 4096
            or not isinstance(row.text, str) or len(row.text.encode("utf-8")) > MAX_SOURCE_BYTES
            or not isinstance(row.query, str) or len(row.query) > 1024
            or not isinstance(row.content_type, str) or len(row.content_type) > 256):
        raise ValueError("invalid sanctuary source")
    for value in (row.fetched_at, row.valid_until):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("invalid sanctuary source clock")
    if row.fetched_at > as_of + 300 or row.valid_until <= as_of:
        raise ValueError("sanctuary source consent or freshness expired")
    target = urlsplit(row.fetched_url)
    if target.scheme not in {"http", "https"} or not target.hostname or target.username or target.password:
        raise ValueError("invalid sanctuary source origin")


def project_sanctuary(rows: list[SanctuarySource], *, as_of: float,
                      selected_sessions: list[dict], excluded_sessions: int,
                      candidate_limit_reached: bool) -> dict:
    if (not isinstance(rows, list) or len(rows) > MAX_CANDIDATES
            or not isinstance(selected_sessions, list) or len(selected_sessions) > MAX_EXPEDITIONS
            or type(excluded_sessions) is not int or not 0 <= excluded_sessions <= MAX_EXPEDITIONS
            or type(candidate_limit_reached) is not bool or isinstance(as_of, bool)
            or not isinstance(as_of, (int, float)) or not math.isfinite(as_of)):
        raise ValueError("invalid sanctuary envelope")
    sessions = {}
    for revision in selected_sessions:
        if (not isinstance(revision, dict) or set(revision) != {"session_id", "version", "snapshot_digest"}
                or not isinstance(revision["session_id"], str) or not 1 <= len(revision["session_id"]) <= 128
                or revision["session_id"] in sessions
                or type(revision["version"]) is not int or revision["version"] < 1
                or not isinstance(revision["snapshot_digest"], str) or not _HEX.fullmatch(revision["snapshot_digest"])):
            raise ValueError("invalid sanctuary revision identity")
        sessions[revision["session_id"]] = revision
    identities = set()
    hashes = set()
    archive = []
    hosts = set()
    formats = Counter()
    per_host = defaultdict(float)
    contributions = Counter()
    duplicate_count = 0
    low_signal = 0
    novel_count = 0
    credit_total = 0.
    source_refs = []
    for row in sorted(rows, key=lambda x: (x.fetched_at, x.session_id, x.source_id)):
        _check(row, as_of=as_of)
        identity = row.session_id, row.source_id
        if row.session_id not in sessions or identity in identities:
            raise ValueError("sanctuary source is not bound to one selected revision")
        identities.add(identity)
        if row.content_hash in hashes:
            duplicate_count += 1
            continue
        hashes.add(row.content_hash)
        signature = _signature(row.text)
        novelty = 1 - max((_similarity(signature, previous) for previous in archive), default=0.) if signature else 0.
        if signature:
            archive.append(signature)
        wanted = frozenset(sorted(_unicode_terms(row.query))[:32])
        relevant = len(_unicode_terms(row.text) & wanted) / len(wanted) if wanted else .5
        host = urlsplit(row.fetched_url).hostname
        quality = _lexical_quality(row.text)
        reward = novelty * relevant * quality / math.sqrt(1 + per_host[host])
        if len(row.text) < 80 or novelty < .25 or reward < .05:
            low_signal += 1
            continue
        per_host[host] += reward
        hosts.add(host)
        formats[_medium(row.content_type)] += 1
        contributions[row.session_id] += 1
        credit_total += reward
        novel_count += 1
        if len(source_refs) < 16:
            source_refs.append({"session_id": row.session_id, "source_id": row.source_id,
                                "credit_milli": round(reward*1000)})
    # This index is the current consent-authorized portfolio, not permanent XP.
    collection = min(1., .55 * min(1., credit_total / 16)
                     + .25 * min(1., len(hosts) / 8)
                     + .20 * min(1., len(formats) / 6))
    index = int(round(collection * 1000))
    stage = sum(index >= threshold for threshold in (120, 300, 550, 800))
    revision_digest = _digest({
        "revisions": sorted(selected_sessions, key=lambda x: x["session_id"]),
        "identities": sorted((row.session_id, row.source_id, row.content_hash) for row in rows),
        "novel_count": novel_count, "collection": index, "formats": dict(formats),
    })
    return {"schema": SCHEMA, "collection_index": index, "stage": stage,
            "form": ("hatchling", "scout", "scholar", "pathfinder", "archivist")[stage],
            "eligible_expeditions": len(sessions), "contributing_expeditions": len(contributions),
            "unqualified_expeditions": excluded_sessions, "candidate_sources": len(rows),
            "distinct_content": len(hashes), "credited_sources": novel_count,
            "exact_duplicates": duplicate_count, "low_signal_sources": low_signal,
            "distinct_origins": len(hosts), "habitats": dict(sorted(formats.items())),
            "source_refs": source_refs, "revision_digest": revision_digest,
            "candidate_limit_reached": candidate_limit_reached,
            "as_of_unix": round(as_of, 3),
            "earliest_source_expiry": min((row.valid_until for row in rows), default=None),
            "current_consent_only": True, "persistent_reward_wallet": False,
            "source_text_returned": False, "training_permission": False,
            "network_authority_expanded": False}
