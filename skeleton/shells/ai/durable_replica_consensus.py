"""Cross-replica root consensus for durable evidence failover.

Replica readiness proves that each target is locally consistent with the source
observed by its own replication manager.  It does not, by itself, prove that
independent managers agree on one source history.  This module adds that
missing fleet-level invariant.

The evaluator groups ready replicas by the exact journal/receipt source heads
they observed, requires one unique quorum across failure domains, verifies that
the selected targets are themselves caught up to those heads, and can issue a
short-lived signed certificate over the resulting state.  It is not a
Byzantine-consensus protocol and does not claim network consensus; it is a
deterministic split-brain detection and promotion-safety control.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import secrets
import time
from typing import Callable

from skeleton.shells.ai.durable_replica_fleet import (
    DurableReplicaFleet,
    DurableReplicaFleetMemberReport,
    DurableReplicaFleetReport,
)
from skeleton.shells.ai.signed_artifact import (
    ArtifactSignatureError,
    ArtifactSigner,
    SignedArtifact,
)


REPLICA_CONSENSUS_ARTIFACT_TYPE = (
    "shell-ai-durable-replica-consensus"
)


def _identity(
    name: str,
    value: str,
    *,
    max_length: int = 128,
) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be str")
    if not value or len(value) > max_length:
        raise ValueError(f"invalid {name}")
    return value


def _digest(
    name: str,
    value: str,
    *,
    optional: bool = False,
) -> str:
    if optional and not value:
        return ""
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be SHA-256 hex")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(
            f"{name} must be SHA-256 hex"
        ) from exc
    return value.lower()


def _non_negative_int(
    name: str,
    value: int,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        raise ValueError(
            f"{name} must be non-negative integer"
        )
    return value


def _stable_digest(
    value: object,
) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, order=True)
class DurableReplicaConsensusHead:
    """One candidate paired journal/receipt source history."""

    journal_sequence: int
    journal_root: str
    receipt_sequence: int
    receipt_root: str

    def __post_init__(self) -> None:
        _non_negative_int(
            "journal_sequence",
            self.journal_sequence,
        )
        _non_negative_int(
            "receipt_sequence",
            self.receipt_sequence,
        )
        object.__setattr__(
            self,
            "journal_root",
            _digest(
                "journal_root",
                self.journal_root,
            ),
        )
        object.__setattr__(
            self,
            "receipt_root",
            _digest(
                "receipt_root",
                self.receipt_root,
            ),
        )

    @property
    def digest(self) -> str:
        return _stable_digest(
            self.to_dict(
                include_digest=False
            )
        )

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "journal_sequence": self.journal_sequence,
            "journal_root": self.journal_root,
            "receipt_sequence": self.receipt_sequence,
            "receipt_root": self.receipt_root,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableReplicaConsensusPolicy:
    """Fail-closed policy for selecting one fleet history."""

    min_agreeing_replicas: int = 2
    min_agreeing_failure_domains: int = 2
    min_agreement_fraction: float = 2.0 / 3.0
    require_fleet_quorum: bool = True
    require_all_required_members: bool = True
    require_target_caught_up: bool = True
    require_member_source_integrity: bool = True
    require_member_target_integrity: bool = True
    max_members: int = 1024
    max_findings: int = 4096

    def __post_init__(self) -> None:
        for name, lower, upper in (
            ("min_agreeing_replicas", 1, 1024),
            (
                "min_agreeing_failure_domains",
                1,
                1024,
            ),
            ("max_members", 1, 4096),
            ("max_findings", 1, 65536),
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
        if (
            isinstance(
                self.min_agreement_fraction,
                bool,
            )
            or not isinstance(
                self.min_agreement_fraction,
                (int, float),
            )
            or not math.isfinite(
                float(
                    self.min_agreement_fraction
                )
            )
            or not (
                0.5
                < float(
                    self.min_agreement_fraction
                )
                <= 1.0
            )
        ):
            raise ValueError(
                "min_agreement_fraction must be in (0.5, 1.0]"
            )
        object.__setattr__(
            self,
            "min_agreement_fraction",
            float(
                self.min_agreement_fraction
            ),
        )
        for name in (
            "require_fleet_quorum",
            "require_all_required_members",
            "require_target_caught_up",
            "require_member_source_integrity",
            "require_member_target_integrity",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool"
                )

    @property
    def digest(self) -> str:
        return _stable_digest(
            self.to_dict()
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "min_agreeing_replicas": (
                self.min_agreeing_replicas
            ),
            "min_agreeing_failure_domains": (
                self.min_agreeing_failure_domains
            ),
            "min_agreement_fraction": (
                self.min_agreement_fraction
            ),
            "require_fleet_quorum": (
                self.require_fleet_quorum
            ),
            "require_all_required_members": (
                self.require_all_required_members
            ),
            "require_target_caught_up": (
                self.require_target_caught_up
            ),
            "require_member_source_integrity": (
                self.require_member_source_integrity
            ),
            "require_member_target_integrity": (
                self.require_member_target_integrity
            ),
            "max_members": self.max_members,
            "max_findings": self.max_findings,
        }


class DurableReplicaConsensusVoteState(
    str,
    Enum,
):
    AGREEING = "agreeing"
    DISSENTING = "dissenting"
    UNREADY = "unready"
    INVALID = "invalid"


@dataclass(frozen=True)
class DurableReplicaConsensusVote:
    target_id: str
    failure_domain: str
    required: bool
    ready: bool
    head: DurableReplicaConsensusHead
    target_journal_sequence: int
    target_journal_root: str
    target_receipt_sequence: int
    target_receipt_root: str
    source_valid: bool
    target_valid: bool
    replication_digest: str
    replication_policy_digest: str
    state: DurableReplicaConsensusVoteState
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_id",
            _identity(
                "target_id",
                self.target_id,
            ),
        )
        object.__setattr__(
            self,
            "failure_domain",
            _identity(
                "failure_domain",
                self.failure_domain,
            ),
        )
        if not isinstance(self.required, bool):
            raise ValueError(
                "required must be bool"
            )
        if not isinstance(self.ready, bool):
            raise ValueError(
                "ready must be bool"
            )
        if not isinstance(
            self.head,
            DurableReplicaConsensusHead,
        ):
            raise TypeError(
                "head must be DurableReplicaConsensusHead"
            )
        _non_negative_int(
            "target_journal_sequence",
            self.target_journal_sequence,
        )
        _non_negative_int(
            "target_receipt_sequence",
            self.target_receipt_sequence,
        )
        object.__setattr__(
            self,
            "target_journal_root",
            _digest(
                "target_journal_root",
                self.target_journal_root,
            ),
        )
        object.__setattr__(
            self,
            "target_receipt_root",
            _digest(
                "target_receipt_root",
                self.target_receipt_root,
            ),
        )
        if not isinstance(
            self.source_valid,
            bool,
        ):
            raise ValueError(
                "source_valid must be bool"
            )
        if not isinstance(
            self.target_valid,
            bool,
        ):
            raise ValueError(
                "target_valid must be bool"
            )
        object.__setattr__(
            self,
            "replication_digest",
            _digest(
                "replication_digest",
                self.replication_digest,
            ),
        )
        object.__setattr__(
            self,
            "replication_policy_digest",
            _digest(
                "replication_policy_digest",
                self.replication_policy_digest,
            ),
        )
        object.__setattr__(
            self,
            "state",
            DurableReplicaConsensusVoteState(
                self.state
            ),
        )
        if len(self.reason) > 2048:
            raise ValueError(
                "consensus vote reason too long"
            )

    @property
    def caught_up(self) -> bool:
        return (
            self.target_journal_sequence
            == self.head.journal_sequence
            and self.target_journal_root
            == self.head.journal_root
            and self.target_receipt_sequence
            == self.head.receipt_sequence
            and self.target_receipt_root
            == self.head.receipt_root
        )

    @property
    def digest(self) -> str:
        return _stable_digest(
            self.to_dict(
                include_digest=False
            )
        )

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "target_id": self.target_id,
            "failure_domain": (
                self.failure_domain
            ),
            "required": self.required,
            "ready": self.ready,
            "head": self.head.to_dict(),
            "target_journal_sequence": (
                self.target_journal_sequence
            ),
            "target_journal_root": (
                self.target_journal_root
            ),
            "target_receipt_sequence": (
                self.target_receipt_sequence
            ),
            "target_receipt_root": (
                self.target_receipt_root
            ),
            "source_valid": self.source_valid,
            "target_valid": self.target_valid,
            "replication_digest": (
                self.replication_digest
            ),
            "replication_policy_digest": (
                self.replication_policy_digest
            ),
            "state": self.state.value,
            "reason": self.reason,
            "caught_up": self.caught_up,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableReplicaConsensusCandidate:
    head: DurableReplicaConsensusHead
    target_ids: tuple[str, ...]
    failure_domains: tuple[str, ...]
    required_target_ids: tuple[str, ...]
    ready_voters: int
    total_ready_voters: int

    def __post_init__(self) -> None:
        if not isinstance(
            self.head,
            DurableReplicaConsensusHead,
        ):
            raise TypeError(
                "head must be DurableReplicaConsensusHead"
            )
        for name in (
            "target_ids",
            "failure_domains",
            "required_target_ids",
        ):
            values = tuple(
                getattr(self, name)
            )
            if values != tuple(
                sorted(values)
            ):
                raise ValueError(
                    f"{name} must be sorted"
                )
            if len(values) != len(
                set(values)
            ):
                raise ValueError(
                    f"{name} must be unique"
                )
            object.__setattr__(
                self,
                name,
                values,
            )
        for name in (
            "ready_voters",
            "total_ready_voters",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    f"{name} must be non-negative integer"
                )
        if self.ready_voters != len(
            self.target_ids
        ):
            raise ValueError(
                "ready_voters differs from target_ids"
            )
        if (
            self.ready_voters
            > self.total_ready_voters
        ):
            raise ValueError(
                "candidate voters exceed total ready voters"
            )

    @property
    def agreement_fraction(self) -> float:
        if not self.total_ready_voters:
            return 0.0
        return (
            self.ready_voters
            / self.total_ready_voters
        )

    @property
    def digest(self) -> str:
        return _stable_digest(
            self.to_dict(
                include_digest=False
            )
        )

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "head": self.head.to_dict(),
            "target_ids": list(
                self.target_ids
            ),
            "failure_domains": list(
                self.failure_domains
            ),
            "required_target_ids": list(
                self.required_target_ids
            ),
            "ready_voters": self.ready_voters,
            "total_ready_voters": (
                self.total_ready_voters
            ),
            "agreement_fraction": (
                self.agreement_fraction
            ),
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableReplicaConsensusFinding:
    code: str
    message: str
    target_id: str = ""

    def __post_init__(self) -> None:
        if not self.code or len(self.code) > 128:
            raise ValueError(
                "invalid consensus finding code"
            )
        if not self.message or len(self.message) > 2048:
            raise ValueError(
                "invalid consensus finding message"
            )
        if self.target_id:
            _identity(
                "target_id",
                self.target_id,
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "target_id": self.target_id,
        }


@dataclass(frozen=True)
class DurableReplicaConsensusReport:
    source_id: str
    observed_at: float
    fleet_state_digest: str
    fleet_policy_digest: str
    consensus_policy_digest: str
    votes: tuple[
        DurableReplicaConsensusVote,
        ...,
    ]
    candidates: tuple[
        DurableReplicaConsensusCandidate,
        ...,
    ]
    selected: (
        DurableReplicaConsensusCandidate
        | None
    )
    findings: tuple[
        DurableReplicaConsensusFinding,
        ...,
    ]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_id",
            _identity(
                "source_id",
                self.source_id,
            ),
        )
        if (
            isinstance(self.observed_at, bool)
            or not isinstance(
                self.observed_at,
                (int, float),
            )
            or not math.isfinite(
                float(self.observed_at)
            )
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
        for name in (
            "fleet_state_digest",
            "fleet_policy_digest",
            "consensus_policy_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(
                    name,
                    getattr(self, name),
                ),
            )
        object.__setattr__(
            self,
            "votes",
            tuple(self.votes),
        )
        object.__setattr__(
            self,
            "candidates",
            tuple(self.candidates),
        )
        object.__setattr__(
            self,
            "findings",
            tuple(self.findings),
        )
        if not self.votes:
            raise ValueError(
                "consensus report requires votes"
            )
        targets = [
            vote.target_id
            for vote in self.votes
        ]
        if targets != sorted(targets):
            raise ValueError(
                "consensus votes must be target-sorted"
            )
        if len(targets) != len(
            set(targets)
        ):
            raise ValueError(
                "consensus vote target ids must be unique"
            )
        candidate_digests = [
            item.head.digest
            for item in self.candidates
        ]
        if candidate_digests != sorted(
            candidate_digests
        ):
            raise ValueError(
                "consensus candidates must be head-digest sorted"
            )
        if len(candidate_digests) != len(
            set(candidate_digests)
        ):
            raise ValueError(
                "consensus candidate heads must be unique"
            )
        if (
            self.selected is not None
            and self.selected.head.digest
            not in set(candidate_digests)
        ):
            raise ValueError(
                "selected consensus candidate not present in candidates"
            )

    @property
    def ready_votes(self) -> tuple[
        DurableReplicaConsensusVote,
        ...,
    ]:
        return tuple(
            vote
            for vote in self.votes
            if vote.ready
        )

    @property
    def agreeing_targets(self) -> tuple[str, ...]:
        if self.selected is None:
            return ()
        return self.selected.target_ids

    @property
    def agreeing_failure_domains(
        self,
    ) -> tuple[str, ...]:
        if self.selected is None:
            return ()
        return (
            self.selected.failure_domains
        )

    @property
    def dissenting_targets(self) -> tuple[str, ...]:
        selected = set(
            self.agreeing_targets
        )
        return tuple(
            vote.target_id
            for vote in self.ready_votes
            if vote.target_id not in selected
        )

    @property
    def split_brain(self) -> bool:
        return (
            len(
                {
                    vote.head.digest
                    for vote in self.ready_votes
                }
            )
            > 1
        )

    @property
    def certifiable(self) -> bool:
        return (
            self.selected is not None
            and not self.findings
        )

    @property
    def state_digest(self) -> str:
        return _stable_digest(
            {
                "source_id": self.source_id,
                "fleet_state_digest": (
                    self.fleet_state_digest
                ),
                "fleet_policy_digest": (
                    self.fleet_policy_digest
                ),
                "consensus_policy_digest": (
                    self.consensus_policy_digest
                ),
                "votes": [
                    vote.to_dict()
                    for vote in self.votes
                ],
                "candidates": [
                    item.to_dict()
                    for item in self.candidates
                ],
                "selected": (
                    None
                    if self.selected is None
                    else self.selected.to_dict()
                ),
                "findings": [
                    item.to_dict()
                    for item in self.findings
                ],
            }
        )

    @property
    def digest(self) -> str:
        return _stable_digest(
            self.to_dict(
                include_digest=False
            )
        )

    def require_target(
        self,
        target_id: str,
    ) -> DurableReplicaConsensusVote:
        target_id = _identity(
            "target_id",
            target_id,
        )
        if not self.certifiable:
            raise DurableReplicaConsensusError(
                "replica consensus is not certifiable"
            )
        for vote in self.votes:
            if vote.target_id == target_id:
                if (
                    target_id
                    not in self.agreeing_targets
                ):
                    raise DurableReplicaConsensusError(
                        "target does not belong to consensus quorum"
                    )
                if not vote.caught_up:
                    raise DurableReplicaConsensusError(
                        "consensus target is not caught up"
                    )
                return vote
        raise DurableReplicaConsensusError(
            "target is not a consensus fleet member"
        )

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "source_id": self.source_id,
            "observed_at": self.observed_at,
            "fleet_state_digest": (
                self.fleet_state_digest
            ),
            "fleet_policy_digest": (
                self.fleet_policy_digest
            ),
            "consensus_policy_digest": (
                self.consensus_policy_digest
            ),
            "votes": [
                vote.to_dict()
                for vote in self.votes
            ],
            "candidates": [
                item.to_dict()
                for item in self.candidates
            ],
            "selected": (
                None
                if self.selected is None
                else self.selected.to_dict()
            ),
            "findings": [
                item.to_dict()
                for item in self.findings
            ],
            "ready_targets": [
                vote.target_id
                for vote in self.ready_votes
            ],
            "agreeing_targets": list(
                self.agreeing_targets
            ),
            "agreeing_failure_domains": list(
                self.agreeing_failure_domains
            ),
            "dissenting_targets": list(
                self.dissenting_targets
            ),
            "split_brain": self.split_brain,
            "certifiable": self.certifiable,
            "state_digest": self.state_digest,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableReplicaConsensusError(
    RuntimeError,
):
    pass


class DurableReplicaConsensusEvaluator:
    """Evaluate one fleet snapshot for a unique promotion-safe history."""

    def __init__(
        self,
        policy: (
            DurableReplicaConsensusPolicy
            | None
        ) = None,
    ) -> None:
        self.policy = (
            policy
            or DurableReplicaConsensusPolicy()
        )
        if not isinstance(
            self.policy,
            DurableReplicaConsensusPolicy,
        ):
            raise TypeError(
                "policy must be DurableReplicaConsensusPolicy"
            )

    @staticmethod
    def _head(
        member: DurableReplicaFleetMemberReport,
    ) -> DurableReplicaConsensusHead:
        report = member.replication
        return DurableReplicaConsensusHead(
            report.journal.source_sequence,
            report.journal.source_root,
            report.receipts.source_sequence,
            report.receipts.source_root,
        )

    @staticmethod
    def _caught_up(
        member: DurableReplicaFleetMemberReport,
    ) -> bool:
        report = member.replication
        return (
            report.journal.target_sequence
            == report.journal.source_sequence
            and report.journal.target_root
            == report.journal.source_root
            and report.receipts.target_sequence
            == report.receipts.source_sequence
            and report.receipts.target_root
            == report.receipts.source_root
        )

    def _eligible(
        self,
        member: DurableReplicaFleetMemberReport,
    ) -> tuple[bool, str]:
        report = member.replication
        if not member.ready:
            return (
                False,
                "fleet member is not ready",
            )
        if (
            self.policy.require_member_source_integrity
            and not (
                report.journal.source_valid
                and report.receipts.source_valid
            )
        ):
            return (
                False,
                "source integrity is not valid",
            )
        if (
            self.policy.require_member_target_integrity
            and not (
                report.journal.target_valid
                and report.receipts.target_valid
            )
        ):
            return (
                False,
                "target integrity is not valid",
            )
        if (
            self.policy.require_target_caught_up
            and not self._caught_up(member)
        ):
            return (
                False,
                "target does not exactly match source heads",
            )
        return True, ""

    def evaluate(
        self,
        fleet: DurableReplicaFleetReport,
    ) -> DurableReplicaConsensusReport:
        if not isinstance(
            fleet,
            DurableReplicaFleetReport,
        ):
            raise TypeError(
                "fleet must be DurableReplicaFleetReport"
            )
        if len(fleet.members) > self.policy.max_members:
            raise DurableReplicaConsensusError(
                "replica consensus member bound exceeded"
            )

        preliminary: list[
            tuple[
                DurableReplicaFleetMemberReport,
                DurableReplicaConsensusHead,
                bool,
                str,
            ]
        ] = []
        eligible_members: list[
            DurableReplicaFleetMemberReport
        ] = []
        groups: dict[
            DurableReplicaConsensusHead,
            list[
                DurableReplicaFleetMemberReport
            ],
        ] = {}

        for member in fleet.members:
            head = self._head(member)
            eligible, reason = self._eligible(
                member
            )
            preliminary.append(
                (
                    member,
                    head,
                    eligible,
                    reason,
                )
            )
            if eligible:
                eligible_members.append(
                    member
                )
                groups.setdefault(
                    head,
                    [],
                ).append(member)

        total_ready = len(
            eligible_members
        )
        candidates: list[
            DurableReplicaConsensusCandidate
        ] = []
        for head, members in groups.items():
            targets = tuple(
                sorted(
                    member.target_id
                    for member in members
                )
            )
            domains = tuple(
                sorted(
                    {
                        member.failure_domain
                        for member in members
                    }
                )
            )
            required = tuple(
                sorted(
                    member.target_id
                    for member in members
                    if member.required
                )
            )
            candidates.append(
                DurableReplicaConsensusCandidate(
                    head,
                    targets,
                    domains,
                    required,
                    len(targets),
                    total_ready,
                )
            )
        candidates.sort(
            key=lambda item: (
                item.head.digest,
            )
        )

        qualifying = tuple(
            item
            for item in candidates
            if (
                item.ready_voters
                >= self.policy.min_agreeing_replicas
                and len(
                    item.failure_domains
                )
                >= self.policy.min_agreeing_failure_domains
                and item.agreement_fraction
                >= self.policy.min_agreement_fraction
            )
        )

        findings: list[
            DurableReplicaConsensusFinding
        ] = []
        selected = (
            qualifying[0]
            if len(qualifying) == 1
            else None
        )

        if (
            self.policy.require_fleet_quorum
            and not fleet.quorum_ready
        ):
            findings.append(
                DurableReplicaConsensusFinding(
                    "consensus.fleet_quorum_unready",
                    "replica fleet quorum is not ready",
                )
            )

        if total_ready < self.policy.min_agreeing_replicas:
            findings.append(
                DurableReplicaConsensusFinding(
                    "consensus.ready_voters_insufficient",
                    "eligible ready replica count is below consensus quorum",
                )
            )

        if not qualifying:
            findings.append(
                DurableReplicaConsensusFinding(
                    "consensus.no_unique_quorum",
                    "no replica head group satisfies consensus policy",
                )
            )
        elif len(qualifying) > 1:
            findings.append(
                DurableReplicaConsensusFinding(
                    "consensus.ambiguous_quorum",
                    "multiple replica head groups satisfy consensus policy",
                )
            )

        required_targets = {
            member.target_id
            for member in fleet.members
            if member.required
        }
        if (
            self.policy.require_all_required_members
            and selected is not None
        ):
            missing = tuple(
                sorted(
                    required_targets
                    - set(
                        selected.target_ids
                    )
                )
            )
            if missing:
                findings.append(
                    DurableReplicaConsensusFinding(
                        "consensus.required_replica_missing",
                        "required replicas are outside selected consensus: "
                        + ",".join(missing),
                    )
                )

        if (
            len(
                {
                    head.digest
                    for _, head, eligible, _
                    in preliminary
                    if eligible
                }
            )
            > 1
        ):
            findings.append(
                DurableReplicaConsensusFinding(
                    "consensus.split_brain_detected",
                    "eligible replicas report more than one source history",
                )
            )

        selected_targets = (
            set()
            if selected is None
            else set(
                selected.target_ids
            )
        )
        votes: list[
            DurableReplicaConsensusVote
        ] = []
        for (
            member,
            head,
            eligible,
            reason,
        ) in preliminary:
            if not eligible:
                state = (
                    DurableReplicaConsensusVoteState.UNREADY
                    if not member.ready
                    else DurableReplicaConsensusVoteState.INVALID
                )
            elif (
                member.target_id
                in selected_targets
            ):
                state = (
                    DurableReplicaConsensusVoteState.AGREEING
                )
            else:
                state = (
                    DurableReplicaConsensusVoteState.DISSENTING
                )
            report = member.replication
            votes.append(
                DurableReplicaConsensusVote(
                    member.target_id,
                    member.failure_domain,
                    member.required,
                    member.ready,
                    head,
                    report.journal.target_sequence,
                    report.journal.target_root,
                    report.receipts.target_sequence,
                    report.receipts.target_root,
                    (
                        report.journal.source_valid
                        and report.receipts.source_valid
                    ),
                    (
                        report.journal.target_valid
                        and report.receipts.target_valid
                    ),
                    report.digest,
                    report.policy_digest,
                    state,
                    reason,
                )
            )
        votes.sort(
            key=lambda item: item.target_id
        )

        if len(findings) > self.policy.max_findings:
            raise DurableReplicaConsensusError(
                "replica consensus finding bound exceeded"
            )

        return DurableReplicaConsensusReport(
            fleet.source_id,
            fleet.observed_at,
            fleet.state_digest,
            fleet.policy_digest,
            self.policy.digest,
            tuple(votes),
            tuple(candidates),
            selected,
            tuple(findings),
        )

    def require_consensus(
        self,
        fleet: DurableReplicaFleetReport,
        *,
        target_id: str = "",
    ) -> DurableReplicaConsensusReport:
        report = self.evaluate(fleet)
        if not report.certifiable:
            detail = (
                report.findings[0].message
                if report.findings
                else "replica consensus is not certifiable"
            )
            raise DurableReplicaConsensusError(
                detail
            )
        if target_id:
            report.require_target(
                target_id
            )
        return report


@dataclass(frozen=True)
class DurableReplicaConsensusCertificate:
    schema_version: int
    certificate_id: str
    source_id: str
    issued_at: float
    expires_at: float
    nonce: str
    consensus_state_digest: str
    consensus_policy_digest: str
    fleet_state_digest: str
    fleet_policy_digest: str
    journal_sequence: int
    journal_root: str
    receipt_sequence: int
    receipt_root: str
    agreeing_targets: tuple[str, ...]
    agreeing_failure_domains: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported replica consensus certificate schema"
            )
        object.__setattr__(
            self,
            "certificate_id",
            _digest(
                "certificate_id",
                self.certificate_id,
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _identity(
                "source_id",
                self.source_id,
            ),
        )
        for name in (
            "issued_at",
            "expires_at",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(
                    value,
                    (int, float),
                )
                or not math.isfinite(
                    float(value)
                )
                or float(value) < 0.0
            ):
                raise ValueError(
                    f"{name} must be finite and non-negative"
                )
            object.__setattr__(
                self,
                name,
                float(value),
            )
        if self.expires_at <= self.issued_at:
            raise ValueError(
                "consensus certificate expiry must follow issue time"
            )
        if (
            not self.nonce
            or len(self.nonce) > 128
        ):
            raise ValueError(
                "invalid consensus certificate nonce"
            )
        for name in (
            "consensus_state_digest",
            "consensus_policy_digest",
            "fleet_state_digest",
            "fleet_policy_digest",
            "journal_root",
            "receipt_root",
        ):
            object.__setattr__(
                self,
                name,
                _digest(
                    name,
                    getattr(self, name),
                ),
            )
        _non_negative_int(
            "journal_sequence",
            self.journal_sequence,
        )
        _non_negative_int(
            "receipt_sequence",
            self.receipt_sequence,
        )
        for name in (
            "agreeing_targets",
            "agreeing_failure_domains",
        ):
            values = tuple(
                getattr(self, name)
            )
            if not values:
                raise ValueError(
                    f"{name} must not be empty"
                )
            if values != tuple(
                sorted(values)
            ):
                raise ValueError(
                    f"{name} must be sorted"
                )
            if len(values) != len(
                set(values)
            ):
                raise ValueError(
                    f"{name} must be unique"
                )
            object.__setattr__(
                self,
                name,
                values,
            )

    @property
    def head(self) -> DurableReplicaConsensusHead:
        return DurableReplicaConsensusHead(
            self.journal_sequence,
            self.journal_root,
            self.receipt_sequence,
            self.receipt_root,
        )

    @staticmethod
    def derive_id(
        *,
        source_id: str,
        issued_at: float,
        expires_at: float,
        nonce: str,
        consensus_state_digest: str,
        journal_root: str,
        receipt_root: str,
        agreeing_targets: tuple[str, ...],
    ) -> str:
        return _stable_digest(
            {
                "source_id": source_id,
                "issued_at": issued_at,
                "expires_at": expires_at,
                "nonce": nonce,
                "consensus_state_digest": (
                    consensus_state_digest
                ),
                "journal_root": journal_root,
                "receipt_root": receipt_root,
                "agreeing_targets": list(
                    agreeing_targets
                ),
            }
        )

    @property
    def digest(self) -> str:
        return _stable_digest(
            self.to_dict()
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "certificate_id": (
                self.certificate_id
            ),
            "source_id": self.source_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "nonce": self.nonce,
            "consensus_state_digest": (
                self.consensus_state_digest
            ),
            "consensus_policy_digest": (
                self.consensus_policy_digest
            ),
            "fleet_state_digest": (
                self.fleet_state_digest
            ),
            "fleet_policy_digest": (
                self.fleet_policy_digest
            ),
            "journal_sequence": (
                self.journal_sequence
            ),
            "journal_root": self.journal_root,
            "receipt_sequence": (
                self.receipt_sequence
            ),
            "receipt_root": self.receipt_root,
            "agreeing_targets": list(
                self.agreeing_targets
            ),
            "agreeing_failure_domains": list(
                self.agreeing_failure_domains
            ),
        }


@dataclass(frozen=True)
class SignedDurableReplicaConsensusCertificate:
    certificate: DurableReplicaConsensusCertificate
    signature: SignedArtifact

    def __post_init__(self) -> None:
        if not isinstance(
            self.certificate,
            DurableReplicaConsensusCertificate,
        ):
            raise TypeError(
                "certificate must be DurableReplicaConsensusCertificate"
            )
        if not isinstance(
            self.signature,
            SignedArtifact,
        ):
            raise TypeError(
                "signature must be SignedArtifact"
            )
        if (
            self.signature.artifact_type
            != REPLICA_CONSENSUS_ARTIFACT_TYPE
        ):
            raise ValueError(
                "invalid replica consensus signature artifact type"
            )
        if (
            self.signature.artifact_digest
            != self.certificate.digest
        ):
            raise ValueError(
                "replica consensus signature does not bind certificate"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "certificate": (
                self.certificate.to_dict()
            ),
            "certificate_digest": (
                self.certificate.digest
            ),
            "signature": (
                self.signature.to_dict()
            ),
        }


class DurableReplicaConsensusAuthority:
    """Issue and verify short-lived certificates over one consensus state."""

    def __init__(
        self,
        signer: ArtifactSigner,
        evaluator: DurableReplicaConsensusEvaluator,
        *,
        max_ttl_seconds: float = 300.0,
        max_clock_skew_seconds: float = 5.0,
        clock: Callable[[], float] = time.time,
        nonce_factory: (
            Callable[[], str] | None
        ) = None,
    ) -> None:
        if not isinstance(
            signer,
            ArtifactSigner,
        ):
            raise TypeError(
                "signer must be ArtifactSigner"
            )
        if not isinstance(
            evaluator,
            DurableReplicaConsensusEvaluator,
        ):
            raise TypeError(
                "evaluator must be DurableReplicaConsensusEvaluator"
            )
        for name, value in (
            (
                "max_ttl_seconds",
                max_ttl_seconds,
            ),
            (
                "max_clock_skew_seconds",
                max_clock_skew_seconds,
            ),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(
                    value,
                    (int, float),
                )
                or not math.isfinite(
                    float(value)
                )
                or float(value) <= 0.0
            ):
                raise ValueError(
                    f"{name} must be finite and positive"
                )
        if not callable(clock):
            raise TypeError(
                "clock must be callable"
            )
        if (
            nonce_factory is not None
            and not callable(nonce_factory)
        ):
            raise TypeError(
                "nonce_factory must be callable"
            )
        self.signer = signer
        self.evaluator = evaluator
        self.max_ttl_seconds = float(
            max_ttl_seconds
        )
        self.max_clock_skew_seconds = float(
            max_clock_skew_seconds
        )
        self._clock = clock
        self._nonce_factory = (
            nonce_factory
            or (
                lambda: secrets.token_hex(16)
            )
        )

    def issue(
        self,
        fleet: DurableReplicaFleetReport,
        *,
        ttl_seconds: float = 60.0,
        target_id: str = "",
    ) -> SignedDurableReplicaConsensusCertificate:
        if (
            isinstance(ttl_seconds, bool)
            or not isinstance(
                ttl_seconds,
                (int, float),
            )
            or not math.isfinite(
                float(ttl_seconds)
            )
            or float(ttl_seconds) <= 0.0
            or float(ttl_seconds)
            > self.max_ttl_seconds
        ):
            raise ValueError(
                "ttl_seconds outside supported range"
            )
        report = (
            self.evaluator
            .require_consensus(
                fleet,
                target_id=target_id,
            )
        )
        selected = report.selected
        if selected is None:
            raise DurableReplicaConsensusError(
                "consensus report has no selected head"
            )
        now = float(self._clock())
        if (
            not math.isfinite(now)
            or now < 0.0
        ):
            raise DurableReplicaConsensusError(
                "consensus clock returned invalid time"
            )
        expires_at = (
            now + float(ttl_seconds)
        )
        nonce = str(
            self._nonce_factory()
        )
        if (
            not nonce
            or len(nonce) > 128
        ):
            raise DurableReplicaConsensusError(
                "consensus nonce factory returned invalid value"
            )
        certificate_id = (
            DurableReplicaConsensusCertificate
            .derive_id(
                source_id=report.source_id,
                issued_at=now,
                expires_at=expires_at,
                nonce=nonce,
                consensus_state_digest=(
                    report.state_digest
                ),
                journal_root=(
                    selected.head.journal_root
                ),
                receipt_root=(
                    selected.head.receipt_root
                ),
                agreeing_targets=(
                    selected.target_ids
                ),
            )
        )
        certificate = (
            DurableReplicaConsensusCertificate(
                1,
                certificate_id,
                report.source_id,
                now,
                expires_at,
                nonce,
                report.state_digest,
                report.consensus_policy_digest,
                report.fleet_state_digest,
                report.fleet_policy_digest,
                selected.head.journal_sequence,
                selected.head.journal_root,
                selected.head.receipt_sequence,
                selected.head.receipt_root,
                selected.target_ids,
                selected.failure_domains,
            )
        )
        signature = self.signer.sign(
            REPLICA_CONSENSUS_ARTIFACT_TYPE,
            certificate.digest,
            metadata={
                "certificate_id": (
                    certificate.certificate_id
                ),
                "source_id": (
                    certificate.source_id
                ),
                "expires_at": repr(
                    certificate.expires_at
                ),
                "consensus_state_digest": (
                    certificate
                    .consensus_state_digest
                ),
            },
        )
        return (
            SignedDurableReplicaConsensusCertificate(
                certificate,
                signature,
            )
        )

    def verify_static(
        self,
        signed: SignedDurableReplicaConsensusCertificate,
        *,
        source_id: str = "",
        target_id: str = "",
        enforce_time: bool = True,
    ) -> DurableReplicaConsensusCertificate:
        if not isinstance(
            signed,
            SignedDurableReplicaConsensusCertificate,
        ):
            raise TypeError(
                "signed must be SignedDurableReplicaConsensusCertificate"
            )
        if not isinstance(
            enforce_time,
            bool,
        ):
            raise ValueError(
                "enforce_time must be bool"
            )
        try:
            self.signer.verify(
                signed.signature
            )
        except ArtifactSignatureError as exc:
            raise DurableReplicaConsensusError(
                "replica consensus certificate signature verification failed"
            ) from exc
        certificate = signed.certificate
        if (
            source_id
            and certificate.source_id
            != source_id
        ):
            raise DurableReplicaConsensusError(
                "replica consensus source_id mismatch"
            )
        if (
            target_id
            and target_id
            not in certificate.agreeing_targets
        ):
            raise DurableReplicaConsensusError(
                "target is not covered by replica consensus certificate"
            )
        metadata = signed.signature.metadata
        if (
            metadata.get(
                "certificate_id"
            )
            != certificate.certificate_id
            or metadata.get(
                "source_id"
            )
            != certificate.source_id
            or metadata.get(
                "expires_at"
            )
            != repr(
                certificate.expires_at
            )
            or metadata.get(
                "consensus_state_digest"
            )
            != certificate.consensus_state_digest
        ):
            raise DurableReplicaConsensusError(
                "replica consensus signed metadata mismatch"
            )

        if enforce_time:
            now = float(self._clock())
            if (
                not math.isfinite(now)
                or now < 0.0
            ):
                raise DurableReplicaConsensusError(
                    "consensus clock returned invalid time"
                )
            if (
                certificate.issued_at
                > now
                + self.max_clock_skew_seconds
            ):
                raise DurableReplicaConsensusError(
                    "consensus certificate issue time is too far in future"
                )
            if now > certificate.expires_at:
                raise DurableReplicaConsensusError(
                    "replica consensus certificate expired"
                )
            if (
                certificate.expires_at
                - certificate.issued_at
                > self.max_ttl_seconds
            ):
                raise DurableReplicaConsensusError(
                    "replica consensus certificate TTL exceeds authority maximum"
                )
            if (
                abs(
                    signed.signature.issued_at
                    - certificate.issued_at
                )
                > self.max_clock_skew_seconds
            ):
                raise DurableReplicaConsensusError(
                    "consensus signature/certificate issue times differ"
                )
        return certificate

    def verify_report(
        self,
        signed: SignedDurableReplicaConsensusCertificate,
        fleet: DurableReplicaFleetReport,
        *,
        target_id: str = "",
    ) -> DurableReplicaConsensusReport:
        certificate = self.verify_static(
            signed,
            source_id=fleet.source_id,
            target_id=target_id,
            enforce_time=True,
        )
        report = (
            self.evaluator
            .require_consensus(
                fleet,
                target_id=target_id,
            )
        )
        selected = report.selected
        if selected is None:
            raise DurableReplicaConsensusError(
                "live consensus has no selected head"
            )
        checks = (
            (
                certificate.consensus_state_digest,
                report.state_digest,
                "live consensus state differs from certificate",
            ),
            (
                certificate.consensus_policy_digest,
                report.consensus_policy_digest,
                "live consensus policy differs from certificate",
            ),
            (
                certificate.fleet_state_digest,
                report.fleet_state_digest,
                "live fleet state differs from certificate",
            ),
            (
                certificate.fleet_policy_digest,
                report.fleet_policy_digest,
                "live fleet policy differs from certificate",
            ),
            (
                certificate.journal_root,
                selected.head.journal_root,
                "live journal consensus root differs from certificate",
            ),
            (
                certificate.receipt_root,
                selected.head.receipt_root,
                "live receipt consensus root differs from certificate",
            ),
        )
        for expected, actual, message in checks:
            if expected != actual:
                raise DurableReplicaConsensusError(
                    message
                )
        if (
            certificate.journal_sequence
            != selected.head.journal_sequence
        ):
            raise DurableReplicaConsensusError(
                "live journal consensus sequence differs from certificate"
            )
        if (
            certificate.receipt_sequence
            != selected.head.receipt_sequence
        ):
            raise DurableReplicaConsensusError(
                "live receipt consensus sequence differs from certificate"
            )
        if (
            certificate.agreeing_targets
            != selected.target_ids
        ):
            raise DurableReplicaConsensusError(
                "live consensus target set differs from certificate"
            )
        if (
            certificate.agreeing_failure_domains
            != selected.failure_domains
        ):
            raise DurableReplicaConsensusError(
                "live consensus failure-domain set differs from certificate"
            )
        return report

    def verify_fleet(
        self,
        signed: SignedDurableReplicaConsensusCertificate,
        fleet: DurableReplicaFleet,
        *,
        target_id: str = "",
    ) -> DurableReplicaConsensusReport:
        if not isinstance(
            fleet,
            DurableReplicaFleet,
        ):
            raise TypeError(
                "fleet must be DurableReplicaFleet"
            )
        return self.verify_report(
            signed,
            fleet.inspect(),
            target_id=target_id,
        )
