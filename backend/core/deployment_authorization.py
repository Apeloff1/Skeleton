"""Single-use deployment authorizations bound to stable preflight and plan identity.

The ledger is a cross-process, append-only authorization state machine. Issue and
consume events are hash-chained and semantically replay-verified: consumes must
reference a prior issue, match its immutable root/plan identity, occur at most once,
and fall inside the authorization validity window.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import uuid
from typing import Any

from core.control_plane_deployment import (
    ControlPlaneDeploymentPreflight,
    verify_control_plane_deployment_preflight,
)
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


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def plan_digest(plan: dict[str, Any]) -> str:
    if not isinstance(plan, dict) or not plan:
        raise ValueError("deployment plan must be a non-empty object")
    return _sha(plan)


def _parse(value: str) -> datetime:
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("authorization timestamps must be timezone-aware")
    return stamp.astimezone(UTC)


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
            if row.get("version") != AUTH_VERSION or int(row.get("sequence", 0)) != sequence or row.get("previous_sha256", "") != previous:
                raise DeploymentAuthorizationError("authorization ledger ancestry/version mismatch")
            claimed = str(row.get("sha256") or "")
            payload = {k: v for k, v in row.items() if k != "sha256"}
            if not _SHA256.fullmatch(claimed) or not hmac.compare_digest(_sha(payload), claimed):
                raise DeploymentAuthorizationError("authorization event hash mismatch")
            kind = row.get("kind")
            auth_id = str(row.get("authorization_id") or "")
            if kind not in {"issue", "consume"} or not auth_id:
                raise DeploymentAuthorizationError("authorization event malformed")
            for field in ("system_root_sha256", "plan_sha256"):
                if not _SHA256.fullmatch(str(row.get(field) or "")):
                    raise DeploymentAuthorizationError(f"authorization {field} malformed")
            if kind == "issue":
                if auth_id in issues:
                    raise DeploymentAuthorizationError("duplicate authorization issue")
                if not _SHA256.fullmatch(str(row.get("preflight_sha256") or "")):
                    raise DeploymentAuthorizationError("authorization preflight digest malformed")
                try:
                    issued = _parse(str(row["issued_at"]))
                    expires = _parse(str(row["expires_at"]))
                except (KeyError, ValueError) as exc:
                    raise DeploymentAuthorizationError("authorization issue timestamps malformed") from exc
                if expires <= issued:
                    raise DeploymentAuthorizationError("authorization expiry must follow issue time")
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
                    consumed_at = _parse(str(row["consumed_at"]))
                    issued = _parse(str(issue["issued_at"]))
                    expires = _parse(str(issue["expires_at"]))
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
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
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
        if ttl_seconds < 1 or ttl_seconds > 3600:
            raise ValueError("authorization ttl must be between 1 and 3600 seconds")
        stamp = issued_at or datetime.now(UTC).isoformat()
        issued = _parse(stamp)
        expires = (issued + timedelta(seconds=ttl_seconds)).isoformat()
        digest = plan_digest(plan)
        auth_id = uuid.uuid4().hex
        with self._lease.acquire():
            rows = self._load_verified()
            event = self._append({
                "kind": "issue",
                "authorization_id": auth_id,
                "system_root_sha256": preflight.root_after_sha256,
                "preflight_sha256": preflight.attestation_sha256,
                "plan_sha256": digest,
                "issued_at": stamp,
                "expires_at": expires,
            }, rows)
        return DeploymentAuthorization(
            auth_id, preflight.root_after_sha256, preflight.attestation_sha256,
            digest, stamp, expires, event["sha256"],
        )

    def consume(self, authorization_id: str, *, current_system_root_sha256: str, plan: dict[str, Any],
                consumed_at: str | None = None) -> DeploymentConsumption:
        stamp = consumed_at or datetime.now(UTC).isoformat()
        now = _parse(stamp)
        digest = plan_digest(plan)
        with self._lease.acquire():
            rows = self._load_verified()
            issue, prior = self._state(authorization_id, rows)
            if issue is None:
                raise DeploymentAuthorizationError("authorization not found")
            if prior is not None:
                raise DeploymentAuthorizationError("authorization already consumed")
            if now > _parse(str(issue["expires_at"])):
                raise DeploymentAuthorizationError("authorization expired")
            if now < _parse(str(issue["issued_at"])):
                raise DeploymentAuthorizationError("authorization cannot be consumed before issue")
            if not hmac.compare_digest(str(issue["system_root_sha256"]), str(current_system_root_sha256)):
                raise DeploymentAuthorizationError("system root changed after preflight")
            if not hmac.compare_digest(str(issue["plan_sha256"]), digest):
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
        with self._lease.acquire():
            rows = self._load_verified()
            issue, _ = self._state(authorization_id, rows)
        if issue is None:
            return None
        return DeploymentAuthorization(
            str(issue["authorization_id"]), str(issue["system_root_sha256"]), str(issue["preflight_sha256"]),
            str(issue["plan_sha256"]), str(issue["issued_at"]), str(issue["expires_at"]), str(issue["sha256"]),
        )

    def consumption(self, authorization_id: str) -> DeploymentConsumption | None:
        with self._lease.acquire():
            rows = self._load_verified()
            _, consume = self._state(authorization_id, rows)
        if consume is None:
            return None
        return DeploymentConsumption(
            authorization_id, str(consume["consumed_at"]), str(consume["system_root_sha256"]),
            str(consume["plan_sha256"]), str(consume["sha256"]),
        )

    def proof_events(self, authorization_id: str) -> dict[str, Any]:
        """Export verified issue/consume events plus the current ledger head.

        The raw events are required for independent hash recomputation. Returning
        them through this method guarantees the full local ledger has already passed
        sequence, ancestry, semantic, timestamp, and digest verification.
        """
        authorization_id = str(authorization_id).strip()
        if not authorization_id:
            raise ValueError("authorization_id is required")
        with self._lease.acquire():
            rows = self._load_verified()
            issue, consume = self._state(authorization_id, rows)
        if issue is None:
            raise KeyError(authorization_id)
        return {
            "issue": dict(issue),
            "consume": dict(consume) if consume is not None else None,
            "ledger_head_sha256": str(rows[-1]["sha256"]) if rows else "",
            "ledger_events": len(rows),
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
        return {
            "version": AUTH_VERSION,
            "issued": len(issues),
            "consumed": len(consumed),
            "outstanding": sum(x.get("authorization_id") not in consumed for x in issues),
            "head_sha256": rows[-1]["sha256"] if rows else "",
            "cross_process_locking": True,
            "lock_backend": self._lease.backend,
            "verified": True,
        }
