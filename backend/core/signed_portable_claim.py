"""Offline-verifiable claim envelope anchored by signed transparency finality.

The envelope deliberately separates *proof material* from *trust policy*. Witness
keys, independence groups, quorum size, and freshness bounds are supplied by the
verifier from an external trust store. A producer cannot self-declare its own
witnesses authoritative by embedding keys in the packet.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import hmac
import json
from typing import Any, Mapping

from core.portable_claim_proof import (
    PortableClaimProof,
    build_portable_claim_proof,
    verify_portable_claim_proof,
)
from core.signed_finality_evidence import (
    build_signed_finality_evidence,
    verify_signed_finality_evidence,
)

SIGNED_PORTABLE_VERSION = 1


@dataclass(frozen=True, slots=True)
class SignedPortableClaimEnvelope:
    version: int
    claim_packet: dict[str, Any]
    signed_finality_evidence: dict[str, Any]
    envelope_sha256: str


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _payload(*, claim_packet: Mapping[str, Any], signed_finality_evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "version": SIGNED_PORTABLE_VERSION,
        "claim_packet": dict(claim_packet),
        "signed_finality_evidence": dict(signed_finality_evidence),
    }


def build_signed_portable_claim_envelope(
    engine,
    claim: str,
    *,
    trust_runtime,
    generated_at: str | None = None,
    max_age_seconds: int = 900,
) -> SignedPortableClaimEnvelope:
    """Build the strongest portable claim packet supported by the runtime.

    The current transparency head must already have signed quorum finality. Building
    a packet never weakens policy or auto-finalizes a provisional head.
    """
    if trust_runtime.policy.signed_finality_required is not True:
        raise ValueError("signed portable envelope requires signed-finality policy")

    packet = build_portable_claim_proof(
        engine,
        claim,
        transparency=trust_runtime.transparency,
        finality=trust_runtime.finality,
        generated_at=generated_at,
        max_age_seconds=max_age_seconds,
    )
    if packet.finality_anchor is None:
        raise ValueError("current transparency head is not signed-finalized")

    evidence = build_signed_finality_evidence(trust_runtime)
    if evidence is None:
        raise ValueError("signed finality evidence unavailable")

    packet_finality = str(packet.finality_anchor.get("sha256") or "")
    evidence_finality = str(evidence.get("finality", {}).get("sha256") or "")
    if not packet_finality or not hmac.compare_digest(packet_finality, evidence_finality):
        raise ValueError("claim and signed-witness finality anchors diverged")

    payload = _payload(claim_packet=asdict(packet), signed_finality_evidence=evidence)
    return SignedPortableClaimEnvelope(**payload, envelope_sha256=_sha(payload))


def verify_signed_portable_claim_envelope(
    envelope: SignedPortableClaimEnvelope | Mapping[str, Any],
    *,
    trusted_witnesses: Mapping[str, Mapping[str, str]],
    required_groups: int,
    max_age_seconds: int,
    now=None,
    expected_claim: str | None = None,
    expected_authority_root: str | None = None,
    expected_transparency_root: str | None = None,
    expected_finality_sha256: str | None = None,
) -> bool:
    """Verify a claim envelope without consulting the producing runtime.

    External callers should pin at least the witness registry and quorum policy;
    high-assurance callers can additionally pin claim/root/finality identities.
    """
    try:
        raw = asdict(envelope) if isinstance(envelope, SignedPortableClaimEnvelope) else dict(envelope)
        if int(raw.get("version", 0)) != SIGNED_PORTABLE_VERSION:
            return False
        if required_groups < 1 or max_age_seconds < 1:
            return False

        packet_raw = raw.get("claim_packet")
        evidence = raw.get("signed_finality_evidence")
        if not isinstance(packet_raw, dict) or not isinstance(evidence, dict):
            return False

        packet = PortableClaimProof(**packet_raw)
        if expected_claim is not None and packet.claim != expected_claim:
            return False

        finality = evidence.get("finality")
        if not isinstance(finality, Mapping):
            return False
        finality_sha = str(finality.get("sha256") or "")
        if not finality_sha:
            return False
        if expected_finality_sha256 is not None and not hmac.compare_digest(finality_sha, str(expected_finality_sha256)):
            return False

        if not verify_portable_claim_proof(
            packet,
            now=now,
            expected_authority_root=expected_authority_root,
            expected_transparency_root=expected_transparency_root,
            expected_finality_sha256=finality_sha,
            require_transparency=True,
            require_finality=True,
        ):
            return False

        if not verify_signed_finality_evidence(
            evidence,
            trusted_witnesses=trusted_witnesses,
            required_groups=required_groups,
            max_age_seconds=max_age_seconds,
            expected_finality_sha256=finality_sha,
        ):
            return False

        if packet.finality_anchor is None:
            return False
        if not hmac.compare_digest(str(packet.finality_anchor.get("sha256") or ""), finality_sha):
            return False

        payload = _payload(claim_packet=packet_raw, signed_finality_evidence=evidence)
        return hmac.compare_digest(_sha(payload), str(raw.get("envelope_sha256") or ""))
    except (KeyError, TypeError, ValueError):
        return False


def signed_portable_claim_envelope_dict(engine, claim: str, *, trust_runtime,
                                        max_age_seconds: int = 900) -> dict[str, Any]:
    envelope = build_signed_portable_claim_envelope(
        engine,
        claim,
        trust_runtime=trust_runtime,
        max_age_seconds=max_age_seconds,
    )
    result = asdict(envelope)
    result["trust_level"] = "signed_finalized"
    result["verification_note"] = (
        "Offline verification requires an externally pinned Ed25519 witness registry, "
        "independence groups, quorum threshold, and freshness policy."
    )
    return result
