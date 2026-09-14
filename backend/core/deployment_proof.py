"""Portable, independently verifiable deployment transition proofs.

A deployment is not considered proven merely because its individual records hash.
This packet carries the exact canonical rollout plan, the complete self-verifying
preflight, and suffix witnesses from the authorization issue, activated release, and
transition receipt to each ledger's current head. Verification cross-binds the plan,
decision, authorization, release target, artifact, pre/post roots, timestamps, and all
three durable chains.

External consumers must pin the expected ledger heads out of band. Supplying heads
from the same packet proves consistency only, not external trust.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import hmac
import re
from typing import Any, Mapping, Sequence

from core.atomic_release_deployer import RELEASE_LEDGER_VERSION
from core.canonical_json import canonical_json_sha256
from core.deployment_authorization import AUTH_VERSION, plan_digest, restore_preflight_snapshot
from core.deployment_planner import verify_deployment_plan
from core.deployment_receipts import DEPLOYMENT_RECEIPT_VERSION

DEPLOYMENT_PROOF_VERSION = 3
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PROOF_KEYS = {
    "version", "authorization_id", "plan_sha256", "plan",
    "pre_system_root_sha256", "post_system_root_sha256", "preflight",
    "authorization_suffix", "authorization_head_sha256", "release",
    "release_suffix", "release_channel_head_sha256", "transition_receipt",
    "receipt_suffix", "receipt_head_sha256", "proof_sha256",
}
_RELEASE_KEYS = {
    "version", "sequence", "release_id", "authorization_id", "target",
    "environment", "artifact", "plan_sha256", "system_root_sha256",
    "activated_at", "previous_release_id", "previous_sha256", "sha256",
}
_RECEIPT_KEYS = {
    "version", "sequence", "authorization_id", "plan_sha256", "release_id",
    "release_sha256", "target", "environment", "artifact",
    "pre_system_root_sha256", "post_system_root_sha256", "executed_at",
    "previous_sha256", "sha256",
}
_ISSUE_KEYS = {
    "version", "sequence", "kind", "authorization_id", "system_root_sha256",
    "preflight_sha256", "preflight", "plan_sha256", "plan", "issued_at",
    "expires_at", "previous_sha256", "sha256",
}
_LEGACY_ISSUE_KEYS = _ISSUE_KEYS - {"preflight", "plan"}
_CONSUME_KEYS = {
    "version", "sequence", "kind", "authorization_id", "system_root_sha256",
    "plan_sha256", "consumed_at", "issue_event_sha256", "previous_sha256", "sha256",
}


@dataclass(frozen=True, slots=True)
class PortableDeploymentProof:
    version: int
    authorization_id: str
    plan_sha256: str
    plan: dict[str, Any]
    pre_system_root_sha256: str
    post_system_root_sha256: str
    preflight: dict[str, Any]
    authorization_suffix: tuple[dict[str, Any], ...]
    authorization_head_sha256: str
    release: dict[str, Any]
    release_suffix: tuple[dict[str, Any], ...]
    release_channel_head_sha256: str
    transition_receipt: dict[str, Any]
    receipt_suffix: tuple[dict[str, Any], ...]
    receipt_head_sha256: str
    proof_sha256: str


def _sha(value: Any) -> str:
    return canonical_json_sha256(value)


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256.fullmatch(value))


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("proof timestamp must be a non-empty string")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("proof timestamps must be timezone-aware")
    return stamp


def _record_hash(record: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in record.items() if key != "sha256"}
    return _sha(payload)


def _expected_release_id(*, authorization_id: str, plan_sha256: str, system_root_sha256: str) -> str:
    return hashlib.sha256(
        f"{authorization_id}\0{plan_sha256}\0{system_root_sha256}".encode("utf-8")
    ).hexdigest()


def _authorization_event_schema(row: Mapping[str, Any]) -> bool:
    kind = row.get("kind")
    keys = set(row)
    if kind == "issue":
        if keys not in {_ISSUE_KEYS, _LEGACY_ISSUE_KEYS}:
            return False
        if not _is_sha(row.get("preflight_sha256")):
            return False
    elif kind == "consume":
        if keys != _CONSUME_KEYS or not _is_sha(row.get("issue_event_sha256")):
            return False
    else:
        return False
    return (
        row.get("version") == AUTH_VERSION
        and _positive_int(row.get("sequence")) is not None
        and isinstance(row.get("authorization_id"), str)
        and bool(row.get("authorization_id"))
        and _is_sha(row.get("system_root_sha256"))
        and _is_sha(row.get("plan_sha256"))
        and _is_sha(row.get("sha256"))
        and isinstance(row.get("previous_sha256"), str)
    )


def _release_record_semantics(row: Mapping[str, Any]) -> bool:
    try:
        if set(row) != _RELEASE_KEYS or row.get("version") != RELEASE_LEDGER_VERSION:
            return False
        sequence = _positive_int(row.get("sequence"))
        if sequence is None or not isinstance(row.get("authorization_id"), str) or not row.get("authorization_id"):
            return False
        if not all(_is_sha(row.get(field)) for field in (
            "release_id", "plan_sha256", "system_root_sha256", "sha256",
        )):
            return False
        expected_release_id = _expected_release_id(
            authorization_id=row["authorization_id"],
            plan_sha256=row["plan_sha256"],
            system_root_sha256=row["system_root_sha256"],
        )
        if not hmac.compare_digest(row["release_id"], expected_release_id):
            return False
        if not all(isinstance(row.get(field), str) and row.get(field).strip()
                   for field in ("target", "environment", "artifact")):
            return False
        _parse_time(row.get("activated_at"))
        previous_id = row.get("previous_release_id")
        previous_sha = row.get("previous_sha256")
        if not isinstance(previous_id, str) or not isinstance(previous_sha, str):
            return False
        if sequence == 1:
            return not previous_id and not previous_sha
        return _is_sha(previous_id) and _is_sha(previous_sha)
    except (KeyError, TypeError, ValueError):
        return False


def _receipt_record_semantics(row: Mapping[str, Any]) -> bool:
    try:
        if set(row) != _RECEIPT_KEYS or row.get("version") != DEPLOYMENT_RECEIPT_VERSION:
            return False
        sequence = _positive_int(row.get("sequence"))
        if sequence is None:
            return False
        if not all(isinstance(row.get(field), str) and row.get(field).strip() for field in (
            "authorization_id", "release_id", "target", "environment", "artifact",
        )):
            return False
        if not all(_is_sha(row.get(field)) for field in (
            "plan_sha256", "release_sha256", "pre_system_root_sha256",
            "post_system_root_sha256", "sha256",
        )):
            return False
        if hmac.compare_digest(row["pre_system_root_sha256"], row["post_system_root_sha256"]):
            return False
        _parse_time(row.get("executed_at"))
        previous_sha = row.get("previous_sha256")
        if not isinstance(previous_sha, str):
            return False
        return (not previous_sha) if sequence == 1 else _is_sha(previous_sha)
    except (KeyError, TypeError, ValueError):
        return False


def _proof_payload(proof: PortableDeploymentProof | Mapping[str, Any]) -> dict[str, Any]:
    raw = asdict(proof) if isinstance(proof, PortableDeploymentProof) else dict(proof)
    return {key: value for key, value in raw.items() if key != "proof_sha256"}


def _portable_plan(issue: Mapping[str, Any]) -> dict[str, Any]:
    raw = issue.get("plan")
    if not isinstance(raw, dict) or not raw:
        raise ValueError("deployment authorization predates portable plan snapshots")
    plan = dict(raw)
    if not verify_deployment_plan(plan):
        raise ValueError("persisted deployment plan failed integrity verification")
    expected = issue.get("plan_sha256")
    if not _is_sha(expected) or not hmac.compare_digest(plan_digest(plan), expected):
        raise ValueError("persisted deployment plan diverges from authorization digest")
    return plan


def build_portable_deployment_proof(gateway, authorization_id: str) -> PortableDeploymentProof:
    authorization_id = str(authorization_id).strip()
    if not authorization_id:
        raise ValueError("authorization_id is required")

    authorization_events = list(gateway.authorizations.snapshot_events())
    issue_index = next((i for i, row in enumerate(authorization_events)
                        if row.get("kind") == "issue" and row.get("authorization_id") == authorization_id), None)
    if issue_index is None:
        raise KeyError(authorization_id)
    authorization_suffix = tuple(dict(row) for row in authorization_events[issue_index:])
    issue = authorization_suffix[0]
    preflight_raw = issue.get("preflight")
    if not isinstance(preflight_raw, dict):
        raise ValueError("deployment authorization predates portable preflight snapshots")
    preflight = restore_preflight_snapshot(preflight_raw)
    if not preflight.allowed or not preflight.stable:
        raise ValueError("deployment preflight is not authorizing/stable")
    plan = _portable_plan(issue)
    consume = next((row for row in authorization_suffix
                    if row.get("kind") == "consume" and row.get("authorization_id") == authorization_id), None)
    if consume is None:
        raise ValueError("deployment authorization has not been consumed")

    release = gateway.releases.find_by_authorization(authorization_id)
    if release is None:
        raise ValueError("deployment authorization has no activated release")
    release_raw = asdict(release)
    if not _release_record_semantics(release_raw):
        raise ValueError("activated release failed semantic verification")
    release_rows = [row for row in gateway.releases.snapshot()
                    if row.target == release.target and row.environment == release.environment]
    release_rows.sort(key=lambda row: row.sequence)
    release_index = next((i for i, row in enumerate(release_rows) if row.release_id == release.release_id), None)
    if release_index is None:
        raise ValueError("activated release is missing from verified channel history")
    release_suffix = tuple(asdict(row) for row in release_rows[release_index:])

    receipt = gateway.receipts.by_authorization(authorization_id)
    if receipt is None:
        raise ValueError("deployment transition receipt is missing")
    receipt_raw = asdict(receipt)
    if not _receipt_record_semantics(receipt_raw):
        raise ValueError("deployment transition receipt failed semantic verification")
    receipt_rows = list(gateway.receipts.snapshot())
    receipt_index = next((i for i, row in enumerate(receipt_rows) if row.authorization_id == authorization_id), None)
    if receipt_index is None:
        raise ValueError("transition receipt is missing from verified receipt history")
    receipt_suffix = tuple(asdict(row) for row in receipt_rows[receipt_index:])

    if receipt.plan_sha256 != issue.get("plan_sha256") or release.plan_sha256 != issue.get("plan_sha256"):
        raise ValueError("deployment evidence diverges from authorized plan")
    if any(str(plan.get(field) or "") != getattr(release, field) for field in ("target", "environment", "artifact")):
        raise ValueError("activated release diverges from authorized rollout identity")

    payload = {
        "version": DEPLOYMENT_PROOF_VERSION,
        "authorization_id": authorization_id,
        "plan_sha256": receipt.plan_sha256,
        "plan": plan,
        "pre_system_root_sha256": receipt.pre_system_root_sha256,
        "post_system_root_sha256": receipt.post_system_root_sha256,
        "preflight": dict(preflight_raw),
        "authorization_suffix": authorization_suffix,
        "authorization_head_sha256": authorization_events[-1]["sha256"],
        "release": release_raw,
        "release_suffix": release_suffix,
        "release_channel_head_sha256": release_rows[-1].sha256,
        "transition_receipt": receipt_raw,
        "receipt_suffix": receipt_suffix,
        "receipt_head_sha256": receipt_rows[-1].sha256,
    }
    return PortableDeploymentProof(**payload, proof_sha256=_sha(payload))


def _verify_chain_suffix(rows: Sequence[Mapping[str, Any]], *, expected_head: str,
                         require_sequence_contiguous: bool = True) -> bool:
    if not rows or not _is_sha(expected_head):
        return False
    previous_hash = ""
    previous_sequence: int | None = None
    for index, row in enumerate(rows):
        claimed = row.get("sha256")
        if not _is_sha(claimed) or not hmac.compare_digest(_record_hash(row), claimed):
            return False
        sequence = _positive_int(row.get("sequence"))
        if sequence is None:
            return False
        if index > 0:
            if row.get("previous_sha256") != previous_hash:
                return False
            if require_sequence_contiguous and previous_sequence is not None and sequence != previous_sequence + 1:
                return False
        previous_hash = claimed
        previous_sequence = sequence
    return hmac.compare_digest(previous_hash, expected_head)


def _verify_release_suffix(rows: Sequence[Mapping[str, Any]], *, expected_head: str) -> bool:
    if not _verify_chain_suffix(rows, expected_head=expected_head):
        return False
    previous_release_id = ""
    for index, row in enumerate(rows):
        if not _release_record_semantics(row):
            return False
        if index > 0 and row.get("previous_release_id") != previous_release_id:
            return False
        previous_release_id = row["release_id"]
    return True


def _verify_receipt_suffix(rows: Sequence[Mapping[str, Any]], *, expected_head: str) -> bool:
    return _verify_chain_suffix(rows, expected_head=expected_head) and all(
        _receipt_record_semantics(row) for row in rows
    )


def verify_portable_deployment_proof(
    proof: PortableDeploymentProof | Mapping[str, Any],
    *,
    expected_authorization_head_sha256: str,
    expected_release_channel_head_sha256: str,
    expected_receipt_head_sha256: str,
) -> bool:
    """Verify a deployment proof against three externally pinned durable heads."""
    try:
        raw = asdict(proof) if isinstance(proof, PortableDeploymentProof) else dict(proof)
        if set(raw) != _PROOF_KEYS or raw.get("version") != DEPLOYMENT_PROOF_VERSION:
            return False
        if not all(_is_sha(raw.get(name)) for name in (
            "plan_sha256", "pre_system_root_sha256", "post_system_root_sha256",
            "authorization_head_sha256", "release_channel_head_sha256", "receipt_head_sha256",
            "proof_sha256",
        )):
            return False
        if not hmac.compare_digest(_sha(_proof_payload(raw)), raw["proof_sha256"]):
            return False
        if not hmac.compare_digest(raw["authorization_head_sha256"], expected_authorization_head_sha256):
            return False
        if not hmac.compare_digest(raw["release_channel_head_sha256"], expected_release_channel_head_sha256):
            return False
        if not hmac.compare_digest(raw["receipt_head_sha256"], expected_receipt_head_sha256):
            return False

        authorization_id = raw.get("authorization_id")
        plan_sha = raw["plan_sha256"]
        pre_root = raw["pre_system_root_sha256"]
        post_root = raw["post_system_root_sha256"]
        if not isinstance(authorization_id, str) or not authorization_id or hmac.compare_digest(pre_root, post_root):
            return False

        plan = raw.get("plan")
        if not isinstance(plan, dict) or not plan or not verify_deployment_plan(plan):
            return False
        if not hmac.compare_digest(plan_digest(plan), plan_sha):
            return False
        for field in ("target", "environment", "artifact"):
            if not isinstance(plan.get(field), str) or not plan[field].strip():
                return False

        preflight_raw = raw.get("preflight")
        if not isinstance(preflight_raw, dict):
            return False
        preflight = restore_preflight_snapshot(preflight_raw)
        if not preflight.allowed or not preflight.stable:
            return False
        if preflight.root_before_sha256 != pre_root or preflight.root_after_sha256 != pre_root:
            return False
        if preflight.report.system_root_sha256 != pre_root or not preflight.report.allowed:
            return False

        auth_suffix = tuple(dict(row) for row in raw.get("authorization_suffix") or ())
        if not auth_suffix or not all(_authorization_event_schema(row) for row in auth_suffix):
            return False
        if not _verify_chain_suffix(auth_suffix, expected_head=expected_authorization_head_sha256):
            return False
        issue = auth_suffix[0]
        if issue.get("kind") != "issue" or issue.get("authorization_id") != authorization_id:
            return False
        consume = next((row for row in auth_suffix[1:]
                        if row.get("kind") == "consume" and row.get("authorization_id") == authorization_id), None)
        if consume is None:
            return False
        if issue.get("preflight") != preflight_raw or issue.get("plan") != plan:
            return False
        if issue.get("preflight_sha256") != preflight.attestation_sha256:
            return False
        if consume.get("issue_event_sha256") != issue.get("sha256"):
            return False
        if issue.get("plan_sha256") != plan_sha or consume.get("plan_sha256") != plan_sha:
            return False
        if issue.get("system_root_sha256") != pre_root or consume.get("system_root_sha256") != pre_root:
            return False
        issued = _parse_time(issue.get("issued_at"))
        expires = _parse_time(issue.get("expires_at"))
        consumed_at = _parse_time(consume.get("consumed_at"))
        if not (issued <= consumed_at <= expires):
            return False

        release = dict(raw.get("release") or {})
        if not _release_record_semantics(release):
            return False
        if not hmac.compare_digest(_record_hash(release), release["sha256"]):
            return False
        if release.get("authorization_id") != authorization_id or release.get("plan_sha256") != plan_sha:
            return False
        if release.get("system_root_sha256") != pre_root:
            return False
        if any(release.get(field) != plan.get(field) for field in ("target", "environment", "artifact")):
            return False
        activated_at = _parse_time(release.get("activated_at"))
        if activated_at < consumed_at:
            return False
        release_suffix = tuple(dict(row) for row in raw.get("release_suffix") or ())
        if not release_suffix or release_suffix[0].get("sha256") != release.get("sha256"):
            return False
        if any(row.get("target") != release.get("target") or row.get("environment") != release.get("environment") for row in release_suffix):
            return False
        if not _verify_release_suffix(release_suffix, expected_head=expected_release_channel_head_sha256):
            return False

        receipt = dict(raw.get("transition_receipt") or {})
        if not _receipt_record_semantics(receipt):
            return False
        if not hmac.compare_digest(_record_hash(receipt), receipt["sha256"]):
            return False
        if receipt.get("authorization_id") != authorization_id or receipt.get("plan_sha256") != plan_sha:
            return False
        if receipt.get("release_id") != release.get("release_id") or receipt.get("release_sha256") != release.get("sha256"):
            return False
        if receipt.get("pre_system_root_sha256") != pre_root or receipt.get("post_system_root_sha256") != post_root:
            return False
        if any(receipt.get(field) != release.get(field) or receipt.get(field) != plan.get(field)
               for field in ("target", "environment", "artifact")):
            return False
        executed_at = _parse_time(receipt.get("executed_at"))
        if executed_at != activated_at:
            return False
        receipt_suffix = tuple(dict(row) for row in raw.get("receipt_suffix") or ())
        if not receipt_suffix or receipt_suffix[0].get("sha256") != receipt.get("sha256"):
            return False
        if not _verify_receipt_suffix(receipt_suffix, expected_head=expected_receipt_head_sha256):
            return False
        return True
    except (KeyError, TypeError, ValueError):
        return False
