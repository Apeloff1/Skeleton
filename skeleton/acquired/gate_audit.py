"""Repo-mined fail-closed gate and tamper-evident audit primitives.

Adapted from Apeloff1/gameforge-middleware's PrincipalAuth/GatePolicy/WormAuditLog
design for Skeleton's Python runtime. The port deliberately strengthens two
edges from the source design: route prefixes match path-segment boundaries and
raw seal credentials are never persisted to the audit ledger.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import threading
import time
from typing import Mapping


GENESIS_HASH = "GENESIS"


class AuditChainError(RuntimeError):
    """Raised when a persisted audit chain cannot be verified."""


class SealRejected(ValueError):
    """Raised when a principal seal is malformed, expired, or unverifiable."""


@dataclass(frozen=True, slots=True)
class AuditEntry:
    seq: int
    timestamp: str
    kind: str
    seal_fingerprint: str
    principal: str
    route: str
    detail: str
    prev_hash: str
    hash: str = ""


@dataclass(frozen=True, slots=True)
class PrincipalSeal:
    principal: str
    attester: str
    expires_at: int
    matched_key: str


class WormAuditLog:
    """Append-only, hash-chained JSONL ledger with durable writes.

    In-memory state advances only after flush + fsync completes. Existing
    entries are verified on startup; malformed, reordered, deleted, or edited
    entries therefore fail closed with :class:`AuditChainError`.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._latest: AuditEntry | None = None
        self._seq = 0
        self._restore_chain()

    @property
    def latest(self) -> AuditEntry | None:
        return self._latest

    @property
    def sequence(self) -> int:
        return self._seq

    @staticmethod
    def _seal_fingerprint(seal: str) -> str:
        if not seal:
            return ""
        return hashlib.sha256(seal.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _canonical_payload(entry: AuditEntry) -> bytes:
        record = asdict(entry)
        record.pop("hash", None)
        return json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    @classmethod
    def _compute_hash(cls, entry: AuditEntry) -> str:
        return hashlib.sha256(cls._canonical_payload(entry)).hexdigest()

    @classmethod
    def _decode_entry(cls, raw: str, line_no: int) -> AuditEntry:
        try:
            data = json.loads(raw)
            entry = AuditEntry(**data)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AuditChainError(f"audit chain unreadable at line {line_no}") from exc
        return entry

    def _read_verified_chain(self) -> tuple[AuditEntry | None, int]:
        if not self.path.exists():
            return None, 0

        latest: AuditEntry | None = None
        expected_seq = 1
        prev_hash = GENESIS_HASH
        with self.path.open("r", encoding="utf-8") as handle:
            for line_no, raw in enumerate(handle, start=1):
                raw = raw.strip()
                if not raw:
                    continue
                entry = self._decode_entry(raw, line_no)
                if entry.seq != expected_seq:
                    raise AuditChainError(
                        f"audit sequence broken at line {line_no}: "
                        f"expected {expected_seq}, got {entry.seq}"
                    )
                if entry.prev_hash != prev_hash:
                    raise AuditChainError(f"audit predecessor hash broken at seq {entry.seq}")
                expected_hash = self._compute_hash(replace(entry, hash=""))
                if not hmac.compare_digest(entry.hash, expected_hash):
                    raise AuditChainError(f"audit entry hash broken at seq {entry.seq}")
                latest = entry
                prev_hash = entry.hash
                expected_seq += 1
        return latest, expected_seq - 1

    def _restore_chain(self) -> None:
        self._latest, self._seq = self._read_verified_chain()

    def verify(self) -> AuditEntry | None:
        """Re-verify the complete persisted chain and return its head."""
        with self._lock:
            latest, _ = self._read_verified_chain()
            return latest

    def append(
        self,
        kind: str,
        seal: str,
        principal: str,
        route: str,
        detail: str,
        *,
        timestamp: datetime | None = None,
    ) -> AuditEntry:
        if not kind.strip():
            raise ValueError("audit kind must not be empty")
        if not route.strip():
            raise ValueError("audit route must not be empty")

        ts = timestamp or datetime.now(timezone.utc)
        if ts.tzinfo is None:
            raise ValueError("audit timestamp must be timezone-aware")
        timestamp_text = ts.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        )

        with self._lock:
            draft = AuditEntry(
                seq=self._seq + 1,
                timestamp=timestamp_text,
                kind=kind,
                seal_fingerprint=self._seal_fingerprint(seal),
                principal=principal,
                route=route,
                detail=detail,
                prev_hash=self._latest.hash if self._latest else GENESIS_HASH,
            )
            entry = replace(draft, hash=self._compute_hash(draft))
            serialized = json.dumps(
                asdict(entry),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )

            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(serialized + "\n")
                handle.flush()
                os.fsync(handle.fileno())

            self._latest = entry
            self._seq = entry.seq
            return entry


class PrincipalSealKeyring:
    """Rotatable HMAC-SHA256 principal seals compatible with the mined gate.

    Seal wire format remains ``principal.attester.expiry.signature``. The
    verifier checks every live key in constant time; issuing uses one explicit
    signing key while old keys may remain verification-only during rotation.
    """

    def __init__(self, keys: Mapping[str, bytes], *, signing_key: str | None = None):
        if not keys:
            raise ValueError("principal seal keyring must not be empty")

        normalized: dict[str, bytes] = {}
        for key_id, key in keys.items():
            key_bytes = bytes(key)
            if not key_id:
                raise ValueError("key id must not be empty")
            if len(key_bytes) < 32:
                raise ValueError(f"key {key_id!r} must contain at least 32 bytes")
            normalized[str(key_id)] = key_bytes

        self._keys = normalized
        self._signing_key = signing_key or next(reversed(normalized))
        if self._signing_key not in self._keys:
            raise ValueError("signing key must exist in keyring")

    @staticmethod
    def _validate_identity(value: str, field: str) -> None:
        if not value or "." in value:
            raise ValueError(f"{field} must be non-empty and must not contain '.'")

    def issue(
        self,
        principal: str,
        attester: str,
        *,
        ttl_seconds: int = 300,
        now: int | float | None = None,
    ) -> str:
        self._validate_identity(principal, "principal")
        self._validate_identity(attester, "attester")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")

        issued_at = int(time.time() if now is None else now)
        expiry = issued_at + int(ttl_seconds)
        payload = f"{principal}.{attester}.{expiry}".encode("utf-8")
        signature = hmac.new(
            self._keys[self._signing_key], payload, hashlib.sha256
        ).hexdigest()
        return f"{principal}.{attester}.{expiry}.{signature}"

    def verify(self, seal: str, *, now: int | float | None = None) -> PrincipalSeal:
        parts = seal.split(".")
        if len(parts) != 4:
            raise SealRejected("seal malformed")
        principal, attester, expiry_raw, signature = parts

        try:
            self._validate_identity(principal, "principal")
            self._validate_identity(attester, "attester")
            expiry = int(expiry_raw)
            supplied = bytes.fromhex(signature)
        except (ValueError, TypeError) as exc:
            raise SealRejected("seal unreadable") from exc

        if len(supplied) != hashlib.sha256().digest_size:
            raise SealRejected("seal signature invalid")

        current = int(time.time() if now is None else now)
        if expiry <= current:
            raise SealRejected("seal expired")

        payload = f"{principal}.{attester}.{expiry_raw}".encode("utf-8")
        matched_key: str | None = None
        for key_id, key in self._keys.items():
            expected = hmac.new(key, payload, hashlib.sha256).digest()
            if hmac.compare_digest(expected, supplied):
                matched_key = key_id

        if matched_key is None:
            raise SealRejected("seal signature invalid")
        return PrincipalSeal(
            principal=principal,
            attester=attester,
            expires_at=expiry,
            matched_key=matched_key,
        )


class GatePolicy:
    """Route-to-domain policy where unwritten routes are sealed by default."""

    DEFAULT_OPEN_PREFIXES = ("/health", "/ready")
    DEFAULT_DOMAINS = {
        "/api/v1/retrieval": "retrieval",
        "/api/v1/forge": "forge",
        "/api/v1/pipeline": "pipeline",
    }

    def __init__(
        self,
        *,
        open_prefixes: tuple[str, ...] | None = None,
        domains: Mapping[str, str] | None = None,
    ):
        self.open_prefixes = tuple(open_prefixes or self.DEFAULT_OPEN_PREFIXES)
        self.domains = dict(domains or self.DEFAULT_DOMAINS)

    @staticmethod
    def _matches(path: str, prefix: str) -> bool:
        clean = prefix.rstrip("/") or "/"
        return path == clean or path.startswith(clean + "/")

    def is_open_route(self, path: str) -> bool:
        return any(self._matches(path, prefix) for prefix in self.open_prefixes)

    def required_domain(self, path: str) -> str | None:
        best: tuple[int, str] | None = None
        for prefix, domain in self.domains.items():
            if self._matches(path, prefix):
                candidate = (len(prefix), domain)
                if best is None or candidate[0] > best[0]:
                    best = candidate
        return None if best is None else best[1]

    def is_sealed(self, path: str) -> bool:
        """Return whether a route must reject unauthenticated access."""
        return not self.is_open_route(path)
