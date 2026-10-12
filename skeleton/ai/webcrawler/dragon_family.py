"""Idle-only Dragon Family on the canonical crawler's owner-scoped SQLite store.

This is the companion/game projection, NOT another crawler, source authority,
model training path, or HTTP fetcher. The trusted host supplies independently
approved source receipts and idle/capacity observations. No client can mint XP.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from math import isfinite, isqrt
from typing import Callable, Iterable
from urllib.parse import urlsplit
import json
import re
import sqlite3

SCHEMA = "skeleton.ai.dragon.family.v1"
ROLES = ("article", "video", "monitor")
NAMES = {"article": "Ember", "video": "Flicker", "monitor": "Scout"}
ZERO = "0" * 64
HEX = re.compile(r"^[0-9a-f]{64}$")


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def _hash(value: object) -> str:
    return sha256(_json(value).encode("utf-8")).hexdigest()


def _owner(owner: str) -> None:
    if not isinstance(owner, str) or not 1 <= len(owner) <= 128 or any(ord(c) < 32 for c in owner):
        raise ValueError("invalid owner")


def _epoch(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
        raise ValueError("invalid timestamp")
    return float(value)


def _utc(value: float) -> str:
    return datetime.fromtimestamp(_epoch(value), tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _digest(value: str) -> None:
    if not isinstance(value, str) or HEX.fullmatch(value) is None:
        raise ValueError("invalid SHA-256 receipt")


def _tokens(values: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(values, tuple) or len(values) > 24:
        raise ValueError("invalid topic collection")
    clean = []
    for value in values:
        if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_.+-]{1,63}", value):
            raise ValueError("invalid topic")
        clean.append(value)
    return tuple(sorted(set(clean)))


def _uri(url: str) -> None:
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) < 32 for c in url):
        raise ValueError("invalid URL")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("only credential-free HTTPS sources may be registered")


def _source_id(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{1,127}", value):
        raise ValueError("invalid source identity")


@dataclass(frozen=True)
class SourceSeed:
    source_id: str
    url: str
    media: str
    topics: tuple[str, ...]


@dataclass(frozen=True)
class SourceReceipt:
    """Trusted crawler result; caller must verify approval against canonical custody.

    `content_digest` hashes actual canonical source bytes, not title/URL/time.
    `review_digest` binds independent approval; it is not itself an approval.
    `improvement` is a validated delta summary, not an invented model-quality claim.
    """
    source_id: str
    content_digest: str
    review_digest: str
    observed_at: float
    improvement: str = ""


@dataclass(frozen=True)
class IdleWindow:
    now: float
    last_user_activity_at: float
    busy_jobs: int
    foreground_active: bool
    consent: bool
    resources_available: bool = True

    def permitted(self, *, min_idle_seconds: float = 300) -> bool:
        now = _epoch(self.now)
        last = _epoch(self.last_user_activity_at)
        if not isinstance(self.busy_jobs, int) or isinstance(self.busy_jobs, bool) or self.busy_jobs < 0:
            raise ValueError("invalid active job count")
        if not all(type(x) is bool for x in (self.foreground_active, self.consent, self.resources_available)):
            raise ValueError("invalid idle signals")
        return (self.consent and self.resources_available and not self.foreground_active
                and self.busy_jobs == 0 and 0 <= now - last and now - last >= min_idle_seconds)


class DragonFamily:
    """Owner-scoped, append-only provenance and tamper-detecting event projection.

    Pass `approval` ONLY from the trusted crawler producer, never from a client.
    Status/read methods require authorization but cannot insert source receipts.
    """
    def __init__(self, db: sqlite3.Connection,
                 approval: Callable[[SourceReceipt], bool] | None = None,
                 *, min_idle_seconds: float = 300, max_events: int = 100000):
        if not isfinite(min_idle_seconds) or not 60 <= min_idle_seconds <= 86400:
            raise ValueError("invalid idle policy")
        if type(max_events) is not int or not 100 <= max_events <= 1000000:
            raise ValueError("invalid audit budget")
        self.db = db
        self.approval = approval
        self.min_idle_seconds = min_idle_seconds
        self.max_events = max_events
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_family_sources (
          owner TEXT NOT NULL, source_id TEXT NOT NULL, url TEXT NOT NULL,
          media TEXT NOT NULL, topics_json TEXT NOT NULL, registered_at REAL NOT NULL,
          parent_digest TEXT NOT NULL DEFAULT '', PRIMARY KEY(owner,source_id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_family_broods (
          owner TEXT PRIMARY KEY, laid_at REAL NOT NULL, source_total INTEGER NOT NULL,
          source_fingerprint TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_family_readings (
          owner TEXT NOT NULL, dragon TEXT NOT NULL, source_id TEXT NOT NULL,
          content_digest TEXT NOT NULL, review_digest TEXT NOT NULL,
          observed_at REAL NOT NULL, improvement TEXT NOT NULL,
          PRIMARY KEY(owner,dragon,source_id,content_digest))""")
        db.execute("""CREATE INDEX IF NOT EXISTS dragon_family_reading_recent
          ON dragon_family_readings(owner,dragon,observed_at)""")
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_family_events (
          owner TEXT NOT NULL, sequence INTEGER NOT NULL, at REAL NOT NULL,
          dragon TEXT NOT NULL, action TEXT NOT NULL, source_id TEXT NOT NULL,
          details TEXT NOT NULL, previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL,
          PRIMARY KEY(owner,sequence))""")
        db.commit()

    def _writer(self, receipt: SourceReceipt | None, *, authorized: bool) -> None:
        if not authorized or self.approval is None:
            raise PermissionError("trusted, authenticated crawler producer required")
        if receipt is not None:
            _source_id(receipt.source_id)
            _digest(receipt.content_digest)
            _digest(receipt.review_digest)
            _epoch(receipt.observed_at)
            if not isinstance(receipt.improvement, str) or len(receipt.improvement) > 240:
                raise ValueError("invalid improvement description")
            if any(ord(c) < 32 for c in receipt.improvement):
                raise ValueError("invalid improvement description")
            if self.approval(receipt) is not True:
                raise PermissionError("source custody or review was not approved")

    def _event(self, owner: str, at: float, dragon: str, action: str,
               source_id: str, details: str) -> None:
        prev = self.db.execute("""SELECT sequence,event_hash FROM dragon_family_events
             WHERE owner=? ORDER BY sequence DESC LIMIT 1""", (owner,)).fetchone()
        seq, previous = (prev[0] + 1, prev[1]) if prev else (1, ZERO)
        if seq > self.max_events:
            raise ValueError("dragon history capacity exceeded")
        payload = [owner, seq, at, dragon, action, source_id, details, previous]
        digest = _hash(payload)
        self.db.execute("""INSERT INTO dragon_family_events
          VALUES(?,?,?,?,?,?,?,?,?)""",
          (owner, seq, at, dragon, action, source_id, details, previous, digest))

    def enroll(self, owner: str, sources: tuple[SourceSeed, ...], *,
               authorized: bool, now: float) -> int:
        """Register bounded source inventory; existing identities are immutable."""
        _owner(owner)
        self._writer(None, authorized=authorized)
        at = _epoch(now)
        if not isinstance(sources, tuple) or not 1 <= len(sources) <= 500:
            raise ValueError("register 1..500 sources per batch")
        prepared = []
        for seed in sources:
            if not isinstance(seed, SourceSeed) or seed.media not in ("article", "video"):
                raise ValueError("invalid inventory seed")
            _source_id(seed.source_id)
            _uri(seed.url)
            tags = _tokens(seed.topics)
            if not tags:
                raise ValueError("source requires task topics")
            prepared.append((seed.source_id, seed.url, seed.media, _json(tags)))
        if len(set(x[0] for x in prepared)) != len(prepared):
            raise ValueError("duplicate source IDs")
        added = 0
        self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            for sid, url, media, tags in prepared:
                prior = self.db.execute("""SELECT url,media,topics_json FROM dragon_family_sources
                    WHERE owner=? AND source_id=?""", (owner, sid)).fetchone()
                if prior:
                    if prior != (url, media, tags):
                        raise ValueError("immutable source identity conflict")
                    continue
                self.db.execute("""INSERT INTO dragon_family_sources
                    (owner,source_id,url,media,topics_json,registered_at)
                    VALUES(?,?,?,?,?,?)""", (owner, sid, url, media, tags, at))
                self._event(owner, at, "parent", "source_registered", sid, "Source enters the curated research map")
                added += 1
        return added

    def consume(self, owner: str, receipt: SourceReceipt, *,
                authorized: bool) -> bool:
        """Parent only consumes approved unique inventory once. No reread farming."""
        _owner(owner)
        self._writer(receipt, authorized=authorized)
        at = _epoch(receipt.observed_at)
        self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            row = self.db.execute("""SELECT parent_digest FROM dragon_family_sources
                WHERE owner=? AND source_id=?""",
                (owner, receipt.source_id)).fetchone()
            if row is None:
                raise LookupError("source not in curated inventory")
            if row[0]:
                if row[0] != receipt.content_digest:
                    raise ValueError("parent intake is immutable; route revisions to idle brood")
                return False
            brood = self.db.execute("SELECT 1 FROM dragon_family_broods WHERE owner=?", (owner,)).fetchone()
            if brood:
                raise ValueError("parent's initial inventory already completed")
            self.db.execute("""UPDATE dragon_family_sources SET parent_digest=?
                WHERE owner=? AND source_id=? AND parent_digest=''""",
                (receipt.content_digest, owner, receipt.source_id))
            self.db.execute("""INSERT INTO dragon_family_readings
                VALUES(?,?,?,?,?,?,?)""",
                (owner, "parent", receipt.source_id, receipt.content_digest,
                 receipt.review_digest, at, receipt.improvement))
            total, eaten = self.db.execute("""SELECT COUNT(*),COUNT(NULLIF(parent_digest,''))
                FROM dragon_family_sources WHERE owner=?""", (owner,)).fetchone()
            phase = self._phase(total, eaten)
            self._event(owner, at, "parent", "consumed", receipt.source_id,
                        f"{phase}: approved source digested ({eaten}/{total})")
            if total and eaten == total:
                rows = self.db.execute("""SELECT source_id,parent_digest FROM dragon_family_sources
                    WHERE owner=? ORDER BY source_id""", (owner,)).fetchall()
                fingerprint = _hash(rows)
                self.db.execute("INSERT INTO dragon_family_broods VALUES(?,?,?,?)",
                                (owner, at, total, fingerprint))
                self._event(owner, at, "parent", "three_eggs_laid", "",
                            "Adult dragon completed its original source inventory; three idle-only eggs laid")
        return True

    @staticmethod
    def _phase(total: int, eaten: int) -> str:
        if not eaten:
            return "egg"
        if eaten == total:
            return "adult"
        fraction = eaten / total
        return ("hatchling" if fraction < .25 else
                "juvenile" if fraction < .55 else
                "adolescent" if fraction < .85 else "winged")

    def digest_idle(self, owner: str, dragon: str, receipt: SourceReceipt, *,
                    authorized: bool, window: IdleWindow,
                    task_topics: tuple[str, ...], adjacent_topics: tuple[str, ...] = ()) -> bool:
        """Hatch/grow only from novel content under current verified idle admission.

        No fetching is performed here. `monitor` only accepts real revisions to
        previously consumed versions; article/video may accept new discoveries.
        """
        _owner(owner)
        if dragon not in ROLES:
            raise ValueError("unknown hatchling")
        self._writer(receipt, authorized=authorized)
        if not isinstance(window, IdleWindow) or not window.permitted(min_idle_seconds=self.min_idle_seconds):
            raise PermissionError("idle-only brood paused: foreground, activity, capacity or consent")
        current = _tokens(task_topics)
        adjacent = _tokens(adjacent_topics)
        at = _epoch(receipt.observed_at)
        if at > window.now or at < window.last_user_activity_at:
            raise ValueError("receipt outside active idle window")
        self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            if not self.db.execute("SELECT 1 FROM dragon_family_broods WHERE owner=?", (owner,)).fetchone():
                raise PermissionError("brood has not been laid")
            source = self.db.execute("""SELECT media,topics_json,parent_digest FROM dragon_family_sources
                WHERE owner=? AND source_id=?""", (owner, receipt.source_id)).fetchone()
            if source is None:
                raise LookupError("source not in authorized catalog")
            media, tags_json, parent_digest = source
            if dragon != "monitor" and media != dragon:
                raise ValueError("source media does not match hatchling specialty")
            source_topics = set(json.loads(tags_json))
            direct = bool(source_topics.intersection(current))
            near = bool(source_topics.intersection(adjacent))
            if not (direct or near):
                raise ValueError("source unrelated to task or approved adjacent topics")
            latest = self.db.execute("""SELECT content_digest FROM dragon_family_readings
                WHERE owner=? AND dragon=? AND source_id=? ORDER BY observed_at DESC,rowid DESC LIMIT 1""",
                (owner, dragon, receipt.source_id)).fetchone()
            baseline = latest[0] if latest else parent_digest
            if baseline == receipt.content_digest:
                return False
            if dragon == "monitor" and not baseline:
                # Source has never been acquired; an update cannot be claimed.
                return False
            previous = self.db.execute("""SELECT 1 FROM dragon_family_readings
                WHERE owner=? AND dragon=? AND source_id=? AND content_digest=?""",
                (owner, dragon, receipt.source_id, receipt.content_digest)).fetchone()
            if previous:
                return False
            # Reject content replays already known to the parent even if the child
            # has not read them yet, and never mint progress from metadata-only rechecks.
            if receipt.content_digest == parent_digest:
                return False
            improved = bool(baseline and receipt.improvement.strip())
            note = ("(improved: " + receipt.improvement.strip() + ")") if improved else (
                "(updated: new verified source revision)" if baseline else
                "(new: independently approved information acquired)")
            relation = "direct" if direct else "adjacent"
            self.db.execute("""INSERT INTO dragon_family_readings VALUES(?,?,?,?,?,?,?)""",
                            (owner, dragon, receipt.source_id, receipt.content_digest,
                             receipt.review_digest, at, note))
            count = self.db.execute("""SELECT COUNT(*) FROM dragon_family_readings
                WHERE owner=? AND dragon=?""", (owner, dragon)).fetchone()[0]
            self._event(owner, at, dragon, "hatched" if count == 1 else "grew",
                        receipt.source_id, f"{relation} task knowledge {note}")
        return True

    def history(self, owner: str, *, authorized: bool, limit: int = 30) -> list[dict[str, object]]:
        _owner(owner)
        if not authorized:
            raise PermissionError("family journal requires authentication")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("invalid history limit")
        # Read and verify *all* entries, even those preceding the displayed page.
        events = self.db.execute("""SELECT sequence,at,dragon,action,source_id,details,previous_hash,event_hash
            FROM dragon_family_events WHERE owner=? ORDER BY sequence""", (owner,)).fetchall()
        result = []
        previous = ZERO
        for expected, row in enumerate(events, 1):
            seq, at, dragon, action, sid, details, prev, digest = row
            if seq != expected or prev != previous or _hash(
                [owner, seq, at, dragon, action, sid, details, prev]) != digest:
                raise ValueError("dragon family history integrity failure")
            previous = digest
            result.append(dict(sequence=seq, at=_utc(at), dragon=dragon,
                               action=action, source_id=sid, change=details,
                               digest=digest))
        return result[-limit:][::-1]

    def snapshot(self, owner: str, *, authorized: bool, limit: int = 20) -> dict[str, object]:
        _owner(owner)
        # Validate integrity before showing gamified progress.
        history = self.history(owner, authorized=authorized, limit=limit)
        total, consumed = self.db.execute("""SELECT COUNT(*),COUNT(NULLIF(parent_digest,''))
            FROM dragon_family_sources WHERE owner=?""", (owner,)).fetchone()
        brood = self.db.execute("""SELECT laid_at,source_total FROM dragon_family_broods
            WHERE owner=?""", (owner,)).fetchone()
        children = []
        for dragon in ROLES:
            count, seen = self.db.execute("""SELECT COUNT(*),MAX(observed_at)
                FROM dragon_family_readings WHERE owner=? AND dragon=?""",
                (owner, dragon)).fetchone()
            children.append(dict(id=dragon, name=NAMES[dragon], specialty={
                "article": "Web articles", "video": "Video evidence",
                "monitor": "Source updates"}[dragon],
                stage=("unborn" if brood is None else "egg" if count == 0
                       else "hatchling" if count < 3 else "juvenile" if count < 10
                       else "dragon"),
                level=(0 if count == 0 else 1 + min(29, isqrt(count * 4))),
                discoveries=count, last_grew_at=_utc(seen) if seen is not None else None,
                idle_only=True))
        return dict(schema=SCHEMA,
                    parent=dict(stage=self._phase(total, consumed) if brood is None else "adult",
                                consumed=consumed if brood is None else brood[1],
                                source_total=total if brood is None else brood[1],
                                complete=brood is not None,
                                laid_at=_utc(brood[0]) if brood else None),
                    children=children, history=history,
                    pending_source_count=max(0, total - consumed) if brood is None else 0,
                    knowledge_authority="canonical human-approved crawler only",
                    update_policy="idle-only; changed, reviewed content; no synthetic XP")


class IdleBroodRunner:
    """Run a bounded host-scheduled tick; not an autonomous or hidden daemon.

    The host injects trusted source adapters and checks live system-idle state
    before and after each bounded fetch. Adapters must impose network timeouts,
    robots/license/SSRF policy, privacy rules and source budgets.
    """
    def __init__(self, family: DragonFamily, *, max_per_tick: int = 3):
        if type(max_per_tick) is not int or not 1 <= max_per_tick <= 12:
            raise ValueError("invalid idle work budget")
        self.family = family
        self.max_per_tick = max_per_tick

    def tick(self, owner: str, tasks: Iterable[tuple[str, Callable[[], SourceReceipt]]], *,
             authorized: bool, idle_state: Callable[[], IdleWindow],
             task_topics: tuple[str, ...], adjacent_topics: tuple[str, ...] = ()) -> dict[str, int | bool]:
        _owner(owner)
        self.family._writer(None, authorized=authorized)
        stats = {"attempted": 0, "grown": 0, "paused": False}
        for dragon, fetch in tasks:
            if stats["attempted"] >= self.max_per_tick:
                break
            start = idle_state()
            if not isinstance(start, IdleWindow) or not start.permitted(
                    min_idle_seconds=self.family.min_idle_seconds):
                stats["paused"] = True
                break
            if dragon not in ROLES or not callable(fetch):
                raise ValueError("invalid idle gatherer task")
            receipt = fetch()
            # A user action while the network adapter ran invalidates the result.
            end = idle_state()
            if not isinstance(end, IdleWindow) or not end.permitted(
                    min_idle_seconds=self.family.min_idle_seconds):
                stats["paused"] = True
                break
            stats["attempted"] += 1
            if self.family.digest_idle(owner, dragon, receipt, authorized=authorized,
                                       window=end, task_topics=task_topics,
                                       adjacent_topics=adjacent_topics):
                stats["grown"] += 1
        return stats
