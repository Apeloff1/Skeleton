"""Append-only, HMAC-authenticated qualification report custody, scoped by model.

Report bytes are source of truth for verification. The ledger is a private
derived attestation, not a hosted registry or proof of CI/release readiness.
"""
from __future__ import annotations

import hashlib
import hmac
import sqlite3
from threading import RLock

from .canonical import decode, encode, identity, sha256
from .errors import deny
from .report import REPORT_SCHEMA

GENESIS = "0" * 64


class ReportLedger:
    def __init__(self, database: sqlite3.Connection, *, mac_key: bytes):
        if not isinstance(database, sqlite3.Connection):
            deny("ledger-database")
        if type(mac_key) is not bytes or len(mac_key) < 32:
            deny("ledger-key")
        self.db = database
        self.key = mac_key
        self.lock = RLock()
        self.db.execute("""CREATE TABLE IF NOT EXISTS qualification_report_ledger(
           scope TEXT NOT NULL, sequence INTEGER NOT NULL, run_id TEXT NOT NULL,
           report_sha256 TEXT NOT NULL, prev_mac TEXT NOT NULL, event_mac TEXT NOT NULL,
           report_bytes BLOB NOT NULL,
           PRIMARY KEY(scope,sequence), UNIQUE(scope,run_id))""")

    def _mac(self, scope: str, sequence: int, run_id: str,
             report_sha: str, previous: str) -> str:
        value = {
            "schema": "skeleton.native-qualification.ledger.v1",
            "scope": scope, "sequence": sequence, "run_id": run_id,
            "report_sha256": report_sha, "prev_mac": previous,
        }
        return hmac.new(self.key, encode(value), hashlib.sha256).hexdigest()

    def append(self, *, scope: str, run_id: str, report_bytes: bytes) -> dict:
        identity(scope, "ledger-scope")
        identity(run_id, "ledger-run")
        if type(report_bytes) is not bytes:
            deny("ledger-report-bytes")
        parsed = decode(report_bytes)
        if type(parsed) is not dict or parsed.get("schema") != REPORT_SCHEMA:
            deny("ledger-report-schema")
        if parsed.get("run_id") != run_id:
            deny("ledger-report-id")
        if encode(parsed) != report_bytes:
            deny("ledger-report-not-canonical")
        if parsed.get("release_certified") is not False:
            deny("ledger-release-claim")
        reported = sha256(report_bytes)
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self.verify(scope)
                existing = self.db.execute(
                    "SELECT sequence,report_sha256 FROM qualification_report_ledger WHERE scope=? AND run_id=?",
                    (scope, run_id),
                ).fetchone()
                if existing is not None:
                    if not hmac.compare_digest(existing[1], reported):
                        deny("ledger-run-collision")
                    # Recheck the complete authenticated chain before calling it replay.
                    self.verify(scope)
                    self.db.execute("COMMIT")
                    return {"status": "replayed", "sequence": existing[0], "sha256": reported}
                previous = self.db.execute(
                    """SELECT sequence,event_mac FROM qualification_report_ledger
                       WHERE scope=? ORDER BY sequence DESC LIMIT 1""", (scope,)
                ).fetchone()
                sequence = 1 if previous is None else previous[0] + 1
                prev_mac = GENESIS if previous is None else previous[1]
                mac = self._mac(scope, sequence, run_id, reported, prev_mac)
                self.db.execute(
                    """INSERT INTO qualification_report_ledger(
                        scope,sequence,run_id,report_sha256,prev_mac,event_mac,report_bytes
                        ) VALUES(?,?,?,?,?,?,?)""",
                    (scope, sequence, run_id, reported, prev_mac, mac, report_bytes),
                )
                self.db.execute("COMMIT")
                return {"status": "recorded", "sequence": sequence, "sha256": reported}
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def verify(self, scope: str, *, expected_head: str | None = None) -> dict:
        identity(scope, "ledger-scope")
        rows = self.db.execute(
            """SELECT sequence,run_id,report_sha256,prev_mac,event_mac,report_bytes
            FROM qualification_report_ledger WHERE scope=? ORDER BY sequence""",
            (scope,),
        ).fetchall()
        prev = GENESIS
        for i, (sequence, run_id, digest, prev_mac, event_mac, data) in enumerate(rows, 1):
            if sequence != i or prev_mac != prev:
                deny("ledger-sequence-tamper")
            if not hmac.compare_digest(digest, sha256(data)):
                deny("ledger-bytes-tamper")
            expect = self._mac(scope, sequence, run_id, digest, prev)
            if not hmac.compare_digest(expect, event_mac):
                deny("ledger-mac-tamper")
            parsed = decode(data)
            if parsed.get("run_id") != run_id or encode(parsed) != data:
                deny("ledger-identity-tamper")
            prev = event_mac
        if expected_head is not None:
            from .canonical import hex64
            hex64(expected_head, "ledger-expected-head")
            if not hmac.compare_digest(expected_head, prev):
                deny("ledger-truncation-or-head-drift")
        return {
            "scope": scope, "entries": len(rows), "head_mac": prev,
            "verified": True, "release_certified": False,
        }
