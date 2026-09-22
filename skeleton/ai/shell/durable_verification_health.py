"""Fleet-level health and admission guard for signed durable verification cursors.

This module composes DurableIncrementalVerifier across a bounded set of durable
evidence chains. Inspection is read-only: it reports whether a chain is current,
needs a bounded tail verification, needs a full replay, or is invalid. Requiring
health advances verification cursors as necessary and fails closed if any chain
cannot be brought to a signed verified state.

The guard intentionally mutates only verification metadata. It never mutates,
archives, truncates, compacts, or repairs evidence chains.
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
    DurableVerificationReport,
    DurableVerificationResult,
    DurableVerificationStatus,
    IncrementallyVerifiableChain,
)


class DurableVerificationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class DurableVerificationFleetPolicy:
    max_chains: int = 32
    max_findings: int = 256
    require_cursor_current: bool = True
    tail_pending_is_warning: bool = True
    full_required_is_warning: bool = True

    def __post_init__(self) -> None:
        for name in (
            "max_chains",
            "max_findings",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(
                    f"{name} must be a positive integer"
                )
        for name in (
            "require_cursor_current",
            "tail_pending_is_warning",
            "full_required_is_warning",
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
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "max_chains": self.max_chains,
            "max_findings": self.max_findings,
            "require_cursor_current": self.require_cursor_current,
            "tail_pending_is_warning": self.tail_pending_is_warning,
            "full_required_is_warning": self.full_required_is_warning,
        }


@dataclass(frozen=True)
class DurableVerificationFinding:
    severity: DurableVerificationSeverity
    code: str
    message: str
    chain_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "severity",
            DurableVerificationSeverity(
                self.severity
            ),
        )
        if not self.code or len(self.code) > 128:
            raise ValueError(
                "invalid durable verification finding code"
            )
        if (
            not self.message
            or len(self.message) > 2048
        ):
            raise ValueError(
                "invalid durable verification finding message"
            )
        if len(self.chain_id) > 128:
            raise ValueError(
                "durable verification chain_id too long"
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "chain_id": self.chain_id,
        }


@dataclass(frozen=True)
class DurableChainVerificationHealth:
    chain_id: str
    status: DurableVerificationStatus
    verified: bool
    current_sequence: int
    current_root: str
    cursor_sequence: int | None
    cursor_root: str
    cursor_digest: str
    tail_items: int
    full_age_seconds: float | None
    items_since_full: int | None
    published: bool
    findings: tuple[
        DurableVerificationFinding,
        ...,
    ]

    def __post_init__(self) -> None:
        if (
            not self.chain_id
            or len(self.chain_id) > 128
        ):
            raise ValueError(
                "invalid durable verification chain_id"
            )
        object.__setattr__(
            self,
            "status",
            DurableVerificationStatus(
                self.status
            ),
        )
        if not isinstance(self.verified, bool):
            raise ValueError("verified must be bool")
        if (
            isinstance(self.current_sequence, bool)
            or not isinstance(
                self.current_sequence,
                int,
            )
            or self.current_sequence < 0
        ):
            raise ValueError(
                "current_sequence must be non-negative"
            )
        if len(self.current_root) != 64:
            raise ValueError(
                "current_root must be a 64-character digest"
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
        if (
            self.cursor_root
            and len(self.cursor_root) != 64
        ):
            raise ValueError(
                "cursor_root must be a 64-character digest"
            )
        if (
            self.cursor_digest
            and len(self.cursor_digest) != 64
        ):
            raise ValueError(
                "cursor_digest must be a 64-character digest"
            )
        if (
            isinstance(self.tail_items, bool)
            or not isinstance(
                self.tail_items,
                int,
            )
            or self.tail_items < 0
        ):
            raise ValueError(
                "tail_items must be non-negative"
            )
        if not isinstance(self.published, bool):
            raise ValueError("published must be bool")
        object.__setattr__(
            self,
            "findings",
            tuple(self.findings),
        )

    @property
    def errors(self) -> int:
        return sum(
            item.severity
            is DurableVerificationSeverity.ERROR
            for item in self.findings
        )

    @property
    def warnings(self) -> int:
        return sum(
            item.severity
            is DurableVerificationSeverity.WARNING
            for item in self.findings
        )

    @property
    def ok(self) -> bool:
        return self.verified and self.errors == 0

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
            "status": self.status.value,
            "verified": self.verified,
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "current_sequence": self.current_sequence,
            "current_root": self.current_root,
            "cursor_sequence": self.cursor_sequence,
            "cursor_root": self.cursor_root,
            "cursor_digest": self.cursor_digest,
            "tail_items": self.tail_items,
            "full_age_seconds": self.full_age_seconds,
            "items_since_full": self.items_since_full,
            "published": self.published,
            "findings": [
                item.to_dict()
                for item in self.findings
            ],
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableVerificationFleetReport:
    policy_digest: str
    verifier_policy_digest: str
    chains: tuple[
        DurableChainVerificationHealth,
        ...,
    ]
    findings: tuple[
        DurableVerificationFinding,
        ...,
    ]
    advanced: bool

    def __post_init__(self) -> None:
        for name in (
            "policy_digest",
            "verifier_policy_digest",
        ):
            if len(getattr(self, name)) != 64:
                raise ValueError(
                    f"{name} must be a 64-character digest"
                )
        chains = tuple(self.chains)
        ids = tuple(
            item.chain_id
            for item in chains
        )
        if ids != tuple(sorted(ids)):
            raise ValueError(
                "verification fleet chains must be sorted"
            )
        if len(ids) != len(set(ids)):
            raise ValueError(
                "duplicate verification fleet chain_id"
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
        if not isinstance(self.advanced, bool):
            raise ValueError("advanced must be bool")

    @property
    def errors(self) -> int:
        own = sum(
            item.severity
            is DurableVerificationSeverity.ERROR
            for item in self.findings
        )
        return own + sum(
            item.errors
            for item in self.chains
        )

    @property
    def warnings(self) -> int:
        own = sum(
            item.severity
            is DurableVerificationSeverity.WARNING
            for item in self.findings
        )
        return own + sum(
            item.warnings
            for item in self.chains
        )

    @property
    def verified(self) -> int:
        return sum(
            item.verified
            for item in self.chains
        )

    @property
    def allowed(self) -> bool:
        return (
            self.errors == 0
            and all(
                item.ok
                for item in self.chains
            )
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
            "allowed": self.allowed,
            "advanced": self.advanced,
            "errors": self.errors,
            "warnings": self.warnings,
            "verified": self.verified,
            "total_chains": len(self.chains),
            "policy_digest": self.policy_digest,
            "verifier_policy_digest": (
                self.verifier_policy_digest
            ),
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


class DurableVerificationFleetError(
    RuntimeError
):
    pass


class DurableVerificationFleetGuard:
    """Read-only inspection plus fail-closed cursor advancement for a fleet."""

    def __init__(
        self,
        verifier: DurableIncrementalVerifier,
        policy: DurableVerificationFleetPolicy | None = None,
    ) -> None:
        if not isinstance(
            verifier,
            DurableIncrementalVerifier,
        ):
            raise TypeError(
                "verifier must be DurableIncrementalVerifier"
            )
        self.verifier = verifier
        self.policy = (
            policy
            or DurableVerificationFleetPolicy()
        )
        if not isinstance(
            self.policy,
            DurableVerificationFleetPolicy,
        ):
            raise TypeError(
                "policy must be DurableVerificationFleetPolicy"
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
                "at least one durable verification chain is required"
            )
        if len(entries) > self.policy.max_chains:
            raise DurableVerificationFleetError(
                "durable verification chain bound exceeded"
            )
        normalized: list[
            tuple[
                str,
                IncrementallyVerifiableChain,
            ]
        ] = []
        ids: set[str] = set()
        for item in entries:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
            ):
                raise ValueError(
                    "durable verification chain entries "
                    "must be (chain_id, chain) pairs"
                )
            chain_id, chain = item
            if (
                not isinstance(chain_id, str)
                or not chain_id
                or len(chain_id) > 128
            ):
                raise ValueError(
                    "invalid durable verification chain_id"
                )
            if chain_id in ids:
                raise ValueError(
                    "duplicate durable verification chain_id"
                )
            ids.add(chain_id)
            if not isinstance(
                chain,
                IncrementallyVerifiableChain,
            ):
                raise TypeError(
                    "durable verification chain does not "
                    "implement incremental protocol"
                )
            normalized.append(
                (chain_id, chain)
            )
        return tuple(
            sorted(
                normalized,
                key=lambda pair: pair[0],
            )
        )

    def _finding_for_status(
        self,
        chain_id: str,
        report: DurableVerificationReport,
    ) -> tuple[
        DurableVerificationFinding,
        ...,
    ]:
        findings: list[
            DurableVerificationFinding
        ] = []
        status = report.status
        if status is DurableVerificationStatus.INVALID:
            findings.append(
                DurableVerificationFinding(
                    DurableVerificationSeverity.ERROR,
                    "durable_verification.invalid",
                    (
                        "; ".join(report.reasons)
                        or "durable verification cursor is invalid"
                    ),
                    chain_id,
                )
            )
        elif status is DurableVerificationStatus.NO_CURSOR:
            findings.append(
                DurableVerificationFinding(
                    (
                        DurableVerificationSeverity.ERROR
                        if self.policy.require_cursor_current
                        else DurableVerificationSeverity.WARNING
                    ),
                    "durable_verification.cursor_missing",
                    "no signed verification cursor exists",
                    chain_id,
                )
            )
        elif status is DurableVerificationStatus.TAIL_PENDING:
            findings.append(
                DurableVerificationFinding(
                    (
                        DurableVerificationSeverity.WARNING
                        if self.policy.tail_pending_is_warning
                        else DurableVerificationSeverity.INFO
                    ),
                    "durable_verification.tail_pending",
                    (
                        "durable evidence tail requires "
                        f"{report.tail_items} item(s) of bounded verification"
                    ),
                    chain_id,
                )
            )
        elif status is DurableVerificationStatus.FULL_REQUIRED:
            findings.append(
                DurableVerificationFinding(
                    (
                        DurableVerificationSeverity.WARNING
                        if self.policy.full_required_is_warning
                        else DurableVerificationSeverity.INFO
                    ),
                    "durable_verification.full_required",
                    (
                        "; ".join(report.reasons)
                        or "periodic full durable evidence verification is required"
                    ),
                    chain_id,
                )
            )
        return tuple(findings)

    def _health_from_report(
        self,
        chain_id: str,
        report: DurableVerificationReport,
        *,
        published: bool,
        verified_override: bool | None = None,
    ) -> DurableChainVerificationHealth:
        verified = (
            report.valid
            if verified_override is None
            else verified_override
        )
        return DurableChainVerificationHealth(
            chain_id,
            report.status,
            verified,
            report.current_sequence,
            report.current_root,
            report.cursor_sequence,
            report.cursor_root,
            report.cursor_digest,
            report.tail_items,
            report.full_age_seconds,
            report.items_since_full,
            published,
            self._finding_for_status(
                chain_id,
                report,
            ),
        )

    def inspect(
        self,
        chains: Iterable[
            tuple[
                str,
                IncrementallyVerifiableChain,
            ]
        ],
    ) -> DurableVerificationFleetReport:
        entries = self._entries(chains)
        health: list[
            DurableChainVerificationHealth
        ] = []
        fleet_findings: list[
            DurableVerificationFinding
        ] = []

        for chain_id, chain in entries:
            try:
                report = self.verifier.inspect(
                    chain_id,
                    chain,
                )
                item = self._health_from_report(
                    chain_id,
                    report,
                    published=False,
                )
            except Exception as exc:
                item = DurableChainVerificationHealth(
                    chain_id,
                    DurableVerificationStatus.INVALID,
                    False,
                    0,
                    "0" * 64,
                    None,
                    "",
                    "",
                    0,
                    None,
                    None,
                    False,
                    (
                        DurableVerificationFinding(
                            DurableVerificationSeverity.ERROR,
                            "durable_verification.inspect_error",
                            (
                                "durable verification inspection raised "
                                f"{type(exc).__name__}"
                            ),
                            chain_id,
                        ),
                    ),
                )
            health.append(item)

        finding_count = (
            len(fleet_findings)
            + sum(
                len(item.findings)
                for item in health
            )
        )
        if finding_count > self.policy.max_findings:
            raise DurableVerificationFleetError(
                "durable verification finding bound exceeded"
            )

        return DurableVerificationFleetReport(
            self.policy.digest,
            self.verifier.policy.digest,
            tuple(health),
            tuple(fleet_findings),
            False,
        )

    def require(
        self,
        chains: Iterable[
            tuple[
                str,
                IncrementallyVerifiableChain,
            ]
        ],
    ) -> DurableVerificationFleetReport:
        entries = self._entries(chains)
        health: list[
            DurableChainVerificationHealth
        ] = []
        fleet_findings: list[
            DurableVerificationFinding
        ] = []
        any_published = False

        for chain_id, chain in entries:
            try:
                result: DurableVerificationResult = (
                    self.verifier.require_current(
                        chain_id,
                        chain,
                    )
                )
                any_published = (
                    any_published
                    or result.published
                )
                health.append(
                    self._health_from_report(
                        chain_id,
                        result.report,
                        published=result.published,
                        verified_override=result.valid,
                    )
                )
            except (
                DurableVerificationCursorError,
                RuntimeError,
                ValueError,
                TypeError,
            ) as exc:
                try:
                    inspected = self.verifier.inspect(
                        chain_id,
                        chain,
                    )
                    current_sequence = (
                        inspected.current_sequence
                    )
                    current_root = (
                        inspected.current_root
                    )
                    cursor_sequence = (
                        inspected.cursor_sequence
                    )
                    cursor_root = (
                        inspected.cursor_root
                    )
                    cursor_digest = (
                        inspected.cursor_digest
                    )
                    tail_items = (
                        inspected.tail_items
                    )
                    full_age_seconds = (
                        inspected.full_age_seconds
                    )
                    items_since_full = (
                        inspected.items_since_full
                    )
                except Exception:
                    current_sequence = 0
                    current_root = "0" * 64
                    cursor_sequence = None
                    cursor_root = ""
                    cursor_digest = ""
                    tail_items = 0
                    full_age_seconds = None
                    items_since_full = None
                health.append(
                    DurableChainVerificationHealth(
                        chain_id,
                        DurableVerificationStatus.INVALID,
                        False,
                        current_sequence,
                        current_root,
                        cursor_sequence,
                        cursor_root,
                        cursor_digest,
                        tail_items,
                        full_age_seconds,
                        items_since_full,
                        False,
                        (
                            DurableVerificationFinding(
                                DurableVerificationSeverity.ERROR,
                                "durable_verification.require_error",
                                (
                                    "durable verification failed: "
                                    f"{type(exc).__name__}"
                                ),
                                chain_id,
                            ),
                        ),
                    )
                )

        finding_count = (
            len(fleet_findings)
            + sum(
                len(item.findings)
                for item in health
            )
        )
        if finding_count > self.policy.max_findings:
            raise DurableVerificationFleetError(
                "durable verification finding bound exceeded"
            )

        report = DurableVerificationFleetReport(
            self.policy.digest,
            self.verifier.policy.digest,
            tuple(health),
            tuple(fleet_findings),
            any_published,
        )
        if not report.allowed:
            detail = next(
                (
                    finding.message
                    for item in report.chains
                    for finding in item.findings
                    if finding.severity
                    is DurableVerificationSeverity.ERROR
                ),
                "durable verification fleet denied admission",
            )
            raise DurableVerificationFleetError(
                detail
            )
        return report
