"""Operational control plane for secondary durable-chain sequence indexes.

Sequence indexes accelerate sequence-to-root and bounded range lookup, but are
never execution or evidence authority.  The underlying hash-linked journal or
receipt chain remains authoritative.  This operator classifies index state,
repairs only missing locators from the committed chain, refuses conflicting
locators, and exposes bounded reports suitable for startup/readiness gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Mapping


def _chain_id(value: str) -> str:
    value = str(value).strip()
    if not value or len(value) > 128:
        raise ValueError("invalid durable sequence-index chain_id")
    return value


def _digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


class DurableSequenceIndexState(str, Enum):
    HEALTHY = "healthy"
    MISSING = "missing"
    CORRUPT = "corrupt"
    BOUNDED_OUT = "bounded_out"
    ERROR = "error"


@dataclass(frozen=True)
class DurableSequenceIndexPolicy:
    max_items_per_chain: int = 100_000
    max_chains: int = 32
    allow_missing_repair: bool = True
    require_healthy: bool = True
    verify_sample_windows: bool = True
    sample_window_items: int = 16

    def __post_init__(self) -> None:
        for name in (
            "max_items_per_chain",
            "max_chains",
            "sample_window_items",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(f"{name} must be positive integer")
        for name in (
            "allow_missing_repair",
            "require_healthy",
            "verify_sample_windows",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be bool")

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "max_items_per_chain": self.max_items_per_chain,
            "max_chains": self.max_chains,
            "allow_missing_repair": self.allow_missing_repair,
            "require_healthy": self.require_healthy,
            "verify_sample_windows": self.verify_sample_windows,
            "sample_window_items": self.sample_window_items,
        }


@dataclass(frozen=True)
class DurableSequenceIndexFinding:
    code: str
    message: str

    def __post_init__(self) -> None:
        if not self.code or len(self.code) > 128:
            raise ValueError("invalid sequence-index finding code")
        if not self.message or len(self.message) > 2048:
            raise ValueError("invalid sequence-index finding message")

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True)
class DurableSequenceIndexChainReport:
    chain_id: str
    state: DurableSequenceIndexState
    head_sequence: int
    head_root: str
    inspected: int
    indexed: int
    missing: int
    corrupt: int
    first_missing_sequence: int | None
    first_corrupt_sequence: int | None
    sample_windows_verified: int
    repaired: bool
    policy_digest: str
    findings: tuple[DurableSequenceIndexFinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "chain_id", _chain_id(self.chain_id))
        object.__setattr__(
            self,
            "state",
            DurableSequenceIndexState(self.state),
        )
        for name in (
            "head_sequence",
            "inspected",
            "indexed",
            "missing",
            "corrupt",
            "sample_windows_verified",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(f"{name} must be non-negative integer")
        for name in (
            "first_missing_sequence",
            "first_corrupt_sequence",
        ):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(f"{name} must be positive when present")
        if self.head_root and len(self.head_root) != 64:
            raise ValueError("head_root must be 64 characters")
        if len(self.policy_digest) != 64:
            raise ValueError("policy_digest must be SHA-256 shaped")
        if not isinstance(self.repaired, bool):
            raise ValueError("repaired must be bool")
        object.__setattr__(
            self,
            "findings",
            tuple(self.findings),
        )

    @property
    def healthy(self) -> bool:
        return self.state is DurableSequenceIndexState.HEALTHY

    @property
    def repairable(self) -> bool:
        return (
            self.state is DurableSequenceIndexState.MISSING
            and self.corrupt == 0
        )

    @property
    def digest(self) -> str:
        return _digest(self.to_dict(include_digest=False))

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "chain_id": self.chain_id,
            "state": self.state.value,
            "healthy": self.healthy,
            "repairable": self.repairable,
            "head_sequence": self.head_sequence,
            "head_root": self.head_root,
            "inspected": self.inspected,
            "indexed": self.indexed,
            "missing": self.missing,
            "corrupt": self.corrupt,
            "first_missing_sequence": self.first_missing_sequence,
            "first_corrupt_sequence": self.first_corrupt_sequence,
            "sample_windows_verified": self.sample_windows_verified,
            "repaired": self.repaired,
            "policy_digest": self.policy_digest,
            "findings": [
                item.to_dict()
                for item in self.findings
            ],
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableSequenceIndexFleetReport:
    chains: tuple[DurableSequenceIndexChainReport, ...]
    policy_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "chains", tuple(self.chains))
        if len(self.policy_digest) != 64:
            raise ValueError("policy_digest must be SHA-256 shaped")
        identifiers = [item.chain_id for item in self.chains]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("duplicate sequence-index chain report")

    @property
    def healthy(self) -> int:
        return sum(item.healthy for item in self.chains)

    @property
    def missing(self) -> int:
        return sum(
            item.state is DurableSequenceIndexState.MISSING
            for item in self.chains
        )

    @property
    def corrupt(self) -> int:
        return sum(
            item.state is DurableSequenceIndexState.CORRUPT
            for item in self.chains
        )

    @property
    def bounded_out(self) -> int:
        return sum(
            item.state is DurableSequenceIndexState.BOUNDED_OUT
            for item in self.chains
        )

    @property
    def errors(self) -> int:
        return sum(
            item.state is DurableSequenceIndexState.ERROR
            for item in self.chains
        )

    @property
    def repaired(self) -> int:
        return sum(item.repaired for item in self.chains)

    @property
    def ok(self) -> bool:
        return bool(self.chains) and self.healthy == len(self.chains)

    @property
    def digest(self) -> str:
        return _digest(self.to_dict(include_digest=False))

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "chains": [
                item.to_dict()
                for item in self.chains
            ],
            "policy_digest": self.policy_digest,
            "healthy": self.healthy,
            "missing": self.missing,
            "corrupt": self.corrupt,
            "bounded_out": self.bounded_out,
            "errors": self.errors,
            "repaired": self.repaired,
            "ok": self.ok,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableSequenceIndexError(RuntimeError):
    pass


class DurableSequenceIndexOperator:
    """Inspect and safely repair secondary sequence locators."""

    def __init__(
        self,
        policy: DurableSequenceIndexPolicy | None = None,
    ) -> None:
        self.policy = policy or DurableSequenceIndexPolicy()
        if not isinstance(
            self.policy,
            DurableSequenceIndexPolicy,
        ):
            raise TypeError(
                "policy must be DurableSequenceIndexPolicy"
            )

    @staticmethod
    def _require_surface(chain: object) -> None:
        for method in (
            "head",
            "inspect_sequence_indexes",
            "repair_sequence_indexes",
            "root_for_sequence",
            "snapshot_range",
        ):
            if not callable(getattr(chain, method, None)):
                raise TypeError(
                    f"chain does not implement {method}"
                )

    @staticmethod
    def _head(chain: object) -> tuple[int, str]:
        head = chain.head()
        sequence = int(head.sequence)
        root = str(head.root_hash)
        if sequence < 0:
            raise DurableSequenceIndexError(
                "chain head sequence is negative"
            )
        if len(root) != 64:
            raise DurableSequenceIndexError(
                "chain head root is not digest shaped"
            )
        return sequence, root

    def _sample_windows(
        self,
        chain: object,
        sequence: int,
    ) -> int:
        if (
            not self.policy.verify_sample_windows
            or sequence == 0
        ):
            return 0
        width = min(
            self.policy.sample_window_items,
            sequence,
        )
        starts = {
            1,
            max(1, sequence - width + 1),
            max(1, (sequence // 2) - (width // 2) + 1),
        }
        verified = 0
        for start in sorted(starts):
            end = min(
                sequence,
                start + width - 1,
            )
            items = chain.snapshot_range(
                start,
                end,
                max_items=self.policy.sample_window_items,
                repair_missing=True,
            )
            expected = end - start + 1
            if len(items) != expected:
                raise DurableSequenceIndexError(
                    "sequence-index sample returned wrong item count"
                )
            first_sequence = int(items[0].sequence)
            last_sequence = int(items[-1].sequence)
            if (
                first_sequence != start
                or last_sequence != end
            ):
                raise DurableSequenceIndexError(
                    "sequence-index sample returned wrong range"
                )
            verified += 1
        return verified

    def _inspect_one(
        self,
        chain_id: str,
        chain: object,
        *,
        repaired: bool = False,
    ) -> DurableSequenceIndexChainReport:
        chain_id = _chain_id(chain_id)
        self._require_surface(chain)
        findings: list[
            DurableSequenceIndexFinding
        ] = []
        try:
            sequence, root = self._head(chain)
            health = chain.inspect_sequence_indexes(
                max_items=self.policy.max_items_per_chain,
            )
        except Exception as exc:
            message = str(exc)
            lowered = message.casefold()
            state = (
                DurableSequenceIndexState.BOUNDED_OUT
                if "bound" in lowered
                or "window" in lowered
                or "capacity" in lowered
                else DurableSequenceIndexState.ERROR
            )
            findings.append(
                DurableSequenceIndexFinding(
                    "index.inspect_failed",
                    f"{type(exc).__name__}: {message}"[:2048],
                )
            )
            try:
                sequence, root = self._head(chain)
            except Exception:
                sequence, root = 0, ""
            return DurableSequenceIndexChainReport(
                chain_id,
                state,
                sequence,
                root,
                0,
                0,
                0,
                0,
                None,
                None,
                0,
                repaired,
                self.policy.digest,
                tuple(findings),
            )

        state = DurableSequenceIndexState.HEALTHY
        if int(health.corrupt):
            state = DurableSequenceIndexState.CORRUPT
            findings.append(
                DurableSequenceIndexFinding(
                    "index.corrupt",
                    f"{health.corrupt} sequence locator(s) conflict with committed chain",
                )
            )
        elif int(health.missing):
            state = DurableSequenceIndexState.MISSING
            findings.append(
                DurableSequenceIndexFinding(
                    "index.missing",
                    f"{health.missing} committed sequence locator(s) are missing",
                )
            )

        samples = 0
        if state is not DurableSequenceIndexState.CORRUPT:
            try:
                samples = self._sample_windows(
                    chain,
                    sequence,
                )
            except Exception as exc:
                state = DurableSequenceIndexState.CORRUPT
                findings.append(
                    DurableSequenceIndexFinding(
                        "index.sample_failed",
                        f"{type(exc).__name__}: {str(exc)}"[:2048],
                    )
                )

        return DurableSequenceIndexChainReport(
            chain_id,
            state,
            sequence,
            root,
            int(health.inspected),
            int(health.indexed),
            int(health.missing),
            int(health.corrupt),
            health.first_missing_sequence,
            health.first_corrupt_sequence,
            samples,
            repaired,
            self.policy.digest,
            tuple(findings),
        )

    def inspect(
        self,
        chains: Mapping[str, object],
    ) -> DurableSequenceIndexFleetReport:
        if not isinstance(chains, Mapping):
            raise TypeError("chains must be a mapping")
        if not chains:
            raise ValueError("at least one chain is required")
        if len(chains) > self.policy.max_chains:
            raise DurableSequenceIndexError(
                "sequence-index chain count exceeds policy"
            )
        reports = tuple(
            self._inspect_one(chain_id, chain)
            for chain_id, chain in sorted(
                chains.items(),
                key=lambda item: str(item[0]),
            )
        )
        return DurableSequenceIndexFleetReport(
            reports,
            self.policy.digest,
        )

    def repair(
        self,
        chains: Mapping[str, object],
    ) -> DurableSequenceIndexFleetReport:
        if not self.policy.allow_missing_repair:
            raise DurableSequenceIndexError(
                "sequence-index repair is disabled by policy"
            )
        initial = self.inspect(chains)
        reports: list[
            DurableSequenceIndexChainReport
        ] = []
        by_id = {
            item.chain_id: item
            for item in initial.chains
        }
        normalized = {
            _chain_id(chain_id): chain
            for chain_id, chain in chains.items()
        }

        for chain_id in sorted(normalized):
            chain = normalized[chain_id]
            report = by_id[chain_id]
            if report.state is DurableSequenceIndexState.HEALTHY:
                reports.append(report)
                continue
            if report.state is DurableSequenceIndexState.CORRUPT:
                reports.append(report)
                continue
            if report.state is not DurableSequenceIndexState.MISSING:
                reports.append(report)
                continue

            try:
                repaired_health = chain.repair_sequence_indexes(
                    max_items=self.policy.max_items_per_chain,
                )
                if not repaired_health.healthy:
                    raise DurableSequenceIndexError(
                        "sequence-index repair did not reach healthy state"
                    )
                repaired_report = self._inspect_one(
                    chain_id,
                    chain,
                    repaired=True,
                )
                if not repaired_report.healthy:
                    raise DurableSequenceIndexError(
                        "sequence-index post-repair verification failed"
                    )
                reports.append(repaired_report)
            except Exception as exc:
                reports.append(
                    DurableSequenceIndexChainReport(
                        chain_id,
                        DurableSequenceIndexState.ERROR,
                        report.head_sequence,
                        report.head_root,
                        report.inspected,
                        report.indexed,
                        report.missing,
                        report.corrupt,
                        report.first_missing_sequence,
                        report.first_corrupt_sequence,
                        report.sample_windows_verified,
                        False,
                        self.policy.digest,
                        report.findings
                        + (
                            DurableSequenceIndexFinding(
                                "index.repair_failed",
                                f"{type(exc).__name__}: {str(exc)}"[:2048],
                            ),
                        ),
                    )
                )

        return DurableSequenceIndexFleetReport(
            tuple(reports),
            self.policy.digest,
        )

    def require_healthy(
        self,
        chains: Mapping[str, object],
        *,
        repair_missing: bool = False,
    ) -> DurableSequenceIndexFleetReport:
        report = (
            self.repair(chains)
            if repair_missing
            else self.inspect(chains)
        )
        if self.policy.require_healthy and not report.ok:
            states = ", ".join(
                f"{item.chain_id}={item.state.value}"
                for item in report.chains
                if not item.healthy
            )
            raise DurableSequenceIndexError(
                "durable sequence indexes are not healthy"
                + (f": {states}" if states else "")
            )
        return report
