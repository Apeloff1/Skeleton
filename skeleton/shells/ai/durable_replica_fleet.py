"""Fleet-level readiness and quorum for durable evidence replicas.

One synchronized replica is useful but does not imply resilient failover.
This module evaluates multiple independently replicated targets, enforces
minimum ready-replica and failure-domain quorum, tracks required members, and
provides bounded best-effort synchronization without hiding per-member errors.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import time
from typing import Callable

from skeleton.shells.ai.durable_replication import (
    DurableEvidenceReplicaManager,
    DurableEvidenceReplicationReport,
    DurableEvidenceReplicationRun,
)


def _identity(
    name: str,
    value: str,
    *,
    max_length: int = 128,
) -> str:
    if not value or len(value) > max_length:
        raise ValueError(f"invalid {name}")
    return value


@dataclass(frozen=True)
class DurableReplicaFleetPolicy:
    min_ready_replicas: int = 1
    min_ready_failure_domains: int = 1
    max_member_lag_items: int = 0
    require_all_required_members: bool = True
    continue_on_sync_error: bool = True

    def __post_init__(self) -> None:
        for name, lower, upper in (
            ("min_ready_replicas", 1, 1024),
            ("min_ready_failure_domains", 1, 1024),
            ("max_member_lag_items", 0, 1_000_000),
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not lower <= value <= upper
            ):
                raise ValueError(
                    f"{name} outside supported range"
                )
        for name in (
            "require_all_required_members",
            "continue_on_sync_error",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be bool")

    def to_dict(self) -> dict[str, object]:
        return {
            "min_ready_replicas": self.min_ready_replicas,
            "min_ready_failure_domains": (
                self.min_ready_failure_domains
            ),
            "max_member_lag_items": self.max_member_lag_items,
            "require_all_required_members": (
                self.require_all_required_members
            ),
            "continue_on_sync_error": (
                self.continue_on_sync_error
            ),
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class DurableReplicaFleetMember:
    target_id: str
    failure_domain: str
    manager: DurableEvidenceReplicaManager
    required: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_id",
            _identity("target_id", self.target_id),
        )
        object.__setattr__(
            self,
            "failure_domain",
            _identity(
                "failure_domain",
                self.failure_domain,
            ),
        )
        if not isinstance(
            self.manager,
            DurableEvidenceReplicaManager,
        ):
            raise TypeError(
                "manager must be DurableEvidenceReplicaManager"
            )
        if not isinstance(self.required, bool):
            raise ValueError("required must be bool")


@dataclass(frozen=True)
class DurableReplicaFleetMemberReport:
    target_id: str
    failure_domain: str
    required: bool
    replication: DurableEvidenceReplicationReport
    ready: bool
    reason: str

    def __post_init__(self) -> None:
        _identity("target_id", self.target_id)
        _identity(
            "failure_domain",
            self.failure_domain,
        )
        if not isinstance(self.required, bool):
            raise ValueError("required must be bool")
        if not isinstance(
            self.replication,
            DurableEvidenceReplicationReport,
        ):
            raise TypeError(
                "replication must be DurableEvidenceReplicationReport"
            )
        if not isinstance(self.ready, bool):
            raise ValueError("ready must be bool")
        if len(self.reason) > 2048:
            raise ValueError("member report reason too long")

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(include_digest=False),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data = {
            "target_id": self.target_id,
            "failure_domain": self.failure_domain,
            "required": self.required,
            "replication": self.replication.to_dict(),
            "ready": self.ready,
            "reason": self.reason,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableReplicaFleetFinding:
    code: str
    message: str

    def __post_init__(self) -> None:
        if not self.code or len(self.code) > 128:
            raise ValueError("invalid fleet finding code")
        if not self.message or len(self.message) > 2048:
            raise ValueError(
                "invalid fleet finding message"
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True)
class DurableReplicaFleetReport:
    source_id: str
    observed_at: float
    members: tuple[
        DurableReplicaFleetMemberReport,
        ...,
    ]
    findings: tuple[DurableReplicaFleetFinding, ...]
    policy_digest: str
    min_ready_replicas: int
    min_ready_failure_domains: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_id",
            _identity("source_id", self.source_id),
        )
        if (
            isinstance(self.observed_at, bool)
            or not isinstance(self.observed_at, (int, float))
            or not math.isfinite(float(self.observed_at))
            or float(self.observed_at) < 0.0
        ):
            raise ValueError(
                "observed_at must be finite and non-negative"
            )
        object.__setattr__(
            self,
            "observed_at",
            float(self.observed_at),
        )
        object.__setattr__(
            self,
            "members",
            tuple(self.members),
        )
        object.__setattr__(
            self,
            "findings",
            tuple(self.findings),
        )
        if not self.members:
            raise ValueError(
                "replica fleet must contain members"
            )
        ids = [
            member.target_id
            for member in self.members
        ]
        if len(ids) != len(set(ids)):
            raise ValueError(
                "replica fleet member target_ids must be unique"
            )
        if len(self.policy_digest) != 64:
            raise ValueError(
                "policy_digest must be SHA-256 hex"
            )
        for name in (
            "min_ready_replicas",
            "min_ready_failure_domains",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(
                    f"{name} must be positive integer"
                )

    @property
    def ready_members(self) -> tuple[
        DurableReplicaFleetMemberReport,
        ...,
    ]:
        return tuple(
            member
            for member in self.members
            if member.ready
        )

    @property
    def ready_targets(self) -> tuple[str, ...]:
        return tuple(
            member.target_id
            for member in self.ready_members
        )

    @property
    def ready_failure_domains(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    member.failure_domain
                    for member in self.ready_members
                }
            )
        )

    @property
    def required_members(self) -> tuple[
        DurableReplicaFleetMemberReport,
        ...,
    ]:
        return tuple(
            member
            for member in self.members
            if member.required
        )

    @property
    def required_ready(self) -> bool:
        return all(
            member.ready
            for member in self.required_members
        )

    @property
    def quorum_ready(self) -> bool:
        return (
            len(self.ready_members)
            >= self.min_ready_replicas
            and len(self.ready_failure_domains)
            >= self.min_ready_failure_domains
            and self.required_ready
        )

    @property
    def degraded(self) -> bool:
        return (
            not self.quorum_ready
            and bool(self.ready_members)
        )

    @property
    def blocked(self) -> bool:
        return not self.ready_members

    @property
    def state_digest(self) -> str:
        raw = json.dumps(
            {
                "source_id": self.source_id,
                "members": [
                    member.to_dict()
                    for member in self.members
                ],
                "findings": [
                    finding.to_dict()
                    for finding in self.findings
                ],
                "policy_digest": self.policy_digest,
                "min_ready_replicas": self.min_ready_replicas,
                "min_ready_failure_domains": (
                    self.min_ready_failure_domains
                ),
                "ready_targets": list(self.ready_targets),
                "ready_failure_domains": list(
                    self.ready_failure_domains
                ),
                "required_ready": self.required_ready,
                "quorum_ready": self.quorum_ready,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(include_digest=False),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def member(
        self,
        target_id: str,
    ) -> DurableReplicaFleetMemberReport:
        for member in self.members:
            if member.target_id == target_id:
                return member
        raise KeyError(target_id)

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data = {
            "source_id": self.source_id,
            "observed_at": self.observed_at,
            "members": [
                member.to_dict()
                for member in self.members
            ],
            "findings": [
                finding.to_dict()
                for finding in self.findings
            ],
            "policy_digest": self.policy_digest,
            "min_ready_replicas": self.min_ready_replicas,
            "min_ready_failure_domains": (
                self.min_ready_failure_domains
            ),
            "ready_targets": list(self.ready_targets),
            "ready_failure_domains": list(
                self.ready_failure_domains
            ),
            "required_ready": self.required_ready,
            "quorum_ready": self.quorum_ready,
            "degraded": self.degraded,
            "blocked": self.blocked,
            "state_digest": self.state_digest,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableReplicaFleetMemberRun:
    target_id: str
    run: DurableEvidenceReplicationRun | None
    error_type: str = ""
    error_message: str = ""

    def __post_init__(self) -> None:
        _identity("target_id", self.target_id)
        if self.run is not None and not isinstance(
            self.run,
            DurableEvidenceReplicationRun,
        ):
            raise TypeError(
                "run must be DurableEvidenceReplicationRun"
            )
        if bool(self.error_type) != bool(
            self.error_message
        ):
            raise ValueError(
                "fleet member run error fields must be paired"
            )
        if self.run is not None and self.error_type:
            raise ValueError(
                "successful fleet member run may not carry error"
            )
        if len(self.error_type) > 256:
            raise ValueError("error_type too long")
        if len(self.error_message) > 2048:
            raise ValueError("error_message too long")

    @property
    def ok(self) -> bool:
        return (
            self.run is not None
            and not self.error_type
        )

    @property
    def transferred_items(self) -> int:
        return (
            0
            if self.run is None
            else self.run.transferred_items
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "target_id": self.target_id,
            "run": (
                None
                if self.run is None
                else self.run.to_dict()
            ),
            "error_type": self.error_type,
            "error_message": self.error_message,
            "ok": self.ok,
            "transferred_items": (
                self.transferred_items
            ),
        }


@dataclass(frozen=True)
class DurableReplicaFleetRun:
    before: DurableReplicaFleetReport
    after: DurableReplicaFleetReport
    members: tuple[DurableReplicaFleetMemberRun, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "members",
            tuple(self.members),
        )
        ids = [
            member.target_id
            for member in self.members
        ]
        if len(ids) != len(set(ids)):
            raise ValueError(
                "fleet run target_ids must be unique"
            )

    @property
    def transferred_items(self) -> int:
        return sum(
            member.transferred_items
            for member in self.members
        )

    @property
    def errors(self) -> int:
        return sum(
            1
            for member in self.members
            if not member.ok
        )

    @property
    def quorum_ready(self) -> bool:
        return self.after.quorum_ready

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(include_digest=False),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data = {
            "before": self.before.to_dict(),
            "after": self.after.to_dict(),
            "members": [
                member.to_dict()
                for member in self.members
            ],
            "transferred_items": self.transferred_items,
            "errors": self.errors,
            "quorum_ready": self.quorum_ready,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableReplicaFleetError(RuntimeError):
    pass


class DurableReplicaFleet:
    """Inspect and synchronize a set of independently replicated targets."""

    def __init__(
        self,
        source_id: str,
        members: tuple[
            DurableReplicaFleetMember,
            ...,
        ],
        *,
        policy: DurableReplicaFleetPolicy | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.source_id = _identity(
            "source_id",
            source_id,
        )
        self.members = tuple(members)
        if not self.members:
            raise ValueError(
                "replica fleet must contain members"
            )
        ids = [
            member.target_id
            for member in self.members
        ]
        if len(ids) != len(set(ids)):
            raise ValueError(
                "replica fleet target_ids must be unique"
            )
        if any(
            not isinstance(
                member,
                DurableReplicaFleetMember,
            )
            for member in self.members
        ):
            raise TypeError(
                "members must be DurableReplicaFleetMember"
            )
        self.policy = (
            policy or DurableReplicaFleetPolicy()
        )
        if (
            self.policy.min_ready_replicas
            > len(self.members)
        ):
            raise ValueError(
                "min_ready_replicas exceeds fleet size"
            )
        domains = {
            member.failure_domain
            for member in self.members
        }
        if (
            self.policy.min_ready_failure_domains
            > len(domains)
        ):
            raise ValueError(
                "min_ready_failure_domains exceeds fleet domains"
            )
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._clock = clock

    def _member_report(
        self,
        member: DurableReplicaFleetMember,
    ) -> DurableReplicaFleetMemberReport:
        try:
            report = member.manager.inspect()
        except Exception as exc:
            # Preserve a concrete report-shaped failure by reusing the manager
            # only if inspection works. Unexpected exceptions are surfaced as
            # fleet inspection errors rather than guessed state.
            raise DurableReplicaFleetError(
                f"replica {member.target_id} inspection failed: "
                f"{type(exc).__name__}"
            ) from exc
        ready = (
            report.promotion_ready
            and report.max_lag_items
            <= self.policy.max_member_lag_items
        )
        reason = ""
        if not report.promotion_ready:
            reason = (
                "journal/receipt replication is not promotion ready"
            )
        elif (
            report.max_lag_items
            > self.policy.max_member_lag_items
        ):
            reason = (
                "replica lag exceeds fleet member policy"
            )
        return DurableReplicaFleetMemberReport(
            member.target_id,
            member.failure_domain,
            member.required,
            report,
            ready,
            reason,
        )

    def inspect(self) -> DurableReplicaFleetReport:
        observed_at = float(self._clock())
        if (
            not math.isfinite(observed_at)
            or observed_at < 0.0
        ):
            raise DurableReplicaFleetError(
                "replica fleet clock returned invalid time"
            )
        reports = tuple(
            self._member_report(member)
            for member in self.members
        )
        findings: list[
            DurableReplicaFleetFinding
        ] = []
        ready = tuple(
            member
            for member in reports
            if member.ready
        )
        domains = {
            member.failure_domain
            for member in ready
        }
        if len(ready) < self.policy.min_ready_replicas:
            findings.append(
                DurableReplicaFleetFinding(
                    "replica_quorum.insufficient",
                    "ready replica count is below policy quorum",
                )
            )
        if (
            len(domains)
            < self.policy.min_ready_failure_domains
        ):
            findings.append(
                DurableReplicaFleetFinding(
                    "failure_domain_quorum.insufficient",
                    "ready failure-domain count is below policy quorum",
                )
            )
        if self.policy.require_all_required_members:
            missing_required = tuple(
                member.target_id
                for member in reports
                if member.required
                and not member.ready
            )
            if missing_required:
                findings.append(
                    DurableReplicaFleetFinding(
                        "required_replica.unready",
                        "required replicas are not ready: "
                        + ",".join(missing_required),
                    )
                )
        return DurableReplicaFleetReport(
            self.source_id,
            observed_at,
            reports,
            tuple(findings),
            self.policy.digest,
            self.policy.min_ready_replicas,
            self.policy.min_ready_failure_domains,
        )

    def sync_all(
        self,
        *,
        max_batches: int | None = None,
    ) -> DurableReplicaFleetRun:
        before = self.inspect()
        runs: list[
            DurableReplicaFleetMemberRun
        ] = []
        for member in self.members:
            try:
                run = member.manager.sync(
                    max_batches=max_batches
                )
                runs.append(
                    DurableReplicaFleetMemberRun(
                        member.target_id,
                        run,
                    )
                )
            except Exception as exc:
                runs.append(
                    DurableReplicaFleetMemberRun(
                        member.target_id,
                        None,
                        type(exc).__name__,
                        str(exc)[:2048]
                        or type(exc).__name__,
                    )
                )
                if not self.policy.continue_on_sync_error:
                    raise DurableReplicaFleetError(
                        f"replica {member.target_id} sync failed"
                    ) from exc
        return DurableReplicaFleetRun(
            before,
            self.inspect(),
            tuple(runs),
        )

    def require_quorum(
        self,
        *,
        target_id: str = "",
    ) -> DurableReplicaFleetReport:
        report = self.inspect()
        if not report.quorum_ready:
            detail = (
                report.findings[0].message
                if report.findings
                else "replica fleet quorum is not ready"
            )
            raise DurableReplicaFleetError(
                detail
            )
        if target_id:
            try:
                target = report.member(
                    target_id
                )
            except KeyError as exc:
                raise DurableReplicaFleetError(
                    "requested failover target is not a fleet member"
                ) from exc
            if not target.ready:
                raise DurableReplicaFleetError(
                    "requested failover target is not ready"
                )
        return report

    def eligible_targets(self) -> tuple[str, ...]:
        report = self.require_quorum()
        return tuple(
            sorted(report.ready_targets)
        )
