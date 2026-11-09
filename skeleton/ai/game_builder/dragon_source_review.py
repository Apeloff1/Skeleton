"""Bounded human source annotations in the existing reviewed-knowledge store.

Crawler captures remain external evidence. An explicit design-reference review
creates a canonical uncalibrated note, never a promotion or training grant.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from .contracts import canonical_digest, canonical_json
from .reviewed_knowledge import (
    KnowledgeError,
    ReviewedDocument,
    ReviewedKnowledgeStore,
    ReviewedNote,
)

MAX_CANDIDATES = 64
MAX_BYTES = 16 * 1024


def checked(raw: str, digest: str, maximum: int = MAX_BYTES) -> dict[str, Any]:
    if not isinstance(raw, str) or len(raw.encode()) > maximum:
        raise KnowledgeError("source review record exceeds bound")

    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise KnowledgeError("duplicate source review field")
            out[key] = value
        return out

    try:
        value = json.loads(
            raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError())
        )
    except (ValueError, TypeError, RecursionError) as exc:
        raise KnowledgeError("source review record is invalid") from exc
    if not isinstance(value, dict) or canonical_json(value) != raw or canonical_digest(value) != digest:
        raise KnowledgeError("source review record digest mismatch")
    return value


def normalized(value: object, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > maximum:
        raise KnowledgeError(f"invalid {name}")
    if any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise KnowledgeError(f"invalid {name}")
    value.encode("utf-8", "strict")
    return value


def command_id(owner: str, key: str) -> str:
    return sha256((owner + "\x00" + normalized(key, "idempotency key", 128)).encode()).hexdigest()


class CapturedSourceReviews:
    """Candidate, review intent and exact source bindings in the same SQLite."""

    def __init__(self, store: ReviewedKnowledgeStore):
        self.store, self.db = store, store.db
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS game_builder_source_candidates(
          owner TEXT NOT NULL, candidate_id TEXT NOT NULL, request_digest TEXT NOT NULL,
          payload TEXT NOT NULL, digest TEXT NOT NULL, state TEXT NOT NULL,
          version INTEGER NOT NULL, created_at TEXT NOT NULL,
          PRIMARY KEY(owner,candidate_id));
        CREATE TABLE IF NOT EXISTS game_builder_source_reviews(
          owner TEXT NOT NULL, review_id TEXT NOT NULL, candidate_id TEXT NOT NULL,
          request_digest TEXT NOT NULL,payload TEXT NOT NULL,digest TEXT NOT NULL,
          PRIMARY KEY(owner,review_id), UNIQUE(owner,candidate_id));
        CREATE TABLE IF NOT EXISTS game_builder_captured_source_bindings(
          owner TEXT NOT NULL,source_id TEXT NOT NULL,revision_digest TEXT NOT NULL,
          payload TEXT NOT NULL,digest TEXT NOT NULL,PRIMARY KEY(owner,source_id));
        """)

    def get(self, owner: str, identifier: str) -> dict:
        row = self.db.execute(
            "SELECT length(CAST(payload AS BLOB)) FROM game_builder_source_candidates WHERE owner=? AND candidate_id=?",
            (owner, identifier),
        ).fetchone()
        if row is None:
            raise LookupError("source candidate not found")
        if row[0] > MAX_BYTES:
            raise KnowledgeError("source candidate exceeds bound")
        row = self.db.execute(
            "SELECT payload,digest,state,version,request_digest FROM game_builder_source_candidates WHERE owner=? AND candidate_id=?",
            (owner, identifier),
        ).fetchone()
        value = checked(row[0], row[1])
        if (
            value.get("candidate_id") != identifier
            or value.get("owner_id") != owner
            or value.get("state") != row[2]
            or value.get("version") != row[3]
            or value.get("request_digest") != row[4]
        ):
            raise KnowledgeError("candidate identity mismatch")
        return value

    def create(self, owner: str, request: dict, evidence: dict) -> dict:
        identifier = command_id(owner, request["idempotency_key"])
        request_digest = canonical_digest(request)
        try:
            prior = self.get(owner, identifier)
        except LookupError:
            prior = None
        if prior is not None:
            if prior["request_digest"] != request_digest:
                raise KnowledgeError("idempotency key has a different source candidate")
            return prior
        source, ref = evidence["source"], evidence["reference"]
        text = source.get("text")
        start, end = request["start"], request["end"]
        if (
            not isinstance(text, str)
            or type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(text)
            or end - start > 1000
        ):
            raise KnowledgeError("invalid exact source codepoint span")
        quote = normalized(text[start:end], "exact quote", 1000)
        now = datetime.now(UTC).isoformat()
        value = {
            "schema_version": "skeleton.dragon.source_candidate.v1",
            "owner_id": owner,
            "candidate_id": identifier,
            "request_digest": request_digest,
            "version": 1,
            "state": "pending_review",
            "session_id": request["session_id"],
            "source_id": request["source_id"],
            "source_ref": ref,
            "source_digest": ref["source_digest"],
            "source_url": source.get("final_url") or source.get("url"),
            "title": str(
                source.get("title") or source.get("final_url") or source.get("url") or "Captured source"
            ).strip()[:300],
            "start": start,
            "end": end,
            "exact_quote": quote,
            "quote_digest": sha256(quote.encode()).hexdigest(),
            "statement": normalized(request["statement"], "statement", 2048),
            "mechanic": request["mechanic"],
            "valid_until": evidence["valid_until"],
            "created_at": now,
            "review": None,
            "knowledge": None,
        }
        raw = canonical_json(value)
        if len(raw.encode()) > MAX_BYTES:
            raise KnowledgeError("candidate payload exceeds bound")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            count = self.db.execute(
                "SELECT COUNT(*) FROM game_builder_source_candidates WHERE owner=?", (owner,)
            ).fetchone()[0]
            if count >= MAX_CANDIDATES:
                raise KnowledgeError("owner source candidate budget exhausted")
            self.db.execute(
                "INSERT INTO game_builder_source_candidates VALUES(?,?,?,?,?,?,?,?)",
                (owner, identifier, request_digest, raw, canonical_digest(value), "pending_review", 1, now),
            )
            self.db.execute("COMMIT")
        except sqlite3.IntegrityError:
            self.db.execute("ROLLBACK")
            prior = self.get(owner, identifier)
            if prior["request_digest"] != request_digest:
                raise KnowledgeError("idempotency key has a different source candidate")
            return prior
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return value

    def list(
        self, owner: str, *, state: str | None = None, after: str = "", limit: int = 20
    ) -> tuple[list[dict], str | None]:
        if (
            type(limit) is not int
            or not 1 <= limit <= 20
            or state not in (None, "pending_review", "approved", "rejected")
        ):
            raise KnowledgeError("invalid source candidate page")
        rows = self.db.execute(
            "SELECT candidate_id FROM game_builder_source_candidates WHERE owner=? AND candidate_id>? AND (? IS NULL OR state=?) ORDER BY candidate_id LIMIT ?",
            (owner, after, state, state, limit + 1),
        ).fetchall()
        values = [self.get(owner, row[0]) for row in rows[:limit]]
        return values, values[-1]["candidate_id"] if len(rows) > limit else None

    def begin_review(self, owner: str, identifier: str, request: dict, reviewer: str) -> dict:
        review_id = command_id(owner, request["idempotency_key"])
        identity = canonical_digest({"candidate_id": identifier, "request": request, "reviewer_id": reviewer})
        self.db.execute("BEGIN IMMEDIATE")
        try:
            prior = self.db.execute(
                "SELECT payload,digest,request_digest FROM game_builder_source_reviews WHERE owner=? AND review_id=?",
                (owner, review_id),
            ).fetchone()
            if prior:
                if prior[2] != identity:
                    raise KnowledgeError("review idempotency conflict")
                result = checked(prior[0], prior[1])
            else:
                candidate = self.get(owner, identifier)
                if (
                    candidate["version"] != request["expected_version"]
                    or candidate["state"] != "pending_review"
                ):
                    raise KnowledgeError("source candidate version conflict")
                result = {
                    "review_id": review_id,
                    "candidate_id": identifier,
                    "decision": request["decision"],
                    "rationale": normalized(request["rationale"], "rationale", 2048),
                    "reviewer_id": reviewer,
                    "rights_reference": request.get("rights_reference"),
                    "reviewed_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "training_allowed": False,
                    "request_digest": identity,
                }
                # Reserve the complete bounded final annotation before issuing
                # an immutable review intent. Oversized rationale cannot strand
                # a candidate behind an unfinishable command.
                projected = {
                    **candidate,
                    "review": result,
                    "knowledge": {
                        "owner": owner,
                        "source_id": "crawler-review:" + identifier,
                        "revision": 0,
                        "revision_digest": "0" * 64,
                        "parent_digest": None,
                        "source_text_digest": "0" * 64,
                        "claim_count": 1,
                        "note_id": "note-" + identifier,
                    },
                }
                if len(canonical_json(projected).encode()) > MAX_BYTES:
                    raise KnowledgeError("complete review record exceeds bound")
                self.db.execute(
                    "INSERT INTO game_builder_source_reviews VALUES(?,?,?,?,?,?)",
                    (
                        owner,
                        review_id,
                        identifier,
                        identity,
                        canonical_json(result),
                        canonical_digest(result),
                    ),
                )
            self.db.execute("COMMIT")
            return result
        except sqlite3.IntegrityError as exc:
            self.db.execute("ROLLBACK")
            raise KnowledgeError("another review already owns this candidate") from exc
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def review_intent(self, owner: str, identifier: str, review_id: str | None = None) -> dict | None:
        header = self.db.execute(
            "SELECT review_id,request_digest,length(CAST(payload AS BLOB)) FROM game_builder_source_reviews WHERE owner=? AND candidate_id=?",
            (owner, identifier),
        ).fetchone()
        if header is None:
            return None
        if header[2] > MAX_BYTES or (review_id is not None and header[0] != review_id):
            raise KnowledgeError("exact prepared review intent is unavailable")
        row = self.db.execute(
            "SELECT payload,digest FROM game_builder_source_reviews WHERE owner=? AND candidate_id=?",
            (owner, identifier),
        ).fetchone()
        value = checked(row[0], row[1])
        if (
            set(value)
            != {
                "review_id",
                "candidate_id",
                "decision",
                "rationale",
                "reviewer_id",
                "rights_reference",
                "reviewed_at",
                "training_allowed",
                "request_digest",
            }
            or value["review_id"] != header[0]
            or value["request_digest"] != header[1]
            or value["candidate_id"] != identifier
            or value["reviewer_id"] != owner
            or value["training_allowed"] is not False
            or value["decision"] not in {"approve_design_reference", "reject"}
        ):
            raise KnowledgeError("prepared review intent identity mismatch")
        return value

    @staticmethod
    def _approval_document(owner: str, candidate: dict, intent: dict, source_text: str) -> ReviewedDocument:
        note = ReviewedNote(
            "note-" + candidate["candidate_id"],
            candidate["mechanic"],
            candidate["statement"],
            candidate["start"],
            candidate["end"],
            "uncertain",
            0,
            "unverified-crawler-corpus",
            ("human-reference",),
        )
        return ReviewedDocument(
            owner,
            "crawler-review:" + candidate["candidate_id"],
            candidate["source_url"],
            candidate["title"],
            source_text,
            intent["reviewed_at"],
            intent["rights_reference"],
            ("design_reference", "research"),
            intent["reviewer_id"],
            True,
            (note,),
        )

    def validate_approval(self, owner: str, identifier: str, request: dict, source_text: str) -> None:
        if request["decision"] != "approve_design_reference":
            return
        candidate = self.get(owner, identifier)
        if len(source_text) > self.store.policy.max_document_chars:
            raise KnowledgeError("source body character budget exceeded")
        if source_text[candidate["start"] : candidate["end"]] != candidate["exact_quote"]:
            raise KnowledgeError("current source span changed")
        self._approval_document(
            owner,
            candidate,
            {
                "reviewed_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "rights_reference": request.get("rights_reference"),
                "reviewer_id": owner,
            },
            source_text,
        )

    def finish_review(self, owner: str, identifier: str, intent: dict, source_text: str) -> dict:
        if (
            not isinstance(intent, dict)
            or self.review_intent(owner, identifier, intent.get("review_id")) != intent
        ):
            raise KnowledgeError("an exact issued review intent is required")
        candidate = self.get(owner, identifier)
        if candidate["review"] is not None:
            if candidate["review"]["review_id"] != intent["review_id"]:
                raise KnowledgeError("source candidate already reviewed")
            return candidate
        if source_text[candidate["start"] : candidate["end"]] != candidate["exact_quote"]:
            raise KnowledgeError("current source span changed")
        receipt = None
        if intent["decision"] == "approve_design_reference":
            document = self._approval_document(owner, candidate, intent, source_text)
            note = document.notes[0]
            # Stable intent time and reserved source ID allow exact reconstruction
            # after canonical import committed but binding publication was interrupted.
            body = {
                "schema": "skeleton.game_builder.reviewed_knowledge.v1",
                "owner": owner,
                "source_id": document.source_id,
                "source_url": document.source_url,
                "title": document.title,
                "observed_at": document.observed_at,
                "license_id": document.license_id,
                "allowed_scopes": list(document.allowed_scopes),
                "reviewer_id": document.reviewer_id,
                "status": "active",
                "source_text_digest": sha256(source_text.encode()).hexdigest(),
                "source_chars": len(source_text),
                "revision": 0,
                "parent_digest": None,
                "notes": [{"note": note.to_payload(), "exact_quote": candidate["exact_quote"]}],
            }
            self.store._verify_payload(body)
            expected = canonical_digest(body)
            history = self.store.history(owner, document.source_id, authorized=True)
            if history:
                if len(history) != 1 or history[0].revision_digest != expected:
                    raise KnowledgeError("reviewed source publication identity mismatch")
                revision = history[0]
            else:
                try:
                    revision = self.store.import_document(
                        document, expected_parent_digest=None, authorized=True
                    )
                except KnowledgeError:
                    history = self.store.history(owner, document.source_id, authorized=True)
                    if len(history) != 1 or history[0].revision_digest != expected:
                        raise
                    revision = history[0]
            receipt = {**revision.to_payload(), "note_id": note.note_id}
        value = {
            **candidate,
            "state": "approved" if receipt else "rejected",
            "version": candidate["version"] + 1,
            "review": intent,
            "knowledge": receipt,
        }
        self.db.execute("BEGIN IMMEDIATE")
        try:
            current = self.get(owner, identifier)
            if current["review"] is not None:
                if current["review"] != intent:
                    raise KnowledgeError("review publication conflict")
                self.db.execute("COMMIT")
                return current
            if receipt:
                binding = {
                    "schema_version": "skeleton.dragon.captured_binding.v1",
                    "owner_id": owner,
                    "candidate_id": identifier,
                    "review_id": intent["review_id"],
                    "source_id": receipt["source_id"],
                    "revision_digest": receipt["revision_digest"],
                    "source_ref": candidate["source_ref"],
                    "valid_until": candidate["valid_until"],
                }
                self.db.execute(
                    "INSERT INTO game_builder_captured_source_bindings VALUES(?,?,?,?,?)",
                    (
                        owner,
                        receipt["source_id"],
                        receipt["revision_digest"],
                        canonical_json(binding),
                        canonical_digest(binding),
                    ),
                )
            self.db.execute(
                "UPDATE game_builder_source_candidates SET payload=?,digest=?,state=?,version=? WHERE owner=? AND candidate_id=? AND version=?",
                (
                    canonical_json(value),
                    canonical_digest(value),
                    value["state"],
                    value["version"],
                    owner,
                    identifier,
                    candidate["version"],
                ),
            )
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return value

    def bindings(self, owner: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT source_id,revision_digest,length(CAST(payload AS BLOB)) FROM game_builder_captured_source_bindings WHERE owner=? LIMIT ?",
            (owner, MAX_CANDIDATES + 1),
        ).fetchall()
        if len(rows) > MAX_CANDIDATES or any(row[2] > MAX_BYTES for row in rows):
            raise KnowledgeError("captured binding budget exceeded")
        out = []
        for source_id, revision, _ in rows:
            raw, digest = self.db.execute(
                "SELECT payload,digest FROM game_builder_captured_source_bindings WHERE owner=? AND source_id=?",
                (owner, source_id),
            ).fetchone()
            value = checked(raw, digest)
            if (
                value.get("owner_id") != owner
                or value.get("source_id") != source_id
                or value.get("revision_digest") != revision
            ):
                raise KnowledgeError("captured binding identity mismatch")
            review_row = self.db.execute(
                "SELECT candidate_id,request_digest,length(CAST(payload AS BLOB)) FROM game_builder_source_reviews WHERE owner=? AND review_id=?",
                (owner, value["review_id"]),
            ).fetchone()
            if review_row is None or review_row[0] != value["candidate_id"] or review_row[2] > MAX_BYTES:
                raise KnowledgeError("captured binding review intent is unavailable")
            review_raw, review_digest = self.db.execute(
                "SELECT payload,digest FROM game_builder_source_reviews WHERE owner=? AND review_id=?",
                (owner, value["review_id"]),
            ).fetchone()
            review = checked(review_raw, review_digest)
            candidate = self.get(owner, value["candidate_id"])
            if review != candidate["review"] or review.get("request_digest") != review_row[1]:
                raise KnowledgeError("captured binding review intent differs")
            if (
                candidate["state"] != "approved"
                or candidate["knowledge"]["revision_digest"] != revision
                or candidate["source_ref"] != value["source_ref"]
                or candidate["valid_until"] != value["valid_until"]
                or candidate["review"]["review_id"] != value["review_id"]
            ):
                raise KnowledgeError("captured binding candidate mismatch")
            out.append(value)
        return out

    @staticmethod
    def unexpired(binding: Mapping) -> bool:
        try:
            deadline = datetime.fromisoformat(binding["valid_until"])
            return deadline.tzinfo is not None and deadline.timestamp() > time.time()
        except (KeyError, TypeError, ValueError):
            return False
