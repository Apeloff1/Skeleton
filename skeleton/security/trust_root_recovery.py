"""Fail-closed trust-root compromise recovery (G084).

A root signing key that may be compromised cannot appoint its replacement,
erase a precommitted successor, or admit artifacts after revocation. Re-signing
is allowed only for admissions recorded at or before the successor's signed
trust cut. Signature verification is delegated to a deployment verifier; this
module does not implement a cryptographic primitive and does not grant
enterprise verification.

Revocation is one-way. Rolling back a successor requires a later precommitted
successor, not an un-revoke. The ledger is single-threaded and bounded.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol


class TrustRootRecoveryError(RuntimeError):
    """Trust-root succession, revocation, or re-sign is unsafe."""


_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+-]{0,255}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_MAX_TICK = 2_147_483_647
_MAX_SIGNATURE = 8192
_MAX_ADMISSIONS = 65536
_MAX_REVOCATIONS = 64


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or _TOKEN.fullmatch(value) is None:
        raise TrustRootRecoveryError(f"{name} must be a canonical token")
    return value


def _digest(name: str, value: object) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise TrustRootRecoveryError(f"{name} must be lowercase sha256")
    return value


def _tick(name: str, value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= _MAX_TICK
    ):
        raise TrustRootRecoveryError(f"{name} must be a bounded nonnegative tick")
    return value


def _signature(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > _MAX_SIGNATURE:
        raise TrustRootRecoveryError("signature must be bounded non-empty text")
    if any(ord(char) < 32 for char in value):
        raise TrustRootRecoveryError("signature contains control characters")
    return value


def _canonical(document: dict[str, object]) -> bytes:
    try:
        raw = json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise TrustRootRecoveryError("trust payload must be canonical JSON") from exc
    return raw.encode("utf-8")


class RootSignatureVerifier(Protocol):
    """Deployment verifier bound to one root key. verify() must return True."""

    @property
    def key_id(self) -> str: ...

    def verify(self, payload: bytes, signature: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class RootIdentity:
    root_id: str
    key_id: str
    algorithm: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "root_id", _token("root_id", self.root_id))
        object.__setattr__(self, "key_id", _token("key_id", self.key_id))
        object.__setattr__(self, "algorithm", _token("algorithm", self.algorithm))


@dataclass(frozen=True, slots=True)
class SuccessorAppointment:
    predecessor: RootIdentity
    successor: RootIdentity
    appointed_tick: int
    signature: str


@dataclass(frozen=True, slots=True)
class RootRevocation:
    root_id: str
    key_id: str
    revoked_tick: int
    trusted_through_tick: int
    successor_root_id: str
    successor_key_id: str


@dataclass(frozen=True, slots=True)
class ArtifactAdmission:
    artifact_id: str
    artifact_digest: str
    root_id: str
    key_id: str
    algorithm: str
    admitted_tick: int


@dataclass(frozen=True, slots=True)
class ResignReceipt:
    artifact_id: str
    artifact_digest: str
    predecessor_root_id: str
    predecessor_key_id: str
    successor_root_id: str
    successor_key_id: str
    trusted_through_tick: int
    resigned_tick: int


def appointment_payload(
    predecessor: RootIdentity,
    successor: RootIdentity,
    appointed_tick: int,
) -> bytes:
    """Bytes the current root must sign to precommit exactly one successor."""
    if not isinstance(predecessor, RootIdentity) or not isinstance(
        successor, RootIdentity
    ):
        raise TypeError("appointment identities must be RootIdentity")
    return _canonical(
        {
            "algorithm": predecessor.algorithm,
            "appointed_tick": _tick("appointed_tick", appointed_tick),
            "kind": "successor_appointment",
            "predecessor_key_id": predecessor.key_id,
            "predecessor_root_id": predecessor.root_id,
            "successor_algorithm": successor.algorithm,
            "successor_key_id": successor.key_id,
            "successor_root_id": successor.root_id,
        }
    )


def revocation_payload(
    predecessor: RootIdentity,
    successor: RootIdentity,
    revoked_tick: int,
    trusted_through_tick: int,
) -> bytes:
    """Bytes the successor must sign. The compromised root cannot authorize this."""
    if not isinstance(predecessor, RootIdentity) or not isinstance(
        successor, RootIdentity
    ):
        raise TypeError("revocation identities must be RootIdentity")
    return _canonical(
        {
            "kind": "root_revocation",
            "predecessor_key_id": predecessor.key_id,
            "predecessor_root_id": predecessor.root_id,
            "revoked_tick": _tick("revoked_tick", revoked_tick),
            "successor_key_id": successor.key_id,
            "successor_root_id": successor.root_id,
            "trusted_through_tick": _tick("trusted_through_tick", trusted_through_tick),
        }
    )


def admission_payload(
    root: RootIdentity,
    artifact_id: str,
    artifact_digest: str,
    admitted_tick: int,
) -> bytes:
    if not isinstance(root, RootIdentity):
        raise TypeError("admission root must be RootIdentity")
    return _canonical(
        {
            "admitted_tick": _tick("admitted_tick", admitted_tick),
            "algorithm": root.algorithm,
            "artifact_digest": _digest("artifact_digest", artifact_digest),
            "artifact_id": _token("artifact_id", artifact_id),
            "key_id": root.key_id,
            "kind": "artifact_admission",
            "root_id": root.root_id,
        }
    )


def resign_payload(
    predecessor: RootIdentity,
    successor: RootIdentity,
    artifact_id: str,
    artifact_digest: str,
    resigned_tick: int,
    trusted_through_tick: int,
) -> bytes:
    if not isinstance(predecessor, RootIdentity) or not isinstance(
        successor, RootIdentity
    ):
        raise TypeError("re-sign identities must be RootIdentity")
    return _canonical(
        {
            "artifact_digest": _digest("artifact_digest", artifact_digest),
            "artifact_id": _token("artifact_id", artifact_id),
            "kind": "artifact_resign",
            "predecessor_algorithm": predecessor.algorithm,
            "predecessor_key_id": predecessor.key_id,
            "predecessor_root_id": predecessor.root_id,
            "resigned_tick": _tick("resigned_tick", resigned_tick),
            "successor_algorithm": successor.algorithm,
            "successor_key_id": successor.key_id,
            "successor_root_id": successor.root_id,
            "trusted_through_tick": _tick("trusted_through_tick", trusted_through_tick),
        }
    )


def _verify(
    verifier: RootSignatureVerifier,
    expected_key_id: str,
    payload: bytes,
    signature: str,
) -> str:
    signature = _signature(signature)
    verify = getattr(verifier, "verify", None)
    if not callable(verify):
        raise TypeError("verifier must provide key_id and verify")
    if _token("verifier.key_id", getattr(verifier, "key_id", None)) != expected_key_id:
        raise TrustRootRecoveryError("verifier key does not match authority")
    try:
        accepted = verify(payload, signature)
    except TrustRootRecoveryError:
        raise
    except Exception as exc:
        raise TrustRootRecoveryError("signature verifier failed") from exc
    if accepted is not True:
        raise TrustRootRecoveryError("signature rejected")
    return signature


class TrustRootLedger:
    """One genesis root, one immutable successor appointment, then revoke and re-sign."""

    def __init__(self) -> None:
        self._current: RootIdentity | None = None
        self._appointment: SuccessorAppointment | None = None
        self._revocations: dict[str, RootRevocation] = {}
        self._revoked_keys: dict[str, int] = {}
        self._admissions: dict[tuple[str, str, str], ArtifactAdmission] = {}
        self._resigns: dict[tuple[str, str, str], ResignReceipt] = {}
        self._high_tick: int | None = None
        self._known_keys: set[str] = set()

    def current(self) -> RootIdentity:
        if self._current is None:
            raise TrustRootRecoveryError("trust root is not installed")
        return self._current

    def appointment(self) -> SuccessorAppointment | None:
        return self._appointment

    def revocation(self, root_id: str) -> RootRevocation | None:
        return self._revocations.get(_token("root_id", root_id))

    def is_revoked_key(self, key_id: str) -> bool:
        return _token("key_id", key_id) in self._revoked_keys

    def admission(
        self,
        artifact_id: str,
        artifact_digest: str,
        root_id: str,
    ) -> ArtifactAdmission | None:
        key = (
            _token("artifact_id", artifact_id),
            _digest("artifact_digest", artifact_digest),
            _token("root_id", root_id),
        )
        return self._admissions.get(key)

    def _reserve(self, name: str, tick: object) -> int:
        value = _tick(name, tick)
        if self._high_tick is not None and value <= self._high_tick:
            raise TrustRootRecoveryError("tick must move forward")
        return value

    def install_genesis(self, root: RootIdentity, *, tick: int) -> RootIdentity:
        if not isinstance(root, RootIdentity):
            raise TypeError("genesis root must be RootIdentity")
        if self._current is not None:
            raise TrustRootRecoveryError("genesis root is immutable")
        installed_tick = self._reserve("tick", tick)
        self._current = root
        self._known_keys.add(root.key_id)
        self._high_tick = installed_tick
        return root

    def precommit_successor(
        self,
        successor: RootIdentity,
        signature: str,
        verifier: RootSignatureVerifier,
        *,
        tick: int,
    ) -> SuccessorAppointment:
        if not isinstance(successor, RootIdentity):
            raise TypeError("successor must be RootIdentity")
        current = self.current()
        if self._appointment is not None:
            raise TrustRootRecoveryError("successor appointment is immutable")
        if successor.root_id == current.root_id or successor.key_id == current.key_id:
            raise TrustRootRecoveryError("successor must be a distinct root")
        if (
            successor.key_id in self._known_keys
            or successor.root_id in self._revocations
        ):
            raise TrustRootRecoveryError("successor identity is already bound")
        appointed_tick = self._reserve("tick", tick)
        payload = appointment_payload(current, successor, appointed_tick)
        signed = _verify(verifier, current.key_id, payload, signature)
        self._appointment = SuccessorAppointment(
            current, successor, appointed_tick, signed
        )
        self._known_keys.add(successor.key_id)
        self._high_tick = appointed_tick
        return self._appointment

    def revoke_and_reroot(
        self,
        signature: str,
        verifier: RootSignatureVerifier,
        *,
        tick: int,
        trusted_through_tick: int,
    ) -> RootRevocation:
        appointment = self._appointment
        if appointment is None:
            raise TrustRootRecoveryError("revocation requires a precommitted successor")
        predecessor = appointment.predecessor
        successor = appointment.successor
        if self.current() != predecessor:
            raise TrustRootRecoveryError(
                "only the appointed predecessor can be revoked"
            )
        if len(self._revocations) >= _MAX_REVOCATIONS:
            raise TrustRootRecoveryError("revocation ledger is full")
        trusted = _tick("trusted_through_tick", trusted_through_tick)
        revoked_tick = self._reserve("tick", tick)
        if trusted >= revoked_tick:
            raise TrustRootRecoveryError("trust cut must precede revocation")
        payload = revocation_payload(predecessor, successor, revoked_tick, trusted)
        _verify(verifier, successor.key_id, payload, signature)
        record = RootRevocation(
            root_id=predecessor.root_id,
            key_id=predecessor.key_id,
            revoked_tick=revoked_tick,
            trusted_through_tick=trusted,
            successor_root_id=successor.root_id,
            successor_key_id=successor.key_id,
        )
        self._revocations[predecessor.root_id] = record
        self._revoked_keys[predecessor.key_id] = revoked_tick
        self._current = successor
        self._appointment = None
        self._high_tick = revoked_tick
        return record

    def admit(
        self,
        artifact_id: str,
        artifact_digest: str,
        signature: str,
        verifier: RootSignatureVerifier,
        *,
        tick: int,
    ) -> ArtifactAdmission:
        current = self.current()
        if current.key_id in self._revoked_keys:
            raise TrustRootRecoveryError("revoked root cannot admit artifacts")
        if len(self._admissions) >= _MAX_ADMISSIONS:
            raise TrustRootRecoveryError("admission ledger is full")
        admitted_tick = self._reserve("tick", tick)
        payload = admission_payload(
            current, artifact_id, artifact_digest, admitted_tick
        )
        _verify(verifier, current.key_id, payload, signature)
        identity = (
            _token("artifact_id", artifact_id),
            _digest("artifact_digest", artifact_digest),
            current.root_id,
        )
        if identity in self._admissions:
            raise TrustRootRecoveryError("duplicate artifact admission")
        record = ArtifactAdmission(
            artifact_id=identity[0],
            artifact_digest=identity[1],
            root_id=current.root_id,
            key_id=current.key_id,
            algorithm=current.algorithm,
            admitted_tick=admitted_tick,
        )
        self._admissions[identity] = record
        self._high_tick = admitted_tick
        return record

    def resign(
        self,
        artifact_id: str,
        artifact_digest: str,
        signature: str,
        verifier: RootSignatureVerifier,
        *,
        tick: int,
    ) -> ResignReceipt:
        current = self.current()
        artifact = _token("artifact_id", artifact_id)
        digest = _digest("artifact_digest", artifact_digest)
        existing = self._resigns.get((artifact, digest, current.root_id))
        if existing is not None:
            return existing
        if len(self._admissions) >= _MAX_ADMISSIONS:
            raise TrustRootRecoveryError("admission ledger is full")
        prior = self._prior_trusted_admission(artifact, digest)
        revocation = self._revocations[prior.root_id]
        predecessor = RootIdentity(prior.root_id, prior.key_id, prior.algorithm)
        resigned_tick = self._reserve("tick", tick)
        payload = resign_payload(
            predecessor,
            current,
            artifact,
            digest,
            resigned_tick,
            revocation.trusted_through_tick,
        )
        _verify(verifier, current.key_id, payload, signature)
        receipt = ResignReceipt(
            artifact_id=artifact,
            artifact_digest=digest,
            predecessor_root_id=prior.root_id,
            predecessor_key_id=prior.key_id,
            successor_root_id=current.root_id,
            successor_key_id=current.key_id,
            trusted_through_tick=revocation.trusted_through_tick,
            resigned_tick=resigned_tick,
        )
        self._resigns[(artifact, digest, current.root_id)] = receipt
        self._admissions[(artifact, digest, current.root_id)] = ArtifactAdmission(
            artifact_id=artifact,
            artifact_digest=digest,
            root_id=current.root_id,
            key_id=current.key_id,
            algorithm=current.algorithm,
            admitted_tick=resigned_tick,
        )
        self._high_tick = resigned_tick
        return receipt

    def _prior_trusted_admission(
        self, artifact_id: str, artifact_digest: str
    ) -> ArtifactAdmission:
        eligible: list[ArtifactAdmission] = []
        for (item_id, digest, _root_id), record in self._admissions.items():
            if item_id != artifact_id or digest != artifact_digest:
                continue
            if record.key_id not in self._revoked_keys:
                continue
            revocation = self._revocations.get(record.root_id)
            if revocation is None:
                continue
            if (
                record.admitted_tick
                <= revocation.trusted_through_tick
                < revocation.revoked_tick
            ):
                eligible.append(record)
        if len(eligible) != 1:
            raise TrustRootRecoveryError(
                "re-sign requires one pre-cut admission from a revoked root"
            )
        return eligible[0]


__all__ = [
    "ArtifactAdmission",
    "ResignReceipt",
    "RootIdentity",
    "RootRevocation",
    "RootSignatureVerifier",
    "SuccessorAppointment",
    "TrustRootLedger",
    "TrustRootRecoveryError",
    "admission_payload",
    "appointment_payload",
    "resign_payload",
    "revocation_payload",
]
