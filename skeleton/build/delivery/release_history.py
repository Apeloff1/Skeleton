"""Append-only, hash-chained release history per environment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from skeleton.build.delivery._util import (
    DeliveryError,
    require_env_name,
    require_id,
    require_non_negative_int,
    require_sha256,
    sha256_json,
)

GENESIS = "0" * 64
OUTCOMES = frozenset({"deployed", "failed", "rolled-back"})


@dataclass(frozen=True)
class ReleaseRecord:
    sequence: int
    environment: str
    release_id: str
    manifest_digest: str
    config_digest: str
    outcome: str
    recorded_at: int
    previous: str

    def body(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "environment": self.environment,
            "release_id": self.release_id,
            "manifest_digest": self.manifest_digest,
            "config_digest": self.config_digest,
            "outcome": self.outcome,
            "recorded_at": self.recorded_at,
            "previous": self.previous,
        }

    @property
    def digest(self) -> str:
        return sha256_json(self.body())


class ReleaseHistory:
    def __init__(self, environment: str, records: Iterable[ReleaseRecord] = ()) -> None:
        self.environment = require_env_name(environment)
        self._records: list[ReleaseRecord] = []
        for record in records:
            self._append_checked(record)

    def __len__(self) -> int:
        return len(self._records)

    @property
    def records(self) -> tuple[ReleaseRecord, ...]:
        return tuple(self._records)

    @property
    def head(self) -> str:
        return self._records[-1].digest if self._records else GENESIS

    def _append_checked(self, record: ReleaseRecord) -> None:
        if record.environment != self.environment:
            raise DeliveryError("record environment mismatch")
        if record.sequence != len(self._records):
            raise DeliveryError("record sequence gap")
        if record.previous != self.head:
            raise DeliveryError("record chain broken")
        if self._records and record.recorded_at < self._records[-1].recorded_at:
            raise DeliveryError("records must be time-ordered")
        self._records.append(record)

    def record(
        self,
        *,
        release_id: str,
        manifest_digest: str,
        config_digest: str,
        outcome: str,
        recorded_at: int,
    ) -> ReleaseRecord:
        require_id(release_id, field="release_id")
        require_sha256(manifest_digest, field="manifest_digest")
        require_sha256(config_digest, field="config_digest")
        require_non_negative_int(recorded_at, field="recorded_at")
        if outcome not in OUTCOMES:
            raise DeliveryError(f"unknown outcome {outcome!r}")
        record = ReleaseRecord(
            len(self._records), self.environment, release_id, manifest_digest,
            config_digest, outcome, recorded_at, self.head,
        )
        self._append_checked(record)
        return record

    def current(self) -> ReleaseRecord | None:
        """The release currently serving traffic (last deployed or rolled-back target)."""
        for record in reversed(self._records):
            if record.outcome in ("deployed", "rolled-back"):
                return record
        return None

    def last_known_good(self, *, exclude_release: str | None = None) -> ReleaseRecord | None:
        failed = {r.release_id for r in self._records if r.outcome == "failed"}
        for record in reversed(self._records):
            if record.outcome != "deployed" or record.release_id in failed:
                continue
            if exclude_release is not None and record.release_id == exclude_release:
                continue
            return record
        return None

    def to_list(self) -> list[dict[str, Any]]:
        return [r.body() | {"digest": r.digest} for r in self._records]

    @classmethod
    def from_list(cls, environment: str, items: Iterable[Mapping[str, Any]]) -> "ReleaseHistory":
        records = []
        for item in items:
            body = {k: item[k] for k in ReleaseRecord.__dataclass_fields__}
            record = ReleaseRecord(**body)
            if "digest" in item and item["digest"] != record.digest:
                raise DeliveryError(f"record {record.sequence} digest mismatch")
            records.append(record)
        return cls(environment, records)
