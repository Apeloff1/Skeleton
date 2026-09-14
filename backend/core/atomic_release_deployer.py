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

from core.deployment_authorization import DeploymentConsumption, plan_digest
from core.deployment_planner import verify_deployment_plan
from core.file_lease import FileLease

RELEASE_LEDGER_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


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


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _channel_key(target: str, environment: str) -> str:
    return hashlib.sha256(f"{environment}\0{target}".encode("utf-8")).hexdigest()[:32]


def _parse_time(value: str) -> datetime:
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("release timestamp must be timezone-aware")
    return stamp.astimezone(UTC)


class AtomicReleaseDeployer:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._global_lease = FileLease(self.root / ".release-index.lock")

    def _channel(self, plan: dict[str, Any]) -> tuple[Path, FileLease]:
        target = str(plan.get("target") or "").strip()
        environment = str(plan.get("environment") or "").strip()
        if not target or not environment:
            raise ReleaseDeploymentError("deployment plan target/environment missing")
        channel = self.root / _channel_key(target, environment)
        channel.mkdir(parents=True, exist_ok=True)
        return channel, FileLease(channel / ".release.lock")

    @staticmethod
    def _restore(raw: dict[str, Any]) -> ReleaseRecord:
        return ReleaseRecord(
            version=int(raw["version"]), sequence=int(raw["sequence"]), release_id=str(raw["release_id"]),
            authorization_id=str(raw["authorization_id"]), target=str(raw["target"]),
            environment=str(raw["environment"]), artifact=str(raw["artifact"]),
            plan_sha256=str(raw["plan_sha256"]), system_root_sha256=str(raw["system_root_sha256"]),
            activated_at=str(raw["activated_at"]), previous_release_id=str(raw.get("previous_release_id", "")),
            previous_sha256=str(raw.get("previous_sha256", "")), sha256=str(raw["sha256"]),
        )

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
        for index, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                row = self._restore(json.loads(line))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise ReleaseDeploymentError("release history malformed") from exc
            if row.version != RELEASE_LEDGER_VERSION or row.sequence != index or row.previous_sha256 != previous:
                raise ReleaseDeploymentError("release history ancestry/version mismatch")
            if not _SHA256.fullmatch(row.sha256) or (row.previous_sha256 and not _SHA256.fullmatch(row.previous_sha256)):
                raise ReleaseDeploymentError("release history digest malformed")
            try:
                _parse_time(row.activated_at)
            except ValueError as exc:
                raise ReleaseDeploymentError(str(exc)) from exc
            payload = {key: value for key, value in asdict(row).items() if key != "sha256"}
            if not hmac.compare_digest(_sha(payload), row.sha256):
                raise ReleaseDeploymentError("release history hash mismatch")
            previous = row.sha256
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
                handle.write(_canonical(envelope))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    def current(self, *, target: str, environment: str) -> ReleaseRecord | None:
        channel = self.root / _channel_key(str(target).strip(), str(environment).strip())
        path = channel / "current.json"
        if not path.exists():
            return None
        lease = FileLease(channel / ".release.lock")
        with lease.acquire():
            try:
                envelope = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ReleaseDeploymentError("current release unreadable") from exc
            payload = {"version": envelope.get("version"), "release": envelope.get("release")}
            if envelope.get("version") != RELEASE_LEDGER_VERSION or not isinstance(envelope.get("release"), dict):
                raise ReleaseDeploymentError("current release malformed")
            if not hmac.compare_digest(_sha(payload), str(envelope.get("sha256") or "")):
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
        authorization_id = str(consumption.authorization_id or "").strip()
        if not authorization_id:
            raise ReleaseDeploymentError("authorization consumption identity is missing")
        if not _SHA256.fullmatch(str(consumption.consume_event_sha256 or "")):
            raise ReleaseDeploymentError("authorization consume event digest is invalid")
        bound_plan = plan_digest(plan)
        if not hmac.compare_digest(bound_plan, consumption.plan_sha256):
            raise ReleaseDeploymentError("authorization consumption is bound to a different deployment plan")
        if not _SHA256.fullmatch(consumption.system_root_sha256):
            raise ReleaseDeploymentError("authorization system root is invalid")
        try:
            consumed_at = _parse_time(consumption.consumed_at)
        except ValueError as exc:
            raise ReleaseDeploymentError("authorization consumption timestamp is invalid") from exc

        stamp = activated_at or datetime.now(UTC).isoformat()
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
                "version": RELEASE_LEDGER_VERSION, "sequence": sequence, "release_id": release_id,
                "authorization_id": authorization_id, "target": str(plan["target"]),
                "environment": str(plan["environment"]), "artifact": str(plan["artifact"]),
                "plan_sha256": bound_plan, "system_root_sha256": consumption.system_root_sha256,
                "activated_at": stamp, "previous_release_id": previous.release_id if previous else "",
                "previous_sha256": previous.sha256 if previous else "",
            }
            record = ReleaseRecord(**payload, sha256=_sha(payload))
            with history_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(record), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
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
