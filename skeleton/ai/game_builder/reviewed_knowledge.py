"""Durable, reviewed gameplay knowledge for the canonical game-builder plane.

The research/crawler plane supplies *untrusted* material. An operator supplies
the source body, rights declaration and independently reviewed exact-span
observations. Nothing in this module fetches URLs, learns a user's taste,
trains a model, executes a build, or promotes a candidate.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

from .contracts import canonical_digest, canonical_json


SCHEMA = "skeleton.game_builder.reviewed_knowledge.v1"
BRIEF_SCHEMA = "skeleton.game_builder.reviewed_brief.v1"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_ALLOWED_SCOPES = frozenset({"research", "design_reference", "training_candidate"})
_ALLOWED_STANCES = frozenset({"supports", "challenges", "uncertain"})


class KnowledgeError(ValueError):
    """A knowledge assertion, custody record or store is not admissible."""


def _id(value: object, name: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise KnowledgeError(f"invalid {name}")
    return value


def _text(value: object, name: str, maximum: int, *, minimum: int = 1) -> str:
    if (
        not isinstance(value, str)
        or not minimum <= len(value) <= maximum
        or not value.strip()
        or value != value.strip()
        or any(ord(char) < 32 and char not in "\n\t" for char in value)
    ):
        raise KnowledgeError(f"invalid {name}")
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise KnowledgeError(f"invalid UTF-8 in {name}") from exc
    return value


def _digest(value: object, name: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise KnowledgeError(f"invalid {name}")
    return value


def _integer(value: object, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise KnowledgeError(f"invalid {name}")
    return value


def _utc(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value
    ):
        raise KnowledgeError("observation timestamp must be UTC RFC3339 seconds")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise KnowledgeError("invalid observation timestamp") from exc
    if dt.tzinfo != timezone.utc or dt.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise KnowledgeError("noncanonical observation timestamp")
    return value


def _source_url(value: object) -> str:
    value = _text(value, "source_url", 2048)
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise KnowledgeError("invalid source URL") from exc
    if (
        parsed.scheme != "https" or not parsed.hostname or parsed.username
        or parsed.password or port not in (None, 443) or parsed.fragment
        or any(char.isspace() for char in value)
        or not re.fullmatch(r"[A-Za-z0-9.-]+", parsed.hostname)
    ):
        raise KnowledgeError("source URL must be a canonical HTTPS citation")
    return value


def _words(value: str) -> Counter[str]:
    return Counter(term.casefold() for term in _WORD.findall(value))


def _strict_json(raw: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in items:
            if key in output:
                raise KnowledgeError("duplicate stored JSON key")
            output[key] = value
        return output

    try:
        return json.loads(
            raw, object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(KnowledgeError("nonfinite JSON")),
        )
    except (ValueError, TypeError, UnicodeDecodeError) as exc:
        raise KnowledgeError("invalid stored JSON") from exc


@dataclass(frozen=True, slots=True)
class KnowledgePolicy:
    max_document_chars: int = 1_000_000
    max_evidence_chars: int = 1000
    max_claims_per_revision: int = 256
    max_revisions_per_owner: int = 10_000
    max_query_results: int = 100
    max_brief_hits: int = 40

    def __post_init__(self) -> None:
        _integer(self.max_document_chars, "max_document_chars", 1, 1_000_000)
        _integer(self.max_evidence_chars, "max_evidence_chars", 1, 1000)
        _integer(self.max_claims_per_revision, "max_claims_per_revision", 1, 256)
        _integer(self.max_revisions_per_owner, "max_revisions_per_owner", 1, 10_000)
        _integer(self.max_query_results, "max_query_results", 1, 100)
        _integer(self.max_brief_hits, "max_brief_hits", 1, 40)


@dataclass(frozen=True, slots=True)
class ReviewedNote:
    note_id: str
    mechanic: str
    statement: str
    start: int
    end: int
    stance: str
    confidence_ppm: int
    dependence_group: str
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _id(self.note_id, "note_id")
        _id(self.mechanic, "mechanic")
        _text(self.statement, "statement", 2048)
        _integer(self.start, "span start", 0, 1_000_000)
        _integer(self.end, "span end", 1, 1_000_000)
        if self.end <= self.start:
            raise KnowledgeError("span end must exceed span start")
        if self.stance not in _ALLOWED_STANCES:
            raise KnowledgeError("invalid stance")
        _integer(self.confidence_ppm, "confidence_ppm", 0, 1_000_000)
        _id(self.dependence_group, "dependence_group")
        if not isinstance(self.tags, tuple) or len(self.tags) > 32:
            raise KnowledgeError("invalid tags")
        for tag in self.tags:
            _id(tag, "tag")
        if tuple(sorted(set(self.tags))) != self.tags:
            raise KnowledgeError("tags must be unique and sorted")

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ReviewedNote":
        fields = {
            "note_id", "mechanic", "statement", "start", "end", "stance",
            "confidence_ppm", "dependence_group", "tags",
        }
        if not isinstance(data, dict) or set(data) != fields or not isinstance(data["tags"], list):
            raise KnowledgeError("invalid reviewed note shape")
        try:
            return cls(
                data["note_id"], data["mechanic"], data["statement"],
                data["start"], data["end"], data["stance"],
                data["confidence_ppm"], data["dependence_group"],
                tuple(data["tags"]),
            )
        except (TypeError, ValueError) as exc:
            raise KnowledgeError("invalid reviewed note") from exc

    def to_payload(self) -> dict[str, Any]:
        return {
            "note_id": self.note_id,
            "mechanic": self.mechanic,
            "statement": self.statement,
            "start": self.start,
            "end": self.end,
            "stance": self.stance,
            "confidence_ppm": self.confidence_ppm,
            "dependence_group": self.dependence_group,
            "tags": list(self.tags),
        }


@dataclass(frozen=True, slots=True)
class ReviewedDocument:
    owner: str
    source_id: str
    source_url: str
    title: str
    text: str
    observed_at: str
    license_id: str
    allowed_scopes: tuple[str, ...]
    reviewer_id: str
    approved: bool
    notes: tuple[ReviewedNote, ...]
    status: str = "active"

    def __post_init__(self) -> None:
        _id(self.owner, "owner")
        _id(self.source_id, "source_id")
        _source_url(self.source_url)
        _text(self.title, "title", 300)
        _utc(self.observed_at)
        _id(self.license_id, "license_id")
        _id(self.reviewer_id, "reviewer_id")
        if type(self.approved) is not bool:
            raise KnowledgeError("approved must be boolean")
        if self.status not in {"active", "retracted"}:
            raise KnowledgeError("invalid source status")
        if not isinstance(self.allowed_scopes, tuple):
            raise KnowledgeError("scope list required")
        if not self.allowed_scopes or set(self.allowed_scopes) - _ALLOWED_SCOPES:
            raise KnowledgeError("unknown or empty rights scopes")
        if self.allowed_scopes != tuple(sorted(set(self.allowed_scopes))):
            raise KnowledgeError("rights scopes must be unique and sorted")
        if not isinstance(self.notes, tuple) or not all(
            isinstance(note, ReviewedNote) for note in self.notes
        ):
            raise KnowledgeError("typed reviewed notes required")
        if self.status == "active" and (not self.approved or not self.notes):
            raise KnowledgeError("active research requires review and evidence")
        if self.status == "retracted" and (self.approved or self.notes):
            raise KnowledgeError("retraction cannot carry approved claims")
        if not isinstance(self.text, str):
            raise KnowledgeError("source body must be text")
        try:
            self.text.encode("utf-8", "strict")
        except UnicodeEncodeError as exc:
            raise KnowledgeError("source body must be valid Unicode") from exc

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ReviewedDocument":
        fields = {
            "owner", "source_id", "source_url", "title", "text", "observed_at",
            "license_id", "allowed_scopes", "reviewer_id", "approved", "notes", "status",
        }
        if not isinstance(data, dict) or set(data) != fields:
            raise KnowledgeError("invalid document import shape")
        if not isinstance(data["allowed_scopes"], list) or not isinstance(data["notes"], list):
            raise KnowledgeError("document scopes and notes must be lists")
        try:
            return cls(
                data["owner"], data["source_id"], data["source_url"], data["title"],
                data["text"], data["observed_at"], data["license_id"],
                tuple(data["allowed_scopes"]), data["reviewer_id"], data["approved"],
                tuple(ReviewedNote.from_mapping(note) for note in data["notes"]),
                data["status"],
            )
        except (TypeError, ValueError) as exc:
            raise KnowledgeError("invalid document import") from exc


@dataclass(frozen=True, slots=True)
class RevisionReceipt:
    owner: str
    source_id: str
    revision: int
    revision_digest: str
    parent_digest: str | None
    source_text_digest: str
    claim_count: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "owner": self.owner, "source_id": self.source_id,
            "revision": self.revision, "revision_digest": self.revision_digest,
            "parent_digest": self.parent_digest,
            "source_text_digest": self.source_text_digest, "claim_count": self.claim_count,
        }


@dataclass(frozen=True, slots=True)
class KnowledgeHit:
    owner: str
    source_id: str
    revision: int
    revision_digest: str
    source_url: str
    source_title: str
    source_text_digest: str
    license_id: str
    observed_at: str
    note_id: str
    mechanic: str
    statement: str
    exact_quote: str
    start: int
    end: int
    stance: str
    confidence_ppm: int
    dependence_group: str
    relevance: int

    def to_payload(self) -> dict[str, Any]:
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class KnowledgeBrief:
    owner: str
    query: str
    scope: str
    knowledge_root: str
    citations: tuple[KnowledgeHit, ...]
    conflicts: tuple[str, ...]
    independent_groups: int
    requires_human_decision: bool = True

    def to_payload(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "schema": BRIEF_SCHEMA,
            "owner": self.owner,
            "query": self.query,
            "scope": self.scope,
            "knowledge_root": self.knowledge_root,
            "citations": [hit.to_payload() for hit in self.citations],
            "conflicts": list(self.conflicts),
            "independent_groups": self.independent_groups,
            "requires_human_decision": self.requires_human_decision,
        }
        return {**body, "brief_digest": canonical_digest(body)}


class ReviewedKnowledgeStore:
    """Append-only revisions and bounded owner-isolated retrieval in SQLite.

    SQLite provides atomic file-backed commits, not physical replication or a
    cryptographic signature. External actor authentication and backups belong
    to the embedding process. Never expose this object as an unauthenticated API.
    """

    def __init__(self, path: str | Path, *, policy: KnowledgePolicy | None = None) -> None:
        self.policy = policy or KnowledgePolicy()
        if not isinstance(self.policy, KnowledgePolicy):
            raise KnowledgeError("KnowledgePolicy required")
        self.db = sqlite3.connect(str(path), timeout=10, isolation_level=None)
        self.db.execute("PRAGMA busy_timeout = 10000")
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA journal_mode = WAL")
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS game_builder_knowledge (
                owner TEXT NOT NULL,
                source_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                parent_digest TEXT,
                payload TEXT NOT NULL,
                digest TEXT NOT NULL,
                PRIMARY KEY(owner, source_id, revision)
            )"""
        )

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "ReviewedKnowledgeStore":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _verify_payload(self, body: Any) -> None:
        fields = {
            "schema", "owner", "source_id", "source_url", "title",
            "observed_at", "license_id", "allowed_scopes", "reviewer_id",
            "status", "source_text_digest", "source_chars",
            "revision", "parent_digest", "notes",
        }
        if not isinstance(body, dict) or set(body) != fields or body["schema"] != SCHEMA:
            raise KnowledgeError("stored knowledge schema mismatch")
        _id(body["owner"], "owner")
        _id(body["source_id"], "source_id")
        _source_url(body["source_url"])
        _text(body["title"], "title", 300)
        _utc(body["observed_at"])
        _id(body["license_id"], "license_id")
        _id(body["reviewer_id"], "reviewer_id")
        _digest(body["source_text_digest"], "source_text_digest")
        _integer(body["source_chars"], "source_chars", 0, self.policy.max_document_chars)
        _integer(body["revision"], "revision", 0, self.policy.max_revisions_per_owner)
        if body["parent_digest"] is not None:
            _digest(body["parent_digest"], "parent_digest")
        if not isinstance(body["allowed_scopes"], list):
            raise KnowledgeError("stored rights scopes invalid")
        scopes = body["allowed_scopes"]
        if not scopes or set(scopes) - _ALLOWED_SCOPES or scopes != sorted(set(scopes)):
            raise KnowledgeError("stored rights scopes invalid")
        if body["status"] not in ("active", "retracted"):
            raise KnowledgeError("stored source status invalid")
        notes = body["notes"]
        if not isinstance(notes, list) or len(notes) > self.policy.max_claims_per_revision:
            raise KnowledgeError("stored notes invalid")
        if body["status"] == "active" and not notes:
            raise KnowledgeError("active source has no reviewed notes")
        if body["status"] == "retracted" and notes:
            raise KnowledgeError("retracted source still contains notes")
        seen: set[str] = set()
        for entry in notes:
            if not isinstance(entry, dict) or set(entry) != {"note", "exact_quote"}:
                raise KnowledgeError("stored evidence shape invalid")
            note = ReviewedNote.from_mapping(entry["note"])
            quote = _text(entry["exact_quote"], "exact_quote", self.policy.max_evidence_chars)
            if len(quote) != note.end - note.start:
                raise KnowledgeError("stored source span mismatch")
            if note.note_id in seen:
                raise KnowledgeError("duplicate stored note id")
            seen.add(note.note_id)

    def _rows(self, owner: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            """SELECT source_id, revision, parent_digest, payload, digest
            FROM game_builder_knowledge WHERE owner=?
            ORDER BY source_id, revision LIMIT ?""",
            (owner, self.policy.max_revisions_per_owner + 1),
        ).fetchall()
        if len(rows) > self.policy.max_revisions_per_owner:
            raise KnowledgeError("knowledge revision scan budget exceeded")
        history: dict[str, tuple[int, str, str]] = {}
        latest: dict[str, dict[str, Any]] = {}
        for source_id, revision, parent, raw, digest in rows:
            if not isinstance(raw, str) or len(raw) > 2_000_000:
                raise KnowledgeError("stored knowledge payload exceeds budget")
            body = _strict_json(raw)
            self._verify_payload(body)
            if raw != canonical_json(body) or canonical_digest(body) != digest:
                raise KnowledgeError("knowledge revision content integrity failure")
            if body["owner"] != owner or body["source_id"] != source_id:
                raise KnowledgeError("knowledge owner or source identity mismatch")
            if body["revision"] != revision or body["parent_digest"] != parent:
                raise KnowledgeError("knowledge revision header mismatch")
            previous = history.get(source_id)
            if previous is None:
                if revision != 0 or parent is not None:
                    raise KnowledgeError("knowledge genesis chain invalid")
            elif revision != previous[0] + 1 or parent != previous[1]:
                raise KnowledgeError("knowledge revision parent mismatch")
            if previous and body["observed_at"] <= previous[2]:
                raise KnowledgeError("knowledge revision timestamp rollback")
            history[source_id] = (revision, digest, body["observed_at"])
            latest[source_id] = {**body, "revision_digest": digest}
        return [latest[source_id] for source_id in sorted(latest)]

    def import_document(
        self,
        document: ReviewedDocument,
        *,
        expected_parent_digest: str | None,
        authorized: bool,
    ) -> RevisionReceipt:
        if not authorized:
            raise PermissionError("game knowledge admission requires external authorization")
        if not isinstance(document, ReviewedDocument):
            raise KnowledgeError("ReviewedDocument required")
        if expected_parent_digest is not None:
            _digest(expected_parent_digest, "expected_parent_digest")
        if len(document.text) > self.policy.max_document_chars:
            raise KnowledgeError("source body character budget exceeded")
        if len(document.notes) > self.policy.max_claims_per_revision:
            raise KnowledgeError("source evidence count budget exceeded")
        ids: set[str] = set()
        entries: list[dict[str, Any]] = []
        for note in document.notes:
            if note.note_id in ids:
                raise KnowledgeError("duplicate note id")
            ids.add(note.note_id)
            if note.end > len(document.text):
                raise KnowledgeError("evidence offset outside source body")
            quote = document.text[note.start:note.end]
            _text(quote, "evidence quote", self.policy.max_evidence_chars)
            entries.append({"note": note.to_payload(), "exact_quote": quote})
        entries.sort(key=lambda x: x["note"]["note_id"])
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self._rows(document.owner)  # fail closed on existing corruption
            last = self.db.execute(
                """SELECT revision, digest, payload FROM game_builder_knowledge
                WHERE owner=? AND source_id=?
                ORDER BY revision DESC LIMIT 1""",
                (document.owner, document.source_id),
            ).fetchone()
            revision = 0 if last is None else last[0] + 1
            parent = None if last is None else last[1]
            if expected_parent_digest != parent:
                raise KnowledgeError("stale or incorrect expected revision parent")
            if last is not None:
                previous = _strict_json(last[2])
                if document.observed_at <= previous["observed_at"]:
                    raise KnowledgeError("source observation timestamps must advance")
            if revision >= self.policy.max_revisions_per_owner:
                raise KnowledgeError("source revision budget exceeded")
            body = {
                "schema": SCHEMA, "owner": document.owner,
                "source_id": document.source_id,
                "source_url": document.source_url, "title": document.title,
                "observed_at": document.observed_at,
                "license_id": document.license_id,
                "allowed_scopes": list(document.allowed_scopes),
                "reviewer_id": document.reviewer_id,
                "status": document.status,
                "source_text_digest": sha256(document.text.encode("utf-8")).hexdigest(),
                "source_chars": len(document.text),
                "revision": revision, "parent_digest": parent, "notes": entries,
            }
            self._verify_payload(body)
            digest = canonical_digest(body)
            raw = canonical_json(body)
            if len(raw) > 2_000_000:
                raise KnowledgeError("serialized revision exceeds budget")
            self.db.execute(
                """INSERT INTO game_builder_knowledge
                (owner, source_id, revision, parent_digest, payload, digest)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (document.owner, document.source_id, revision, parent, raw, digest),
            )
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return RevisionReceipt(
            document.owner, document.source_id, revision, digest, parent,
            body["source_text_digest"], len(entries),
        )

    def snapshot_root(self, owner: str, *, authorized: bool) -> str:
        if not authorized:
            raise PermissionError("game knowledge inspection requires authorization")
        owner = _id(owner, "owner")
        entries = self._rows(owner)
        return canonical_digest([
            [e["source_id"], e["revision"], e["revision_digest"]]
            for e in entries
        ])

    def history(self, owner: str, source_id: str, *, authorized: bool) -> tuple[RevisionReceipt, ...]:
        if not authorized:
            raise PermissionError("knowledge history requires authorization")
        owner, source_id = _id(owner, "owner"), _id(source_id, "source_id")
        self._rows(owner)
        rows = self.db.execute(
            """SELECT revision, digest, parent_digest, payload
            FROM game_builder_knowledge
            WHERE owner=? AND source_id=? ORDER BY revision""",
            (owner, source_id),
        ).fetchall()
        return tuple(RevisionReceipt(
            owner, source_id, revision, digest, parent,
            _strict_json(raw)["source_text_digest"],
            len(_strict_json(raw)["notes"]),
        ) for revision, digest, parent, raw in rows)

    def search(
        self, owner: str, query: str, *,
        scope: str = "design_reference",
        limit: int = 12,
        min_confidence_ppm: int = 0,
        authorized: bool,
        diversify: bool = True,
    ) -> tuple[KnowledgeHit, ...]:
        if not authorized:
            raise PermissionError("game knowledge retrieval requires authorization")
        owner = _id(owner, "owner")
        if scope not in _ALLOWED_SCOPES:
            raise KnowledgeError("unsupported knowledge use scope")
        query = _text(query, "query", 300)
        _integer(limit, "limit", 1, self.policy.max_query_results)
        _integer(min_confidence_ppm, "min_confidence_ppm", 0, 1_000_000)
        if type(diversify) is not bool:
            raise KnowledgeError("diversify must be boolean")
        terms = set(_words(query))
        if not terms:
            raise KnowledgeError("query has no searchable terms")
        found: list[KnowledgeHit] = []
        for source in self._rows(owner):
            if source["status"] != "active" or scope not in source["allowed_scopes"]:
                continue
            for entry in source["notes"]:
                note = ReviewedNote.from_mapping(entry["note"])
                if note.confidence_ppm < min_confidence_ppm:
                    continue
                text_words = _words(note.statement)
                mech_words = _words(note.mechanic)
                tag_words = _words(" ".join(note.tags))
                source_words = _words(source["title"])
                relevance = sum(
                    3 * text_words[t] + 6 * mech_words[t]
                    + 2 * tag_words[t] + source_words[t] for t in terms
                )
                if relevance == 0:
                    continue
                found.append(KnowledgeHit(
                    owner, source["source_id"], source["revision"],
                    source["revision_digest"], source["source_url"],
                    source["title"], source["source_text_digest"],
                    source["license_id"], source["observed_at"],
                    note.note_id, note.mechanic, note.statement,
                    entry["exact_quote"], note.start, note.end,
                    note.stance, note.confidence_ppm,
                    note.dependence_group, relevance,
                ))
        found.sort(key=lambda x: (
            -x.relevance, -x.confidence_ppm,
            x.source_id, x.revision, x.note_id,
        ))
        if not diversify:
            return tuple(found[:limit])
        chosen: list[KnowledgeHit] = []
        seen: set[tuple[str, str, str]] = set()
        for hit in found:
            key = (hit.dependence_group, hit.mechanic, hit.stance)
            if key in seen:
                continue
            seen.add(key)
            chosen.append(hit)
            if len(chosen) == limit:
                break
        return tuple(chosen)

    def build_brief(
        self, owner: str, query: str, *,
        authorized: bool, scope: str = "design_reference",
        max_hits: int = 12, min_confidence_ppm: int = 0,
        min_independent_groups: int = 1,
    ) -> KnowledgeBrief:
        if not authorized:
            raise PermissionError("knowledge handoff requires authorization")
        _integer(max_hits, "max_hits", 1, self.policy.max_brief_hits)
        _integer(min_independent_groups, "min_independent_groups", 1, max_hits)
        hits = self.search(
            owner, query, scope=scope, limit=max_hits,
            min_confidence_ppm=min_confidence_ppm, authorized=True,
        )
        groups = len({hit.dependence_group for hit in hits})
        if groups < min_independent_groups:
            raise KnowledgeError("insufficient independent reviewed source groups")
        by_mechanic: dict[str, set[str]] = {}
        for hit in hits:
            by_mechanic.setdefault(hit.mechanic, set()).add(hit.stance)
        conflicts = tuple(sorted(
            mechanic for mechanic, stances in by_mechanic.items()
            if "supports" in stances and "challenges" in stances
        ))
        return KnowledgeBrief(
            owner, query, scope, self.snapshot_root(owner, authorized=True),
            hits, conflicts, groups,
        )

    def require_fresh_brief(self, brief: KnowledgeBrief, *, authorized: bool) -> None:
        if not authorized:
            raise PermissionError("knowledge handoff verification requires authorization")
        if not isinstance(brief, KnowledgeBrief) or not brief.requires_human_decision:
            raise KnowledgeError("typed human-reviewed brief required")
        if self.snapshot_root(brief.owner, authorized=True) != brief.knowledge_root:
            raise KnowledgeError("knowledge changed; regenerate the design brief")
        # Verify every cited note is still query-retrievable, even after policy changes.
        current = self.search(
            brief.owner, brief.query, scope=brief.scope,
            limit=self.policy.max_query_results, authorized=True,
            diversify=False,
        )
        keys = {
            (hit.source_id, hit.revision, hit.note_id, hit.revision_digest)
            for hit in current
        }
        if any(
            (hit.source_id, hit.revision, hit.note_id, hit.revision_digest) not in keys
            for hit in brief.citations
        ):
            raise KnowledgeError("brief evidence is no longer available")

    def erase_owner(self, owner: str, *, authorized: bool) -> int:
        if not authorized:
            raise PermissionError("knowledge erasure requires authorization")
        owner = _id(owner, "owner")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            result = self.db.execute(
                "DELETE FROM game_builder_knowledge WHERE owner=?", (owner,)
            )
            count = result.rowcount
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return count


__all__ = [
    "KnowledgeError", "KnowledgePolicy", "ReviewedNote", "ReviewedDocument",
    "RevisionReceipt", "KnowledgeHit", "KnowledgeBrief", "ReviewedKnowledgeStore",
]
