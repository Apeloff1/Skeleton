"""Offline-verifiable Ed25519 witness statements for transparency heads.

Transport authentication is operational evidence, not portable proof. Signed witness
verification never falls back: when signed witnesses are configured, the Ed25519
runtime is mandatory. All signed material uses strict portable canonical JSON and
exact JSON types; Python coercion is never part of a trust decision.
"""
from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

    _CRYPTO_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only in deliberately minimal runtimes
    InvalidSignature = Exception
    Ed25519PrivateKey = None
    Ed25519PublicKey = None
    _CRYPTO_AVAILABLE = False

from core.canonical_json import (
    CanonicalJSONError,
    canonical_json_bytes,
    canonical_json_clone,
    canonical_json_sha256,
)
from core.file_lease import FileLease
from core.transparency_witness import TrustedWitness, WitnessQuorum

SIGNED_WITNESS_VERSION = 1
_DOMAIN = "skeleton.transparency.witness.ed25519.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_STATEMENT_KEYS = {
    "version",
    "log_id",
    "tree_size",
    "root_sha256",
    "witness_id",
    "independence_group",
    "observed_at",
    "nonce",
    "public_key_fingerprint",
    "signature_b64",
    "statement_sha256",
}
_ENVELOPE_KEYS = {"version", "statements", "incidents", "sha256"}
_INCIDENT_KEYS = {
    "kind",
    "log_id",
    "tree_size",
    "witness_id",
    "independence_group",
    "roots",
    "observed_at",
}


class SignedWitnessIntegrityError(RuntimeError):
    pass


class SignedWitnessRejected(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SignedWitnessStatement:
    version: int
    log_id: str
    tree_size: int
    root_sha256: str
    witness_id: str
    independence_group: str
    observed_at: str
    nonce: str
    public_key_fingerprint: str
    signature_b64: str
    statement_sha256: str


def _canonical_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be a canonical non-empty string")
    return value


def _canonical_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{field} must be lowercase sha256")
    return value


def _nonnegative_int(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("signed witness timestamp must be a canonical non-empty string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("signed witness timestamp is malformed") from exc
    if parsed.tzinfo is None:
        raise ValueError("signed witness timestamp must be timezone-aware")
    normalized = parsed.astimezone(UTC).isoformat()
    if value.replace("Z", "+00:00") != normalized:
        raise ValueError("signed witness timestamp must be normalized to UTC")
    return parsed.astimezone(UTC)


def _decode_b64(value: Any, *, field: str, expected_len: int | None = None) -> bytes:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be canonical base64 text")
    try:
        raw = base64.b64decode(value, validate=True)
    except Exception as exc:
        raise ValueError(f"{field} is invalid base64") from exc
    if expected_len is not None and len(raw) != expected_len:
        raise ValueError(f"{field} must decode to {expected_len} bytes")
    if base64.b64encode(raw).decode("ascii") != value:
        raise ValueError(f"{field} must use canonical base64 encoding")
    return raw


def _strict_json_loads(text: str) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(text, object_pairs_hook=reject_duplicates)


def public_key_fingerprint(public_key_b64: str) -> str:
    return hashlib.sha256(
        _decode_b64(public_key_b64, field="public_key_b64", expected_len=32)
    ).hexdigest()


def signed_payload(
    *,
    log_id: str,
    tree_size: int,
    root_sha256: str,
    witness_id: str,
    independence_group: str,
    observed_at: str,
    nonce: str,
    public_key_fingerprint: str,
) -> dict[str, Any]:
    return {
        "domain": _DOMAIN,
        "version": SIGNED_WITNESS_VERSION,
        "log_id": _canonical_text(log_id, "log_id"),
        "tree_size": _nonnegative_int(tree_size, "tree_size"),
        "root_sha256": _canonical_sha(root_sha256, "root_sha256"),
        "witness_id": _canonical_text(witness_id, "witness_id"),
        "independence_group": _canonical_text(independence_group, "independence_group"),
        "observed_at": _parse_time(observed_at).isoformat(),
        "nonce": _canonical_text(nonce, "nonce"),
        "public_key_fingerprint": _canonical_sha(public_key_fingerprint, "public_key_fingerprint"),
    }


def _statement_mapping(statement: SignedWitnessStatement | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(statement, SignedWitnessStatement):
        raw = asdict(statement)
    elif isinstance(statement, Mapping):
        raw = dict(statement)
    else:
        raise ValueError("signed witness statement type mismatch")
    if set(raw) != _STATEMENT_KEYS:
        raise ValueError("signed witness statement schema mismatch")
    return canonical_json_clone(raw)


def verify_signed_statement(
    statement: SignedWitnessStatement | Mapping[str, Any],
    *,
    public_key_b64: str,
    expected_group: str | None = None,
) -> bool:
    if not _CRYPTO_AVAILABLE:
        return False
    try:
        raw = _statement_mapping(statement)
        if type(raw["version"]) is not int or raw["version"] != SIGNED_WITNESS_VERSION:
            return False
        if expected_group is not None:
            expected_group = _canonical_text(expected_group, "expected_group")
        fingerprint = public_key_fingerprint(public_key_b64)
        if not hmac.compare_digest(
            _canonical_sha(raw["public_key_fingerprint"], "public_key_fingerprint"),
            fingerprint,
        ):
            return False
        payload = signed_payload(
            log_id=raw["log_id"],
            tree_size=raw["tree_size"],
            root_sha256=raw["root_sha256"],
            witness_id=raw["witness_id"],
            independence_group=raw["independence_group"],
            observed_at=raw["observed_at"],
            nonce=raw["nonce"],
            public_key_fingerprint=fingerprint,
        )
        if expected_group is not None and payload["independence_group"] != expected_group:
            return False
        signature = _decode_b64(raw["signature_b64"], field="signature_b64", expected_len=64)
        public_key = Ed25519PublicKey.from_public_bytes(
            _decode_b64(public_key_b64, field="public_key_b64", expected_len=32)
        )
        public_key.verify(signature, canonical_json_bytes(payload))
        claimed = _canonical_sha(raw["statement_sha256"], "statement_sha256")
        expected = canonical_json_sha256({**payload, "signature_b64": raw["signature_b64"]})
        return hmac.compare_digest(expected, claimed)
    except (CanonicalJSONError, InvalidSignature, KeyError, TypeError, ValueError):
        return False


def sign_statement_for_witness(
    *,
    private_key_b64: str,
    public_key_b64: str,
    log_id: str,
    tree_size: int,
    root_sha256: str,
    witness_id: str,
    independence_group: str,
    observed_at: str,
    nonce: str,
) -> SignedWitnessStatement:
    if not _CRYPTO_AVAILABLE:
        raise RuntimeError("cryptography is required for Ed25519 witness signing")
    private_bytes = _decode_b64(private_key_b64, field="private_key_b64", expected_len=32)
    public_bytes = _decode_b64(public_key_b64, field="public_key_b64", expected_len=32)
    private = Ed25519PrivateKey.from_private_bytes(private_bytes)
    derived_public = private.public_key().public_bytes_raw()
    if not hmac.compare_digest(derived_public, public_bytes):
        raise ValueError("private/public witness key pair does not match")
    fingerprint = hashlib.sha256(public_bytes).hexdigest()
    payload = signed_payload(
        log_id=log_id,
        tree_size=tree_size,
        root_sha256=root_sha256,
        witness_id=witness_id,
        independence_group=independence_group,
        observed_at=observed_at,
        nonce=nonce,
        public_key_fingerprint=fingerprint,
    )
    signature_b64 = base64.b64encode(private.sign(canonical_json_bytes(payload))).decode("ascii")
    statement_sha256 = canonical_json_sha256({**payload, "signature_b64": signature_b64})
    return SignedWitnessStatement(
        version=SIGNED_WITNESS_VERSION,
        log_id=payload["log_id"],
        tree_size=payload["tree_size"],
        root_sha256=payload["root_sha256"],
        witness_id=payload["witness_id"],
        independence_group=payload["independence_group"],
        observed_at=payload["observed_at"],
        nonce=payload["nonce"],
        public_key_fingerprint=fingerprint,
        signature_b64=signature_b64,
        statement_sha256=statement_sha256,
    )


def _validate_incident(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping) or set(raw) != _INCIDENT_KEYS:
        raise SignedWitnessIntegrityError("signed witness incident schema mismatch")
    if raw.get("kind") != "signed_witness_equivocation":
        raise SignedWitnessIntegrityError("signed witness incident kind mismatch")
    tree_size = raw.get("tree_size")
    if type(tree_size) is not int or tree_size < 0:
        raise SignedWitnessIntegrityError("signed witness incident tree size malformed")
    for field in ("log_id", "witness_id", "independence_group"):
        try:
            _canonical_text(raw.get(field), field)
        except ValueError as exc:
            raise SignedWitnessIntegrityError(str(exc)) from exc
    roots = raw.get("roots")
    if not isinstance(roots, list) or len(roots) != 2 or roots != sorted(set(roots)):
        raise SignedWitnessIntegrityError("signed witness incident roots malformed")
    try:
        for root in roots:
            _canonical_sha(root, "incident root")
        _parse_time(raw.get("observed_at"))
    except ValueError as exc:
        raise SignedWitnessIntegrityError(str(exc)) from exc
    return canonical_json_clone(dict(raw))


class SignedTransparencyWitnessLedger:
    def __init__(
        self,
        root: str | Path,
        *,
        trusted_witnesses: Iterable[TrustedWitness] = (),
        required_groups: int = 3,
        max_age_seconds: int = 3600,
    ) -> None:
        if type(required_groups) is not int or required_groups < 1:
            raise ValueError("signed witness quorum must be a positive integer")
        if type(max_age_seconds) is not int or not 1 <= max_age_seconds <= 604800:
            raise ValueError("signed witness max age must be an integer between 1 and 604800")
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "signed-witnesses.json"
        self._lease = FileLease(self.root / ".signed-witnesses.lock")
        self.required_groups = required_groups
        self.max_age_seconds = max_age_seconds
        self._trusted = self._normalize_registry(trusted_witnesses)
        if self._trusted and not _CRYPTO_AVAILABLE:
            raise RuntimeError("cryptography is required when signed transparency witnesses are configured")
        with self._lease.acquire():
            if not self.path.exists():
                self._write([], [])
            else:
                self._load()

    @staticmethod
    def _normalize_registry(rows: Iterable[TrustedWitness]) -> dict[str, TrustedWitness]:
        registry: dict[str, TrustedWitness] = {}
        for row in rows:
            if not isinstance(row, TrustedWitness):
                raise ValueError("signed trusted witness registry contains unsupported entry")
            witness_id = _canonical_text(row.id, "trusted witness id")
            group = _canonical_text(row.independence_group, "trusted witness independence_group")
            if type(row.enabled) is not bool:
                raise ValueError("trusted witness enabled must be boolean")
            public_key = row.public_key_b64
            if not isinstance(public_key, str):
                raise ValueError("trusted witness public_key_b64 must be a string")
            if witness_id in registry:
                raise ValueError(f"duplicate trusted witness: {witness_id}")
            if row.enabled and public_key:
                public_key_fingerprint(public_key)
                registry[witness_id] = TrustedWitness(witness_id, group, True, public_key)
        return registry

    @staticmethod
    def _checksum(rows: list[dict[str, Any]], incidents: list[dict[str, Any]]) -> str:
        return canonical_json_sha256(
            {"version": SIGNED_WITNESS_VERSION, "statements": rows, "incidents": incidents}
        )

    def _load(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        try:
            env = _strict_json_loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise SignedWitnessIntegrityError("signed witness ledger unreadable") from exc
        if not isinstance(env, Mapping) or set(env) != _ENVELOPE_KEYS:
            raise SignedWitnessIntegrityError("signed witness ledger schema mismatch")
        if type(env.get("version")) is not int or env["version"] != SIGNED_WITNESS_VERSION:
            raise SignedWitnessIntegrityError("signed witness ledger version malformed")
        rows = env.get("statements")
        incidents = env.get("incidents")
        checksum = env.get("sha256")
        if not isinstance(rows, list) or not isinstance(incidents, list):
            raise SignedWitnessIntegrityError("signed witness ledger collections malformed")
        try:
            checksum = _canonical_sha(checksum, "signed witness ledger checksum")
        except ValueError as exc:
            raise SignedWitnessIntegrityError(str(exc)) from exc
        try:
            expected_checksum = self._checksum(rows, incidents)
        except CanonicalJSONError as exc:
            raise SignedWitnessIntegrityError("signed witness ledger is not portable canonical JSON") from exc
        if not hmac.compare_digest(checksum, expected_checksum):
            raise SignedWitnessIntegrityError("signed witness ledger checksum mismatch")

        verified_rows: list[dict[str, Any]] = []
        identities: set[tuple[str, int, str]] = set()
        for raw in rows:
            try:
                normalized = _statement_mapping(raw)
                witness_id = _canonical_text(normalized["witness_id"], "witness_id")
                tree_size = _nonnegative_int(normalized["tree_size"], "tree_size")
                log_id = _canonical_text(normalized["log_id"], "log_id")
            except (CanonicalJSONError, KeyError, ValueError) as exc:
                raise SignedWitnessIntegrityError("stored signed witness statement malformed") from exc
            identity = (log_id, tree_size, witness_id)
            if identity in identities:
                raise SignedWitnessIntegrityError("duplicate signed witness statement identity")
            identities.add(identity)
            witness = self._trusted.get(witness_id)
            if witness is None or not verify_signed_statement(
                normalized,
                public_key_b64=witness.public_key_b64,
                expected_group=witness.independence_group,
            ):
                raise SignedWitnessIntegrityError("stored signed witness statement failed verification")
            verified_rows.append(normalized)

        verified_incidents = [_validate_incident(raw) for raw in incidents]
        return verified_rows, verified_incidents

    def _write(self, rows: list[dict[str, Any]], incidents: list[dict[str, Any]]) -> None:
        env = {
            "version": SIGNED_WITNESS_VERSION,
            "statements": rows,
            "incidents": incidents,
            "sha256": self._checksum(rows, incidents),
        }
        temp = self.path.with_suffix(f".{os.getpid()}.tmp")
        try:
            with temp.open("wb") as handle:
                handle.write(canonical_json_bytes(env))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, self.path)
        finally:
            temp.unlink(missing_ok=True)

    def observe(
        self,
        statement: SignedWitnessStatement | Mapping[str, Any],
    ) -> SignedWitnessStatement:
        try:
            raw = _statement_mapping(statement)
            witness_id = _canonical_text(raw["witness_id"], "witness_id")
        except (CanonicalJSONError, KeyError, ValueError) as exc:
            raise SignedWitnessRejected("signed witness statement malformed") from exc
        witness = self._trusted.get(witness_id)
        if witness is None:
            raise SignedWitnessRejected("signed witness is not trusted/enabled or lacks a pinned public key")
        if not verify_signed_statement(
            raw,
            public_key_b64=witness.public_key_b64,
            expected_group=witness.independence_group,
        ):
            raise SignedWitnessRejected("signed witness statement verification failed")
        restored = SignedWitnessStatement(**raw)
        with self._lease.acquire():
            rows, incidents = self._load()
            same = [
                row
                for row in rows
                if row["log_id"] == restored.log_id
                and row["tree_size"] == restored.tree_size
                and row["witness_id"] == restored.witness_id
            ]
            for prior in same:
                if prior["root_sha256"] != restored.root_sha256:
                    incident = {
                        "kind": "signed_witness_equivocation",
                        "log_id": restored.log_id,
                        "tree_size": restored.tree_size,
                        "witness_id": restored.witness_id,
                        "independence_group": witness.independence_group,
                        "roots": sorted({prior["root_sha256"], restored.root_sha256}),
                        "observed_at": restored.observed_at,
                    }
                    if incident not in incidents:
                        incidents.append(incident)
                    self._write(rows, incidents)
                    raise SignedWitnessRejected(
                        "signed trusted witness equivocated for the same tree size"
                    )
                return SignedWitnessStatement(**prior)
            rows.append(canonical_json_clone(asdict(restored)))
            self._write(rows, incidents)
            return restored

    def _target(
        self,
        *,
        log_id: str,
        tree_size: int,
        root_sha256: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        log_id = _canonical_text(log_id, "log_id")
        tree_size = _nonnegative_int(tree_size, "tree_size")
        root_sha256 = _canonical_sha(root_sha256, "root_sha256")
        with self._lease.acquire():
            rows, incidents = self._load()
        return [
            row
            for row in rows
            if row["log_id"] == log_id
            and row["tree_size"] == tree_size
            and row["root_sha256"] == root_sha256
        ], incidents

    def quorum(
        self,
        *,
        log_id: str,
        tree_size: int,
        root_sha256: str,
        now: datetime | None = None,
    ) -> WitnessQuorum:
        current = now or datetime.now(UTC)
        if not isinstance(current, datetime) or current.tzinfo is None:
            raise ValueError("signed quorum evaluation time must be timezone-aware")
        current = current.astimezone(UTC)
        target, incidents = self._target(
            log_id=log_id,
            tree_size=tree_size,
            root_sha256=root_sha256,
        )
        fresh: list[dict[str, Any]] = []
        stale = 0
        for raw in target:
            age = (current - _parse_time(raw["observed_at"])).total_seconds()
            if 0 <= age <= self.max_age_seconds:
                fresh.append(raw)
            else:
                stale += 1
        groups = tuple(sorted({row["independence_group"] for row in fresh}))
        witness_ids = tuple(sorted({row["witness_id"] for row in fresh}))
        frozen = any(
            incident["kind"] == "signed_witness_equivocation"
            and incident["log_id"] == log_id
            for incident in incidents
        )
        reached = not frozen and len(groups) >= self.required_groups
        payload = {
            "log_id": log_id,
            "tree_size": tree_size,
            "root_sha256": root_sha256,
            "trusted_receipts": len(target),
            "fresh_receipts": len(fresh),
            "stale_receipts": stale,
            "independent_groups": len(groups),
            "required_groups": self.required_groups,
            "max_age_seconds": self.max_age_seconds,
            "reached": reached,
            "frozen": frozen,
            "witness_ids": witness_ids,
            "groups": groups,
        }
        return WitnessQuorum(
            **payload,
            attestation_sha256=canonical_json_sha256(payload),
        )

    def evidence(
        self,
        *,
        log_id: str,
        tree_size: int,
        root_sha256: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        quorum = self.quorum(
            log_id=log_id,
            tree_size=tree_size,
            root_sha256=root_sha256,
            now=now,
        )
        target, _ = self._target(
            log_id=log_id,
            tree_size=tree_size,
            root_sha256=root_sha256,
        )
        target = sorted((dict(row) for row in target), key=lambda row: row["witness_id"])
        return {"quorum": asdict(quorum), "statements": target}

    def status(self) -> dict[str, Any]:
        with self._lease.acquire():
            rows, incidents = self._load()
        equivocations = sum(
            incident["kind"] == "signed_witness_equivocation" for incident in incidents
        )
        groups = {witness.independence_group for witness in self._trusted.values()}
        return {
            "version": SIGNED_WITNESS_VERSION,
            "crypto_available": _CRYPTO_AVAILABLE,
            "trusted_signed_witnesses": len(self._trusted),
            "independence_groups": len(groups),
            "required_groups": self.required_groups,
            "max_age_seconds": self.max_age_seconds,
            "statements": len(rows),
            "equivocations": equivocations,
            "healthy": equivocations == 0,
            "cross_process_locking": True,
            "lock_backend": self._lease.backend,
            "sha256": self._checksum(rows, incidents),
        }
