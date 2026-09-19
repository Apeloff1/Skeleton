"""Fail-closed restore validation for signed durable backup manifests.

The verifier compares a restored target against a signed backup manifest and
its signed consistency barrier.  It can require an exact barrier head or allow
strict descendants, but it never treats same-sequence different-root state as
acceptable.  Historical segment commitments are re-hashed from the restored
chain so a valid head alone cannot hide missing or substituted interior data.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
import hashlib
import json
from typing import Iterable, Mapping

from skeleton.shells.ai.durable_backup_manifest import (
    DurableBackupChainManifest,
    DurableBackupManifest,
    DurableBackupManifestStore,
)
from skeleton.shells.ai.durable_consistency_barrier import (
    DurableConsistencyBarrier,
    DurableConsistencyBarrierStore,
)


GENESIS_HASH = "0" * 64


def _stable_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _canonical_item(item: object) -> object:
    to_dict = getattr(item, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    if is_dataclass(item):
        return asdict(item)
    if isinstance(item, Mapping):
        return dict(item)
    raise TypeError(
        "restore segment items must provide to_dict or be dataclasses/mappings"
    )


class DurableRestoreMode(str, Enum):
    EXACT_BARRIER = "exact_barrier"
    DESCENDANT_ALLOWED = "descendant_allowed"


class DurableRestoreChainState(str, Enum):
    VERIFIED = "verified"
    INCOMPLETE = "incomplete"
    DIVERGED = "diverged"
    CORRUPT = "corrupt"


class DurableRestoreState(str, Enum):
    VERIFIED = "verified"
    INCOMPLETE = "incomplete"
    DIVERGED = "diverged"
    CORRUPT = "corrupt"


@dataclass(frozen=True)
class DurableRestorePolicy:
    max_chains: int = 32
    max_segment_items: int = 100_000
    require_chain_verify: bool = True
    require_segment_digest: bool = True
    require_member_binding: bool = True

    def __post_init__(self) -> None:
        for name in (
            "max_chains",
            "max_segment_items",
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
        for name in (
            "require_chain_verify",
            "require_segment_digest",
            "require_member_binding",
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
            "max_chains": self.max_chains,
            "max_segment_items": (
                self.max_segment_items
            ),
            "require_chain_verify": (
                self.require_chain_verify
            ),
            "require_segment_digest": (
                self.require_segment_digest
            ),
            "require_member_binding": (
                self.require_member_binding
            ),
        }


@dataclass(frozen=True)
class DurableRestoreFinding:
    code: str
    message: str

    def __post_init__(self) -> None:
        if not self.code or len(self.code) > 128:
            raise ValueError(
                "invalid restore finding code"
            )
        if (
            not self.message
            or len(self.message) > 2048
        ):
            raise ValueError(
                "invalid restore finding message"
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True)
class DurableRestoreChainReport:
    chain_id: str
    state: DurableRestoreChainState
    expected_sequence: int
    expected_root: str
    current_sequence: int | None
    current_root: str
    exact_head: bool
    expected_root_is_ancestor: bool
    segment_available: bool
    segment_verified: bool
    segment_digest_match: bool
    member_binding_match: bool
    archive_binding_match: bool
    findings: tuple[DurableRestoreFinding, ...]

    def __post_init__(self) -> None:
        if (
            not self.chain_id
            or len(self.chain_id) > 128
        ):
            raise ValueError(
                "invalid restore chain_id"
            )
        object.__setattr__(
            self,
            "state",
            DurableRestoreChainState(
                self.state
            ),
        )
        if (
            isinstance(self.expected_sequence, bool)
            or not isinstance(
                self.expected_sequence,
                int,
            )
            or self.expected_sequence < 0
        ):
            raise ValueError(
                "expected_sequence must be non-negative"
            )
        if len(self.expected_root) != 64:
            raise ValueError(
                "expected_root must be digest-shaped"
            )
        if self.current_sequence is not None and (
            isinstance(self.current_sequence, bool)
            or not isinstance(
                self.current_sequence,
                int,
            )
            or self.current_sequence < 0
        ):
            raise ValueError(
                "current_sequence must be non-negative when present"
            )
        if (
            self.current_root
            and len(self.current_root) != 64
        ):
            raise ValueError(
                "current_root must be digest-shaped when present"
            )
        for name in (
            "exact_head",
            "expected_root_is_ancestor",
            "segment_available",
            "segment_verified",
            "segment_digest_match",
            "member_binding_match",
            "archive_binding_match",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool"
                )
        object.__setattr__(
            self,
            "findings",
            tuple(self.findings),
        )

    @property
    def ok(self) -> bool:
        return (
            self.state
            is DurableRestoreChainState.VERIFIED
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "state": self.state.value,
            "ok": self.ok,
            "expected_sequence": (
                self.expected_sequence
            ),
            "expected_root": self.expected_root,
            "current_sequence": (
                self.current_sequence
            ),
            "current_root": self.current_root,
            "exact_head": self.exact_head,
            "expected_root_is_ancestor": (
                self.expected_root_is_ancestor
            ),
            "segment_available": (
                self.segment_available
            ),
            "segment_verified": (
                self.segment_verified
            ),
            "segment_digest_match": (
                self.segment_digest_match
            ),
            "member_binding_match": (
                self.member_binding_match
            ),
            "archive_binding_match": (
                self.archive_binding_match
            ),
            "findings": [
                item.to_dict()
                for item in self.findings
            ],
        }


@dataclass(frozen=True)
class DurableRestoreReport:
    manifest_id: str
    manifest_digest: str
    barrier_id: str
    barrier_digest: str
    mode: DurableRestoreMode
    policy_digest: str
    state: DurableRestoreState
    chains: tuple[DurableRestoreChainReport, ...]
    findings: tuple[DurableRestoreFinding, ...]

    def __post_init__(self) -> None:
        for name in (
            "manifest_id",
            "manifest_digest",
            "barrier_id",
            "barrier_digest",
            "policy_digest",
        ):
            value = getattr(self, name)
            if len(value) != 64:
                raise ValueError(
                    f"{name} must be digest-shaped"
                )
        object.__setattr__(
            self,
            "mode",
            DurableRestoreMode(
                self.mode
            ),
        )
        object.__setattr__(
            self,
            "state",
            DurableRestoreState(
                self.state
            ),
        )
        chains = tuple(self.chains)
        chain_ids = tuple(
            item.chain_id for item in chains
        )
        if chain_ids != tuple(sorted(chain_ids)):
            raise ValueError(
                "restore chain reports must be sorted"
            )
        if len(chain_ids) != len(set(chain_ids)):
            raise ValueError(
                "duplicate restore chain report"
            )
        object.__setattr__(
            self,
            "chains",
            chains,
        )
        object.__setattr__(
            self,
            "findings",
            tuple(self.findings),
        )

    @property
    def ok(self) -> bool:
        return (
            self.state
            is DurableRestoreState.VERIFIED
        )

    @property
    def incomplete(self) -> bool:
        return (
            self.state
            is DurableRestoreState.INCOMPLETE
        )

    @property
    def diverged(self) -> bool:
        return (
            self.state
            is DurableRestoreState.DIVERGED
        )

    @property
    def corrupt(self) -> bool:
        return (
            self.state
            is DurableRestoreState.CORRUPT
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
            "manifest_id": self.manifest_id,
            "manifest_digest": (
                self.manifest_digest
            ),
            "barrier_id": self.barrier_id,
            "barrier_digest": (
                self.barrier_digest
            ),
            "mode": self.mode.value,
            "policy_digest": (
                self.policy_digest
            ),
            "state": self.state.value,
            "ok": self.ok,
            "incomplete": self.incomplete,
            "diverged": self.diverged,
            "corrupt": self.corrupt,
            "chains": [
                item.to_dict()
                for item in self.chains
            ],
            "findings": [
                item.to_dict()
                for item in self.findings
            ],
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableRestoreValidationError(RuntimeError):
    pass


class DurableRestoreVerifier:
    """Verify restored chain state against a signed backup/barrier pair."""

    def __init__(
        self,
        barrier_store: DurableConsistencyBarrierStore,
        manifest_store: DurableBackupManifestStore,
        *,
        policy: DurableRestorePolicy
        | None = None,
    ) -> None:
        if not isinstance(
            barrier_store,
            DurableConsistencyBarrierStore,
        ):
            raise TypeError(
                "barrier_store must be DurableConsistencyBarrierStore"
            )
        if not isinstance(
            manifest_store,
            DurableBackupManifestStore,
        ):
            raise TypeError(
                "manifest_store must be DurableBackupManifestStore"
            )
        self.barrier_store = barrier_store
        self.manifest_store = (
            manifest_store
        )
        self.policy = (
            policy or DurableRestorePolicy()
        )
        if not isinstance(
            self.policy,
            DurableRestorePolicy,
        ):
            raise TypeError(
                "policy must be DurableRestorePolicy"
            )

    def _entries(
        self,
        chains: Iterable[
            tuple[str, object]
        ],
    ) -> dict[str, object]:
        values = tuple(chains)
        if len(values) > self.policy.max_chains:
            raise DurableRestoreValidationError(
                "restore chain bound exceeded"
            )
        result: dict[str, object] = {}
        for value in values:
            if (
                not isinstance(value, tuple)
                or len(value) != 2
            ):
                raise ValueError(
                    "restore chains must be (chain_id, chain) pairs"
                )
            chain_id, chain = value
            if (
                not isinstance(chain_id, str)
                or not chain_id
                or len(chain_id) > 128
            ):
                raise ValueError(
                    "invalid restore chain_id"
                )
            if chain_id in result:
                raise ValueError(
                    "duplicate restore chain_id"
                )
            for method in (
                "head",
                "verify",
                "snapshot_segment",
                "verify_segment",
            ):
                if not callable(
                    getattr(chain, method, None)
                ):
                    raise TypeError(
                        f"restore chain {chain_id} does not implement {method}"
                    )
            result[chain_id] = chain
        return result

    @staticmethod
    def _overall_state(
        chains: tuple[
            DurableRestoreChainReport,
            ...,
        ],
        findings: tuple[
            DurableRestoreFinding,
            ...,
        ],
    ) -> DurableRestoreState:
        if any(
            item.state
            is DurableRestoreChainState.CORRUPT
            for item in chains
        ):
            return DurableRestoreState.CORRUPT
        if any(
            item.state
            is DurableRestoreChainState.DIVERGED
            for item in chains
        ):
            return DurableRestoreState.DIVERGED
        if any(
            item.state
            is DurableRestoreChainState.INCOMPLETE
            for item in chains
        ):
            return DurableRestoreState.INCOMPLETE
        if findings:
            return DurableRestoreState.CORRUPT
        return DurableRestoreState.VERIFIED

    def _verify_member(
        self,
        member: DurableBackupChainManifest,
        barrier: DurableConsistencyBarrier,
        chain: object,
        mode: DurableRestoreMode,
    ) -> DurableRestoreChainReport:
        findings: list[
            DurableRestoreFinding
        ] = []
        try:
            barrier_member = barrier.member(
                member.chain_id
            )
        except KeyError:
            return DurableRestoreChainReport(
                member.chain_id,
                DurableRestoreChainState.CORRUPT,
                member.barrier_head_sequence,
                member.barrier_head_root,
                None,
                "",
                False,
                False,
                False,
                False,
                False,
                False,
                False,
                (
                    DurableRestoreFinding(
                        "barrier.member_missing",
                        "backup chain is absent from signed barrier",
                    ),
                ),
            )

        member_binding_match = (
            member.barrier_member_digest
            == barrier_member.digest
        )
        if (
            self.policy.require_member_binding
            and not member_binding_match
        ):
            findings.append(
                DurableRestoreFinding(
                    "barrier.member_digest_mismatch",
                    "backup chain binding differs from signed barrier member",
                )
            )

        try:
            head = chain.head()
            current_sequence = int(
                head.sequence
            )
            current_root = str(
                head.root_hash
            )
        except Exception:
            return DurableRestoreChainReport(
                member.chain_id,
                DurableRestoreChainState.CORRUPT,
                member.barrier_head_sequence,
                member.barrier_head_root,
                None,
                "",
                False,
                False,
                False,
                False,
                False,
                member_binding_match,
                False,
                tuple(findings)
                + (
                    DurableRestoreFinding(
                        "chain.head_invalid",
                        "restored chain head has invalid shape",
                    ),
                ),
            )
        if (
            current_sequence < 0
            or len(current_root) != 64
        ):
            findings.append(
                DurableRestoreFinding(
                    "chain.head_invalid",
                    "restored chain head is invalid",
                )
            )

        if (
            self.policy.require_chain_verify
            and not bool(chain.verify())
        ):
            findings.append(
                DurableRestoreFinding(
                    "chain.integrity_failed",
                    "restored chain failed integrity verification",
                )
            )

        exact_head = (
            current_sequence
            == member.barrier_head_sequence
            and current_root
            == member.barrier_head_root
        )
        ancestor = exact_head

        if (
            current_sequence
            < member.barrier_head_sequence
        ):
            findings.append(
                DurableRestoreFinding(
                    "chain.rollback",
                    "restored chain is behind backup barrier sequence",
                )
            )
        elif (
            current_sequence
            == member.barrier_head_sequence
            and current_root
            != member.barrier_head_root
        ):
            findings.append(
                DurableRestoreFinding(
                    "chain.same_sequence_divergence",
                    "restored chain has different root at backup sequence",
                )
            )
        elif (
            current_sequence
            > member.barrier_head_sequence
        ):
            root_is_ancestor = getattr(
                chain,
                "root_is_ancestor",
                None,
            )
            if callable(root_is_ancestor):
                try:
                    ancestor = bool(
                        root_is_ancestor(
                            member.barrier_head_root
                        )
                    )
                except Exception:
                    ancestor = False
            else:
                root_for_sequence = getattr(
                    chain,
                    "root_for_sequence",
                    None,
                )
                if callable(
                    root_for_sequence
                ):
                    try:
                        ancestor = (
                            str(
                                root_for_sequence(
                                    member.barrier_head_sequence
                                )
                            )
                            == member.barrier_head_root
                        )
                    except Exception:
                        ancestor = False
            if not ancestor:
                findings.append(
                    DurableRestoreFinding(
                        "chain.ancestor_missing",
                        "backup barrier root is not a committed ancestor",
                    )
                )
            elif (
                mode
                is DurableRestoreMode.EXACT_BARRIER
            ):
                findings.append(
                    DurableRestoreFinding(
                        "chain.ahead_of_exact_restore",
                        "restored chain is ahead of exact backup barrier",
                    )
                )

        segment_available = False
        segment_verified = False
        segment_digest_match = False
        expected_count = (
            member.segment_item_count
        )
        if expected_count > (
            self.policy.max_segment_items
        ):
            findings.append(
                DurableRestoreFinding(
                    "segment.bound_exceeded",
                    "backup segment exceeds restore verification bound",
                )
            )
        else:
            try:
                segment = chain.snapshot_segment(
                    member.segment_start_root,
                    member.segment_end_root,
                    max_items=(
                        self.policy.max_segment_items
                    ),
                )
                segment_available = True
                if len(segment) != expected_count:
                    findings.append(
                        DurableRestoreFinding(
                            "segment.length_mismatch",
                            "restored segment item count differs from backup",
                        )
                    )
                else:
                    segment_verified = bool(
                        chain.verify_segment(
                            member.segment_start_root,
                            member.segment_end_root,
                            max_items=(
                                self.policy.max_segment_items
                            ),
                        )
                    )
                    if not segment_verified:
                        findings.append(
                            DurableRestoreFinding(
                                "segment.verification_failed",
                                "restored segment failed chain verification",
                            )
                        )
                    canonical = [
                        _canonical_item(item)
                        for item in segment
                    ]
                    digest = _stable_digest(
                        canonical
                    )
                    segment_digest_match = (
                        digest
                        == member.segment_digest
                    )
                    if (
                        self.policy.require_segment_digest
                        and not segment_digest_match
                    ):
                        findings.append(
                            DurableRestoreFinding(
                                "segment.digest_mismatch",
                                "restored segment digest differs from backup manifest",
                            )
                        )
            except Exception as exc:
                findings.append(
                    DurableRestoreFinding(
                        "segment.unavailable",
                        "restored chain cannot materialize backup segment: "
                        f"{type(exc).__name__}",
                    )
                )

        archive_binding_match = True
        if member.prefix_archive_required:
            floor_method = getattr(
                chain,
                "hot_floor",
                None,
            )
            if callable(floor_method):
                try:
                    floor = floor_method()
                    if (
                        floor.sequence
                        == member.segment_start_sequence
                    ):
                        archive_binding_match = (
                            floor.root_hash
                            == member.segment_start_root
                            and floor.archive_id
                            == member.prefix_archive_id
                            and floor.archive_manifest_digest
                            == member.prefix_archive_manifest_digest
                        )
                    elif (
                        floor.sequence
                        > member.segment_start_sequence
                    ):
                        archive_binding_match = False
                except Exception:
                    archive_binding_match = False
            if not archive_binding_match:
                findings.append(
                    DurableRestoreFinding(
                        "archive.binding_mismatch",
                        "restored hot-floor/archive authority differs from backup",
                    )
                )

        codes = {
            item.code
            for item in findings
        }
        if any(
            code in codes
            for code in (
                "chain.head_invalid",
                "chain.integrity_failed",
                "barrier.member_digest_mismatch",
                "segment.digest_mismatch",
            )
        ):
            state = (
                DurableRestoreChainState.CORRUPT
            )
        elif any(
            code in codes
            for code in (
                "chain.same_sequence_divergence",
                "chain.ancestor_missing",
            )
        ):
            state = (
                DurableRestoreChainState.DIVERGED
            )
        elif any(
            code in codes
            for code in (
                "chain.rollback",
                "chain.ahead_of_exact_restore",
                "segment.bound_exceeded",
                "segment.length_mismatch",
                "segment.verification_failed",
                "segment.unavailable",
                "archive.binding_mismatch",
            )
        ):
            state = (
                DurableRestoreChainState.INCOMPLETE
            )
        else:
            state = (
                DurableRestoreChainState.VERIFIED
            )

        return DurableRestoreChainReport(
            member.chain_id,
            state,
            member.barrier_head_sequence,
            member.barrier_head_root,
            current_sequence,
            current_root,
            exact_head,
            ancestor,
            segment_available,
            segment_verified,
            segment_digest_match,
            member_binding_match,
            archive_binding_match,
            tuple(findings),
        )

    def verify(
        self,
        manifest_id: str,
        chains: Iterable[
            tuple[str, object]
        ],
        *,
        mode: DurableRestoreMode = (
            DurableRestoreMode.EXACT_BARRIER
        ),
    ) -> DurableRestoreReport:
        mode = DurableRestoreMode(mode)
        stored_manifest = (
            self.manifest_store.require(
                manifest_id
            )
        )
        manifest = (
            stored_manifest.signed.manifest
        )
        stored_barrier = (
            self.barrier_store.require(
                manifest.barrier_id
            )
        )
        barrier = stored_barrier.signed.barrier

        top_findings: list[
            DurableRestoreFinding
        ] = []
        if (
            barrier.digest
            != manifest.barrier_digest
        ):
            top_findings.append(
                DurableRestoreFinding(
                    "barrier.digest_mismatch",
                    "backup manifest barrier digest differs from signed barrier",
                )
            )
        if (
            barrier.barrier_name
            != manifest.barrier_name
            or barrier.generation
            != manifest.barrier_generation
        ):
            top_findings.append(
                DurableRestoreFinding(
                    "barrier.identity_mismatch",
                    "backup manifest barrier identity differs from signed barrier",
                )
            )

        by_id = self._entries(chains)
        expected_ids = {
            item.chain_id
            for item in manifest.chains
        }
        if set(by_id) != expected_ids:
            missing = sorted(
                expected_ids - set(by_id)
            )
            extra = sorted(
                set(by_id) - expected_ids
            )
            if missing:
                top_findings.append(
                    DurableRestoreFinding(
                        "chain_set.missing",
                        "restore target is missing chains: "
                        + ",".join(missing),
                    )
                )
            if extra:
                top_findings.append(
                    DurableRestoreFinding(
                        "chain_set.extra",
                        "restore target has unexpected chains: "
                        + ",".join(extra),
                    )
                )

        reports: list[
            DurableRestoreChainReport
        ] = []
        for member in manifest.chains:
            chain = by_id.get(
                member.chain_id
            )
            if chain is None:
                reports.append(
                    DurableRestoreChainReport(
                        member.chain_id,
                        DurableRestoreChainState.INCOMPLETE,
                        member.barrier_head_sequence,
                        member.barrier_head_root,
                        None,
                        "",
                        False,
                        False,
                        False,
                        False,
                        False,
                        True,
                        False,
                        (
                            DurableRestoreFinding(
                                "chain.missing",
                                "restore target chain is missing",
                            ),
                        ),
                    )
                )
                continue
            reports.append(
                self._verify_member(
                    member,
                    barrier,
                    chain,
                    mode,
                )
            )

        ordered = tuple(
            sorted(
                reports,
                key=lambda item: item.chain_id,
            )
        )
        overall = self._overall_state(
            ordered,
            tuple(top_findings),
        )
        return DurableRestoreReport(
            manifest.manifest_id,
            manifest.digest,
            barrier.barrier_id,
            barrier.digest,
            mode,
            self.policy.digest,
            overall,
            ordered,
            tuple(top_findings),
        )

    def require_verified(
        self,
        manifest_id: str,
        chains: Iterable[
            tuple[str, object]
        ],
        *,
        mode: DurableRestoreMode = (
            DurableRestoreMode.EXACT_BARRIER
        ),
    ) -> DurableRestoreReport:
        report = self.verify(
            manifest_id,
            chains,
            mode=mode,
        )
        if not report.ok:
            detail = (
                report.findings[0].message
                if report.findings
                else next(
                    (
                        finding.message
                        for chain in report.chains
                        for finding in chain.findings
                    ),
                    (
                        "durable restore validation "
                        f"is {report.state.value}"
                    ),
                )
            )
            raise DurableRestoreValidationError(
                detail
            )
        return report
