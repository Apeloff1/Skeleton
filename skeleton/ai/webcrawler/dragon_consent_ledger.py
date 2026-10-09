"""Durable, revocable consent receipts for Dragon capture and analysis."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json, math, sqlite3


@dataclass(frozen=True)
class ConsentReceipt:
    owner: str
    consent_id: str
    capture: bool
    analysis: bool
    issued_at: float
    expires_at: float
    revoked_at: float | None
    policy_version: str
    scope_digest: str


class DragonConsentLedger:
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_consent(
          owner TEXT NOT NULL, consent_id TEXT NOT NULL,
          capture INTEGER NOT NULL, analysis INTEGER NOT NULL,
          issued_at REAL NOT NULL, expires_at REAL NOT NULL,
          revoked_at REAL, policy_version TEXT NOT NULL,
          scope_digest TEXT NOT NULL, PRIMARY KEY(owner,consent_id))""")
        db.commit()

    def issue(self, owner: str, *, capture: bool, analysis: bool,
              issued_at: float, expires_at: float, policy_version: str,
              scope_digest: str, authorized: bool) -> ConsentReceipt:
        if not authorized:
            raise PermissionError("consent issuance requires authorization")
        if not isinstance(owner,str) or not 1 <= len(owner) <= 128:
            raise ValueError("invalid owner")
        if not capture or not analysis:
            raise ValueError("capture and analysis consent must be explicit")
        if not all(math.isfinite(x) for x in (issued_at,expires_at)) or issued_at < 0 or expires_at <= issued_at:
            raise ValueError("invalid consent lifetime")
        if not policy_version or len(policy_version) > 128:
            raise ValueError("invalid policy version")
        if len(scope_digest) != 64 or any(c not in "0123456789abcdef" for c in scope_digest):
            raise ValueError("invalid scope digest")
        consent_id=sha256(json.dumps(
            [owner,issued_at,expires_at,policy_version,scope_digest],
            separators=(",",":")).encode()).hexdigest()
        with self.db:
            self.db.execute("""INSERT OR IGNORE INTO dragon_consent
              VALUES(?,?,?,?,?,?,?,?,?)""",
              (owner,consent_id,1,1,issued_at,expires_at,None,policy_version,scope_digest))
        return self.get(owner,consent_id,authorized=True)

    def get(self, owner: str, consent_id: str, *, authorized: bool) -> ConsentReceipt | None:
        if not authorized:
            raise PermissionError("consent lookup requires authorization")
        row=self.db.execute("""SELECT capture,analysis,issued_at,expires_at,
          revoked_at,policy_version,scope_digest FROM dragon_consent
          WHERE owner=? AND consent_id=?""",(owner,consent_id)).fetchone()
        return ConsentReceipt(owner,consent_id,bool(row[0]),bool(row[1]),row[2],row[3],row[4],row[5],row[6]) if row else None

    def require_active(self, owner: str, consent_id: str, *, now: float,
                       scope_digest: str, authorized: bool) -> ConsentReceipt:
        receipt=self.get(owner,consent_id,authorized=authorized)
        if receipt is None:
            raise PermissionError("consent receipt not found")
        if receipt.revoked_at is not None or now < receipt.issued_at or now >= receipt.expires_at:
            raise PermissionError("consent is not active")
        if receipt.scope_digest != scope_digest:
            raise PermissionError("consent scope mismatch")
        return receipt

    def revoke(self, owner: str, consent_id: str, *, now: float,
               authorized: bool) -> ConsentReceipt:
        receipt=self.get(owner,consent_id,authorized=authorized)
        if receipt is None:
            raise KeyError("consent receipt not found")
        if not math.isfinite(now) or now < receipt.issued_at:
            raise ValueError("invalid revocation time")
        with self.db:
            self.db.execute("""UPDATE dragon_consent SET revoked_at=COALESCE(revoked_at,?)
              WHERE owner=? AND consent_id=?""",(now,owner,consent_id))
        return self.get(owner,consent_id,authorized=True)
