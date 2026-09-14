"""Offline-verifiable Ed25519 witness statements for transparency heads.

Transport authentication is useful operational evidence but is not portable proof.
This module adds an independent signed-evidence lane: trusted witness public keys are
configured out of band, every statement signs a domain-separated canonical payload,
and quorum collapses by configured independence group. No private key is stored by
the control plane.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from core.file_lease import FileLease
from core.transparency_witness import TrustedWitness, WitnessQuorum

SIGNED_WITNESS_VERSION = 1
_DOMAIN = "skeleton.transparency.witness.ed25519.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


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


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha(value: Any) -> str:
    return _sha_bytes(_canonical(value))


def _decode_b64(value: str, *, expected_len: int | None = None) -> bytes:
    try:
        raw = base64.b64decode(str(value), validate=True)
    except Exception as exc:
        raise ValueError("invalid base64") from exc
    if expected_len is not None and len(raw) != expected_len:
        raise ValueError(f"decoded value must be {expected_len} bytes")
    return raw


def public_key_fingerprint(public_key_b64: str) -> str:
    return _sha_bytes(_decode_b64(public_key_b64, expected_len=32))


def _parse_time(value: str) -> datetime:
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("signed witness timestamp must be timezone-aware")
    return stamp.astimezone(UTC)


def signed_payload(*, log_id: str, tree_size: int, root_sha256: str, witness_id: str,
                   independence_group: str, observed_at: str, nonce: str,
                   public_key_fingerprint: str) -> dict[str, Any]:
    return {
        "domain": _DOMAIN, "version": SIGNED_WITNESS_VERSION,
        "log_id": log_id, "tree_size": tree_size, "root_sha256": root_sha256,
        "witness_id": witness_id, "independence_group": independence_group,
        "observed_at": observed_at, "nonce": nonce,
        "public_key_fingerprint": public_key_fingerprint,
    }


def verify_signed_statement(statement: SignedWitnessStatement | Mapping[str, Any], *, public_key_b64: str,
                            expected_group: str | None = None) -> bool:
    try:
        raw = asdict(statement) if isinstance(statement, SignedWitnessStatement) else dict(statement)
        if int(raw.get("version", 0)) != SIGNED_WITNESS_VERSION:
            return False
        root = str(raw.get("root_sha256", "")).lower().strip()
        if not _SHA256.fullmatch(root) or int(raw.get("tree_size", -1)) < 0:
            return False
        witness_id = str(raw.get("witness_id", "")).strip(); group = str(raw.get("independence_group", "")).strip()
        log_id = str(raw.get("log_id", "")).strip(); nonce = str(raw.get("nonce", "")).strip()
        if not witness_id or not group or not log_id or not nonce:
            return False
        if expected_group is not None and group != expected_group:
            return False
        observed_at = str(raw.get("observed_at", "")); _parse_time(observed_at)
        fingerprint = public_key_fingerprint(public_key_b64)
        if not hmac.compare_digest(fingerprint, str(raw.get("public_key_fingerprint", ""))):
            return False
        payload = signed_payload(
            log_id=log_id, tree_size=int(raw["tree_size"]), root_sha256=root,
            witness_id=witness_id, independence_group=group, observed_at=observed_at,
            nonce=nonce, public_key_fingerprint=fingerprint,
        )
        signature = _decode_b64(str(raw.get("signature_b64", "")), expected_len=64)
        Ed25519PublicKey.from_public_bytes(_decode_b64(public_key_b64, expected_len=32)).verify(signature, _canonical(payload))
        claimed = str(raw.get("statement_sha256", ""))
        if not _SHA256.fullmatch(claimed):
            return False
        expected_statement = _sha({**payload, "signature_b64": str(raw["signature_b64"])})
        return hmac.compare_digest(expected_statement, claimed)
    except (InvalidSignature, TypeError, ValueError, KeyError):
        return False


def sign_statement_for_witness(*, private_key_b64: str, public_key_b64: str, log_id: str,
                               tree_size: int, root_sha256: str, witness_id: str,
                               independence_group: str, observed_at: str, nonce: str) -> SignedWitnessStatement:
    """Client/test helper. Production witnesses should sign outside the control plane."""
    fingerprint = public_key_fingerprint(public_key_b64)
    payload = signed_payload(
        log_id=str(log_id).strip(), tree_size=int(tree_size), root_sha256=str(root_sha256).lower().strip(),
        witness_id=str(witness_id).strip(), independence_group=str(independence_group).strip(),
        observed_at=str(observed_at), nonce=str(nonce).strip(), public_key_fingerprint=fingerprint,
    )
    if not payload["log_id"] or payload["tree_size"] < 0 or not _SHA256.fullmatch(payload["root_sha256"]):
        raise ValueError("invalid signed witness target")
    _parse_time(payload["observed_at"])
    if not payload["witness_id"] or not payload["independence_group"] or not payload["nonce"]:
        raise ValueError("witness id, independence group and nonce are required")
    private = Ed25519PrivateKey.from_private_bytes(_decode_b64(private_key_b64, expected_len=32))
    signature_b64 = base64.b64encode(private.sign(_canonical(payload))).decode("ascii")
    return SignedWitnessStatement(
        SIGNED_WITNESS_VERSION, payload["log_id"], payload["tree_size"], payload["root_sha256"],
        payload["witness_id"], payload["independence_group"], payload["observed_at"], payload["nonce"],
        fingerprint, signature_b64, _sha({**payload, "signature_b64": signature_b64}),
    )


class SignedTransparencyWitnessLedger:
    def __init__(self, root: str | Path, *, trusted_witnesses: Iterable[TrustedWitness] = (),
                 required_groups: int = 3, max_age_seconds: int = 3600) -> None:
        if required_groups < 1 or max_age_seconds < 1:
            raise ValueError("signed witness quorum and max age must be positive")
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "signed-witnesses.json"
        self._lease = FileLease(self.root / ".signed-witnesses.lock")
        self.required_groups = int(required_groups); self.max_age_seconds = int(max_age_seconds)
        self._trusted = {w.id: w for w in trusted_witnesses if w.enabled and str(getattr(w, "public_key_b64", "")).strip()}
        with self._lease.acquire():
            if not self.path.exists(): self._write([], [])
            else: self._load()

    @staticmethod
    def _checksum(statements: list[dict[str, Any]], incidents: list[dict[str, Any]]) -> str:
        return _sha({"version": SIGNED_WITNESS_VERSION, "statements": statements, "incidents": incidents})

    def _load(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        try: env = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc: raise SignedWitnessIntegrityError("signed witness ledger unreadable") from exc
        rows = env.get("statements"); incidents = env.get("incidents"); checksum = env.get("sha256")
        if env.get("version") != SIGNED_WITNESS_VERSION or not isinstance(rows, list) or not isinstance(incidents, list) or not isinstance(checksum, str):
            raise SignedWitnessIntegrityError("signed witness ledger malformed")
        if not hmac.compare_digest(checksum, self._checksum(rows, incidents)):
            raise SignedWitnessIntegrityError("signed witness ledger checksum mismatch")
        for raw in rows:
            witness = self._trusted.get(str(raw.get("witness_id", "")))
            if witness is None or not verify_signed_statement(raw, public_key_b64=witness.public_key_b64, expected_group=witness.independence_group):
                raise SignedWitnessIntegrityError("stored signed witness statement failed verification")
        return [dict(x) for x in rows], [dict(x) for x in incidents]

    def _write(self, rows: list[dict[str, Any]], incidents: list[dict[str, Any]]) -> None:
        env = {"version": SIGNED_WITNESS_VERSION, "statements": rows, "incidents": incidents,
               "sha256": self._checksum(rows, incidents)}
        temp = self.path.with_suffix(f".{os.getpid()}.tmp")
        try:
            with temp.open("wb") as handle:
                handle.write(_canonical(env)); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp, self.path)
        finally: temp.unlink(missing_ok=True)

    def observe(self, statement: SignedWitnessStatement | Mapping[str, Any]) -> SignedWitnessStatement:
        raw = asdict(statement) if isinstance(statement, SignedWitnessStatement) else dict(statement)
        witness_id = str(raw.get("witness_id", "")); witness = self._trusted.get(witness_id)
        if witness is None:
            raise SignedWitnessRejected("signed witness is not trusted/enabled or lacks a pinned public key")
        if not verify_signed_statement(raw, public_key_b64=witness.public_key_b64, expected_group=witness.independence_group):
            raise SignedWitnessRejected("signed witness statement verification failed")
        restored = SignedWitnessStatement(**raw)
        with self._lease.acquire():
            rows, incidents = self._load()
            same = [x for x in rows if x.get("log_id") == restored.log_id and int(x.get("tree_size", -1)) == restored.tree_size and x.get("witness_id") == witness_id]
            for prior in same:
                if prior.get("root_sha256") != restored.root_sha256:
                    incident = {"kind": "signed_witness_equivocation", "log_id": restored.log_id,
                                "tree_size": restored.tree_size, "witness_id": witness_id,
                                "independence_group": witness.independence_group,
                                "roots": sorted({str(prior.get("root_sha256")), restored.root_sha256}),
                                "observed_at": restored.observed_at}
                    if incident not in incidents: incidents.append(incident)
                    self._write(rows, incidents)
                    raise SignedWitnessRejected("signed trusted witness equivocated for the same tree size")
                return SignedWitnessStatement(**prior)
            rows.append(asdict(restored)); self._write(rows, incidents); return restored

    def _target(self, *, log_id: str, tree_size: int, root_sha256: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        with self._lease.acquire(): rows, incidents = self._load()
        return [x for x in rows if x.get("log_id") == log_id and int(x.get("tree_size", -1)) == tree_size and x.get("root_sha256") == root_sha256], incidents

    def quorum(self, *, log_id: str, tree_size: int, root_sha256: str, now: datetime | None = None) -> WitnessQuorum:
        current = now or datetime.now(UTC)
        if current.tzinfo is None: raise ValueError("signed quorum evaluation time must be timezone-aware")
        current = current.astimezone(UTC); target, incidents = self._target(log_id=log_id, tree_size=tree_size, root_sha256=root_sha256)
        fresh: list[dict[str, Any]] = []; stale = 0
        for raw in target:
            age = (current - _parse_time(str(raw["observed_at"]))).total_seconds()
            if 0 <= age <= self.max_age_seconds: fresh.append(raw)
            else: stale += 1
        groups = tuple(sorted({str(x["independence_group"]) for x in fresh})); ids = tuple(sorted({str(x["witness_id"]) for x in fresh}))
        frozen = any(x.get("kind") == "signed_witness_equivocation" and x.get("log_id") == log_id for x in incidents)
        reached = not frozen and len(groups) >= self.required_groups
        payload = {"log_id": log_id, "tree_size": tree_size, "root_sha256": root_sha256,
                   "trusted_receipts": len(target), "fresh_receipts": len(fresh), "stale_receipts": stale,
                   "independent_groups": len(groups), "required_groups": self.required_groups,
                   "max_age_seconds": self.max_age_seconds, "reached": reached, "frozen": frozen,
                   "witness_ids": ids, "groups": groups}
        return WitnessQuorum(**payload, attestation_sha256=_sha(payload))

    def evidence(self, *, log_id: str, tree_size: int, root_sha256: str, now: datetime | None = None) -> dict[str, Any]:
        quorum = self.quorum(log_id=log_id, tree_size=tree_size, root_sha256=root_sha256, now=now)
        target, _ = self._target(log_id=log_id, tree_size=tree_size, root_sha256=root_sha256)
        fresh_ids = set(quorum.witness_ids)
        statements = [x for x in target if x.get("witness_id") in fresh_ids]
        statements.sort(key=lambda x: str(x.get("witness_id", "")))
        return {"quorum": asdict(quorum), "statements": statements}

    def status(self) -> dict[str, Any]:
        with self._lease.acquire(): rows, incidents = self._load()
        equivocations = sum(x.get("kind") == "signed_witness_equivocation" for x in incidents)
        groups = {w.independence_group for w in self._trusted.values()}
        return {"version": SIGNED_WITNESS_VERSION, "trusted_signed_witnesses": len(self._trusted),
                "independence_groups": len(groups), "required_groups": self.required_groups,
                "max_age_seconds": self.max_age_seconds, "statements": len(rows),
                "equivocations": equivocations, "healthy": equivocations == 0,
                "cross_process_locking": True, "lock_backend": self._lease.backend,
                "sha256": self._checksum(rows, incidents)}
