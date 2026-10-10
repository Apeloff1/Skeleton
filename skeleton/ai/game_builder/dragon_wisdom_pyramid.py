"""Derived Dragon Almanac -> Wiki -> HOAG evidence ledger.

The canonical ReviewedKnowledgeStore owns source bytes, licensed use, revisions and
claims. This ledger stores only digests/identifiers, never crawled text. It has
no network, worker, training, legal clearance or automatic publication authority.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from collections.abc import Callable
from typing import Any

from .contracts import canonical_digest, canonical_json
from .reviewed_knowledge import KnowledgeBrief, ReviewedKnowledgeStore

_SCHEMA = "skeleton.dragon.wisdom_pyramid.v1"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_REASONS = frozenset({
    "changed_source", "stale_source", "contradiction", "missing_evidence",
    "rights_change", "platform_change", "quality_regression", "scheduled_refresh",
})


def _id(value: object) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError("bounded canonical identifier required")
    return value


def _hash(value: object) -> str:
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise ValueError("lowercase SHA-256 digest required")
    return value


def _time(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 4_102_444_800:
        raise ValueError("bounded UTC epoch seconds required")
    return value


def _authority(authorized: bool, trusted_worker: bool = False) -> None:
    if authorized is not True:
        raise PermissionError("authenticated knowledge owner required")
    if trusted_worker is not True:
        raise PermissionError("trusted Wiki worker required")


class DragonWisdomPyramid:
    """Append-only derived evidence journal, scoped to canonical library owners.

    The embedding process must authenticate owner, reviewer and human approval.
    Hashes detect accidental/tampered local state, not malicious DB replacement.
    The runtime must externally anchor journal heads for tamper-evident custody.
    """

    def __init__(self, library: ReviewedKnowledgeStore):
        if not isinstance(library, ReviewedKnowledgeStore):
            raise TypeError("canonical ReviewedKnowledgeStore required")
        self.library = library
        self.db = library.db
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_wisdom_pyramid (
            owner TEXT NOT NULL, sequence INTEGER NOT NULL,
            prior_digest TEXT, body TEXT NOT NULL, digest TEXT NOT NULL,
            PRIMARY KEY(owner, sequence))""")
        self.db.execute("""CREATE INDEX IF NOT EXISTS idx_dragon_wisdom_owner
            ON dragon_wisdom_pyramid(owner, sequence)""")

    def _history(self, owner: str) -> list[dict[str, Any]]:
        rows = self.db.execute("""SELECT sequence,prior_digest,body,digest
            FROM dragon_wisdom_pyramid WHERE owner=?
            ORDER BY sequence LIMIT 10001""", (owner,)).fetchall()
        if len(rows) > 10000:
            raise ValueError("journal retention limit reached")
        previous = None
        events: list[dict[str, Any]] = []
        for expected, (sequence, prior, raw, digest) in enumerate(rows):
            if not isinstance(raw, str) or len(raw.encode("utf-8")) > 8192:
                raise ValueError("journal event size or type invalid")
            try:
                event = json.loads(raw)
            except (ValueError, TypeError) as exc:
                raise ValueError("corrupt journal JSON") from exc
            if (not isinstance(event, dict)
                    or event.get("schema") != _SCHEMA
                    or event.get("owner") != owner
                    or event.get("sequence") != expected
                    or event.get("prior_digest") != previous
                    or sequence != expected or prior != previous
                    or canonical_json(event) != raw or canonical_digest(event) != digest):
                raise ValueError("journal custody chain invalid")
            previous = digest
            events.append({**event, "digest": digest})
        return events

    @staticmethod
    def _open_orders(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        pending: dict[str, dict[str, Any]] = {}
        for event in events:
            if event["kind"] == "recrawl_requested":
                pending[event["source_id"]] = event
            elif event["kind"] == "recrawl_completed":
                previous = pending.get(event["source_id"])
                if previous is None or previous["digest"] != event["request_digest"]:
                    raise ValueError("recrawl completion has no matching order")
                del pending[event["source_id"]]
        return pending

    @staticmethod
    def _review(events: list[dict[str, Any]], digest: str) -> dict[str, Any]:
        matches = [row for row in events if row["kind"] == "wiki_review" and row["digest"] == digest]
        if len(matches) != 1:
            raise ValueError("unknown Wiki review")
        return matches[0]

    def _latest_revision(self, owner: str, source_id: str) -> str:
        receipts = self.library.history(owner, source_id, authorized=True)
        if not receipts:
            raise ValueError("source is not registered with canonical Almanac")
        return receipts[-1].revision_digest

    def _append(self, owner: str, kind: str, fields: dict[str, Any],
                now: int, check: Callable[[list[dict[str, Any]]], None]) -> dict[str, Any]:
        _id(owner)
        _time(now)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            events = self._history(owner)
            if events and now < events[-1]["at"]:
                raise ValueError("journal timestamps cannot move backwards")
            check(events)
            if len(events) >= 10000:
                raise ValueError("journal event budget exhausted")
            prior = events[-1]["digest"] if events else None
            body = {"schema": _SCHEMA, "owner": owner, "sequence": len(events),
                    "prior_digest": prior, "kind": kind, "at": now, **fields}
            raw = canonical_json(body)
            if len(raw.encode("utf-8")) > 8192:
                raise ValueError("journal event budget exceeded")
            digest = canonical_digest(body)
            self.db.execute("""INSERT INTO dragon_wisdom_pyramid
                (owner,sequence,prior_digest,body,digest) VALUES(?,?,?,?,?)""",
                (owner, len(events), prior, raw, digest))
            self.db.execute("COMMIT")
            return {**body, "digest": digest}
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def recrawl(self, owner: str, source_id: str, *, reason: str,
                expected_revision: str, now: int, authorized: bool,
                trusted_worker: bool, priority: int = 2) -> dict[str, Any]:
        """Queue only a bounded intent. Existing crawler decides when/how to fetch."""
        _authority(authorized, trusted_worker)
        _id(source_id)
        _hash(expected_revision)
        if reason not in _REASONS or type(priority) is not int or priority not in (1, 2, 3):
            raise ValueError("invalid recrawl reason or priority")

        def check(events: list[dict[str, Any]]) -> None:
            if source_id in self._open_orders(events):
                raise ValueError("source already has an outstanding recrawl")
            if self._latest_revision(owner, source_id) != expected_revision:
                raise ValueError("stale source; refresh its revision before ordering")
        return self._append(owner, "recrawl_requested", {
            "source_id": source_id, "revision": expected_revision,
            "reason": reason, "priority": priority,
        }, now, check)

    def complete_recrawl(self, owner: str, source_id: str, *, request_digest: str,
                         new_revision: str, now: int, authorized: bool,
                         trusted_worker: bool) -> dict[str, Any]:
        """Only an actual new canonical revision resolves an outstanding order."""
        _authority(authorized, trusted_worker)
        _id(source_id)
        _hash(request_digest)
        _hash(new_revision)

        def check(events: list[dict[str, Any]]) -> None:
            order = self._open_orders(events).get(source_id)
            if order is None or order["digest"] != request_digest:
                raise ValueError("wrong or already completed recrawl")
            if order["revision"] == new_revision or self._latest_revision(owner, source_id) != new_revision:
                raise ValueError("recrawl needs an independently admitted new source revision")
            receipts = self.library.history(owner, source_id, authorized=True)
            if not any(r.revision_digest == order["revision"] for r in receipts[:-1]):
                raise ValueError("recrawl baseline is not an ancestor")
        return self._append(owner, "recrawl_completed", {
            "source_id": source_id, "request_digest": request_digest,
            "new_revision": new_revision,
        }, now, check)

    def wiki_review(self, owner: str, brief: KnowledgeBrief, *, mechanic: str,
                    disposition: str, independent_reviewer_id: str,
                    review_evidence_digest: str, now: int, expires_at: int,
                    authorized: bool, trusted_worker: bool) -> dict[str, Any]:
        """Verify canonical citations before recording an independent verdict.

        Reviewer's identity/independence must be checked at trusted invocation.
        This function cannot authenticate a caller-supplied reviewer name.
        """
        _authority(authorized, trusted_worker)
        _id(mechanic)
        _id(independent_reviewer_id)
        _hash(review_evidence_digest)
        _time(now)
        _time(expires_at)
        if disposition not in ("accepted", "challenged", "insufficient") or not now < expires_at <= now + 30 * 86400:
            raise ValueError("invalid disposition or review lifetime")
        if not isinstance(brief, KnowledgeBrief) or brief.owner != owner or brief.scope != "design_reference":
            raise ValueError("owner-bound design-reference brief required")
        citations = tuple(hit for hit in brief.citations if hit.mechanic == mechanic)
        if not citations:
            raise ValueError("no citations for reviewed mechanic")
        if any(int(datetime.fromisoformat(h.observed_at.replace("Z", "+00:00")).timestamp()) > now
               for h in citations):
            raise ValueError("future-dated source cannot support Wiki review")
        refs = sorted({(h.source_id, h.revision_digest, h.note_id, h.dependence_group)
                       for h in citations})
        groups = {h.dependence_group for h in citations if h.stance == "supports"}
        source_ids = {h.source_id for h in citations if h.stance == "supports"}
        if disposition == "accepted":
            # A brief is a bounded, relevance-ranked view. It may omit a lower-
            # ranked contradiction. Recheck EVERY current, in-scope claim for
            # this mechanic before admitting even a selected clean subset.
            # The canonical _rows method validates the complete custody chain.
            all_stances = []
            for source in self.library._rows(owner):
                if source["status"] != "active" or "design_reference" not in source["allowed_scopes"]:
                    continue
                for entry in source["notes"]:
                    if entry["note"]["mechanic"] == mechanic:
                        all_stances.append(entry["note"]["stance"])
            if (len(groups) < 2 or len(source_ids) < 2
                    or any(h.stance != "supports" for h in citations)
                    or mechanic in brief.conflicts
                    or any(stance != "supports" for stance in all_stances)):
                raise ValueError("acceptance needs two independent supporting sources without challenge")

        def check(events: list[dict[str, Any]]) -> None:
            self.library.require_fresh_brief(brief, authorized=True)
            if any(h.source_id in self._open_orders(events) for h in citations):
                raise ValueError("cannot review a source awaiting recrawl")
        return self._append(owner, "wiki_review", {
            "mechanic": mechanic, "disposition": disposition,
            "reviewer": independent_reviewer_id,
            "review_evidence": review_evidence_digest,
            "knowledge_root": brief.knowledge_root,
            "brief_digest": brief.to_payload()["brief_digest"],
            "source_refs": [list(ref) for ref in refs],
            "independent_groups": len(groups), "expires_at": expires_at,
        }, now, check)

    def promote(self, owner: str, review_digest: str, *, now: int,
                authorized: bool, trusted_worker: bool,
                human_approved: bool) -> dict[str, Any]:
        """HOAG/memory eligibility only, never model training or release authority."""
        _authority(authorized, trusted_worker)
        _hash(review_digest)
        if human_approved is not True:
            raise PermissionError("explicit human memory approval required")

        def check(events: list[dict[str, Any]]) -> None:
            review = self._review(events, review_digest)
            if review["disposition"] != "accepted" or not review["at"] <= now < review["expires_at"]:
                raise ValueError("Wiki review unapproved or expired")
            if self.library.snapshot_root(owner, authorized=True) != review["knowledge_root"]:
                raise ValueError("Almanac revisions changed since Wiki review")
            if any(ref[0] in self._open_orders(events) for ref in review["source_refs"]):
                raise ValueError("recrawl must be resolved before memory promotion")
            if any(e["kind"] == "revoked" and e["review_digest"] == review_digest for e in events):
                raise ValueError("review was revoked")
            if any(e["kind"] == "promoted" and e["review_digest"] == review_digest for e in events):
                raise ValueError("review was already promoted")
            if any(e["kind"] == "wiki_review" and e["mechanic"] == review["mechanic"]
                   and e["sequence"] > review["sequence"] and e["disposition"] != "accepted"
                   for e in events):
                raise ValueError("later adversarial challenge requires a fresh review")
        return self._append(owner, "promoted", {
            "review_digest": review_digest, "memory_scope": "advisory_design",
            "training_authorized": False, "release_authorized": False,
        }, now, check)

    def revoke(self, owner: str, review_digest: str, *, reason: str,
               now: int, authorized: bool, trusted_worker: bool) -> dict[str, Any]:
        _authority(authorized, trusted_worker)
        _hash(review_digest)
        if reason not in _REASONS:
            raise ValueError("bounded revocation reason required")

        def check(events: list[dict[str, Any]]) -> None:
            self._review(events, review_digest)
            if any(e["kind"] == "revoked" and e["review_digest"] == review_digest for e in events):
                raise ValueError("review already revoked")
        return self._append(owner, "revoked", {
            "review_digest": review_digest, "reason": reason,
        }, now, check)

    def enqueue_canonical_refreshes(
        self, owner: str, *, now: int, authorized: bool,
        trusted_worker: bool, max_age_seconds: int = 604800,
        min_independent_groups: int = 2, min_confidence_ppm: int = 800000,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Atomically bridge the authoritative gap planner to this journal.

        No crawler executes and no request gains global resource authority.
        A single canonical source snapshot determines the full capped batch;
        repeated scheduling ignores outstanding orders instead of minting
        duplicate requests. Historical planners/policies remain separate.
        """
        _authority(authorized, trusted_worker)
        _id(owner)
        _time(now)
        if type(limit) is not int or not 1 <= limit <= 32:
            raise ValueError("bounded recrawl enqueue limit required")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            events = self._history(owner)
            if events and now < events[-1]["at"]:
                raise ValueError("refresh clock predates the source journal")
            utc = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            plan = self.library.plan_recrawl(
                owner, as_of=utc, scope="design_reference", authorized=True,
                max_age_seconds=max_age_seconds,
                min_independent_groups=min_independent_groups,
                min_confidence_ppm=min_confidence_ppm, limit=limit,
            )
            if plan["knowledge_root"] != self.library.snapshot_root(owner, authorized=True):
                raise ValueError("canonical knowledge changed during planning")
            outstanding = self._open_orders(events)
            scheduled: list[dict[str, Any]] = []
            skipped: list[str] = []
            reason_map = {
                "future_observation": "stale_source",
                "contradictory_evidence": "contradiction",
                "stale_observation": "stale_source",
                "uncertain_evidence": "missing_evidence",
                "low_confidence": "missing_evidence",
                "insufficient_independent_support": "missing_evidence",
            }
            for request in plan["requests"]:
                source_id = _id(request["source_id"])
                revision = _hash(request["expected_parent_digest"])
                if source_id in outstanding:
                    skipped.append(source_id)
                    continue
                if revision != self._latest_revision(owner, source_id):
                    raise ValueError("canonical parent changed before enqueue")
                reasons = request["reasons"]
                if not isinstance(reasons, list) or not reasons or any(
                    reason not in reason_map for reason in reasons
                ):
                    raise ValueError("unrecognized canonical recrawl reason")
                # Preserve all original reasons for audit, but emit a
                # deterministic primary handling category for queue clients.
                primary = next(reason_map[r] for r in (
                    "future_observation", "contradictory_evidence",
                    "stale_observation", "uncertain_evidence",
                    "low_confidence", "insufficient_independent_support",
                ) if r in reasons)
                if len(events) + len(scheduled) >= 10000:
                    raise ValueError("refresh journal capacity exhausted")
                sequence = len(events) + len(scheduled)
                previous = (scheduled[-1]["digest"] if scheduled
                            else events[-1]["digest"] if events else None)
                body = {
                    "schema": _SCHEMA, "owner": owner, "sequence": sequence,
                    "prior_digest": previous, "kind": "recrawl_requested",
                    "at": now, "source_id": source_id, "revision": revision,
                    "reason": primary, "priority": max(1, request["priority"]),
                    "plan_digest": _hash(plan["plan_digest"]),
                    "request_digest": _hash(request["request_digest"]),
                    "plan_reasons": reasons,
                }
                raw = canonical_json(body)
                if len(raw.encode("utf-8")) > 8192:
                    raise ValueError("refresh event exceeds journal budget")
                digest = canonical_digest(body)
                self.db.execute("""INSERT INTO dragon_wisdom_pyramid
                    (owner,sequence,prior_digest,body,digest) VALUES(?,?,?,?,?)""",
                    (owner, sequence, previous, raw, digest))
                scheduled.append({**body, "digest": digest})
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return {
            "schema": "skeleton.dragon.recrawl_bridge.v1",
            "owner": owner, "knowledge_root": plan["knowledge_root"],
            "plan_digest": plan["plan_digest"],
            "planned": len(plan["requests"]),
            "queued": tuple({
                "source_id": row["source_id"], "order_digest": row["digest"],
                "source_revision": row["revision"], "priority": row["priority"],
                "reason": row["reason"], "request_digest": row["request_digest"],
            } for row in scheduled),
            "already_pending": tuple(skipped),
            "deferred": plan["deferred_requests"],
            "execution_authorized": False, "memory_promotion_authorized": False,
        }

    def recrawl_queue(self, owner: str, *, now: int, authorized: bool,
                      limit: int = 32) -> tuple[dict[str, Any], ...]:
        if authorized is not True:
            raise PermissionError("owner-scoped recrawl access required")
        _id(owner)
        _time(now)
        if type(limit) is not int or not 1 <= limit <= 128:
            raise ValueError("invalid queue limit")
        pending = self._open_orders(self._history(owner))
        return tuple({"source_id": e["source_id"], "reason": e["reason"],
                      "priority": e["priority"], "revision": e["revision"],
                      "order_digest": e["digest"], "ordered_at": e["at"],
                      "execution_authorized": False}
                     for e in sorted(pending.values(),
                                     key=lambda x: (x["priority"], x["sequence"]))[:limit])

    def hoag_view(self, owner: str, *, now: int, authorized: bool,
                  limit: int = 32) -> dict[str, Any]:
        """Never exposes source text, unreviewed claims or revoked memories."""
        if authorized is not True:
            raise PermissionError("authenticated owner required")
        _id(owner)
        _time(now)
        if type(limit) is not int or not 1 <= limit <= 64:
            raise ValueError("invalid view limit")
        events = self._history(owner)
        pending = self._open_orders(events)
        root = self.library.snapshot_root(owner, authorized=True)
        revoked = {e["review_digest"] for e in events if e["kind"] == "revoked"}
        promoted = [e for e in events if e["kind"] == "promoted"]
        cards: list[dict[str, Any]] = []
        for event in reversed(promoted):
            review = self._review(events, event["review_digest"])
            if (review["digest"] in revoked or review["knowledge_root"] != root
                    or not event["at"] <= now or not review["at"] <= now < review["expires_at"]
                    or any(ref[0] in pending for ref in review["source_refs"])
                    or any(e["kind"] == "wiki_review" and e["mechanic"] == review["mechanic"]
                           and e["sequence"] > review["sequence"] and e["disposition"] != "accepted"
                           for e in events)):
                continue
            cards.append({
                "mechanic": review["mechanic"],
                "grade": "independently_reviewed_not_universal_truth",
                "independent_groups": review["independent_groups"],
                "review_digest": review["digest"],
                "review_evidence_digest": review["review_evidence"],
                "source_revisions": sorted({ref[1] for ref in review["source_refs"]}),
                "expires_at": review["expires_at"],
                "training_authorized": False, "release_authorized": False,
            })
            if len(cards) >= limit:
                break
        return {
            "schema": "skeleton.dragon.hoag_wisdom_view.v1",
            "owner": owner, "knowledge_root": root, "items": cards,
            "pending_recrawls": len(pending),
            "head_digest": events[-1]["digest"] if events else None,
            "permanent_memory_eligible": len(cards),
            "authority": "advisory_only",
        }
