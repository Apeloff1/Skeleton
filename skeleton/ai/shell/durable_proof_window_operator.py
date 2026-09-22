"""Operator control plane for bounded durable historical proof windows.

Proof windows accelerate historical verification but never replace the
authoritative chain, sequence index, or signed checkpoint registry.  This
operator gives startup and maintenance workflows a bounded, deterministic
surface for inspection and safe cache population.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Iterable, Mapping

from skeleton.shells.ai.durable_proof_window import (
    DurableHistoricalProofAuthority,
    DurableHistoricalProofError,
    DurableHistoricalProofStore,
    DurableHistoricalProofVerification,
    SignedDurableHistoricalProofWindow,
)


def _digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _identity(
    name: str,
    value: str,
    maximum: int,
) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
    ):
        raise ValueError(f"invalid {name}")
    return value


class DurableProofWindowState(str, Enum):
    CURRENT = "current"
    MISSING = "missing"
    INVALID = "invalid"
    OUT_OF_WINDOW = "out_of_window"
    UNANCHORED = "unanchored"
    ERROR = "error"


@dataclass(frozen=True)
class DurableProofWindowPolicy:
    max_targets: int = 1024
    require_all: bool = True
    allow_build_missing: bool = True
    refresh_invalid: bool = False
    require_cached: bool = False

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_targets, bool)
            or not isinstance(
                self.max_targets,
                int,
            )
            or self.max_targets <= 0
        ):
            raise ValueError(
                "max_targets must be positive integer"
            )
        for name in (
            "require_all",
            "allow_build_missing",
            "refresh_invalid",
            "require_cached",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool"
                )
        if (
            self.require_cached
            and self.allow_build_missing
        ):
            raise ValueError(
                "require_cached conflicts with allow_build_missing"
            )

    @property
    def digest(self) -> str:
        return _digest(
            self.to_dict()
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "max_targets": self.max_targets,
            "require_all": self.require_all,
            "allow_build_missing": self.allow_build_missing,
            "refresh_invalid": self.refresh_invalid,
            "require_cached": self.require_cached,
        }


@dataclass(frozen=True)
class DurableProofWindowTarget:
    chain_id: str
    target_root: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "chain_id",
            _identity(
                "chain_id",
                self.chain_id,
                128,
            ),
        )
        if (
            not isinstance(
                self.target_root,
                str,
            )
            or len(self.target_root) != 64
        ):
            raise ValueError(
                "target_root must be digest-shaped"
            )
        try:
            int(self.target_root, 16)
        except ValueError as exc:
            raise ValueError(
                "target_root must be SHA-256 hex"
            ) from exc
        object.__setattr__(
            self,
            "target_root",
            self.target_root.lower(),
        )

    @property
    def key(self) -> str:
        return (
            self.chain_id
            + ":"
            + self.target_root
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "chain_id": self.chain_id,
            "target_root": self.target_root,
        }


@dataclass(frozen=True)
class DurableProofWindowFinding:
    code: str
    message: str

    def __post_init__(self) -> None:
        if not self.code or len(self.code) > 128:
            raise ValueError(
                "invalid proof-window finding code"
            )
        if (
            not self.message
            or len(self.message) > 2048
        ):
            raise ValueError(
                "invalid proof-window finding message"
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True)
class DurableProofWindowReport:
    target: DurableProofWindowTarget
    state: DurableProofWindowState
    cached: bool
    built: bool
    proof_digest: str
    checkpoint_sequence: int | None
    target_sequence: int | None
    checked_items: int
    verification: DurableHistoricalProofVerification | None
    findings: tuple[DurableProofWindowFinding, ...]

    def __post_init__(self) -> None:
        if not isinstance(
            self.target,
            DurableProofWindowTarget,
        ):
            raise TypeError(
                "target must be DurableProofWindowTarget"
            )
        object.__setattr__(
            self,
            "state",
            DurableProofWindowState(
                self.state
            ),
        )
        for name in (
            "cached",
            "built",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool"
                )
        if self.proof_digest:
            if len(self.proof_digest) != 64:
                raise ValueError(
                    "proof_digest must be digest-shaped"
                )
        for name in (
            "checkpoint_sequence",
            "target_sequence",
        ):
            value = getattr(
                self,
                name,
            )
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(
                    value,
                    int,
                )
                or value < 0
            ):
                raise ValueError(
                    f"{name} must be non-negative"
                )
        if (
            isinstance(self.checked_items, bool)
            or not isinstance(
                self.checked_items,
                int,
            )
            or self.checked_items < 0
        ):
            raise ValueError(
                "checked_items must be non-negative"
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
            is DurableProofWindowState.CURRENT
            and self.verification is not None
            and self.verification.valid
        )

    @property
    def repairable(self) -> bool:
        return self.state in {
            DurableProofWindowState.MISSING,
            DurableProofWindowState.INVALID,
        }

    @property
    def digest(self) -> str:
        return _digest(
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
            "target": self.target.to_dict(),
            "state": self.state.value,
            "ok": self.ok,
            "repairable": self.repairable,
            "cached": self.cached,
            "built": self.built,
            "proof_digest": self.proof_digest,
            "checkpoint_sequence": (
                self.checkpoint_sequence
            ),
            "target_sequence": (
                self.target_sequence
            ),
            "checked_items": self.checked_items,
            "verification": (
                None
                if self.verification is None
                else self.verification.to_dict()
            ),
            "findings": [
                item.to_dict()
                for item in self.findings
            ],
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableProofWindowFleetReport:
    policy_digest: str
    reports: tuple[DurableProofWindowReport, ...]
    mutations: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.policy_digest) != 64:
            raise ValueError(
                "policy_digest must be digest-shaped"
            )
        object.__setattr__(
            self,
            "reports",
            tuple(self.reports),
        )
        object.__setattr__(
            self,
            "mutations",
            tuple(self.mutations),
        )
        keys = tuple(
            item.target.key
            for item in self.reports
        )
        if keys != tuple(sorted(keys)):
            raise ValueError(
                "proof-window reports must be sorted"
            )
        if len(keys) != len(set(keys)):
            raise ValueError(
                "duplicate proof-window target report"
            )
        if len(self.mutations) != len(
            set(self.mutations)
        ):
            raise ValueError(
                "duplicate proof-window mutation"
            )

    @property
    def current(self) -> int:
        return sum(
            item.state
            is DurableProofWindowState.CURRENT
            for item in self.reports
        )

    @property
    def missing(self) -> int:
        return sum(
            item.state
            is DurableProofWindowState.MISSING
            for item in self.reports
        )

    @property
    def invalid(self) -> int:
        return sum(
            item.state
            is DurableProofWindowState.INVALID
            for item in self.reports
        )

    @property
    def out_of_window(self) -> int:
        return sum(
            item.state
            is DurableProofWindowState.OUT_OF_WINDOW
            for item in self.reports
        )

    @property
    def unanchored(self) -> int:
        return sum(
            item.state
            is DurableProofWindowState.UNANCHORED
            for item in self.reports
        )

    @property
    def errors(self) -> int:
        return sum(
            item.state
            is DurableProofWindowState.ERROR
            for item in self.reports
        )

    @property
    def ok(self) -> bool:
        return all(
            item.ok
            for item in self.reports
        )

    @property
    def repaired(self) -> bool:
        return bool(
            self.mutations
        )

    @property
    def digest(self) -> str:
        return _digest(
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
            "policy_digest": self.policy_digest,
            "reports": [
                item.to_dict()
                for item in self.reports
            ],
            "mutations": list(
                self.mutations
            ),
            "current": self.current,
            "missing": self.missing,
            "invalid": self.invalid,
            "out_of_window": (
                self.out_of_window
            ),
            "unanchored": self.unanchored,
            "errors": self.errors,
            "ok": self.ok,
            "repaired": self.repaired,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableProofWindowOperatorError(RuntimeError):
    pass


class DurableProofWindowOperator:
    """Bounded inspect/build operator for historical proof-window caches."""

    def __init__(
        self,
        authority: DurableHistoricalProofAuthority,
        store: DurableHistoricalProofStore,
        chains: Mapping[str, object],
        *,
        policy: DurableProofWindowPolicy | None = None,
    ) -> None:
        if not isinstance(
            authority,
            DurableHistoricalProofAuthority,
        ):
            raise TypeError(
                "authority must be DurableHistoricalProofAuthority"
            )
        if not isinstance(
            store,
            DurableHistoricalProofStore,
        ):
            raise TypeError(
                "store must be DurableHistoricalProofStore"
            )
        self.authority = authority
        self.store = store
        self.policy = (
            policy
            or DurableProofWindowPolicy()
        )
        normalized: dict[str, object] = {}
        for chain_id, chain in chains.items():
            chain_id = _identity(
                "chain_id",
                chain_id,
                128,
            )
            self.authority._require_chain(
                chain
            )
            if chain_id in normalized:
                raise ValueError(
                    "duplicate proof-window chain_id"
                )
            normalized[chain_id] = chain
        self.chains = normalized

    def _chain(
        self,
        chain_id: str,
    ) -> object:
        try:
            return self.chains[
                chain_id
            ]
        except KeyError as exc:
            raise DurableProofWindowOperatorError(
                "proof-window target references unknown chain"
            ) from exc

    @staticmethod
    def _state_from_error(
        exc: BaseException,
    ) -> DurableProofWindowState:
        message = str(exc).lower()
        if (
            "no signed checkpoint" in message
            or "checkpoint" in message
            and "anchor" in message
        ):
            return (
                DurableProofWindowState.UNANCHORED
            )
        if (
            "window" in message
            or "bounded" in message
        ):
            return (
                DurableProofWindowState.OUT_OF_WINDOW
            )
        return DurableProofWindowState.ERROR

    def verify_root(
        self,
        chain_id: str,
        target_root: str,
    ) -> bool:
        target = DurableProofWindowTarget(
            chain_id,
            target_root,
        )
        try:
            return self.inspect_target(
                target
            ).ok
        except Exception:
            return False

    def require_root(
        self,
        chain_id: str,
        target_root: str,
    ) -> DurableProofWindowReport:
        target = DurableProofWindowTarget(
            chain_id,
            target_root,
        )
        report = self.inspect_target(
            target
        )
        if not report.ok:
            detail = (
                report.findings[0].message
                if report.findings
                else "historical proof root is not verified"
            )
            raise DurableProofWindowOperatorError(
                detail
            )
        return report

    def inspect_target(
        self,
        target: DurableProofWindowTarget,
    ) -> DurableProofWindowReport:
        chain = self._chain(
            target.chain_id
        )
        try:
            cached = self.store.find_target(
                target.chain_id,
                target.target_root,
            )
        except Exception as exc:
            return DurableProofWindowReport(
                target,
                DurableProofWindowState.INVALID,
                True,
                False,
                "",
                None,
                None,
                0,
                None,
                (
                    DurableProofWindowFinding(
                        "proof.cache_corrupt",
                        "cached proof lookup failed: "
                        f"{type(exc).__name__}",
                    ),
                ),
            )
        if cached is None:
            return DurableProofWindowReport(
                target,
                DurableProofWindowState.MISSING,
                False,
                False,
                "",
                None,
                None,
                0,
                None,
                (
                    DurableProofWindowFinding(
                        "proof.missing",
                        "historical proof window is not cached",
                    ),
                ),
            )
        try:
            verification = (
                self.authority.verify(
                    cached,
                    chain,
                )
            )
        except Exception as exc:
            return DurableProofWindowReport(
                target,
                DurableProofWindowState.INVALID,
                True,
                False,
                cached.proof.digest,
                cached.proof.checkpoint_sequence,
                cached.proof.target_sequence,
                0,
                None,
                (
                    DurableProofWindowFinding(
                        "proof.verify_error",
                        "proof verification raised "
                        f"{type(exc).__name__}",
                    ),
                ),
            )
        state = (
            DurableProofWindowState.CURRENT
            if verification.valid
            else DurableProofWindowState.INVALID
        )
        findings = tuple(
            DurableProofWindowFinding(
                "proof.invalid",
                reason,
            )
            for reason in (
                verification.reasons
            )
        )
        return DurableProofWindowReport(
            target,
            state,
            True,
            False,
            cached.proof.digest,
            cached.proof.checkpoint_sequence,
            cached.proof.target_sequence,
            verification.checked_items,
            verification,
            findings,
        )

    def ensure_target(
        self,
        target: DurableProofWindowTarget,
    ) -> DurableProofWindowReport:
        current = self.inspect_target(
            target
        )
        if current.ok:
            return current
        if (
            current.state
            is DurableProofWindowState.MISSING
            and not self.policy.allow_build_missing
        ):
            return current
        if (
            current.state
            is DurableProofWindowState.INVALID
            and not self.policy.refresh_invalid
        ):
            return current
        if (
            self.policy.require_cached
        ):
            return current

        chain = self._chain(
            target.chain_id
        )
        try:
            built = (
                self.authority.build_for_root(
                    target.chain_id,
                    chain,
                    target.target_root,
                )
            )
            cached = self.store.put_once_for_target(
                built
            )
            verification = (
                self.authority.require(
                    cached,
                    chain,
                )
            )
        except DurableHistoricalProofError as exc:
            state = self._state_from_error(
                exc
            )
            return DurableProofWindowReport(
                target,
                state,
                False,
                False,
                "",
                None,
                None,
                0,
                None,
                (
                    DurableProofWindowFinding(
                        "proof.build_failed",
                        str(exc),
                    ),
                ),
            )
        except Exception as exc:
            return DurableProofWindowReport(
                target,
                DurableProofWindowState.ERROR,
                False,
                False,
                "",
                None,
                None,
                0,
                None,
                (
                    DurableProofWindowFinding(
                        "proof.build_error",
                        "proof build raised "
                        f"{type(exc).__name__}",
                    ),
                ),
            )
        return DurableProofWindowReport(
            target,
            DurableProofWindowState.CURRENT,
            True,
            True,
            cached.proof.digest,
            cached.proof.checkpoint_sequence,
            cached.proof.target_sequence,
            verification.checked_items,
            verification,
            (),
        )

    def _targets(
        self,
        targets: Iterable[
            DurableProofWindowTarget
        ],
    ) -> tuple[
        DurableProofWindowTarget,
        ...,
    ]:
        values = tuple(
            targets
        )
        if len(values) > self.policy.max_targets:
            raise DurableProofWindowOperatorError(
                "proof-window target set exceeds policy bound"
            )
        if any(
            not isinstance(
                item,
                DurableProofWindowTarget,
            )
            for item in values
        ):
            raise TypeError(
                "targets must contain DurableProofWindowTarget"
            )
        ordered = tuple(
            sorted(
                values,
                key=lambda item: item.key,
            )
        )
        keys = tuple(
            item.key
            for item in ordered
        )
        if len(keys) != len(set(keys)):
            raise DurableProofWindowOperatorError(
                "duplicate proof-window target"
            )
        return ordered

    def inspect(
        self,
        targets: Iterable[
            DurableProofWindowTarget
        ],
    ) -> DurableProofWindowFleetReport:
        ordered = self._targets(
            targets
        )
        return DurableProofWindowFleetReport(
            self.policy.digest,
            tuple(
                self.inspect_target(
                    item
                )
                for item in ordered
            ),
            (),
        )

    def ensure(
        self,
        targets: Iterable[
            DurableProofWindowTarget
        ],
    ) -> DurableProofWindowFleetReport:
        ordered = self._targets(
            targets
        )
        reports: list[
            DurableProofWindowReport
        ] = []
        mutations: list[str] = []
        for target in ordered:
            report = self.ensure_target(
                target
            )
            reports.append(
                report
            )
            if report.built:
                mutations.append(
                    target.key
                )
        return DurableProofWindowFleetReport(
            self.policy.digest,
            tuple(reports),
            tuple(mutations),
        )

    def require(
        self,
        targets: Iterable[
            DurableProofWindowTarget
        ],
        *,
        build_missing: bool = False,
    ) -> DurableProofWindowFleetReport:
        report = (
            self.ensure(targets)
            if build_missing
            else self.inspect(targets)
        )
        if self.policy.require_all and not report.ok:
            first = next(
                (
                    item
                    for item in report.reports
                    if not item.ok
                ),
                None,
            )
            detail = (
                first.findings[0].message
                if (
                    first is not None
                    and first.findings
                )
                else "proof-window fleet is not healthy"
            )
            raise DurableProofWindowOperatorError(
                detail
            )
        return report
