"""Durable, revocable advisory memory projection from the Dragon Wiki.

Only an accepted Wiki review with a separate signed human approval may enter
this index. It stores no scraped source text, no trained model parameters and
no original game assets. Every read revalidates against authoritative evidence.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from .contracts import canonical_digest, canonical_json
from .dragon_wisdom_pyramid import DragonWisdomPyramid, _id, _time


class DragonWisdomMemory:
    def __init__(self, pyramid: DragonWisdomPyramid):
        if not isinstance(pyramid, DragonWisdomPyramid):
            raise TypeError("canonical Wiki evidence required")
        self.pyramid = pyramid
        self.db = pyramid.db
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_advisory_memory (
            owner TEXT NOT NULL, review_digest TEXT NOT NULL,
            mechanic TEXT NOT NULL, source_root TEXT NOT NULL,
            approval_digest TEXT NOT NULL, expires_at INTEGER NOT NULL,
            body TEXT NOT NULL, digest TEXT NOT NULL,
            PRIMARY KEY(owner, review_digest))""")
        self.db.execute("""CREATE INDEX IF NOT EXISTS idx_dragon_advisory_mechanic
            ON dragon_advisory_memory(owner,mechanic)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_advisory_memory_events (
            owner TEXT NOT NULL, sequence INTEGER NOT NULL,
            prior_digest TEXT, action TEXT NOT NULL, subject_digest TEXT NOT NULL,
            source_root TEXT NOT NULL, at INTEGER NOT NULL,
            digest TEXT NOT NULL, PRIMARY KEY(owner,sequence))""")

    def _events(self, owner: str) -> list[dict[str, Any]]:
        rows = self.db.execute("""SELECT sequence,prior_digest,action,
            subject_digest,source_root,at,digest FROM dragon_advisory_memory_events
            WHERE owner=? ORDER BY sequence LIMIT 20001""", (owner,)).fetchall()
        if len(rows) > 20000:
            raise ValueError("memory lineage capacity exhausted")
        previous = None
        events = []
        for position, (sequence, prior, action, subject, root, at, digest) in enumerate(rows):
            body = {"owner": owner, "sequence": sequence, "prior_digest": prior,
                    "action": action, "subject_digest": subject,
                    "source_root": root, "at": at}
            if sequence != position or prior != previous or action not in ("admit", "withdraw") or canonical_digest(body) != digest:
                raise ValueError("advisory memory event lineage corrupt")
            previous = digest
            events.append({**body, "digest": digest})
        return events

    def _rows(self, owner: str) -> dict[str, dict[str, Any]]:
        rows = self.db.execute("""SELECT review_digest,mechanic,source_root,
            approval_digest,expires_at,body,digest FROM dragon_advisory_memory
            WHERE owner=? LIMIT 20001""", (owner,)).fetchall()
        if len(rows) > 20000:
            raise ValueError("memory index capacity exhausted")
        result = {}
        for digest, mechanic, root, approval, expires, raw, value in rows:
            try:
                body = json.loads(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError("memory index record corrupt") from exc
            if (not isinstance(body, dict) or canonical_json(body) != raw
                    or canonical_digest(body) != value
                    or body.get("owner") != owner
                    or body.get("review_digest") != digest
                    or body.get("mechanic") != mechanic
                    or body.get("knowledge_root") != root
                    or body.get("approval_evidence_digest") != approval
                    or body.get("expires_at") != expires):
                raise ValueError("advisory memory index integrity invalid")
            result[digest] = body
        return result

    def reconcile(self, owner: str, *, now: int, authorized: bool,
                  trusted_worker: bool) -> dict[str, Any]:
        if authorized is not True or trusted_worker is not True:
            raise PermissionError("trusted owner-bound memory reconciler required")
        _id(owner); _time(now)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            events = self._events(owner)
            if events and now < events[-1]["at"]:
                raise ValueError("memory replay clock rollback")
            prior = self._rows(owner)
            # HOAG is always derived again from current source revisions,
            # recrawl status, challenge history, revocations and time.
            view = self.pyramid.hoag_view(owner, now=now, authorized=True, limit=64)
            journal = self.pyramid._history(owner)
            promoted = {e["review_digest"]: e for e in journal if e["kind"] == "promoted"}
            eligible = {}
            for card in view["items"]:
                approval = promoted[card["review_digest"]].get("approval_evidence_digest")
                if not isinstance(approval, str) or len(approval) != 64 or any(
                        c not in "0123456789abcdef" for c in approval):
                    continue  # Legacy unsigned approval is NEVER made durable.
                body = {
                    "schema": "skeleton.dragon.advisory_memory.v1",
                    "owner": owner, "review_digest": card["review_digest"],
                    "mechanic": card["mechanic"], "knowledge_root": view["knowledge_root"],
                    "review_evidence_digest": card["review_evidence_digest"],
                    "approval_evidence_digest": approval,
                    "source_revisions": card["source_revisions"],
                    "expires_at": card["expires_at"],
                    "training_authorized": False, "release_authorized": False,
                    "memorized_source_text": False,
                }
                eligible[card["review_digest"]] = body
            if len(eligible) > 64:
                raise ValueError("memory projection capacity exceeded")
            operations = []
            for review_digest, old in sorted(prior.items()):
                if eligible.get(review_digest) != old:
                    operations.append(("withdraw", review_digest))
            for review_digest, body in sorted(eligible.items()):
                if prior.get(review_digest) != body:
                    operations.append(("admit", review_digest))
            if len(events) + len(operations) > 20000:
                raise ValueError("memory lineage limit exceeded")
            for action, digest in operations:
                prior_hash = events[-1]["digest"] if events else None
                body = {"owner": owner, "sequence": len(events),
                        "prior_digest": prior_hash, "action": action,
                        "subject_digest": digest, "source_root": view["knowledge_root"],
                        "at": now}
                chain_digest = canonical_digest(body)
                self.db.execute("""INSERT INTO dragon_advisory_memory_events
                    (owner,sequence,prior_digest,action,subject_digest,source_root,at,digest)
                    VALUES(?,?,?,?,?,?,?,?)""",
                    (owner, len(events), prior_hash, action, digest, view["knowledge_root"],
                     now, chain_digest))
                events.append({**body, "digest": chain_digest})
                if action == "withdraw":
                    self.db.execute("""DELETE FROM dragon_advisory_memory
                        WHERE owner=? AND review_digest=?""", (owner, digest))
                else:
                    item = eligible[digest]
                    raw = canonical_json(item)
                    self.db.execute("""INSERT INTO dragon_advisory_memory
                        (owner,review_digest,mechanic,source_root,approval_digest,
                         expires_at,body,digest) VALUES(?,?,?,?,?,?,?,?)
                        ON CONFLICT(owner,review_digest) DO UPDATE SET
                         mechanic=excluded.mechanic,source_root=excluded.source_root,
                         approval_digest=excluded.approval_digest,
                         expires_at=excluded.expires_at,body=excluded.body,digest=excluded.digest""",
                        (owner, digest, item["mechanic"], item["knowledge_root"],
                         item["approval_evidence_digest"], item["expires_at"],
                         raw, canonical_digest(item)))
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return {
            "schema": "skeleton.dragon.advisory_memory_sync.v1", "owner": owner,
            "current_root": view["knowledge_root"],
            "eligible": len(eligible), "changes": len(operations),
            "journal_head": events[-1]["digest"] if events else None,
            "training_authorized": False, "release_authorized": False,
        }

    def read_current(self, owner: str, *, now: int, authorized: bool,
                     mechanic: str | None = None, limit: int = 32) -> dict:
        """Read-only, fail-closed index projection suitable for product routes.

        Never mutates on GET. The trusted background reconciler separately
        applies withdrawals; stale persisted cards are excluded immediately
        even if that worker has not run.
        """
        if authorized is not True:
            raise PermissionError("authenticated advisory memory read required")
        _id(owner); _time(now)
        if mechanic is not None:
            _id(mechanic)
        if type(limit) is not int or not 1 <= limit <= 64:
            raise ValueError("bounded advisory retrieval required")
        events = self._events(owner)
        persisted = self._rows(owner)
        source = self.pyramid.hoag_view(owner, now=now, authorized=True, limit=64)
        promoted = {row["review_digest"]: row
                    for row in self.pyramid._history(owner)
                    if row["kind"] == "promoted"}
        valid = {}
        for card in source["items"]:
            rec = persisted.get(card["review_digest"])
            approval = promoted[card["review_digest"]].get("approval_evidence_digest")
            if (rec is None or not isinstance(approval, str)
                    or rec["approval_evidence_digest"] != approval
                    or rec["knowledge_root"] != source["knowledge_root"]
                    or rec["review_evidence_digest"] != card["review_evidence_digest"]
                    or rec["source_revisions"] != card["source_revisions"]
                    or rec["expires_at"] != card["expires_at"]
                    or (mechanic is not None and rec["mechanic"] != mechanic)):
                continue
            valid[card["review_digest"]] = rec
        rows = sorted(valid.values(), key=lambda x: (x["mechanic"], x["review_digest"]))
        return {
            "schema": "skeleton.dragon.advisory_memory_view.v1",
            "owner": owner, "items": rows[:limit],
            "knowledge_root": source["knowledge_root"],
            "journal_head": events[-1]["digest"] if events else None,
            "reconciliation_required": set(valid) != set(persisted),
            "training_authorized": False, "release_authorized": False,
        }

    def retrieve(self, owner: str, mechanic: str, *, now: int,
                 authorized: bool, trusted_worker: bool, limit: int = 16) -> tuple[dict, ...]:
        _id(owner); _id(mechanic); _time(now)
        if type(limit) is not int or not 1 <= limit <= 64:
            raise ValueError("bounded retrieval results required")
        self.reconcile(owner, now=now, authorized=authorized,
                       trusted_worker=trusted_worker)
        matches = [item for item in self._rows(owner).values()
                   if item["mechanic"] == mechanic and item["expires_at"] > now]
        return tuple(sorted(matches, key=lambda x: x["review_digest"])[:limit])
