"""Tamper-evident deployment transition receipts.

A release record proves activation happened, while a deployment receipt proves the
state transition that activation caused. Receipts bind an authorization/plan/release
triple to the whole-system root immediately before and after activation. They are
append-only, process-safe, replay-idempotent, and intentionally excluded from the
system root they attest to avoid self-reference.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hmac
import json
import os
from pathlib import Path
import re
from typing import Any

from core.canonical_json import CanonicalJSONError, canonical_json_bytes, canonical_json_sha256, canonical_json_text
from core.file_lease import FileLease

DEPLOYMENT_RECEIPT_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RECEIPT_KEYS = {
    "version", "sequence", "authorization_id", "plan_sha256", "release_id",
    "release_sha256", "target", "environment", "artifact",
    "pre_system_root_sha256", "post_system_root_sha256", "executed_at",
    "previous_sha256", "sha256",
}
_STRING_FIELDS = _RECEIPT_KEYS - {"version", "sequence"}


class DeploymentReceiptIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DeploymentTransitionReceipt:
    version: int
    sequence: int
    authorization_id: str
    plan_sha256: str
    release_id: str
    release_sha256: str
    target: str
    environment: str
    artifact: str
    pre_system_root_sha256: str
    post_system_root_sha256: str
    executed_at: str
    previous_sha256: str
    sha256: str


def _sha(value: Any) -> str:
    return canonical_json_sha256(value)


def _digest(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be sha256")
    value = value.strip()
    if not _SHA256.fullmatch(value):
        raise ValueError(f"{field} must be sha256")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    value = value.strip()
    if not value:
        raise ValueError(f"{field} must be non-empty")
    return value


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("deployment receipt timestamp must be a non-empty string")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("deployment receipt timestamp must be timezone-aware")
    return stamp.astimezone(UTC)


def _receipt_hash(*, sequence: int, authorization_id: str, plan_sha256: str,
                  release_id: str, release_sha256: str, target: str,
                  environment: str, artifact: str, pre_system_root_sha256: str,
                  post_system_root_sha256: str, executed_at: str,
                  previous_sha256: str) -> str:
    return _sha({
        "version": DEPLOYMENT_RECEIPT_VERSION,
        "sequence": sequence,
        "authorization_id": authorization_id,
        "plan_sha256": plan_sha256,
        "release_id": release_id,
        "release_sha256": release_sha256,
        "target": target,
        "environment": environment,
        "artifact": artifact,
        "pre_system_root_sha256": pre_system_root_sha256,
        "post_system_root_sha256": post_system_root_sha256,
        "executed_at": executed_at,
        "previous_sha256": previous_sha256,
    })


def _validate_raw_receipt(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != _RECEIPT_KEYS:
        raise DeploymentReceiptIntegrityError("deployment receipt schema mismatch")
    if type(raw.get("version")) is not int or raw["version"] != DEPLOYMENT_RECEIPT_VERSION:
        raise DeploymentReceiptIntegrityError("deployment receipt version malformed")
    if type(raw.get("sequence")) is not int or raw["sequence"] < 1:
        raise DeploymentReceiptIntegrityError("deployment receipt sequence malformed")
    if any(not isinstance(raw.get(field), str) for field in _STRING_FIELDS):
        raise DeploymentReceiptIntegrityError("deployment receipt field type mismatch")
    if not all(raw[field] for field in ("authorization_id", "release_id", "target", "environment", "artifact")):
        raise DeploymentReceiptIntegrityError("deployment receipt identity fields are incomplete")
    try:
        canonical_json_bytes(raw)
    except CanonicalJSONError as exc:
        raise DeploymentReceiptIntegrityError("deployment receipt is not canonical JSON") from exc
    return raw


class DeploymentReceiptLedger:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "deployment-receipts.jsonl"
        self._lease = FileLease(self.root / ".deployment-receipts.lock")
        with self._lease.acquire():
            if not self.path.exists():
                self.path.touch()
            self._load_verified()

    @staticmethod
    def _restore(raw: dict[str, Any]) -> DeploymentTransitionReceipt:
        return DeploymentTransitionReceipt(**_validate_raw_receipt(raw))

    def _load_verified(self) -> tuple[DeploymentTransitionReceipt, ...]:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise DeploymentReceiptIntegrityError("deployment receipt ledger unreadable") from exc
        rows: list[DeploymentTransitionReceipt] = []
        previous = ""
        authorizations: set[str] = set()
        releases: set[str] = set()
        for index, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                decoded = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DeploymentReceiptIntegrityError("deployment receipt ledger malformed") from exc
            row = self._restore(decoded)
            if row.sequence != index:
                raise DeploymentReceiptIntegrityError("deployment receipt sequence/version mismatch")
            if row.authorization_id in authorizations:
                raise DeploymentReceiptIntegrityError("duplicate deployment authorization receipt")
            if row.release_id in releases:
                raise DeploymentReceiptIntegrityError("duplicate deployment release receipt")
            try:
                plan = _digest(row.plan_sha256, "plan")
                release = _digest(row.release_sha256, "release")
                pre = _digest(row.pre_system_root_sha256, "pre-system root")
                post = _digest(row.post_system_root_sha256, "post-system root")
                claimed = _digest(row.sha256, "receipt")
                if row.previous_sha256:
                    _digest(row.previous_sha256, "previous receipt")
                _parse_time(row.executed_at)
            except ValueError as exc:
                raise DeploymentReceiptIntegrityError(str(exc)) from exc
            if hmac.compare_digest(pre, post):
                raise DeploymentReceiptIntegrityError("deployment receipt must attest a system-root transition")
            if row.previous_sha256 != previous:
                raise DeploymentReceiptIntegrityError("deployment receipt ancestry mismatch")
            expected = _receipt_hash(
                sequence=row.sequence, authorization_id=row.authorization_id, plan_sha256=plan,
                release_id=row.release_id, release_sha256=release, target=row.target,
                environment=row.environment, artifact=row.artifact,
                pre_system_root_sha256=pre, post_system_root_sha256=post,
                executed_at=row.executed_at, previous_sha256=row.previous_sha256,
            )
            if not hmac.compare_digest(expected, claimed):
                raise DeploymentReceiptIntegrityError("deployment receipt hash mismatch")
            previous = claimed
            authorizations.add(row.authorization_id)
            releases.add(row.release_id)
            rows.append(row)
        return tuple(rows)

    def record(self, *, authorization_id: str, plan_sha256: str, release_id: str,
               release_sha256: str, target: str, environment: str, artifact: str,
               pre_system_root_sha256: str, post_system_root_sha256: str,
               executed_at: str | None = None) -> DeploymentTransitionReceipt:
        authorization_id = _text(authorization_id, "authorization_id")
        release_id = _text(release_id, "release_id")
        target = _text(target, "target")
        environment = _text(environment, "environment")
        artifact = _text(artifact, "artifact")
        plan = _digest(plan_sha256, "plan")
        release = _digest(release_sha256, "release")
        pre = _digest(pre_system_root_sha256, "pre-system root")
        post = _digest(post_system_root_sha256, "post-system root")
        if hmac.compare_digest(pre, post):
            raise ValueError("deployment receipt must attest a system-root transition")
        stamp = executed_at or datetime.now(UTC).isoformat()
        _parse_time(stamp)
        with self._lease.acquire():
            rows = self._load_verified()
            existing = next((row for row in rows if row.authorization_id == authorization_id), None)
            if existing is not None:
                candidate = (
                    existing.plan_sha256 == plan and existing.release_id == release_id and
                    existing.release_sha256 == release and existing.target == target and
                    existing.environment == environment and existing.artifact == artifact and
                    existing.pre_system_root_sha256 == pre and existing.post_system_root_sha256 == post
                )
                if not candidate:
                    raise DeploymentReceiptIntegrityError("authorization already has conflicting deployment receipt")
                return existing
            if any(row.release_id == release_id for row in rows):
                raise DeploymentReceiptIntegrityError("release already attested by another authorization")
            sequence = len(rows) + 1
            previous = rows[-1].sha256 if rows else ""
            digest = _receipt_hash(
                sequence=sequence, authorization_id=authorization_id, plan_sha256=plan,
                release_id=release_id, release_sha256=release, target=target,
                environment=environment, artifact=artifact,
                pre_system_root_sha256=pre, post_system_root_sha256=post,
                executed_at=stamp, previous_sha256=previous,
            )
            row = DeploymentTransitionReceipt(
                DEPLOYMENT_RECEIPT_VERSION, sequence, authorization_id, plan, release_id, release,
                target, environment, artifact, pre, post, stamp, previous, digest,
            )
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(canonical_json_text(asdict(row)) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            return row

    def by_authorization(self, authorization_id: str) -> DeploymentTransitionReceipt | None:
        if not isinstance(authorization_id, str):
            raise ValueError("authorization_id must be a string")
        with self._lease.acquire():
            rows = self._load_verified()
        return next((row for row in rows if row.authorization_id == authorization_id), None)

    def snapshot(self) -> tuple[DeploymentTransitionReceipt, ...]:
        with self._lease.acquire():
            return self._load_verified()

    def status(self) -> dict[str, Any]:
        with self._lease.acquire():
            rows = self._load_verified()
        return {
            "version": DEPLOYMENT_RECEIPT_VERSION,
            "receipts": len(rows),
            "head_sha256": rows[-1].sha256 if rows else "",
            "verified": True,
            "cross_process_locking": True,
            "lock_backend": self._lease.backend,
            "self_referential_root_component": False,
        }
