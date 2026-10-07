"""Current truth-state ledger for claims promoted into authoritative context.

Knowledge records are append-preserving historical artifacts. Truth state is a
separate mutable projection: claims can expire, be reverified, or be revoked when
evidence is retracted/contradicted. Historical records remain intact for audit,
while live reasoning consumes only claims whose current truth state is authoritative.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any, Iterable

from core.file_lease import FileLease


TRUTH_LEDGER_VERSION = 1


class TruthLedgerIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ClaimTruthState:
    claim: str
    verification_state: str
    verification_attestation_sha256: str
    evidence_record_ids: tuple[str, ...]
    verified_at: str
    valid_until: str
    revoked_at: str = ""
    revocation_reason: str = ""
    revision: int = 1


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _parse(stamp: str) -> datetime:
    value = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if value.tzinfo is None: raise ValueError("truth-state timestamp must be timezone-aware")
    return value.astimezone(UTC)


class ClaimTruthLedger:
    def __init__(self, root: str | Path, *, default_valid_days: int = 180) -> None:
        if default_valid_days < 1: raise ValueError("default_valid_days must be >= 1")
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "claim-truth-ledger.json"
        self.default_valid_days = int(default_valid_days)
        self._lease = FileLease(self.root / ".claim-truth.lock")
        with self._lease.acquire():
            if not self.path.exists(): self._write({})
            else: self._load()

    @staticmethod
    def _key(claim: str) -> str:
        return _sha(" ".join(str(claim).split()).strip().casefold())

    @staticmethod
    def _checksum(states: dict[str, dict[str, Any]]) -> str:
        return _sha({"version": TRUTH_LEDGER_VERSION, "states": states})

    def _load(self) -> dict[str, dict[str, Any]]:
        try: env = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc: raise TruthLedgerIntegrityError("truth ledger unreadable") from exc
        states = env.get("states"); checksum = env.get("sha256")
        if env.get("version") != TRUTH_LEDGER_VERSION: raise TruthLedgerIntegrityError("unsupported truth ledger version")
        if not isinstance(states, dict) or not isinstance(checksum, str): raise TruthLedgerIntegrityError("truth ledger malformed")
        if not hmac.compare_digest(checksum, self._checksum(states)): raise TruthLedgerIntegrityError("truth ledger checksum mismatch")
        return {str(k): dict(v) for k, v in states.items() if isinstance(v, dict)}

    def _write(self, states: dict[str, dict[str, Any]]) -> None:
        env = {"version": TRUTH_LEDGER_VERSION, "states": states, "sha256": self._checksum(states)}
        temp = self.path.with_suffix(f".{os.getpid()}.tmp")
        try:
            with temp.open("wb") as handle:
                handle.write(_canonical(env)); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp, self.path)
        finally: temp.unlink(missing_ok=True)

    @staticmethod
    def _restore(raw: dict[str, Any]) -> ClaimTruthState:
        return ClaimTruthState(
            claim=str(raw["claim"]), verification_state=str(raw["verification_state"]),
            verification_attestation_sha256=str(raw["verification_attestation_sha256"]),
            evidence_record_ids=tuple(raw.get("evidence_record_ids", ())), verified_at=str(raw["verified_at"]),
            valid_until=str(raw["valid_until"]), revoked_at=str(raw.get("revoked_at", "")),
            revocation_reason=str(raw.get("revocation_reason", "")), revision=int(raw.get("revision", 1)),
        )

    def record(self, *, claim: str, verification_state: str, verification_attestation_sha256: str,
               evidence_record_ids: Iterable[str], verified_at: str | None = None,
               valid_days: int | None = None) -> ClaimTruthState:
        claim = " ".join(str(claim).split()).strip()
        if not claim: raise ValueError("claim cannot be blank")
        if len(verification_attestation_sha256) != 64: raise ValueError("verification attestation must be sha256")
        now = _parse(verified_at) if verified_at else datetime.now(UTC)
        days = self.default_valid_days if valid_days is None else int(valid_days)
        if days < 1: raise ValueError("valid_days must be >= 1")
        key = self._key(claim)
        evidence = tuple(sorted(dict.fromkeys(str(x) for x in evidence_record_ids if str(x))))
        with self._lease.acquire():
            states = self._load(); prior = states.get(key); revision = int(prior.get("revision", 0)) + 1 if prior else 1
            state = ClaimTruthState(
                claim=claim, verification_state=str(verification_state),
                verification_attestation_sha256=verification_attestation_sha256,
                evidence_record_ids=evidence, verified_at=now.isoformat(),
                valid_until=(now + timedelta(days=days)).isoformat(), revision=revision,
            )
            states[key] = asdict(state); self._write(states); return state

    def revoke(self, claim: str, reason: str, *, revoked_at: str | None = None) -> bool:
        reason = " ".join(str(reason).split()).strip()
        if not reason: raise ValueError("revocation reason required")
        key = self._key(claim); stamp = _parse(revoked_at).isoformat() if revoked_at else datetime.now(UTC).isoformat()
        with self._lease.acquire():
            states = self._load(); raw = states.get(key)
            if raw is None: return False
            raw["revoked_at"] = stamp; raw["revocation_reason"] = reason[:2000]
            raw["revision"] = int(raw.get("revision", 1)) + 1
            states[key] = raw; self._write(states); return True

    def get(self, claim: str) -> ClaimTruthState | None:
        with self._lease.acquire(): raw = self._load().get(self._key(claim))
        return self._restore(raw) if raw else None

    def authoritative(self, claim: str, *, now: datetime | None = None) -> bool:
        state = self.get(claim)
        if state is None or state.verification_state != "verified" or state.revoked_at: return False
        now = now or datetime.now(UTC)
        if now.tzinfo is None: raise ValueError("now must be timezone-aware")
        return _parse(state.valid_until) > now.astimezone(UTC)

    def expired_claims(self, *, now: datetime | None = None) -> tuple[str, ...]:
        now = now or datetime.now(UTC)
        if now.tzinfo is None: raise ValueError("now must be timezone-aware")
        with self._lease.acquire(): states = self._load()
        return tuple(sorted(
            str(raw["claim"]) for raw in states.values()
            if not raw.get("revoked_at") and str(raw.get("verification_state")) == "verified" and _parse(str(raw["valid_until"])) <= now.astimezone(UTC)
        ))

    def snapshot(self, *, include_revoked: bool = True) -> tuple[ClaimTruthState, ...]:
        with self._lease.acquire(): states = self._load()
        rows = [self._restore(raw) for raw in states.values()]
        if not include_revoked: rows = [x for x in rows if not x.revoked_at]
        return tuple(sorted(rows, key=lambda x: x.claim.casefold()))

    def stats(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        rows = self.snapshot()
        authoritative = sum(self.authoritative(x.claim, now=now) for x in rows)
        revoked = sum(bool(x.revoked_at) for x in rows)
        expired = sum(not x.revoked_at and x.verification_state == "verified" and _parse(x.valid_until) <= now for x in rows)
        with self._lease.acquire(): states = self._load()
        return {"version": TRUTH_LEDGER_VERSION, "claims": len(rows), "authoritative": authoritative,
                "revoked": revoked, "expired": expired, "default_valid_days": self.default_valid_days,
                "sha256": self._checksum(states), "cross_process_locking": True, "lock_backend": self._lease.backend}
