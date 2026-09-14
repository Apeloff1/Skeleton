"""Portable verification of Ed25519-backed transparency finality.

The finality ledger alone proves that the server consistently recorded a quorum
digest. This bundle proves what that digest came from. Verification requires an
external trust registry (witness id -> pinned public key + independence group) and
an external quorum threshold; packet-carried trust metadata never grants authority.

All bundle hashing and verification uses strict canonical JSON and exact JSON types.
No ``str()``/``int()`` coercion participates in a trust decision.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import hmac
import re
from typing import Any, Mapping

from core.canonical_json import CanonicalJSONError, canonical_json_clone, canonical_json_sha256
from core.signed_transparency_witness import verify_signed_statement
from core.transparency_finality_proof import verify_finality_record

SIGNED_FINALITY_EVIDENCE_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_BUNDLE_KEYS = {"version", "finality", "witness_evidence", "bundle_sha256"}
_EVIDENCE_KEYS = {"quorum", "statements"}
_TRUST_KEYS = {"public_key_b64", "independence_group"}
_FINALITY_KEYS = {
    "version",
    "sequence",
    "log_id",
    "tree_size",
    "root_sha256",
    "witness_quorum_sha256",
    "witness_groups",
    "finalized_at",
    "previous_sha256",
    "sha256",
}
_QUORUM_KEYS = {
    "log_id",
    "tree_size",
    "root_sha256",
    "trusted_receipts",
    "fresh_receipts",
    "stale_receipts",
    "independent_groups",
    "required_groups",
    "max_age_seconds",
    "reached",
    "frozen",
    "witness_ids",
    "groups",
    "attestation_sha256",
}


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256.fullmatch(value))


def _canonical_text(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("value must be a canonical non-empty string")
    return value


def _positive_int(value: Any, *, maximum: int | None = None) -> int:
    if type(value) is not int or value < 1 or (maximum is not None and value > maximum):
        raise ValueError("value must be a positive integer in range")
    return value


def _nonnegative_int(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("value must be a non-negative integer")
    return value


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("timestamp must be canonical non-empty text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp is malformed") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _validate_finality_shape(finality: Any) -> Mapping[str, Any]:
    if not isinstance(finality, Mapping) or set(finality) != _FINALITY_KEYS:
        raise ValueError("signed finality record schema mismatch")
    if type(finality.get("version")) is not int:
        raise ValueError("signed finality version type mismatch")
    _positive_int(finality.get("sequence"))
    _positive_int(finality.get("tree_size"))
    _canonical_text(finality.get("log_id"))
    if not _is_sha(finality.get("root_sha256")) or not _is_sha(finality.get("witness_quorum_sha256")):
        raise ValueError("signed finality digest malformed")
    if not _is_sha(finality.get("sha256")):
        raise ValueError("signed finality record digest malformed")
    previous = finality.get("previous_sha256")
    if not isinstance(previous, str) or (previous and not _is_sha(previous)):
        raise ValueError("signed finality previous digest malformed")
    groups = finality.get("witness_groups")
    if not isinstance(groups, (list, tuple)) or not groups:
        raise ValueError("signed finality witness groups malformed")
    normalized_groups = []
    for group in groups:
        normalized_groups.append(_canonical_text(group))
    if tuple(normalized_groups) != tuple(sorted(set(normalized_groups))):
        raise ValueError("signed finality witness groups must be unique and sorted")
    _parse_time(finality.get("finalized_at"))
    return finality


def _validate_quorum_shape(quorum: Any) -> Mapping[str, Any]:
    if not isinstance(quorum, Mapping) or set(quorum) != _QUORUM_KEYS:
        raise ValueError("signed finality quorum schema mismatch")
    _canonical_text(quorum.get("log_id"))
    _nonnegative_int(quorum.get("tree_size"))
    if not _is_sha(quorum.get("root_sha256")) or not _is_sha(quorum.get("attestation_sha256")):
        raise ValueError("signed finality quorum digest malformed")
    for field in (
        "trusted_receipts",
        "fresh_receipts",
        "stale_receipts",
        "independent_groups",
        "required_groups",
        "max_age_seconds",
    ):
        _nonnegative_int(quorum.get(field))
    if type(quorum.get("reached")) is not bool or type(quorum.get("frozen")) is not bool:
        raise ValueError("signed finality quorum boolean type mismatch")
    for field in ("witness_ids", "groups"):
        values = quorum.get(field)
        if not isinstance(values, (list, tuple)):
            raise ValueError(f"signed finality quorum {field} malformed")
        normalized = tuple(_canonical_text(value) for value in values)
        if normalized != tuple(sorted(set(normalized))):
            raise ValueError(f"signed finality quorum {field} must be unique and sorted")
    return quorum


def _normalize_trust_registry(
    trusted_witnesses: Mapping[str, Mapping[str, str]],
) -> dict[str, dict[str, str]]:
    if not isinstance(trusted_witnesses, Mapping):
        raise ValueError("trusted witness registry must be an object")
    normalized: dict[str, dict[str, str]] = {}
    for witness_id, raw in trusted_witnesses.items():
        witness_id = _canonical_text(witness_id)
        if not isinstance(raw, Mapping) or set(raw) != _TRUST_KEYS:
            raise ValueError("trusted witness registry entry schema mismatch")
        public_key = _canonical_text(raw.get("public_key_b64"))
        group = _canonical_text(raw.get("independence_group"))
        normalized[witness_id] = {
            "public_key_b64": public_key,
            "independence_group": group,
        }
    return normalized


def build_signed_finality_evidence(runtime) -> dict[str, Any] | None:
    latest = runtime.finality.latest()
    if latest is None:
        return None
    when = _parse_time(latest.finalized_at)
    quorum = runtime.signed_witnesses.quorum(
        log_id=latest.log_id,
        tree_size=latest.tree_size,
        root_sha256=latest.root_sha256,
        now=when,
    )
    # Export the complete target set, not only fresh statements, so an offline verifier
    # can reproduce trusted/fresh/stale counts and the exact quorum attestation.
    statements, _ = runtime.signed_witnesses._target(
        log_id=latest.log_id,
        tree_size=latest.tree_size,
        root_sha256=latest.root_sha256,
    )
    statements = sorted(
        (canonical_json_clone(dict(row)) for row in statements),
        key=lambda row: row["witness_id"],
    )
    evidence = canonical_json_clone({"quorum": asdict(quorum), "statements": statements})
    payload = canonical_json_clone(
        {
            "version": SIGNED_FINALITY_EVIDENCE_VERSION,
            "finality": asdict(latest),
            "witness_evidence": evidence,
        }
    )
    payload["bundle_sha256"] = canonical_json_sha256(payload)
    return payload


def verify_signed_finality_evidence(
    bundle: Mapping[str, Any],
    *,
    trusted_witnesses: Mapping[str, Mapping[str, str]],
    required_groups: int,
    max_age_seconds: int,
    expected_finality_sha256: str | None = None,
) -> bool:
    try:
        if not isinstance(bundle, Mapping) or set(bundle) != _BUNDLE_KEYS:
            return False
        if type(bundle.get("version")) is not int or bundle["version"] != SIGNED_FINALITY_EVIDENCE_VERSION:
            return False
        required_groups = _positive_int(required_groups)
        max_age_seconds = _positive_int(max_age_seconds, maximum=604800)
        if expected_finality_sha256 is not None and not _is_sha(expected_finality_sha256):
            return False
        finality = _validate_finality_shape(bundle.get("finality"))
        evidence = bundle.get("witness_evidence")
        if not isinstance(evidence, Mapping) or set(evidence) != _EVIDENCE_KEYS:
            return False
        declared_quorum = _validate_quorum_shape(evidence.get("quorum"))
        if not verify_finality_record(finality):
            return False
        if expected_finality_sha256 is not None and not hmac.compare_digest(
            finality["sha256"], expected_finality_sha256
        ):
            return False
        finality_time = _parse_time(finality["finalized_at"])
        statements = evidence.get("statements")
        if not isinstance(statements, list):
            return False
        trust_registry = _normalize_trust_registry(trusted_witnesses)

        trusted_total: dict[str, Mapping[str, Any]] = {}
        fresh: dict[str, Mapping[str, Any]] = {}
        stale = 0
        for raw in statements:
            if not isinstance(raw, Mapping):
                return False
            witness_id = raw.get("witness_id")
            if not isinstance(witness_id, str) or not witness_id or witness_id != witness_id.strip():
                return False
            trust = trust_registry.get(witness_id)
            if trust is None:
                continue
            if not verify_signed_statement(
                raw,
                public_key_b64=trust["public_key_b64"],
                expected_group=trust["independence_group"],
            ):
                continue
            if raw.get("log_id") != finality["log_id"]:
                continue
            if type(raw.get("tree_size")) is not int or raw["tree_size"] != finality["tree_size"]:
                continue
            if raw.get("root_sha256") != finality["root_sha256"]:
                continue
            prior = trusted_total.get(witness_id)
            if prior is not None:
                if prior.get("statement_sha256") != raw.get("statement_sha256"):
                    return False
                # Exact duplicate witness evidence is also non-canonical in a portable
                # bundle: one witness identity contributes at most one statement.
                return False
            trusted_total[witness_id] = raw
            observed = _parse_time(raw.get("observed_at"))
            age = (finality_time - observed).total_seconds()
            if 0 <= age <= max_age_seconds:
                fresh[witness_id] = raw
            else:
                stale += 1

        groups = tuple(sorted({trust_registry[witness_id]["independence_group"] for witness_id in fresh}))
        witness_ids = tuple(sorted(fresh))
        if len(groups) < required_groups:
            return False
        quorum_payload = {
            "log_id": finality["log_id"],
            "tree_size": finality["tree_size"],
            "root_sha256": finality["root_sha256"],
            "trusted_receipts": len(trusted_total),
            "fresh_receipts": len(fresh),
            "stale_receipts": stale,
            "independent_groups": len(groups),
            "required_groups": required_groups,
            "max_age_seconds": max_age_seconds,
            "reached": True,
            "frozen": False,
            "witness_ids": witness_ids,
            "groups": groups,
        }
        quorum_sha256 = canonical_json_sha256(quorum_payload)
        if not hmac.compare_digest(quorum_sha256, finality["witness_quorum_sha256"]):
            return False
        if tuple(finality["witness_groups"]) != groups:
            return False

        expected_declared = canonical_json_clone({
            **quorum_payload,
            "attestation_sha256": quorum_sha256,
        })
        if canonical_json_clone(dict(declared_quorum)) != expected_declared:
            return False

        raw_payload = canonical_json_clone(
            {
                "version": SIGNED_FINALITY_EVIDENCE_VERSION,
                "finality": dict(finality),
                "witness_evidence": dict(evidence),
            }
        )
        bundle_sha = bundle.get("bundle_sha256")
        if not _is_sha(bundle_sha):
            return False
        return hmac.compare_digest(canonical_json_sha256(raw_payload), bundle_sha)
    except (CanonicalJSONError, KeyError, TypeError, ValueError):
        return False
