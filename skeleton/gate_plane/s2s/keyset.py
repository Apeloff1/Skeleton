"""JWKS-style key-set documents for the s2s key ring (metadata only).

Pack F keys are symmetric (HS256), so - unlike an RSA/EC JWKS - the key set
**never** carries key material. It publishes, per kid, the lifecycle state,
the overlap window and a secret-free fingerprint, so verifier replicas can:

* learn which kids are valid right now (ACTIVE + RETIRING-in-overlap +
  pre-published PENDING) and when overlaps close;
* propagate revocations and shortened overlaps from the authority ring to
  their own ring with :func:`apply_keyset` (revoke / shorten only - a
  published document can never re-enable or extend a key);
* detect key drift (same kid, different fingerprint) and fail closed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from skeleton.gate_plane.s2s.keyring import KeyRing, KeyState, validate_kid
from skeleton.gate_plane.s2s.tokens import ALG

KEYSET_VERSION = 1
_ALLOWED_STATUS = {s.value for s in KeyState}
_KEY_FIELDS = {"kid", "kty", "alg", "use", "status", "fp", "nbf", "retire_at", "revoked_at"}


class KeySetError(ValueError):
    """Malformed or inconsistent key-set document."""


def export_keyset(ring: KeyRing, *, issuer: str = "", include_expired: bool = False) -> Dict[str, Any]:
    snap = ring.snapshot()
    keys: List[Dict[str, Any]] = []
    for row in snap["keys"]:  # type: ignore[index]
        status = row["state"]
        if status == KeyState.EXPIRED.value and not include_expired:
            continue
        keys.append({
            "kid": row["kid"],
            "kty": "oct",
            "alg": ALG,
            "use": "sig",
            "status": status,
            "fp": row["fingerprint"],
            "nbf": row["activated_at"],
            "retire_at": row["retire_at"],
            "revoked_at": row["revoked_at"],
        })
    doc: Dict[str, Any] = {"v": KEYSET_VERSION, "iss": issuer, "active_kid": snap["active_kid"], "keys": keys}
    doc["digest"] = keyset_digest(doc)
    return doc


def keyset_digest(doc: Mapping[str, Any]) -> str:
    body = {k: v for k, v in doc.items() if k != "digest"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


def validate_keyset(doc: Mapping[str, Any]) -> None:
    if not isinstance(doc, Mapping):
        raise KeySetError("key set must be an object")
    if doc.get("v") != KEYSET_VERSION:
        raise KeySetError(f"unsupported key set version {doc.get('v')!r}")
    keys = doc.get("keys")
    if not isinstance(keys, list):
        raise KeySetError("keys must be a list")
    seen = set()
    actives = 0
    for k in keys:
        if not isinstance(k, Mapping):
            raise KeySetError("key entries must be objects")
        extra = set(k) - _KEY_FIELDS
        if extra:
            raise KeySetError(f"unexpected key fields {sorted(extra)} (key material is never published)")
        try:
            validate_kid(k.get("kid"))  # type: ignore[arg-type]
        except ValueError as exc:
            raise KeySetError(str(exc)) from exc
        if k["kid"] in seen:
            raise KeySetError(f"duplicate kid {k['kid']!r}")
        seen.add(k["kid"])
        if k.get("kty") != "oct" or k.get("alg") != ALG or k.get("use") != "sig":
            raise KeySetError(f"{k['kid']}: kty/alg/use must be oct/{ALG}/sig")
        if k.get("status") not in _ALLOWED_STATUS:
            raise KeySetError(f"{k['kid']}: bad status {k.get('status')!r}")
        if k["status"] == KeyState.ACTIVE.value:
            actives += 1
    if actives > 1:
        raise KeySetError("more than one ACTIVE kid")
    if "digest" in doc and doc["digest"] != keyset_digest(doc):
        raise KeySetError("digest mismatch")


@dataclass
class KeySetSyncReport:
    revoked: List[str] = field(default_factory=list)
    shortened: List[str] = field(default_factory=list)
    unknown: List[str] = field(default_factory=list)
    drift: List[str] = field(default_factory=list)
    ignored: List[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.revoked or self.shortened)

    def as_dict(self) -> Dict[str, List[str]]:
        return {k: list(getattr(self, k)) for k in ("revoked", "shortened", "unknown", "drift", "ignored")}


def apply_keyset(ring: KeyRing, doc: Mapping[str, Any], *, revoke_on_drift: bool = True) -> KeySetSyncReport:
    """Narrow-only sync from an authority key set into a local ring."""
    validate_keyset(doc)
    report = KeySetSyncReport()
    for k in doc["keys"]:
        kid = k["kid"]
        if kid not in ring:
            report.unknown.append(kid)
            continue
        local = ring.get(kid)
        if local.fingerprint != k.get("fp"):
            report.drift.append(kid)
            if revoke_on_drift and local.state is not KeyState.REVOKED:
                ring.revoke(kid, reason="keyset_fingerprint_drift")
                report.revoked.append(kid)
            continue
        status = k["status"]
        if status == KeyState.REVOKED.value and local.state is not KeyState.REVOKED:
            ring.revoke(kid, reason="keyset_revoked")
            report.revoked.append(kid)
        elif (
            status == KeyState.RETIRING.value
            and local.state is KeyState.RETIRING
            and k.get("retire_at") is not None
            and local.retire_at is not None
            and float(k["retire_at"]) < local.retire_at
        ):
            ring.shorten_overlap(kid, float(k["retire_at"]))
            report.shortened.append(kid)
        else:
            report.ignored.append(kid)
    return report


def verifiable_kids(doc: Mapping[str, Any], now: float, *, accept_pending: bool = False) -> List[str]:
    validate_keyset(doc)
    out: List[str] = []
    for k in doc["keys"]:
        st = k["status"]
        if st == KeyState.ACTIVE.value:
            out.append(k["kid"])
        elif st == KeyState.RETIRING.value and k.get("retire_at") is not None and now < float(k["retire_at"]):
            out.append(k["kid"])
        elif st == KeyState.PENDING.value and accept_pending:
            out.append(k["kid"])
    return out


__all__ = [
    "KEYSET_VERSION",
    "KeySetError",
    "KeySetSyncReport",
    "apply_keyset",
    "export_keyset",
    "keyset_digest",
    "validate_keyset",
    "verifiable_kids",
]
