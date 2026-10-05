"""Canonical evidence-bound technical debt ledger for VOL-115.

Debt is modeled as owned, measurable repository liability. Retirement is not an
administrative flag: it requires exact evidence bound to the debt revision and
an independent verifier. The ledger keeps deterministic active-risk ordering and
an auditable retirement history without granting merge or completion authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import re
from typing import Iterable

DEBT_SCHEMA = "skeleton.contracts.technical_debt.v1"
_MAX_ITEMS = 20_000
_MAX_EVIDENCE = 100_000
_MAX_TEXT = 4_096
_MAX_VALUE = 2_147_483_647
_ID = re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class DebtError(ValueError):
    """Technical-debt state is malformed, contradictory, or unsafe."""


class DebtEvidenceKind(str, Enum):
    MIGRATION = "migration"
    COMPATIBILITY = "compatibility"
    ROLLBACK = "rollback"
    VERIFICATION = "verification"


def _id(value: object, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise DebtError(f"{field} must be stable identifier")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise DebtError(f"{field} must be lowercase sha256")
    return value


def _text(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > _MAX_TEXT
    ):
        raise DebtError(f"{field} must be bounded canonical text")
    if any(ord(char) < 32 and char not in "\t" for char in value):
        raise DebtError(f"{field} contains control characters")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DebtError(f"{field} must be nonnegative integer")
    if not 0 <= value <= _MAX_VALUE:
        raise DebtError(f"{field} must be nonnegative integer")
    return value


def _digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DebtError("debt state must be deterministic JSON") from exc
    return sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class DebtImpact:
    operational_interest: int
    engineering_interest: int
    risk: int

    def __post_init__(self) -> None:
        for field in (
            "operational_interest",
            "engineering_interest",
            "risk",
        ):
            object.__setattr__(
                self,
                field,
                _nonnegative_int(getattr(self, field), field),
            )

    @property
    def total(self) -> int:
        return (
            self.operational_interest
            + self.engineering_interest
            + self.risk
        )

    @property
    def digest(self) -> str:
        return _digest(
            [
                DEBT_SCHEMA,
                self.operational_interest,
                self.engineering_interest,
                self.risk,
            ]
        )


@dataclass(frozen=True, slots=True)
class DebtItem:
    debt_id: str
    source: str
    contract_ids: tuple[str, ...]
    owner_id: str
    target_disposition: str
    impact: DebtImpact

    def __post_init__(self) -> None:
        object.__setattr__(self, "debt_id", _id(self.debt_id, "debt_id"))
        object.__setattr__(self, "owner_id", _id(self.owner_id, "owner_id"))
        object.__setattr__(self, "source", _text(self.source, "source"))
        object.__setattr__(
            self,
            "target_disposition",
            _text(self.target_disposition, "target_disposition"),
        )
        if not isinstance(self.contract_ids, tuple) or not self.contract_ids:
            raise DebtError("contract_ids must be non-empty tuple")
        contracts = tuple(
            _id(item, "contract_id") for item in self.contract_ids
        )
        if len(contracts) != len(set(contracts)):
            raise DebtError("duplicate affected contract")
        object.__setattr__(self, "contract_ids", tuple(sorted(contracts)))
        if not isinstance(self.impact, DebtImpact):
            raise DebtError("impact must be DebtImpact")

    @property
    def digest(self) -> str:
        return _digest(
            [
                DEBT_SCHEMA,
                self.debt_id,
                self.source,
                list(self.contract_ids),
                self.owner_id,
                self.target_disposition,
                self.impact.digest,
            ]
        )


@dataclass(frozen=True, slots=True)
class DebtEvidence:
    evidence_id: str
    debt_id: str
    debt_digest: str
    kind: DebtEvidenceKind
    artifact_digest: str
    observed_tick: int
    passed: bool
    producer_id: str
    verifier_id: str

    def __post_init__(self) -> None:
        for field in ("evidence_id", "debt_id", "producer_id", "verifier_id"):
            object.__setattr__(
                self,
                field,
                _id(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "debt_digest",
            _sha(self.debt_digest, "debt_digest"),
        )
        object.__setattr__(
            self,
            "artifact_digest",
            _sha(self.artifact_digest, "artifact_digest"),
        )
        if not isinstance(self.kind, DebtEvidenceKind):
            raise DebtError("kind must be DebtEvidenceKind")
        object.__setattr__(
            self,
            "observed_tick",
            _nonnegative_int(self.observed_tick, "observed_tick"),
        )
        if not isinstance(self.passed, bool):
            raise DebtError("passed must be boolean")

    @property
    def digest(self) -> str:
        return _digest(
            [
                DEBT_SCHEMA,
                self.evidence_id,
                self.debt_id,
                self.debt_digest,
                self.kind.value,
                self.artifact_digest,
                self.observed_tick,
                self.passed,
                self.producer_id,
                self.verifier_id,
            ]
        )


def debt_evidence_set_digest(items: Iterable[DebtEvidence]) -> str:
    materialized = tuple(items)
    if any(not isinstance(item, DebtEvidence) for item in materialized):
        raise TypeError("items must contain DebtEvidence")
    ids = [item.evidence_id for item in materialized]
    if len(ids) != len(set(ids)):
        raise DebtError("duplicate debt evidence id in evidence set")
    return _digest(sorted(item.digest for item in materialized))


@dataclass(frozen=True, slots=True)
class DebtRetirement:
    debt_id: str
    debt_digest: str
    migration_evidence_id: str
    compatibility_evidence_id: str
    rollback_evidence_id: str
    verification_evidence_id: str
    evidence_set_digest: str
    verifier_id: str
    observed_tick: int

    def __post_init__(self) -> None:
        for field in (
            "debt_id",
            "migration_evidence_id",
            "compatibility_evidence_id",
            "rollback_evidence_id",
            "verification_evidence_id",
            "verifier_id",
        ):
            object.__setattr__(
                self,
                field,
                _id(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "debt_digest",
            _sha(self.debt_digest, "debt_digest"),
        )
        object.__setattr__(
            self,
            "evidence_set_digest",
            _sha(self.evidence_set_digest, "evidence_set_digest"),
        )
        object.__setattr__(
            self,
            "observed_tick",
            _nonnegative_int(self.observed_tick, "observed_tick"),
        )
        evidence_ids = (
            self.migration_evidence_id,
            self.compatibility_evidence_id,
            self.rollback_evidence_id,
            self.verification_evidence_id,
        )
        if len(evidence_ids) != len(set(evidence_ids)):
            raise DebtError("retirement evidence ids must be distinct")

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return (
            self.migration_evidence_id,
            self.compatibility_evidence_id,
            self.rollback_evidence_id,
            self.verification_evidence_id,
        )

    @property
    def digest(self) -> str:
        return _digest(
            [
                DEBT_SCHEMA,
                self.debt_id,
                self.debt_digest,
                list(self.evidence_ids),
                self.evidence_set_digest,
                self.verifier_id,
                self.observed_tick,
            ]
        )


@dataclass(frozen=True, slots=True)
class DebtSnapshot:
    ledger_digest: str
    active_debt_ids: tuple[str, ...]
    retirement_digests: tuple[str, ...]

    @property
    def digest(self) -> str:
        return _digest(
            [
                DEBT_SCHEMA,
                self.ledger_digest,
                list(self.active_debt_ids),
                list(self.retirement_digests),
            ]
        )


class DebtLedger:
    """Owned debt inventory with evidence-bound retirement."""

    _REQUIRED_KINDS = {
        DebtEvidenceKind.MIGRATION,
        DebtEvidenceKind.COMPATIBILITY,
        DebtEvidenceKind.ROLLBACK,
        DebtEvidenceKind.VERIFICATION,
    }

    def __init__(
        self,
        items: Iterable[DebtItem],
        evidence: Iterable[DebtEvidence] = (),
    ) -> None:
        materialized_items = tuple(items)
        materialized_evidence = tuple(evidence)

        if len(materialized_items) > _MAX_ITEMS:
            raise DebtError("debt item count exceeds safety bound")
        if len(materialized_evidence) > _MAX_EVIDENCE:
            raise DebtError("debt evidence count exceeds safety bound")
        if any(not isinstance(item, DebtItem) for item in materialized_items):
            raise TypeError("items must contain DebtItem")
        if any(
            not isinstance(item, DebtEvidence)
            for item in materialized_evidence
        ):
            raise TypeError("evidence must contain DebtEvidence")

        debt_ids = [item.debt_id for item in materialized_items]
        if len(debt_ids) != len(set(debt_ids)):
            raise DebtError("duplicate debt identity")
        evidence_ids = [item.evidence_id for item in materialized_evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise DebtError("duplicate debt evidence id")

        self.items = {
            item.debt_id: item
            for item in sorted(
                materialized_items,
                key=lambda item: item.debt_id,
            )
        }
        self.evidence = {
            item.evidence_id: item
            for item in sorted(
                materialized_evidence,
                key=lambda item: item.evidence_id,
            )
        }
        self.retired: dict[str, DebtRetirement] = {}

        for item in self.evidence.values():
            debt = self._item(item.debt_id)
            if item.debt_digest != debt.digest:
                raise DebtError("evidence debt digest mismatch")

    def _item(self, debt_id: str) -> DebtItem:
        debt_id = _id(debt_id, "debt_id")
        try:
            return self.items[debt_id]
        except KeyError as exc:
            raise DebtError("unknown debt") from exc

    @property
    def ledger_digest(self) -> str:
        return _digest(
            [
                DEBT_SCHEMA,
                [item.digest for item in self.items.values()],
                [item.digest for item in self.evidence.values()],
            ]
        )

    def interest(self, debt_id: str) -> int:
        return self._item(debt_id).impact.total

    def total_active_interest(self) -> int:
        return sum(self.interest(item.debt_id) for item in self.active_by_risk())

    def active_by_risk(self) -> tuple[DebtItem, ...]:
        return tuple(
            sorted(
                (
                    item
                    for item in self.items.values()
                    if item.debt_id not in self.retired
                ),
                key=lambda item: (-item.impact.total, item.debt_id),
            )
        )

    def debts_for_contract(
        self,
        contract_id: str,
        *,
        include_retired: bool = False,
    ) -> tuple[DebtItem, ...]:
        contract_id = _id(contract_id, "contract_id")
        if not isinstance(include_retired, bool):
            raise TypeError("include_retired must be boolean")
        return tuple(
            item
            for item in self.items.values()
            if contract_id in item.contract_ids
            and (include_retired or item.debt_id not in self.retired)
        )

    def owner_interest(
        self,
        owner_id: str,
        *,
        include_retired: bool = False,
    ) -> int:
        owner_id = _id(owner_id, "owner_id")
        if not isinstance(include_retired, bool):
            raise TypeError("include_retired must be boolean")
        return sum(
            item.impact.total
            for item in self.items.values()
            if item.owner_id == owner_id
            and (include_retired or item.debt_id not in self.retired)
        )

    def retire(self, receipt: DebtRetirement) -> DebtRetirement:
        if not isinstance(receipt, DebtRetirement):
            raise DebtError("receipt must be DebtRetirement")
        debt = self._item(receipt.debt_id)
        if receipt.debt_id in self.retired:
            raise DebtError("debt already retired")
        if receipt.debt_digest != debt.digest:
            raise DebtError("retirement debt digest mismatch")
        if receipt.verifier_id == debt.owner_id:
            raise DebtError("retirement verifier must be independent of debt owner")

        selected: list[DebtEvidence] = []
        for evidence_id in receipt.evidence_ids:
            try:
                item = self.evidence[evidence_id]
            except KeyError as exc:
                raise DebtError("retirement references unknown evidence") from exc
            if item.debt_id != debt.debt_id:
                raise DebtError("retirement references foreign debt evidence")
            if item.debt_digest != debt.digest:
                raise DebtError("retirement evidence debt digest mismatch")
            if item.observed_tick > receipt.observed_tick:
                raise DebtError("retirement references future evidence")
            if not item.passed:
                raise DebtError("retirement references failed evidence")
            selected.append(item)

        kinds = {item.kind for item in selected}
        if kinds != self._REQUIRED_KINDS:
            missing = sorted(item.value for item in self._REQUIRED_KINDS - kinds)
            extra = sorted(item.value for item in kinds - self._REQUIRED_KINDS)
            detail = []
            if missing:
                detail.append("missing=" + ",".join(missing))
            if extra:
                detail.append("extra=" + ",".join(extra))
            raise DebtError(
                "retirement evidence kinds invalid"
                + (":" + ";".join(detail) if detail else "")
            )

        expected_kind_by_id = {
            receipt.migration_evidence_id: DebtEvidenceKind.MIGRATION,
            receipt.compatibility_evidence_id: DebtEvidenceKind.COMPATIBILITY,
            receipt.rollback_evidence_id: DebtEvidenceKind.ROLLBACK,
            receipt.verification_evidence_id: DebtEvidenceKind.VERIFICATION,
        }
        for item in selected:
            if item.kind is not expected_kind_by_id[item.evidence_id]:
                raise DebtError("retirement evidence id bound to wrong kind")

        if receipt.evidence_set_digest != debt_evidence_set_digest(selected):
            raise DebtError("retirement evidence set mismatch")

        verification = next(
            item
            for item in selected
            if item.kind is DebtEvidenceKind.VERIFICATION
        )
        if verification.verifier_id != receipt.verifier_id:
            raise DebtError("retirement verifier mismatch")
        if verification.verifier_id in {
            verification.producer_id,
            debt.owner_id,
        }:
            raise DebtError("verification evidence is not independent")

        self.retired[debt.debt_id] = receipt
        return receipt

    def snapshot(self) -> DebtSnapshot:
        return DebtSnapshot(
            ledger_digest=self.ledger_digest,
            active_debt_ids=tuple(
                item.debt_id for item in self.active_by_risk()
            ),
            retirement_digests=tuple(
                self.retired[debt_id].digest
                for debt_id in sorted(self.retired)
            ),
        )


__all__ = [
    "DEBT_SCHEMA",
    "DebtError",
    "DebtEvidence",
    "DebtEvidenceKind",
    "DebtImpact",
    "DebtItem",
    "DebtLedger",
    "DebtRetirement",
    "DebtSnapshot",
    "debt_evidence_set_digest",
]
