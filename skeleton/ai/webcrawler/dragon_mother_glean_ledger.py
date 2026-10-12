"""Durable, tamper-evident ledger for mother Dragon's multi-lens findings.

The ledger records research hypotheses, never learner/model parameters. Only the
trusted run() method can append after rechecking the canonical nest, evidence,
idle authorization, and reviewed-knowledge root. Identical findings are
idempotent across repeated idle polls.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import hmac
import json
import sqlite3

from skeleton.ai.game_builder.contracts import canonical_digest, canonical_json
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore
from .dragon_mother_glean_matrix import (
    HatchlingReceipt, LensProbe, MeaningHypothesis, MotherGleanReport,
    SynergyHypothesis, glean_mother_insights, verify_mother_report,
)
from .dragon_nest_progression import DragonNest, _id, _instant

MAX_EVENTS = 2048
MAX_BYTES = 750_000


def _decode(payload: str) -> MotherGleanReport:
    if not isinstance(payload, str) or len(payload.encode("utf-8")) > MAX_BYTES:
        raise ValueError("mother glean ledger payload exceeds safe bounds")
    try:
        record = json.loads(payload)
        if not isinstance(record, dict) or canonical_json(record) != payload:
            raise ValueError("noncanonical mother report")
        record["acquisitions"] = tuple(HatchlingReceipt(**r) for r in record["acquisitions"])
        record["probes"] = tuple(LensProbe(
            **{**p, "evidence_ids": tuple(p["evidence_ids"])}
        ) for p in record["probes"])
        record["hypotheses"] = tuple(MeaningHypothesis(
            **{**h, "evidence_ids": tuple(h["evidence_ids"])}
        ) for h in record["hypotheses"])
        record["synergies"] = tuple(SynergyHypothesis(
            **{**s, "evidence_ids": tuple(s["evidence_ids"]),
               "lenses": tuple(s["lenses"])}
        ) for s in record["synergies"])
        record["research_gaps"] = tuple(record["research_gaps"])
        record["conflict_ids"] = tuple(record["conflict_ids"])
        result = MotherGleanReport(**record)
        if not verify_mother_report(result):
            raise ValueError("mother evidence digest invalid")
        return result
    except (TypeError, KeyError, IndexError, UnicodeError,
            ValueError, OverflowError) as exc:
        raise ValueError("mother glean report malformed or unsigned") from exc


class MotherGleanLedger:
    def __init__(self, db: sqlite3.Connection, *, signing_key: bytes):
        if not isinstance(db, sqlite3.Connection):
            raise TypeError("durable SQLite authority required")
        if not isinstance(signing_key, bytes) or len(signing_key) < 32:
            raise ValueError("independent mother audit signing key required")
        self.db = db
        self.key = signing_key
        with db:
            db.execute("""CREATE TABLE IF NOT EXISTS dragon_mother_glean (
                owner TEXT NOT NULL, seq INTEGER NOT NULL,
                acquisition_key TEXT NOT NULL, payload TEXT NOT NULL,
                previous_head TEXT NOT NULL, head TEXT NOT NULL,
                mac TEXT NOT NULL,
                PRIMARY KEY(owner,seq), UNIQUE(owner,acquisition_key))""")

    def _mac(self, owner: str, seq: int, key: str, body: str,
             previous: str, head: str) -> str:
        data = canonical_json((owner, seq, key, body, previous, head))
        return hmac.new(self.key, data.encode("utf-8"), sha256).hexdigest()

    def _history(self, owner: str) -> tuple[tuple[str, MotherGleanReport, str], ...]:
        owner = _id(owner)
        rows = self.db.execute(
            "SELECT seq,acquisition_key,payload,previous_head,head,mac "
            "FROM dragon_mother_glean WHERE owner=? ORDER BY seq", (owner,),
        )
        output = []
        previous = "0" * 64
        previous_at = None
        for number, (seq, key, raw, prev, head, mac) in enumerate(rows, 1):
            if number > MAX_EVENTS or seq != number or prev != previous:
                raise ValueError("mother append-only history contains gap or rollback")
            if (not isinstance(key, str) or len(key) != 64
                    or not isinstance(head, str) or len(head) != 64
                    or not isinstance(mac, str)
                    or not hmac.compare_digest(mac, self._mac(
                        owner, seq, key, raw, prev, head
                    ))):
                raise ValueError("mother ledger signature invalid")
            report = _decode(raw)
            expected = canonical_digest((prev, key, report.digest, number))
            if (report.owner != owner or expected != head):
                raise ValueError("mother history custody hash mismatch")
            if previous_at is not None and _instant(report.at) < previous_at:
                raise ValueError("mother historical timestamps regressed")
            previous_at = _instant(report.at)
            previous = head
            output.append((key, report, head))
        return tuple(output)

    def history(self, owner: str, *, authorized: bool) -> tuple[MotherGleanReport, ...]:
        if authorized is not True:
            raise PermissionError("owner approval required")
        return tuple(x[1] for x in self._history(owner))

    def run(
        self, library: ReviewedKnowledgeStore, nest: DragonNest,
        acquisitions: tuple[HatchlingReceipt, ...], *,
        at: str, idle_since: str, owner_authorized: bool,
        consented: bool, background_allowed: bool,
    ) -> MotherGleanReport:
        if owner_authorized is not True:
            raise PermissionError("mother glean worker is not authorized")
        # Glean must be rerun against current sources on a new acquisition.
        report = glean_mother_insights(
            library, nest, acquisitions, at=at, idle_since=idle_since,
            owner_authorized=True, consented=consented,
            background_allowed=background_allowed,
        )
        key = canonical_digest((
            report.owner, report.knowledge_root,
            report.nest_history_head,
            tuple(asdict(a) for a in report.acquisitions),
        ))
        if not verify_mother_report(report):
            raise ValueError("unsound mother-glean report")
        self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            prior = self._history(report.owner)
            for prior_key, prior_report, _ in prior:
                if prior_key == key:
                    return prior_report
            if len(prior) >= MAX_EVENTS:
                raise ValueError("mother history budget exhausted")
            if prior and _instant(report.at) < _instant(prior[-1][1].at):
                raise ValueError("mother event timestamp cannot go backwards")
            # Detect a concurrent canonical knowledge update before committing
            # the report to the historical record.
            if library.snapshot_root(report.owner, authorized=True) != report.knowledge_root:
                raise ValueError("reviewed knowledge changed during glean commit")
            body = canonical_json(asdict(report))
            if len(body.encode("utf-8")) > MAX_BYTES:
                raise ValueError("mother report storage cap exceeded")
            number = len(prior) + 1
            previous = prior[-1][2] if prior else "0" * 64
            head = canonical_digest((previous, key, report.digest, number))
            mac = self._mac(report.owner, number, key, body, previous, head)
            self.db.execute(
                "INSERT INTO dragon_mother_glean "
                "(owner,seq,acquisition_key,payload,previous_head,head,mac) "
                "VALUES(?,?,?,?,?,?,?)",
                (report.owner, number, key, body, previous, head, mac),
            )
        return report
