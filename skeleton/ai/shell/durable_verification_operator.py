"""Operator diagnostics and explicit refresh actions for durable verification.

Normal service admission uses DurableVerificationFleetGuard. Operators need a
different surface: inspect cursor lineage, compare signed cursor heads with live
chain heads, force a stronger full replay, and produce a bounded audit report.

This module never edits evidence, archives, checkpoints, retention state, or
compaction authority. The only mutation it can perform is publishing a newly
signed verification cursor after successful full verification.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Iterable

from skeleton.shells.ai.durable_verification_cursor import (
    DurableIncrementalVerifier,
    DurableVerificationCursorError,
    DurableVerificationCursorStore,
    DurableVerificationMode,
    DurableVerificationResult,
    IncrementallyVerifiableChain,
)


class DurableVerificationOperatorState(str, Enum):
    UNINITIALIZED = "uninitialized"
    CURRENT = "current"
    BEHIND = "behind"
    FORKED = "forked"
    REGRESSED = "regressed"
    LINEAGE_INVALID = "lineage_invalid"
    ERROR = "error"


@dataclass(frozen=True)
class DurableVerificationOperatorPolicy:
    max_chains: int = 32
    max_lineage_items: int = 4096

    def __post_init__(self) -> None:
        for name in (
            "max_chains",
            "max_lineage_items",
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
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "max_chains": self.max_chains,
            "max_lineage_items": (
                self.max_lineage_items
            ),
        }


@dataclass(frozen=True)
class DurableVerificationOperatorChainReport:
    chain_id: str
    state: DurableVerificationOperatorState
    live_sequence: int
    live_root: str
    cursor_sequence: int | None
    cursor_root: str
    cursor_digest: str
    lineage_items: int
    full_cursor_count: int
    incremental_cursor_count: int
    oldest_cursor_digest: str
    newest_cursor_digest: str
    lineage_valid: bool
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not self.chain_id
            or len(self.chain_id) > 128
        ):
            raise ValueError(
                "invalid operator chain_id"
            )
        object.__setattr__(
            self,
            "state",
            DurableVerificationOperatorState(
                self.state
            ),
        )
        if (
            isinstance(self.live_sequence, bool)
            or not isinstance(
                self.live_sequence,
                int,
            )
            or self.live_sequence < 0
        ):
            raise ValueError(
                "live_sequence must be non-negative"
            )
        if len(self.live_root) != 64:
            raise ValueError(
                "live_root must be digest-shaped"
            )
        if self.cursor_sequence is not None and (
            isinstance(
                self.cursor_sequence,
                bool,
            )
            or not isinstance(
                self.cursor_sequence,
                int,
            )
            or self.cursor_sequence < 0
        ):
            raise ValueError(
                "cursor_sequence must be non-negative"
            )
        for name in (
            "cursor_root",
            "cursor_digest",
            "oldest_cursor_digest",
            "newest_cursor_digest",
        ):
            value = getattr(self, name)
            if value and len(value) != 64:
                raise ValueError(
                    f"{name} must be digest-shaped"
                )
        for name in (
            "lineage_items",
            "full_cursor_count",
            "incremental_cursor_count",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    f"{name} must be non-negative"
                )
        if not isinstance(
            self.lineage_valid,
            bool,
        ):
            raise ValueError(
                "lineage_valid must be bool"
            )
        object.__setattr__(
            self,
            "reasons",
            tuple(self.reasons),
        )

    @property
    def ok(self) -> bool:
        return (
            self.state
            is DurableVerificationOperatorState.CURRENT
            and self.lineage_valid
        )

    @property
    def cursor_lag(self) -> int | None:
        if self.cursor_sequence is None:
            return None
        return max(
            0,
            self.live_sequence
            - self.cursor_sequence
        )

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(
                include_digest=False
            ),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "chain_id": self.chain_id,
            "state": self.state.value,
            "ok": self.ok,
            "live_sequence": self.live_sequence,
            "live_root": self.live_root,
            "cursor_sequence": self.cursor_sequence,
            "cursor_root": self.cursor_root,
            "cursor_digest": self.cursor_digest,
            "cursor_lag": self.cursor_lag,
            "lineage_items": self.lineage_items,
            "full_cursor_count": (
                self.full_cursor_count
            ),
            "incremental_cursor_count": (
                self.incremental_cursor_count
            ),
            "oldest_cursor_digest": (
                self.oldest_cursor_digest
            ),
            "newest_cursor_digest": (
                self.newest_cursor_digest
            ),
            "lineage_valid": self.lineage_valid,
            "reasons": list(self.reasons),
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableVerificationOperatorReport:
    policy_digest: str
    chains: tuple[
        DurableVerificationOperatorChainReport,
        ...,
    ]

    def __post_init__(self) -> None:
        if len(self.policy_digest) != 64:
            raise ValueError(
                "policy_digest must be digest-shaped"
            )
        chains = tuple(self.chains)
        ids = tuple(
            item.chain_id
            for item in chains
        )
        if ids != tuple(sorted(ids)):
            raise ValueError(
                "operator chains must be sorted"
            )
        if len(ids) != len(set(ids)):
            raise ValueError(
                "duplicate operator chain_id"
            )
        object.__setattr__(
            self,
            "chains",
            chains,
        )

    @property
    def ok(self) -> bool:
        return all(
            item.ok
            for item in self.chains
        )

    @property
    def initialized(self) -> int:
        return sum(
            item.cursor_sequence is not None
            for item in self.chains
        )

    @property
    def total_lineage_items(self) -> int:
        return sum(
            item.lineage_items
            for item in self.chains
        )

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(
                include_digest=False
            ),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "ok": self.ok,
            "initialized": self.initialized,
            "total_chains": len(self.chains),
            "total_lineage_items": (
                self.total_lineage_items
            ),
            "policy_digest": self.policy_digest,
            "chains": [
                item.to_dict()
                for item in self.chains
            ],
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableVerificationRefreshReport:
    audit_before: DurableVerificationOperatorReport
    results: tuple[
        tuple[str, DurableVerificationResult],
        ...,
    ]
    audit_after: DurableVerificationOperatorReport

    def __post_init__(self) -> None:
        results = tuple(self.results)
        ids = tuple(
            item[0]
            for item in results
        )
        if ids != tuple(sorted(ids)):
            raise ValueError(
                "refresh results must be sorted"
            )
        if len(ids) != len(set(ids)):
            raise ValueError(
                "duplicate refresh chain_id"
            )
        object.__setattr__(
            self,
            "results",
            results,
        )

    @property
    def ok(self) -> bool:
        return (
            self.audit_after.ok
            and all(
                result.valid
                for _, result in self.results
            )
        )

    @property
    def published(self) -> int:
        return sum(
            result.published
            for _, result in self.results
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "published": self.published,
            "audit_before": (
                self.audit_before.to_dict()
            ),
            "results": {
                chain_id: result.to_dict()
                for chain_id, result
                in self.results
            },
            "audit_after": (
                self.audit_after.to_dict()
            ),
        }


class DurableVerificationOperatorError(
    RuntimeError
):
    pass


class DurableVerificationOperator:
    """Bounded audit and full-refresh control plane for verification cursors."""

    def __init__(
        self,
        store: DurableVerificationCursorStore,
        verifier: DurableIncrementalVerifier,
        policy: DurableVerificationOperatorPolicy | None = None,
    ) -> None:
        if not isinstance(
            store,
            DurableVerificationCursorStore,
        ):
            raise TypeError(
                "store must be DurableVerificationCursorStore"
            )
        if not isinstance(
            verifier,
            DurableIncrementalVerifier,
        ):
            raise TypeError(
                "verifier must be DurableIncrementalVerifier"
            )
        if verifier.store is not store:
            raise ValueError(
                "operator store must match verifier store"
            )
        self.store = store
        self.verifier = verifier
        self.policy = (
            policy
            or DurableVerificationOperatorPolicy()
        )
        if not isinstance(
            self.policy,
            DurableVerificationOperatorPolicy,
        ):
            raise TypeError(
                "policy must be DurableVerificationOperatorPolicy"
            )

    def _entries(
        self,
        chains: Iterable[
            tuple[
                str,
                IncrementallyVerifiableChain,
            ]
        ],
    ) -> tuple[
        tuple[
            str,
            IncrementallyVerifiableChain,
        ],
        ...,
    ]:
        entries = tuple(chains)
        if not entries:
            raise ValueError(
                "at least one verification chain is required"
            )
        if len(entries) > self.policy.max_chains:
            raise DurableVerificationOperatorError(
                "verification operator chain bound exceeded"
            )
        normalized = []
        seen: set[str] = set()
        for item in entries:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
            ):
                raise ValueError(
                    "verification operator chain entries "
                    "must be (chain_id, chain) pairs"
                )
            chain_id, chain = item
            if (
                not isinstance(chain_id, str)
                or not chain_id
                or len(chain_id) > 128
            ):
                raise ValueError(
                    "invalid verification operator chain_id"
                )
            if chain_id in seen:
                raise ValueError(
                    "duplicate verification operator chain_id"
                )
            seen.add(chain_id)
            if not isinstance(
                chain,
                IncrementallyVerifiableChain,
            ):
                raise TypeError(
                    "verification operator chain does not "
                    "implement incremental protocol"
                )
            normalized.append(
                (chain_id, chain)
            )
        return tuple(
            sorted(
                normalized,
                key=lambda item: item[0],
            )
        )

    def _audit_chain(
        self,
        chain_id: str,
        chain: IncrementallyVerifiableChain,
    ) -> DurableVerificationOperatorChainReport:
        reasons: list[str] = []
        try:
            head = chain.head()
            live_sequence = int(
                head.sequence
            )
            live_root = str(
                head.root_hash
            )
            if (
                live_sequence < 0
                or len(live_root) != 64
            ):
                raise ValueError(
                    "invalid live chain head"
                )
        except Exception as exc:
            return DurableVerificationOperatorChainReport(
                chain_id,
                DurableVerificationOperatorState.ERROR,
                0,
                "0" * 64,
                None,
                "",
                "",
                0,
                0,
                0,
                "",
                "",
                False,
                (
                    "live chain head inspection failed: "
                    f"{type(exc).__name__}",
                ),
            )

        latest = None
        try:
            latest = self.store.latest(
                chain_id
            )
        except Exception as exc:
            reasons.append(
                "signed cursor head lookup failed: "
                f"{type(exc).__name__}"
            )
            return DurableVerificationOperatorChainReport(
                chain_id,
                DurableVerificationOperatorState.ERROR,
                live_sequence,
                live_root,
                None,
                "",
                "",
                0,
                0,
                0,
                "",
                "",
                False,
                tuple(reasons),
            )

        if latest is None:
            return DurableVerificationOperatorChainReport(
                chain_id,
                DurableVerificationOperatorState.UNINITIALIZED,
                live_sequence,
                live_root,
                None,
                "",
                "",
                0,
                0,
                0,
                "",
                "",
                False,
                (
                    "no signed verification cursor exists",
                ),
            )

        cursor = latest.item.cursor
        lineage = ()
        lineage_valid = False
        try:
            lineage = self.store.lineage(
                chain_id,
                max_items=(
                    self.policy.max_lineage_items
                ),
            )
            lineage_valid = True
        except Exception as exc:
            reasons.append(
                "signed cursor lineage audit failed: "
                f"{type(exc).__name__}"
            )

        full_count = sum(
            item.cursor.mode
            is DurableVerificationMode.FULL
            for item in lineage
        )
        incremental_count = sum(
            item.cursor.mode
            is DurableVerificationMode.INCREMENTAL
            for item in lineage
        )
        oldest_digest = (
            ""
            if not lineage
            else lineage[0].cursor.digest
        )
        newest_digest = (
            ""
            if not lineage
            else lineage[-1].cursor.digest
        )

        if not lineage_valid:
            state = (
                DurableVerificationOperatorState.LINEAGE_INVALID
            )
        elif live_sequence < cursor.sequence:
            state = (
                DurableVerificationOperatorState.REGRESSED
            )
            reasons.append(
                "live chain sequence is behind signed cursor"
            )
        elif (
            live_sequence == cursor.sequence
            and live_root != cursor.root_hash
        ):
            state = (
                DurableVerificationOperatorState.FORKED
            )
            reasons.append(
                "live chain root differs at signed cursor sequence"
            )
        elif (
            live_sequence == cursor.sequence
            and live_root == cursor.root_hash
        ):
            state = (
                DurableVerificationOperatorState.CURRENT
            )
        else:
            state = (
                DurableVerificationOperatorState.BEHIND
            )
            reasons.append(
                "signed cursor is behind live chain head"
            )

        return DurableVerificationOperatorChainReport(
            chain_id,
            state,
            live_sequence,
            live_root,
            cursor.sequence,
            cursor.root_hash,
            cursor.digest,
            len(lineage),
            full_count,
            incremental_count,
            oldest_digest,
            newest_digest,
            lineage_valid,
            tuple(reasons),
        )

    def audit(
        self,
        chains: Iterable[
            tuple[
                str,
                IncrementallyVerifiableChain,
            ]
        ],
    ) -> DurableVerificationOperatorReport:
        entries = self._entries(
            chains
        )
        reports = tuple(
            self._audit_chain(
                chain_id,
                chain,
            )
            for chain_id, chain
            in entries
        )
        return DurableVerificationOperatorReport(
            self.policy.digest,
            reports,
        )

    def require_current(
        self,
        chains: Iterable[
            tuple[
                str,
                IncrementallyVerifiableChain,
            ]
        ],
    ) -> DurableVerificationOperatorReport:
        report = self.audit(
            chains
        )
        if not report.ok:
            detail = next(
                (
                    reason
                    for item in report.chains
                    for reason in item.reasons
                ),
                "verification cursor fleet is not current",
            )
            raise DurableVerificationOperatorError(
                detail
            )
        return report

    def force_full_refresh(
        self,
        chains: Iterable[
            tuple[
                str,
                IncrementallyVerifiableChain,
            ]
        ],
    ) -> DurableVerificationRefreshReport:
        entries = self._entries(
            chains
        )
        before = self.audit(
            entries
        )
        results = []
        for chain_id, chain in entries:
            try:
                result = self.verifier.full_verify(
                    chain_id,
                    chain,
                )
            except (
                DurableVerificationCursorError,
                RuntimeError,
                ValueError,
                TypeError,
            ) as exc:
                raise DurableVerificationOperatorError(
                    "full verification refresh failed for "
                    f"{chain_id}: {type(exc).__name__}"
                ) from exc
            results.append(
                (chain_id, result)
            )
        after = self.audit(
            entries
        )
        report = DurableVerificationRefreshReport(
            before,
            tuple(results),
            after,
        )
        if not report.ok:
            raise DurableVerificationOperatorError(
                "verification fleet is not current after full refresh"
            )
        return report
