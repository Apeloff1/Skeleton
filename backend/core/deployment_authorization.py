"""Single-use deployment authorizations bound to stable preflight and plan identity.

The ledger is a cross-process, append-only authorization state machine. New issue
events persist both the complete self-verifying preflight snapshot and the canonical
plan body, so later portable proofs can reconstruct exactly what decision and rollout
were authorized. Legacy hash-only rows remain readable but are reported explicitly.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
import hmac
import json
import os
from pathlib import Path
import re
import uuid
from typing import Any, Mapping

from core.canonical_json import (
    CanonicalJSONError,
    canonical_json_clone,
    canonical_json_sha256,
    canonical_json_text,
)
from core.control_plane_deployment import (
    ControlPlaneDeploymentPreflight,
    verify_control_plane_deployment_preflight,
)
from core.deployment_planner import verify_deployment_plan
from core.deployment_preflight import DeploymentPreflight, PreflightFinding
from core.file_lease import FileLease

AUTH_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class DeploymentAuthorizationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DeploymentAuthorization:
    id: str
    system_root_sha256: str
    preflight_sha256: str
    plan_sha256: str
    issued_at: str
    expires_at: str
    issue_event_sha256: str


@dataclass(frozen=True, slots=True)
class DeploymentConsumption:
    authorization_id: str
    consumed_at: str
    system_root_sha256: str
    plan_sha256: str
    consume_event_sha256: str


def _sha(value: Any) -> str:
    return canonical_json_sha256(value)


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256.fullmatch(value))


def _exact_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _exact_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _exact_str(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ValueError(f"{field} must be a string")
    return value


def _snapshot_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, dict) or not plan:
        raise ValueError("deployment plan must be a non-empty object")
    try:
        snapshot = canonical_json_clone(plan)
    except CanonicalJSONError as exc:
        raise ValueError("deployment plan must contain only finite canonical JSON values") from exc
    if not isinstance(snapshot, dict) or not snapshot:
        raise ValueError("deployment plan must be a non-empty object")
    if not verify_deployment_plan(snapshot):
        raise ValueError("deployment plan failed semantic verification")
    return snapshot


def plan_digest(plan: dict[str, Any]) -> str:
    return _sha(_snapshot_plan(plan))


def _parse(value: Any) -> datetime:
    value = _exact_str(value, "authorization timestamp")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("authorization timestamps must be timezone-aware")
    return stamp.astimezone(UTC)


def serialize_preflight_snapshot(preflight: ControlPlaneDeploymentPreflight) -> dict[str, Any]:
    if not verify_control_plane_deployment_preflight(preflight):
        raise ValueError("deployment preflight snapshot is not self-verifying")
    return asdict(preflight)


def _restore_finding(raw: Any, *, field: str) -> PreflightFinding:
    if not isinstance(raw, Mapping) or set(raw) != {"id", "severity", "detail"}:
        raise ValueError(f"{field} finding is malformed")
    return PreflightFinding(
        _exact_str(raw["id"], f"{field}.id"),
        _exact_str(raw["severity"], f"{field}.severity"),
        _exact_str(raw["detail"], f"{field}.detail"),
    )


def restore_preflight_snapshot(raw: Mapping[str, Any]) -> ControlPlaneDeploymentPreflight:
    try:
        if not isinstance(raw, Mapping):
            raise TypeError("preflight snapshot must be an object")
        report_raw = raw["report"]
        if not isinstance(report_raw, Mapping):
            raise TypeError("preflight report must be an object")
        blockers_raw = report_raw.get("blockers", ())
        warnings_raw = report_raw.get("warnings", ())
        if not isinstance(blockers_raw, (list, tuple)) or not isinstance(warnings_raw, (list, tuple)):
            raise TypeError("preflight findings must be arrays")
        report = DeploymentPreflight(
            version=_exact_int(report_raw["version"], "report.version"),
            allowed=_exact_bool(report_raw["allowed"], "report.allowed"),
            posture=_exact_str(report_raw["posture"], "report.posture"),
            blockers=tuple(_restore_finding(item, field="report.blockers") for item in blockers_raw),
            warnings=tuple(_restore_finding(item, field="report.warnings") for item in warnings_raw),
            assurance_attestation_sha256=_exact_str(report_raw["assurance_attestation_sha256"], "report.assurance_attestation_sha256"),
            system_root_sha256=_exact_str(report_raw["system_root_sha256"], "report.system_root_sha256"),
            trust_state_sha256=_exact_str(report_raw["trust_state_sha256"], "report.trust_state_sha256"),
            finality_required=_exact_bool(report_raw["finality_required"], "report.finality_required"),
            finality_satisfied=_exact_bool(report_raw["finality_satisfied"], "report.finality_satisfied"),
            attestation_sha256=_exact_str(report_raw["attestation_sha256"], "report.attestation_sha256"),
        )
        preflight = ControlPlaneDeploymentPreflight(
            version=_exact_int(raw["version"], "preflight.version"),
            allowed=_exact_bool(raw["allowed"], "preflight.allowed"),
            stable=_exact_bool(raw["stable"], "preflight.stable"),
            attempts=_exact_int(raw["attempts"], "preflight.attempts"),
            root_before_sha256=_exact_str(raw["root_before_sha256"], "preflight.root_before_sha256"),
            root_after_sha256=_exact_str(raw["root_after_sha256"], "preflight.root_after_sha256"),
            evaluated_at=_exact_str(raw["evaluated_at"], "preflight.evaluated_at"),
            unstable_reason=_exact_str(raw.get("unstable_reason", ""), "preflight.unstable_reason", allow_empty=True),
            report=report,
            attestation_sha256=_exact_str(raw["attestation_sha256"], "preflight.attestation_sha256"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("deployment preflight snapshot is malformed") from exc
    if not verify_control_plane_deployment_preflight(preflight):
        raise ValueError("deployment preflight snapshot failed verification")
    return preflight


class DeploymentAuthorizationLedger:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "deployment-authorizations.jsonl"
        self._lease = FileLease(self.root / ".deployment-authorizations.lock")
        with self._lease.acquire():
            if not self.path.exists():
                self.path.touch()
            self._load_verified()

    def _load_verified(self) -> list[dict[str, Any]]:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise DeploymentAuthorizationError("authorization ledger unreadable") from exc
        rows: list[dict[str, Any]] = []
        previous = ""
        issues: dict[str, dict[str, Any]] = {}
        consumed: set[str] = set()
        for sequence, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DeploymentAuthorizationError("authorization ledger malformed") from exc
            raw_version = row.get("version")
            raw_sequence = row.get("sequence")
            if (
                isinstance(raw_version, bool)
                or raw_version != AUTH_VERSION
                or isinstance(raw_sequence, bool)
                or not isinstance(raw_sequence, int)
                or raw_sequence != sequence
                or row.get("previous_sha256", "") != previous
            ):
                raise DeploymentAuthorizationError("authorization ledger ancestry/version mismatch")
            claimed = row.get("sha256")
            if not _is_sha(claimed):
                raise DeploymentAuthorizationError("authorization event hash malformed")
            payload = {k: v for k, v in row.items() if k != "sha256"}
            try:
                hash_valid = hmac.compare_digest(_sha(payload), claimed)
            except CanonicalJSONError as exc:
                raise DeploymentAuthorizationError("authorization event is not canonical JSON") from exc
            if not hash_valid:
                raise DeploymentAuthorizationError("authorization event hash mismatch")
            kind = row.get("kind")
            auth_id = row.get("authorization_id")
            if kind not in {"issue", "consume"} or not isinstance(auth_id, str) or not auth_id:
                raise DeploymentAuthorizationError("authorization event malformed")
            for field in ("system_root_sha256", "plan_sha256"):
                if not _is_sha(row.get(field)):
                    raise DeploymentAuthorizationError(f"authorization {field} malformed")
            if kind == "issue":
                if auth_id in issues:
                    raise DeploymentAuthorizationError("duplicate authorization issue")
                if not _is_sha(row.get("preflight_sha256")):
                    raise DeploymentAuthorizationError("authorization preflight digest malformed")
                try:
                    issued = _parse(row["issued_at"])
                    expires = _parse(row["expires_at"])
                except (KeyError, ValueError) as exc:
                    raise DeploymentAuthorizationError("authorization issue timestamps malformed") from exc
                if expires <= issued:
                    raise DeploymentAuthorizationError("authorization expiry must follow issue time")
                if "preflight" in row:
                    try:
                        preflight = restore_preflight_snapshot(row["preflight"])
                    except ValueError as exc:
                        raise DeploymentAuthorizationError(str(exc)) from exc
                    if not preflight.allowed or not preflight.stable:
                        raise DeploymentAuthorizationError("persisted preflight is not authorizing/stable")
                    if preflight.attestation_sha256 != row["preflight_sha256"]:
                        raise DeploymentAuthorizationError("persisted preflight digest diverges from issue event")
                    if preflight.root_after_sha256 != row["system_root_sha256"]:
                        raise DeploymentAuthorizationError("persisted preflight root diverges from issue event")
                if "plan" in row:
                    plan = row["plan"]
                    if not isinstance(plan, dict) or not plan:
                        raise DeploymentAuthorizationError("persisted deployment plan snapshot is malformed")
                    try:
                        persisted_digest = plan_digest(plan)
                    except ValueError as exc:
                        raise DeploymentAuthorizationError("persisted deployment plan snapshot failed verification") from exc
                    if not hmac.compare_digest(persisted_digest, row["plan_sha256"]):
                        raise DeploymentAuthorizationError("persisted deployment plan digest diverges from issue event")
                issues[auth_id] = row
            else:
                issue = issues.get(auth_id)
                if issue is None:
                    raise DeploymentAuthorizationError("authorization consumed before issue")
                if auth_id in consumed:
                    raise DeploymentAuthorizationError("authorization consumed more than once")
                if row.get("issue_event_sha256") != issue.get("sha256"):
                    raise DeploymentAuthorizationError("authorization consume does not reference its issue event")
                if row.get("system_root_sha256") != issue.get("system_root_sha256") or row.get("plan_sha256") != issue.get("plan_sha256"):
                    raise DeploymentAuthorizationError("authorization consume identity diverges from issue")
                try:
                    consumed_at = _parse(row["consumed_at"])
                    issued = _parse(issue["issued_at"])
                    expires = _parse(issue["expires_at"])
                except (KeyError, ValueError) as exc:
                    raise DeploymentAuthorizationError("authorization consume timestamp malformed") from exc
                if consumed_at < issued or consumed_at > expires:
                    raise DeploymentAuthorizationError("authorization consumed outside validity window")
                consumed.add(auth_id)
            previous = claimed
            rows.append(row)
        return rows

    def _append(self, payload: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
        event = {
            "version": AUTH_VERSION,
            "sequence": len(rows) + 1,
            **payload,
            "previous_sha256": rows[-1]["sha256"] if rows else "",
        }
        event["sha256"] = _sha(event)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(canonical_json_text(event) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return event

    @staticmethod
    def _state(authorization_id: str, rows: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        issue = next((x for x in rows if x.get("kind") == "issue" and x.get("authorization_id") == authorization_id), None)
        consume = next((x for x in rows if x.get("kind") == "consume" and x.get("authorization_id") == authorization_id), None)
        return issue, consume

    def issue(self, *, preflight: ControlPlaneDeploymentPreflight, plan: dict[str, Any],
              ttl_seconds: int = 300, issued_at: str | None = None) -> DeploymentAuthorization:
        if not verify_control_plane_deployment_preflight(preflight) or not preflight.allowed or not preflight.stable:
            raise DeploymentAuthorizationError("deployment preflight is not authorizing/stable")
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or ttl_seconds < 1 or ttl_seconds > 3600:
            raise ValueError("authorization ttl must be an integer between 1 and 3600 seconds")
        snapshot = _snapshot_plan(plan)
        digest = _sha(snapshot)
        stamp = issued_at if issued_at is not None else datetime.now(UTC).isoformat()
        issued = _parse(stamp)
        expires = (issued + timedelta(seconds=ttl_seconds)).isoformat()
        auth_id = uuid.uuid4().hex
        with self._lease.acquire():
            rows = self._load_verified()
            event = self._append({
                "kind": "issue",
                "authorization_id": auth_id,
                "system_root_sha256": preflight.root_after_sha256,
                "preflight_sha256": preflight.attestation_sha256,
                "preflight": serialize_preflight_snapshot(preflight),
                "plan_sha256": digest,
                "plan": snapshot,
                "issued_at": stamp,
                "expires_at": expires,
            }, rows)
        return DeploymentAuthorization(
            auth_id, preflight.root_after_sha256, preflight.attestation_sha256,
            digest, stamp, expires, event["sha256"],
        )

    def consume(self, authorization_id: str, *, current_system_root_sha256: str, plan: dict[str, Any],
                consumed_at: str | None = None) -> DeploymentConsumption:
        if not isinstance(authorization_id, str) or not authorization_id:
            raise ValueError("authorization_id must be a non-empty string")
        if not _is_sha(current_system_root_sha256):
            raise ValueError("current_system_root_sha256 must be sha256")
        stamp = consumed_at if consumed_at is not None else datetime.now(UTC).isoformat()
        now = _parse(stamp)
        digest = plan_digest(plan)
        with self._lease.acquire():
            rows = self._load_verified()
            issue, prior = self._state(authorization_id, rows)
            if issue is None:
                raise DeploymentAuthorizationError("authorization not found")
            if prior is not None:
                raise DeploymentAuthorizationError("authorization already consumed")
            if now > _parse(issue["expires_at"]):
                raise DeploymentAuthorizationError("authorization expired")
            if now < _parse(issue["issued_at"]):
                raise DeploymentAuthorizationError("authorization cannot be consumed before issue")
            if not hmac.compare_digest(issue["system_root_sha256"], current_system_root_sha256):
                raise DeploymentAuthorizationError("system root changed after preflight")
            if not hmac.compare_digest(issue["plan_sha256"], digest):
                raise DeploymentAuthorizationError("deployment plan changed after authorization")
            event = self._append({
                "kind": "consume",
                "authorization_id": authorization_id,
                "system_root_sha256": current_system_root_sha256,
                "plan_sha256": digest,
                "consumed_at": stamp,
                "issue_event_sha256": issue["sha256"],
            }, rows)
        return DeploymentConsumption(
            authorization_id, stamp, current_system_root_sha256, digest, event["sha256"],
        )

    def authorization(self, authorization_id: str) -> DeploymentAuthorization | None:
        if not isinstance(authorization_id, str) or not authorization_id:
            return None
        with self._lease.acquire():
            rows = self._load_verified()
            issue, _ = self._state(authorization_id, rows)
        if issue is None:
            return None
        return DeploymentAuthorization(
            issue["authorization_id"], issue["system_root_sha256"], issue["preflight_sha256"],
            issue["plan_sha256"], issue["issued_at"], issue["expires_at"], issue["sha256"],
        )

    def consumption(self, authorization_id: str) -> DeploymentConsumption | None:
        if not isinstance(authorization_id, str) or not authorization_id:
            return None
        with self._lease.acquire():
            rows = self._load_verified()
            _, consume = self._state(authorization_id, rows)
        if consume is None:
            return None
        return DeploymentConsumption(
            authorization_id, consume["consumed_at"], consume["system_root_sha256"],
            consume["plan_sha256"], consume["sha256"],
        )

    def proof_events(self, authorization_id: str) -> dict[str, Any]:
        if not isinstance(authorization_id, str) or not authorization_id.strip():
            raise ValueError("authorization_id is required")
        authorization_id = authorization_id.strip()
        with self._lease.acquire():
            rows = self._load_verified()
            issue, consume = self._state(authorization_id, rows)
        if issue is None:
            raise KeyError(authorization_id)
        return {
            "issue": dict(issue),
            "consume": dict(consume) if consume is not None else None,
            "ledger_head_sha256": rows[-1]["sha256"] if rows else "",
            "ledger_events": len(rows),
            "portable_preflight": isinstance(issue.get("preflight"), dict),
            "portable_plan": isinstance(issue.get("plan"), dict),
            "verified": True,
        }

    def snapshot_events(self) -> tuple[dict[str, Any], ...]:
        with self._lease.acquire():
            rows = self._load_verified()
        return tuple(dict(row) for row in rows)

    def status(self) -> dict[str, Any]:
        with self._lease.acquire():
            rows = self._load_verified()
        issues = [x for x in rows if x.get("kind") == "issue"]
        consumed = {x.get("authorization_id") for x in rows if x.get("kind") == "consume"}
        preflight_snapshots = sum(isinstance(row.get("preflight"), dict) for row in issues)
        plan_snapshots = sum(isinstance(row.get("plan"), dict) for row in issues)
        return {
            "version": AUTH_VERSION,
            "issued": len(issues),
            "consumed": len(consumed),
            "outstanding": sum(x.get("authorization_id") not in consumed for x in issues),
            "preflight_snapshots": preflight_snapshots,
            "plan_snapshots": plan_snapshots,
            "legacy_preflight_hash_only": len(issues) - preflight_snapshots,
            "legacy_plan_hash_only": len(issues) - plan_snapshots,
            "head_sha256": rows[-1]["sha256"] if rows else "",
            "cross_process_locking": True,
            "lock_backend": self._lease.backend,
            "verified": True,
        }
