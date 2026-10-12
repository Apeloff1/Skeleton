"""Dragon -> Almanakk -> Wiki -> shadow-evaluation -> weight handoff.

This is a review ledger over the existing DragonFamily readings. It does not
crawl, consume more energy, grant XP, create model weights, or impersonate Wiki
or a human reviewer. The trusted host supplies *independent* evaluators that
can verify the supplied opaque Wiki/holdout/signoff receipts. A digest by itself
is never authority. Every action is transactionally fenced and owner-scoped.

HOAG/Jeeves may read the queue for user-visible project evidence. It may not
treat an entry as a weight update; promotion emits a handoff receipt only.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from typing import Callable
import json
import sqlite3

from .dragon_family import DragonFamily, SourceReceipt, _digest, _epoch, _hash, _owner, _source_id, _utc

SCHEMA = "skeleton.ai.dragon.almanakk.v1"
_STAGES = ("collected", "wiki_verified", "shadow_validated", "weight_handoff")
_ROLES = ("parent", "article", "video", "monitor")


@dataclass(frozen=True)
class WikiEvidence:
    """Wiki verification attested independently of the original producer."""
    fingerprint: str
    verified_at: float
    independence_groups: int
    meets_source_rights: bool
    explanation: str


@dataclass(frozen=True)
class SandboxEvidence:
    """Verified holdout evaluation; a claim of improvement is not proof."""
    fingerprint: str
    evaluated_at: float
    baseline_score: float
    candidate_score: float
    independent_cases: int
    critical_regressions: int
    regression_note: str


class DragonAlmanakkLane:
    def __init__(self, db: sqlite3.Connection, *,
                 source_approval: Callable[[SourceReceipt], bool] | None = None,
                 wiki_verify: Callable[[str, str, WikiEvidence], bool] | None = None,
                 sandbox_verify: Callable[[str, str, SandboxEvidence], bool] | None = None,
                 handoff_verify: Callable[[str, str, str], bool] | None = None,
                 minimum_gain: float = 0.02, owner_scope: str | None = None):
        if not isinstance(minimum_gain, (int, float)) or isinstance(minimum_gain, bool) or not isfinite(minimum_gain) or not 0 < minimum_gain <= 1:
            raise ValueError("invalid gain policy")
        if owner_scope is not None:
            _owner(owner_scope)
        self.owner_scope = owner_scope
        self.db = db
        self.source_approval = source_approval
        self.wiki_verify = wiki_verify
        self.sandbox_verify = sandbox_verify
        self.handoff_verify = handoff_verify
        self.minimum_gain = minimum_gain
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_almanakk_reviews (
            owner TEXT NOT NULL, dragon TEXT NOT NULL, source_id TEXT NOT NULL,
            content_digest TEXT NOT NULL, stage TEXT NOT NULL,
            wiki_fingerprint TEXT NOT NULL DEFAULT '',
            sandbox_fingerprint TEXT NOT NULL DEFAULT '',
            handoff_fingerprint TEXT NOT NULL DEFAULT '',
            quality_delta REAL NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL, details TEXT NOT NULL,
            PRIMARY KEY(owner,dragon,source_id,content_digest))""")
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_almanakk_review_events (
            owner TEXT NOT NULL, sequence INTEGER NOT NULL, dragon TEXT NOT NULL,
            source_id TEXT NOT NULL, content_digest TEXT NOT NULL,
            at REAL NOT NULL, stage TEXT NOT NULL, details TEXT NOT NULL,
            previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL,
            PRIMARY KEY(owner,sequence))""")
        db.commit()

    def _assert_owner(self, owner: str) -> None:
        _owner(owner)
        if self.owner_scope is not None and owner != self.owner_scope:
            raise PermissionError("Almanakk producer is bound to another owner")

    @staticmethod
    def _identity(owner: str, role: str, source_id: str, digest: str) -> None:
        _owner(owner)
        if role not in _ROLES:
            raise ValueError("invalid dragon role")
        _source_id(source_id)
        _digest(digest)

    def _latest(self, owner: str, source_id: str) -> tuple | None:
        return self.db.execute("""SELECT dragon,content_digest,review_digest,observed_at,improvement
            FROM dragon_family_readings WHERE owner=? AND source_id=?
            ORDER BY observed_at DESC,rowid DESC LIMIT 1""", (owner, source_id)).fetchone()

    def _admit(self, owner: str, role: str, source_id: str, digest: str) -> tuple:
        self._assert_owner(owner)
        self._identity(owner, role, source_id, digest)
        if self.source_approval is None:
            raise PermissionError("canonical source review unavailable")
        reading = self._latest(owner, source_id)
        if reading is None or reading[0] != role or reading[1] != digest:
            raise ValueError("knowledge revision is missing or superseded")
        receipt = SourceReceipt(source_id, digest, reading[2], reading[3])
        if self.source_approval(receipt) is not True:
            raise PermissionError("source review revoked or superseded")
        return reading

    def _row(self, owner: str, role: str, source_id: str, digest: str):
        return self.db.execute("""SELECT stage,wiki_fingerprint,sandbox_fingerprint,
            handoff_fingerprint,quality_delta,updated_at FROM dragon_almanakk_reviews
            WHERE owner=? AND dragon=? AND source_id=? AND content_digest=?""",
            (owner, role, source_id, digest)).fetchone()

    def _event(self, owner: str, role: str, source_id: str, digest: str,
               at: float, stage: str, details: str) -> str:
        previous = self.db.execute("""SELECT sequence,event_hash,at
            FROM dragon_almanakk_review_events WHERE owner=?
            ORDER BY sequence DESC LIMIT 1""", (owner,)).fetchone()
        if previous and at < previous[2]:
            raise ValueError("review event clock must be monotonic")
        seq, prior = (previous[0] + 1, previous[1]) if previous else (1, "0"*64)
        if seq > 100000:
            raise ValueError("review journal capacity exhausted")
        digest_hash = _hash([owner,seq,role,source_id,digest,at,stage,details,prior])
        self.db.execute("""INSERT INTO dragon_almanakk_review_events
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (owner,seq,role,source_id,digest,at,stage,details,prior,digest_hash))
        return digest_hash

    def _transition(self, owner: str, role: str, source_id: str, digest: str,
                    *, authorized: bool, stage: str, fingerprint: str,
                    at: float, description: str, gain: float = 0.0) -> bool:
        if not authorized:
            raise PermissionError("independent reviewer authorization required")
        _epoch(at)
        _digest(fingerprint)
        if stage not in _STAGES[1:]:
            raise ValueError("invalid knowledge transition")
        # No caller can write/alter the canonical acquisition/readings table.
        self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            read = self._admit(owner, role, source_id, digest)
            if at < read[3]:
                raise ValueError("review cannot precede source observation")
            row = self._row(owner, role, source_id, digest)
            old = row[0] if row else "collected"
            if _STAGES.index(old) >= _STAGES.index(stage):
                return False
            if _STAGES.index(stage) != _STAGES.index(old) + 1:
                raise PermissionError("knowledge stages cannot be skipped")
            old_wiki, old_shadow, old_handoff = (row[1],row[2],row[3]) if row else ("","","")
            wiki = fingerprint if stage == "wiki_verified" else old_wiki
            shadow = fingerprint if stage == "shadow_validated" else old_shadow
            handoff = fingerprint if stage == "weight_handoff" else old_handoff
            if not isinstance(description,str) or not 3 <= len(description) <= 200 or any(ord(c)<32 for c in description):
                raise ValueError("invalid reviewer explanation")
            note = f"(improved: {description})" if stage == "shadow_validated" else f"(reviewed: {description})"
            self.db.execute("""INSERT INTO dragon_almanakk_reviews
                (owner,dragon,source_id,content_digest,stage,wiki_fingerprint,
                 sandbox_fingerprint,handoff_fingerprint,quality_delta,updated_at,details)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(owner,dragon,source_id,content_digest) DO UPDATE SET
                stage=excluded.stage,wiki_fingerprint=excluded.wiki_fingerprint,
                sandbox_fingerprint=excluded.sandbox_fingerprint,
                handoff_fingerprint=excluded.handoff_fingerprint,
                quality_delta=excluded.quality_delta,updated_at=excluded.updated_at,
                details=excluded.details""",
                (owner,role,source_id,digest,stage,wiki,shadow,handoff,gain if stage=="shadow_validated" else (row[4] if row else 0),at,note))
            self._event(owner,role,source_id,digest,at,stage,note)
        return True

    def wiki_review(self, owner: str, role: str, source_id: str,
                    digest: str, decision: WikiEvidence, *, authorized: bool) -> bool:
        self._assert_owner(owner)
        self._identity(owner,role,source_id,digest)
        if not isinstance(decision,WikiEvidence):
            raise ValueError("independent Wiki receipt required")
        _digest(decision.fingerprint)
        _epoch(decision.verified_at)
        if (type(decision.independence_groups) is not int or decision.independence_groups < 2
                or decision.independence_groups > 10000 or decision.meets_source_rights is not True):
            raise PermissionError("Wiki evidence fails independence or source-rights gate")
        if self.wiki_verify is None or self.wiki_verify(owner, digest, decision) is not True:
            raise PermissionError("Wiki reviewer did not verify evidence")
        return self._transition(owner,role,source_id,digest,authorized=authorized,
                                stage="wiki_verified",fingerprint=decision.fingerprint,
                                at=decision.verified_at,description=decision.explanation)

    def sandbox_review(self, owner: str, role: str, source_id: str,
                       digest: str, evaluation: SandboxEvidence, *, authorized: bool) -> bool:
        self._assert_owner(owner)
        self._identity(owner,role,source_id,digest)
        if not isinstance(evaluation,SandboxEvidence):
            raise ValueError("sandbox evaluation receipt required")
        _digest(evaluation.fingerprint)
        _epoch(evaluation.evaluated_at)
        numeric = (evaluation.baseline_score,evaluation.candidate_score)
        if any(isinstance(n,bool) or not isinstance(n,(int,float)) or not isfinite(n) or not 0<=n<=1 for n in numeric):
            raise ValueError("invalid evaluation scores")
        if (type(evaluation.independent_cases) is not int or evaluation.independent_cases < 30
                or type(evaluation.critical_regressions) is not int or evaluation.critical_regressions != 0):
            raise PermissionError("insufficient holdout evidence or critical regression")
        improvement = float(evaluation.candidate_score-evaluation.baseline_score)
        if improvement < self.minimum_gain:
            raise PermissionError("measured improvement below acceptance floor")
        if self.sandbox_verify is None or self.sandbox_verify(owner,digest,evaluation) is not True:
            raise PermissionError("independent sandbox receipt not verified")
        reason = evaluation.regression_note.strip() or f"measured holdout gain +{improvement:.3f}"
        return self._transition(owner,role,source_id,digest,authorized=authorized,
                                stage="shadow_validated",fingerprint=evaluation.fingerprint,
                                at=evaluation.evaluated_at,description=reason,gain=improvement)

    def authorize_weight_handoff(self, owner: str, role: str, source_id: str,
                                 digest: str, *, authorized: bool, signed_receipt: str,
                                 approved_at: float) -> str:
        """Produces an integration request, NEVER mutates model parameters."""
        self._assert_owner(owner)
        self._identity(owner,role,source_id,digest)
        _digest(signed_receipt)
        _epoch(approved_at)
        if self.handoff_verify is None or self.handoff_verify(owner,digest,signed_receipt) is not True:
            raise PermissionError("weight handoff needs separate signed authorization")
        self._transition(owner,role,source_id,digest,authorized=authorized,
                         stage="weight_handoff",fingerprint=signed_receipt,
                         at=approved_at,
                         description="separately authorized weight handoff; no weights changed")
        persisted = self._row(owner,role,source_id,digest)
        if persisted is None or persisted[0] != "weight_handoff" or persisted[3] != signed_receipt:
            raise ValueError("handoff replay must match persisted signed receipt")
        return _hash([SCHEMA,owner,role,source_id,digest,signed_receipt])

    def history(self, owner: str, *, authorized: bool, limit: int = 25) -> list[dict]:
        self._assert_owner(owner)
        if not authorized:
            raise PermissionError("authenticated review history required")
        if type(limit) is not int or not 1<=limit<=100:
            raise ValueError("invalid history limit")
        rows = self.db.execute("""SELECT sequence,dragon,source_id,content_digest,
            at,stage,details,previous_hash,event_hash
            FROM dragon_almanakk_review_events WHERE owner=? ORDER BY sequence""",
            (owner,)).fetchall()
        prior = "0"*64
        records = []
        for expected,row in enumerate(rows,1):
            seq,role,sid,revision,at,stage,details,p,digest = row
            if (seq!=expected or p!=prior or digest!=_hash(
                  [owner,seq,role,sid,revision,at,stage,details,p])):
                raise ValueError("Almanakk chain integrity failure")
            prior = digest
            records.append(dict(sequence=seq,dragon=role,source_id=sid,
                                stage=stage,at=_utc(at),change=details,
                                event_hash=digest))
        return records[-limit:][::-1]

    def projection(self, owner: str, *, authorized: bool, limit: int = 15) -> dict:
        """Latest source revisions, including reviewed and still-pending work.

        Parent and children contribute evidence to the same knowledge pyramid.
        Superseded revisions are visible in history, but never count as ready.
        """
        history = self.history(owner,authorized=authorized,limit=limit)
        # Also verify Dragon custody journal; do not mask lineage tampering.
        DragonFamily(self.db).history(owner,authorized=True,limit=1)
        rows = self.db.execute("""SELECT r.source_id,r.dragon,r.content_digest,r.observed_at,
            s.topics_json FROM dragon_family_readings r
            JOIN dragon_family_sources s ON s.owner=r.owner AND s.source_id=r.source_id
            WHERE r.owner=? AND r.rowid IN (
                SELECT r2.rowid FROM dragon_family_readings r2
                WHERE r2.owner=? AND r2.source_id=r.source_id
                ORDER BY r2.observed_at DESC,r2.rowid DESC LIMIT 1
            ) ORDER BY r.observed_at DESC,r.source_id""", (owner,owner)).fetchall()
        entries=[]
        stages={x:0 for x in _STAGES}
        for sid,role,revision,at,topics in rows[:1000]:
            reviewed=self._row(owner,role,sid,revision)
            stage=reviewed[0] if reviewed else "collected"
            stages[stage]+=1
            if len(entries)<limit:
                entries.append(dict(source_id=sid,dragon=role,stage=stage,
                                    last_acquired_at=_utc(at),
                                    topics=tuple(json.loads(topics)),
                                    measured_gain=round(reviewed[4],4) if reviewed else None))
        return dict(schema=SCHEMA,
                    architecture="Dragon → Almanakk → Wiki → HOAG/Jeeves → Game Builder",
                    counts=stages,
                    items=entries,history=history,
                    policy="evidence only; weight handoff never mutates model parameters")
