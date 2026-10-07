"""Atomic, replay-safe release activation backend.

A validated deployment plan activates an immutable release record for a
(target, environment) channel. Activation pointers are atomically replaced and all
releases remain in hash-chained history. Authorization ID is the idempotency key.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
from typing import Any

from core.canonical_json import CanonicalJSONError, canonical_json_bytes, canonical_json_sha256, canonical_json_text
from core.deployment_authorization import DeploymentConsumption, plan_digest
from core.deployment_planner import verify_deployment_plan
from core.file_lease import FileLease

RELEASE_LEDGER_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RELEASE_KEYS = {
    "version", "sequence", "release_id", "authorization_id", "target",
    "environment", "artifact", "plan_sha256", "system_root_sha256",
    "activated_at", "previous_release_id", "previous_sha256", "sha256",
}
_CURRENT_KEYS = {"version", "release", "sha256"}
_STRING_FIELDS = {
    "release_id", "authorization_id", "target", "environment", "artifact",
    "plan_sha256", "system_root_sha256", "activated_at",
    "previous_release_id", "previous_sha256", "sha256",
}


class ReleaseDeploymentError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ReleaseRecord:
    version: int
    sequence: int
    release_id: str
    authorization_id: str
    target: str
    environment: str
    artifact: str
    plan_sha256: str
    system_root_sha256: str
    activated_at: str
    previous_release_id: str
    previous_sha256: str
    sha256: str


def _sha(value: Any) -> str:
    return canonical_json_sha256(value)


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256.fullmatch(value))


def _channel_key(target: str, environment: str) -> str:
    return hashlib.sha256(f"{environment}\0{target}".encode("utf-8")).hexdigest()[:32]


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("release timestamp must be a non-empty string")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("release timestamp must be timezone-aware")
    return stamp.astimezone(UTC)


def _validate_raw_record(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != _RELEASE_KEYS:
        raise ReleaseDeploymentError("release history record schema mismatch")
    if type(raw.get("version")) is not int or raw["version"] != RELEASE_LEDGER_VERSION:
        raise ReleaseDeploymentError("release history version malformed")
    if type(raw.get("sequence")) is not int or raw["sequence"] < 1:
        raise ReleaseDeploymentError("release history sequence malformed")
    if any(not isinstance(raw.get(field), str) for field in _STRING_FIELDS):
        raise ReleaseDeploymentError("release history field type mismatch")
    if not all(raw[field] and raw[field] == raw[field].strip()
               for field in ("authorization_id", "target", "environment", "artifact", "activated_at")):
        raise ReleaseDeploymentError("release history identity fields are incomplete or noncanonical")
    for field in ("release_id", "plan_sha256", "system_root_sha256", "sha256"):
        if not _is_sha(raw[field]):
            raise ReleaseDeploymentError(f"release history {field} malformed")
    if raw["previous_release_id"] and not _is_sha(raw["previous_release_id"]):
        raise ReleaseDeploymentError("release history previous release id malformed")
    if raw["previous_sha256"] and not _is_sha(raw["previous_sha256"]):
        raise ReleaseDeploymentError("release history previous digest malformed")
    try:
        _parse_time(raw["activated_at"])
        canonical_json_bytes(raw)
    except (ValueError, CanonicalJSONError) as exc:
        raise ReleaseDeploymentError("release history is not canonical JSON") from exc
    return raw


class AtomicReleaseDeployer:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._global_lease = FileLease(self.root / ".release-index.lock")

    def _channel(self, plan: dict[str, Any]) -> tuple[Path, FileLease]:
        target = plan.get("target")
        environment = plan.get("environment")
        if not isinstance(target, str) or not target.strip() or not isinstance(environment, str) or not environment.strip():
            raise ReleaseDeploymentError("deployment plan target/environment missing")
        if target != target.strip() or environment != environment.strip():
            raise ReleaseDeploymentError("deployment plan target/environment must be canonical strings")
        channel = self.root / _channel_key(target, environment)
        channel.mkdir(parents=True, exist_ok=True)
        return channel, FileLease(channel / ".release.lock")

    @staticmethod
    def _restore(raw: dict[str, Any]) -> ReleaseRecord:
        validated = _validate_raw_record(raw)
        return ReleaseRecord(**validated)

    def _history(self, channel: Path) -> tuple[ReleaseRecord, ...]:
        path = channel / "releases.jsonl"
        if not path.exists():
            return ()
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise ReleaseDeploymentError("release history unreadable") from exc
        rows: list[ReleaseRecord] = []
        previous = ""
        previous_release_id = ""
        for index, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                decoded = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ReleaseDeploymentError("release history malformed") from exc
            row = self._restore(decoded)
            if row.sequence != index or row.previous_sha256 != previous:
                raise ReleaseDeploymentError("release history ancestry/version mismatch")
            if index == 1:
                if row.previous_release_id:
                    raise ReleaseDeploymentError("first release cannot reference a predecessor")
            elif row.previous_release_id != previous_release_id:
                raise ReleaseDeploymentError("release history predecessor identity mismatch")
            payload = {key: value for key, value in asdict(row).items() if key != "sha256"}
            if not hmac.compare_digest(_sha(payload), row.sha256):
                raise ReleaseDeploymentError("release history hash mismatch")
            expected_release_id = hashlib.sha256(
                f"{row.authorization_id}\0{row.plan_sha256}\0{row.system_root_sha256}".encode("utf-8")
            ).hexdigest()
            if not hmac.compare_digest(expected_release_id, row.release_id):
                raise ReleaseDeploymentError("release identity derivation mismatch")
            previous = row.sha256
            previous_release_id = row.release_id
            rows.append(row)
        return tuple(rows)

    @staticmethod
    def _current_envelope(record: ReleaseRecord) -> dict[str, Any]:
        payload = {"version": RELEASE_LEDGER_VERSION, "release": asdict(record)}
        return {**payload, "sha256": _sha(payload)}

    def _write_current(self, channel: Path, record: ReleaseRecord) -> None:
        path = channel / "current.json"
        temp = path.with_suffix(f".{os.getpid()}.tmp")
        envelope = self._current_envelope(record)
        try:
            with temp.open("wb") as handle:
                handle.write(canonical_json_bytes(envelope))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    def current(self, *, target: str, environment: str) -> ReleaseRecord | None:
        if not isinstance(target, str) or not target or target != target.strip():
            raise ValueError("target must be a canonical non-empty string")
        if not isinstance(environment, str) or not environment or environment != environment.strip():
            raise ValueError("environment must be a canonical non-empty string")
        channel = self.root / _channel_key(target, environment)
        path = channel / "current.json"
        if not path.exists():
            return None
        lease = FileLease(channel / ".release.lock")
        with lease.acquire():
            try:
                envelope = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ReleaseDeploymentError("current release unreadable") from exc
            if not isinstance(envelope, dict) or set(envelope) != _CURRENT_KEYS:
                raise ReleaseDeploymentError("current release envelope schema mismatch")
            if type(envelope.get("version")) is not int or envelope["version"] != RELEASE_LEDGER_VERSION:
                raise ReleaseDeploymentError("current release version malformed")
            if not isinstance(envelope.get("release"), dict):
                raise ReleaseDeploymentError("current release malformed")
            if not _is_sha(envelope.get("sha256")):
                raise ReleaseDeploymentError("current release checksum malformed")
            try:
                canonical_json_bytes(envelope)
            except CanonicalJSONError as exc:
                raise ReleaseDeploymentError("current release is not canonical JSON") from exc
            payload = {"version": envelope["version"], "release": envelope["release"]}
            if not hmac.compare_digest(_sha(payload), envelope["sha256"]):
                raise ReleaseDeploymentError("current release checksum mismatch")
            row = self._restore(envelope["release"])
            history = self._history(channel)
            if not history or history[-1].sha256 != row.sha256:
                raise ReleaseDeploymentError("current release is not the release-history head")
            return row

    def activate(self, plan: dict[str, Any], consumption: DeploymentConsumption,
                 *, activated_at: str | None = None) -> ReleaseRecord:
        if not verify_deployment_plan(plan):
            raise ReleaseDeploymentError("deployment plan integrity verification failed")
        authorization_id = consumption.authorization_id
        if not isinstance(authorization_id, str) or not authorization_id or authorization_id != authorization_id.strip():
            raise ReleaseDeploymentError("authorization consumption identity is missing or noncanonical")
        if not _is_sha(consumption.consume_event_sha256):
            raise ReleaseDeploymentError("authorization consume event digest is invalid")
        bound_plan = plan_digest(plan)
        if not _is_sha(consumption.plan_sha256) or not hmac.compare_digest(bound_plan, consumption.plan_sha256):
            raise ReleaseDeploymentError("authorization consumption is bound to a different deployment plan")
        if not _is_sha(consumption.system_root_sha256):
            raise ReleaseDeploymentError("authorization system root is invalid")
        try:
            consumed_at = _parse_time(consumption.consumed_at)
        except ValueError as exc:
            raise ReleaseDeploymentError("authorization consumption timestamp is invalid") from exc

        stamp = datetime.now(UTC).isoformat() if activated_at is None else activated_at
        try:
            activation_time = _parse_time(stamp)
        except ValueError as exc:
            raise ReleaseDeploymentError(str(exc)) from exc
        if activation_time < consumed_at:
            raise ReleaseDeploymentError("release cannot activate before authorization consumption")
        channel, lease = self._channel(plan)
        history_path = channel / "releases.jsonl"
        with lease.acquire():
            history = list(self._history(channel))
            replay = next((row for row in history if row.authorization_id == authorization_id), None)
            if replay is not None:
                if replay.plan_sha256 != bound_plan or replay.system_root_sha256 != consumption.system_root_sha256:
                    raise ReleaseDeploymentError("authorization id was previously used for different release evidence")
                return replay

            previous = history[-1] if history else None
            sequence = len(history) + 1
            release_id = hashlib.sha256(
                f"{authorization_id}\0{bound_plan}\0{consumption.system_root_sha256}".encode("utf-8")
            ).hexdigest()
            payload = {
                "version": RELEASE_LEDGER_VERSION,
                "sequence": sequence,
                "release_id": release_id,
                "authorization_id": authorization_id,
                "target": plan["target"],
                "environment": plan["environment"],
                "artifact": plan["artifact"],
                "plan_sha256": bound_plan,
                "system_root_sha256": consumption.system_root_sha256,
                "activated_at": stamp,
                "previous_release_id": previous.release_id if previous else "",
                "previous_sha256": previous.sha256 if previous else "",
            }
            record = ReleaseRecord(**payload, sha256=_sha(payload))
            with history_path.open("a", encoding="utf-8") as handle:
                handle.write(canonical_json_text(asdict(record)) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._write_current(channel, record)
            return record

    def snapshot(self) -> tuple[ReleaseRecord, ...]:
        """Return every verified release across all channels in deterministic order."""
        rows: list[ReleaseRecord] = []
        with self._global_lease.acquire():
            for channel in self.root.iterdir():
                if not channel.is_dir():
                    continue
                lease = FileLease(channel / ".release.lock")
                with lease.acquire():
                    rows.extend(self._history(channel))
        return tuple(sorted(rows, key=lambda row: (row.activated_at, row.environment, row.target, row.release_id)))

    def find_by_authorization(self, authorization_id: str) -> ReleaseRecord | None:
        if not isinstance(authorization_id, str) or not authorization_id:
            return None
        return next((row for row in self.snapshot() if row.authorization_id == authorization_id), None)

    def status(self) -> dict[str, Any]:
        rows = self.snapshot()
        channels = {(row.environment, row.target) for row in rows}
        heads: dict[tuple[str, str], ReleaseRecord] = {}
        for row in rows:
            heads[(row.environment, row.target)] = row
        return {
            "version": RELEASE_LEDGER_VERSION,
            "channels": len(channels),
            "releases": len(rows),
            "head_set_sha256": _sha(sorted(row.sha256 for row in heads.values())),
            "cross_process_locking": True,
            "lock_backend": self._global_lease.backend,
            "verified": True,
        }
