"""Attested diagnostics for portable deployment-proof verification.

The boolean verifier remains the authority. This module never upgrades a failed
proof: it performs conservative layer checks to explain *where* trust failed, then
requires the canonical verifier to succeed before returning a valid verdict.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hmac
from typing import Any, Mapping

from core.canonical_json import CanonicalJSONError, canonical_json_sha256
from core.deployment_authorization import plan_digest, restore_preflight_snapshot
from core.deployment_planner import verify_deployment_plan
from core.deployment_proof import (
    DEPLOYMENT_PROOF_VERSION,
    PortableDeploymentProof,
    _PROOF_KEYS,
    _authorization_event_schema,
    _is_sha,
    _proof_payload,
    _receipt_record_semantics,
    _record_hash,
    _release_record_semantics,
    _sha,
    _verify_chain_suffix,
    _verify_receipt_suffix,
    _verify_release_suffix,
    verify_portable_deployment_proof,
)

DIAGNOSTIC_VERSION = 1


@dataclass(frozen=True, slots=True)
class DeploymentProofVerdict:
    version: int
    valid: bool
    stage: str
    reason: str
    proof_sha256: str
    authorization_head_sha256: str
    release_channel_head_sha256: str
    receipt_head_sha256: str
    attestation_sha256: str


def _verdict(
    *,
    valid: bool,
    stage: str,
    reason: str,
    proof_sha256: str,
    authorization_head_sha256: str,
    release_channel_head_sha256: str,
    receipt_head_sha256: str,
) -> DeploymentProofVerdict:
    payload = {
        "version": DIAGNOSTIC_VERSION,
        "valid": valid,
        "stage": stage,
        "reason": reason,
        "proof_sha256": proof_sha256,
        "authorization_head_sha256": authorization_head_sha256,
        "release_channel_head_sha256": release_channel_head_sha256,
        "receipt_head_sha256": receipt_head_sha256,
    }
    return DeploymentProofVerdict(**payload, attestation_sha256=canonical_json_sha256(payload))


def verify_deployment_proof_verdict(verdict: DeploymentProofVerdict) -> bool:
    try:
        if not isinstance(verdict, DeploymentProofVerdict):
            return False
        if verdict.version != DIAGNOSTIC_VERSION or not isinstance(verdict.valid, bool):
            return False
        if not verdict.stage or not verdict.reason:
            return False
        if not all(_is_sha(value) for value in (
            verdict.proof_sha256,
            verdict.authorization_head_sha256,
            verdict.release_channel_head_sha256,
            verdict.receipt_head_sha256,
            verdict.attestation_sha256,
        )):
            return False
        payload = {key: value for key, value in asdict(verdict).items() if key != "attestation_sha256"}
        return hmac.compare_digest(canonical_json_sha256(payload), verdict.attestation_sha256)
    except (CanonicalJSONError, TypeError, ValueError):
        return False


def diagnose_portable_deployment_proof(
    proof: PortableDeploymentProof | Mapping[str, Any],
    *,
    expected_authorization_head_sha256: str,
    expected_release_channel_head_sha256: str,
    expected_receipt_head_sha256: str,
) -> DeploymentProofVerdict:
    """Return the first conservative failure stage plus an attested verdict."""
    pins = (
        expected_authorization_head_sha256,
        expected_release_channel_head_sha256,
        expected_receipt_head_sha256,
    )
    fallback_proof_sha = "0" * 64

    def fail(stage: str, reason: str, proof_sha: str = fallback_proof_sha) -> DeploymentProofVerdict:
        safe_pins = tuple(value if _is_sha(value) else "0" * 64 for value in pins)
        return _verdict(
            valid=False,
            stage=stage,
            reason=reason,
            proof_sha256=proof_sha if _is_sha(proof_sha) else fallback_proof_sha,
            authorization_head_sha256=safe_pins[0],
            release_channel_head_sha256=safe_pins[1],
            receipt_head_sha256=safe_pins[2],
        )

    try:
        raw = asdict(proof) if isinstance(proof, PortableDeploymentProof) else dict(proof)
    except (TypeError, ValueError):
        return fail("packet", "proof is not a mapping or PortableDeploymentProof")

    proof_sha = raw.get("proof_sha256") if _is_sha(raw.get("proof_sha256")) else fallback_proof_sha
    if set(raw) != _PROOF_KEYS or raw.get("version") != DEPLOYMENT_PROOF_VERSION:
        return fail("packet", "proof schema or version mismatch", proof_sha)
    if not all(_is_sha(raw.get(name)) for name in (
        "plan_sha256", "pre_system_root_sha256", "post_system_root_sha256",
        "authorization_head_sha256", "release_channel_head_sha256", "receipt_head_sha256",
        "proof_sha256",
    )):
        return fail("packet", "proof contains malformed digest fields", proof_sha)
    try:
        if not hmac.compare_digest(_sha(_proof_payload(raw)), raw["proof_sha256"]):
            return fail("packet", "proof packet hash mismatch", proof_sha)
    except (CanonicalJSONError, TypeError, ValueError):
        return fail("packet", "proof packet is not canonical JSON", proof_sha)

    if not all(_is_sha(pin) for pin in pins):
        return fail("external_pins", "one or more externally supplied heads are malformed", proof_sha)
    if raw["authorization_head_sha256"] != pins[0]:
        return fail("external_pins", "authorization ledger head does not match external pin", proof_sha)
    if raw["release_channel_head_sha256"] != pins[1]:
        return fail("external_pins", "release channel head does not match external pin", proof_sha)
    if raw["receipt_head_sha256"] != pins[2]:
        return fail("external_pins", "receipt ledger head does not match external pin", proof_sha)

    plan = raw.get("plan")
    if not isinstance(plan, dict) or not verify_deployment_plan(plan):
        return fail("plan", "deployment plan failed semantic verification", proof_sha)
    try:
        if not hmac.compare_digest(plan_digest(plan), raw["plan_sha256"]):
            return fail("plan", "deployment plan digest mismatch", proof_sha)
    except (TypeError, ValueError):
        return fail("plan", "deployment plan is not portable canonical evidence", proof_sha)

    preflight_raw = raw.get("preflight")
    if not isinstance(preflight_raw, dict):
        return fail("preflight", "portable preflight snapshot missing", proof_sha)
    try:
        preflight = restore_preflight_snapshot(preflight_raw)
    except ValueError:
        return fail("preflight", "preflight snapshot failed self-verification", proof_sha)
    if not preflight.allowed or not preflight.stable:
        return fail("preflight", "preflight is not stable and authorizing", proof_sha)
    if preflight.root_before_sha256 != raw["pre_system_root_sha256"] or preflight.root_after_sha256 != raw["pre_system_root_sha256"]:
        return fail("preflight", "preflight roots diverge from deployment pre-root", proof_sha)

    auth_suffix_raw = raw.get("authorization_suffix")
    if not isinstance(auth_suffix_raw, (list, tuple)):
        return fail("authorization", "authorization suffix is not an array", proof_sha)
    try:
        auth_suffix = tuple(dict(row) for row in auth_suffix_raw)
    except (TypeError, ValueError):
        return fail("authorization", "authorization suffix contains non-object rows", proof_sha)
    if not auth_suffix or not all(_authorization_event_schema(row) for row in auth_suffix):
        return fail("authorization", "authorization suffix schema verification failed", proof_sha)
    if not _verify_chain_suffix(auth_suffix, expected_head=pins[0]):
        return fail("authorization", "authorization suffix ancestry/hash verification failed", proof_sha)

    release = raw.get("release")
    if not isinstance(release, dict) or not _release_record_semantics(release):
        return fail("release", "release record semantic verification failed", proof_sha)
    if not hmac.compare_digest(_record_hash(release), release["sha256"]):
        return fail("release", "release record hash mismatch", proof_sha)
    release_suffix_raw = raw.get("release_suffix")
    if not isinstance(release_suffix_raw, (list, tuple)):
        return fail("release", "release suffix is not an array", proof_sha)
    try:
        release_suffix = tuple(dict(row) for row in release_suffix_raw)
    except (TypeError, ValueError):
        return fail("release", "release suffix contains non-object rows", proof_sha)
    if not release_suffix or release_suffix[0].get("sha256") != release.get("sha256"):
        return fail("release", "release record is not the start of its proof suffix", proof_sha)
    if not _verify_release_suffix(release_suffix, expected_head=pins[1]):
        return fail("release", "release suffix ancestry/hash verification failed", proof_sha)

    receipt = raw.get("transition_receipt")
    if not isinstance(receipt, dict) or not _receipt_record_semantics(receipt):
        return fail("receipt", "transition receipt semantic verification failed", proof_sha)
    if not hmac.compare_digest(_record_hash(receipt), receipt["sha256"]):
        return fail("receipt", "transition receipt hash mismatch", proof_sha)
    receipt_suffix_raw = raw.get("receipt_suffix")
    if not isinstance(receipt_suffix_raw, (list, tuple)):
        return fail("receipt", "receipt suffix is not an array", proof_sha)
    try:
        receipt_suffix = tuple(dict(row) for row in receipt_suffix_raw)
    except (TypeError, ValueError):
        return fail("receipt", "receipt suffix contains non-object rows", proof_sha)
    if not receipt_suffix or receipt_suffix[0].get("sha256") != receipt.get("sha256"):
        return fail("receipt", "transition receipt is not the start of its proof suffix", proof_sha)
    if not _verify_receipt_suffix(receipt_suffix, expected_head=pins[2]):
        return fail("receipt", "receipt suffix ancestry/hash verification failed", proof_sha)

    if not verify_portable_deployment_proof(
        raw,
        expected_authorization_head_sha256=pins[0],
        expected_release_channel_head_sha256=pins[1],
        expected_receipt_head_sha256=pins[2],
    ):
        return fail("cross_binding", "all layers verify independently but cross-object binding failed", proof_sha)

    return _verdict(
        valid=True,
        stage="verified",
        reason="packet, external pins, plan, preflight, authorization, release, receipt, and cross-binding verified",
        proof_sha256=proof_sha,
        authorization_head_sha256=pins[0],
        release_channel_head_sha256=pins[1],
        receipt_head_sha256=pins[2],
    )
