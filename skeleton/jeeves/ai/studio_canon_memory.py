"""Durable, independently reviewed game-canon facts for native Jeeves.

Worlds, NPC identities, quests, scenes and endings need persistent canon across
months of original game production. This host-owned SQLite store preserves every
change as a complete SHA-256-linked revision. Jeeves retrieves facts, but only
a separate human reviewer can amend or retire them through the host.

Do not confuse reviewer IDs or external source-hash declarations with verified
identity providers. The embedding application must authenticate human actors
and check source receipts before passing them into this owner.
"""
from __future__ import annotations

from collections.abc import Mapping
 import json
from pathlib import Path
import re
import sqlite3
from threading import RLock
from typing import Any

from .studio_interaction_contract import identifier, canonical, digest

SCHEMA = "skeleton.jeeves.game_canon.v1"
MAX_REVISIONS = 100_000
MAX_FACT_BYTES = 16 * 1024
WORD = re.compile(r"[^\W_]+", re.UNICODE)
HEX = re.compile(r"^[0-9a-f]{64}$")

_SQL = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS canon_identity(
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    project_id TEXT NOT NULL,
    revision_count INTEGER NOT NULL,
    head_sha256 TEXT
);
CREATE TABLE IF NOT EXISTS canon_revision(
    sequence INTEGER PRIMARY KEY,
    project_id TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    attribute_id TEXT NOT NULL,
    action TEXT NOT NULL,
    fact_json TEXT,
    prior_fact_sha256 TEXT,
    actor_id TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    source_receipt_sha256 TEXT NOT NULL,
    previous_head TEXT,
    digest TEXT NOT NULL UNIQUE
);
"""


class CanonConflict(ValueError):
    """Review authority, canon identity or verified history does not agree."""


def _sha(value: str | None, name: str) -> str | None:
    if value is not None and (not isinstance(value, str) or not HEX.fullmatch(value)):
        raise CanonConflict("invalid " + name + " SHA-256")
    return value


def _fact(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"statement", "scopes", "anchors"}:
        raise CanonConflict("canon fact needs statement, scopes and anchors")
    statement, scopes, anchors = value["statement"], value["scopes"], value["anchors"]
    if not isinstance(statement, str) or not 8 <= len(statement.strip()) <= 8192:
        raise CanonConflict("canon statement must have 8..8192 characters")
    if (not isinstance(scopes, list) or not 1 <= len(scopes) <= 16
            or not isinstance(anchors, list) or len(anchors) > 32):
        raise CanonConflict("canon scopes/anchors outside bounded lists")
    for tag in scopes + anchors:
        identifier(tag, "canon context")
    if len(set(scopes)) != len(scopes) or len(set(anchors)) != len(anchors):
        raise CanonConflict("duplicate scope or anchor")
    result = {
        "statement": statement.strip(),
        "scopes": list(scopes),
        "anchors": list(anchors),
    }
    if len(canonical(result)) > MAX_FACT_BYTES:
        raise CanonConflict("canon fact exceeds private source budget")
    return result


class StudioCanonStore:
    """Owner-bound hash-linked original game facts and conflict-safe revisions."""

    def __init__(
        self, path: Path, *, project_id: str,
        expected_head_sha256: str | None = None,
    ) -> None:
        self.project_id = identifier(project_id, "project")
        self.path = Path(path)
        if not self.path.is_absolute() or self.path.is_symlink():
            raise CanonConflict("canon store requires private absolute non-symlink path")
        if not self.path.parent.is_dir() or self.path.parent.is_symlink():
            raise CanonConflict("canon store requires existing private directory")
        self.expected_head_sha256 = _sha(expected_head_sha256, "external canon head")
        self._lock = RLock()
        self._db = sqlite3.connect(str(path), timeout=10, isolation_level=None,
                                   check_same_thread=False)
        try:
            self._db.execute("PRAGMA busy_timeout=10000")
            self._db.executescript(_SQL)
            if self._db.execute("SELECT COUNT(*) FROM canon_identity").fetchone()[0] == 0:
                if self._db.execute("SELECT COUNT(*) FROM canon_revision").fetchone()[0]:
                    raise CanonConflict("canon history missing owner metadata")
                if self.expected_head_sha256 is not None:
                    raise CanonConflict("missing externally pinned canon history")
                self._db.execute("INSERT INTO canon_identity VALUES (1,?,0,NULL)",
                                 (self.project_id,))
            self._current: dict[tuple[str, str], dict[str, Any]] = {}
            self._sequence = 0
            self._head: str | None = None
            self.verify()
            self._data_version = self._db.execute("PRAGMA data_version").fetchone()[0]
        except BaseException:
            self._db.close()
            raise

    def verify(self) -> dict[str, Any]:
        """Replay and verify all revisions, including retired canon and metadata."""
        with self._lock:
            identity = self._db.execute(
                "SELECT project_id,revision_count,head_sha256 "
                "FROM canon_identity WHERE singleton=1"
            ).fetchone()
            if identity is None or identity[0] != self.project_id:
                raise CanonConflict("canon identity belongs to another project")
            facts: dict[tuple[str, str], dict[str, Any]] = {}
            prev = None
            count = 0
            for row in self._db.execute(
                "SELECT sequence,project_id,subject_id,attribute_id,action,fact_json,"
                "prior_fact_sha256,actor_id,reviewer_id,source_receipt_sha256,"
                "previous_head,digest FROM canon_revision ORDER BY sequence"
            ):
                (seq, project, subject, attribute, action, json_fact, prior_fact,
                 actor, reviewer, source, previous, head) = row
                if (seq != count or count >= MAX_REVISIONS or project != self.project_id
                        or previous != prev or actor == reviewer
                        or action not in ("establish", "amend", "retire")):
                    raise CanonConflict("canon change ancestry or independent review was altered")
                try:
                    identifier(subject, "subject")
                    identifier(attribute, "attribute")
                    identifier(actor, "author")
                    identifier(reviewer, "human reviewer")
                    _sha(source, "source receipt")
                except (ValueError, TypeError) as exc:
                    raise CanonConflict("invalid persisted canon identity") from exc
                if source is None:
                    raise CanonConflict("canon has no source evidence binding")
                key = (subject, attribute)
                former = facts.get(key)
                if ((former is None) != (action == "establish")
                        or (former is not None and action == "establish")
                        or (former is None and action != "establish")):
                    raise CanonConflict("canon revision does not match source ancestry")
                if prior_fact != (former["revision_sha256"] if former else None):
                    raise CanonConflict("canon revision superseded wrong prior fact")
                try:
                    parsed = _fact(json.loads(json_fact)) if action != "retire" else None
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise CanonConflict("invalid persisted canon fact") from exc
                if action != "retire" and canonical(parsed).decode("utf-8") != json_fact:
                    raise CanonConflict("noncanonical persisted canon fact")
                if action == "retire" and json_fact is not None:
                    raise CanonConflict("retirement cannot invent replacement canon")
                item = {
                    "schema_version": SCHEMA, "sequence": seq,
                    "project_id": project, "subject_id": subject,
                    "attribute_id": attribute, "action": action,
                    "fact": parsed, "prior_fact_sha256": prior_fact,
                    "actor_id": actor, "reviewer_id": reviewer,
                    "source_receipt_sha256": source, "previous_head": previous,
                }
                if not isinstance(head, str) or not HEX.fullmatch(head) or digest(item) != head:
                    raise CanonConflict("canon source content differs from chain hash")
                if action == "retire":
                    del facts[key]
                else:
                    facts[key] = {
                        "subject_id": subject, "attribute_id": attribute,
                        "fact": parsed, "revision_sha256": head,
                        "reviewer_id": reviewer,
                        "source_receipt_sha256": source,
                    }
                count += 1
                prev = head
            if (identity[1] != count or identity[2] != prev
                    or self.expected_head_sha256 is not None
                    and self.expected_head_sha256 != prev):
                raise CanonConflict("canon history metadata or independently pinned head changed")
            self._current = facts
            self._sequence = count
            self._head = prev
            return {
                "schema_version": SCHEMA, "project_id": self.project_id,
                "revision_count": count, "active_facts": len(facts),
                "history_sha256": prev,
                "independently_pinned": self.expected_head_sha256 is not None,
            }

    def _check_external(self) -> None:
        latest = self._db.execute("PRAGMA data_version").fetchone()[0]
        if latest != self._data_version:
            self.verify()
            self._data_version = latest

    def revise(
        self, *, subject_id: str, attribute_id: str,
        action: str, expected_fact_sha256: str | None,
        actor_id: str, reviewer_id: str, source_receipt_sha256: str,
        fact: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Compare-and-swap reviewed canon; never silently overwrite an arc."""
        subject_id = identifier(subject_id, "subject")
        attribute_id = identifier(attribute_id, "attribute")
        actor_id = identifier(actor_id, "author")
        reviewer_id = identifier(reviewer_id, "reviewer")
        if actor_id == reviewer_id:
            raise CanonConflict("source author cannot independently approve own canon change")
        if action not in ("establish", "amend", "retire"):
            raise CanonConflict("unsupported canon action")
        _sha(expected_fact_sha256, "expected prior fact")
        _sha(source_receipt_sha256, "reviewed source")
        if source_receipt_sha256 is None:
            raise CanonConflict("reviewed external source receipt is required")
        parsed = _fact(fact) if action != "retire" else None
        if action == "retire" and fact is not None:
            raise CanonConflict("retirement does not accept replacement content")
        with self._lock:
            self._check_external()
            key = (subject_id, attribute_id)
            former = self._current.get(key)
            current_digest = former["revision_sha256"] if former else None
            if (current_digest != expected_fact_sha256
                    or action == "establish" and former is not None
                    or action != "establish" and former is None):
                raise CanonConflict("canon revision conflict; re-read actual project facts")
            if self._sequence >= MAX_REVISIONS:
                raise CanonConflict("canon journal reached archival budget")
            self._db.execute("BEGIN IMMEDIATE")
            try:
                dbmeta = self._db.execute(
                    "SELECT revision_count,head_sha256 FROM canon_identity "
                    "WHERE singleton=1 AND project_id=?", (self.project_id,)
                ).fetchone()
                if dbmeta != (self._sequence, self._head):
                    raise CanonConflict("concurrent canon writer changed the history head")
                receipt = {
                    "schema_version": SCHEMA, "sequence": self._sequence,
                    "project_id": self.project_id, "subject_id": subject_id,
                    "attribute_id": attribute_id, "action": action,
                    "fact": parsed, "prior_fact_sha256": current_digest,
                    "actor_id": actor_id, "reviewer_id": reviewer_id,
                    "source_receipt_sha256": source_receipt_sha256,
                    "previous_head": self._head,
                }
                head = digest(receipt)
                self._db.execute(
                    "INSERT INTO canon_revision VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (self._sequence, self.project_id, subject_id, attribute_id,
                     action, canonical(parsed).decode("utf-8") if parsed is not None else None,
                     current_digest, actor_id, reviewer_id,
                     source_receipt_sha256, self._head, head),
                )
                changed = self._db.execute(
                    "UPDATE canon_identity SET revision_count=?,head_sha256=? "
                    "WHERE singleton=1 AND project_id=? AND revision_count=?",
                    (self._sequence + 1, head, self.project_id, self._sequence),
                ).rowcount
                if changed != 1:
                    raise CanonConflict("concurrent canon metadata update")
                self._db.execute("COMMIT")
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise
            if action == "retire":
                del self._current[key]
            else:
                self._current[key] = {
                    "subject_id": subject_id, "attribute_id": attribute_id,
                    "fact": parsed, "revision_sha256": head,
                    "reviewer_id": reviewer_id,
                    "source_receipt_sha256": source_receipt_sha256,
                }
            self._head = head
            self._sequence += 1
            # A caller who supplied an independently approved startup head
            # may continue making explicit host-reviewed revisions. Advance
            # only this in-process trusted pin after the SQLite CAS commits.
            if self.expected_head_sha256 is not None:
                self.expected_head_sha256 = head
            return {**receipt, "revision_sha256": head}

    def get(self, subject_id: str, attribute_id: str) -> dict[str, Any] | None:
        key = (identifier(subject_id, "subject"), identifier(attribute_id, "attribute"))
        with self._lock:
            self._check_external()
            fact = self._current.get(key)
            return json.loads(canonical(fact)) if fact else None

    def search(
        self, query: str, *, scopes: tuple[str, ...] = (),
        limit: int = 8,
    ) -> dict[str, Any]:
        """Retrieve relevant independent canon facts for Jeeves' native prompt."""
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 2048:
            raise CanonConflict("search requires a bounded game-production question")
        if (type(limit) is not int or not 1 <= limit <= 16
                or not isinstance(scopes, tuple) or len(scopes) > 16):
            raise CanonConflict("canon retrieval budget invalid")
        for tag in scopes:
            identifier(tag, "canon scope")
        tokens = {word.lower() for word in WORD.findall(query) if len(word) > 2}
        with self._lock:
            self._check_external()
            ranking: list[tuple[int, str, str, dict[str, Any]]] = []
            for (subject, attribute), data in self._current.items():
                fact = data["fact"]
                if scopes and not any(scope in fact["scopes"] for scope in scopes):
                    continue
                searchable = " ".join((
                    subject, attribute, fact["statement"],
                    *fact["scopes"], *fact["anchors"],
                ))
                hits = len(tokens & {w.lower() for w in WORD.findall(searchable)})
                if hits == 0:
                    continue
                ranking.append((-hits, subject, attribute, data))
            ranking.sort(key=lambda row: (row[0], row[1], row[2]))
            facts = [item[3] for item in ranking[:limit]]
            return {
                "schema_version": SCHEMA, "project_id": self.project_id,
                "canon_head_sha256": self._head,
                "results": json.loads(canonical(facts)),
                "results_sha256": digest(facts),
                "active_canon_facts": len(self._current),
                "unanswered_scope": not bool(facts),
                "externally_pinned": self.expected_head_sha256 is not None,
            }

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "StudioCanonStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


__all__ = ["StudioCanonStore", "CanonConflict"]
