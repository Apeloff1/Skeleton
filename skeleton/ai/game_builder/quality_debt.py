"""Quality-debt ratchet for long-running adversarial game-builder work."""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Iterable, Mapping

from .contracts import PROTECTED_AXES, canonical_digest


class QualityDebtError(RuntimeError):
    pass


class DebtSeverity(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 4
    CRITICAL = 8


@dataclass(frozen=True, slots=True)
class DebtItem:
    debt_id: str
    axis: str
    severity: DebtSeverity
    description: str
    evidence_digest: str
    opened_round: int
    protected: bool
    resolved_round: int | None = None

    def __post_init__(self) -> None:
        if not self.debt_id.strip():
            raise ValueError("debt_id must be non-empty")
        if not self.axis.strip():
            raise ValueError("axis must be non-empty")
        if not self.description.strip():
            raise ValueError("description must be non-empty")
        if len(self.evidence_digest) < 16:
            raise ValueError("evidence_digest must be stable")
        if self.opened_round < 0:
            raise ValueError("opened_round must be non-negative")
        if self.resolved_round is not None and self.resolved_round < self.opened_round:
            raise ValueError("resolved_round cannot predate opened_round")

    @property
    def unresolved(self) -> bool:
        return self.resolved_round is None


class QualityDebtLedger:
    """Tracks cumulative quality compromises with a non-increasing ceiling."""

    SCHEMA = "skeleton.ai_game_builder.quality_debt.v1"

    def __init__(
        self,
        *,
        ceiling: int = 12,
        protected_ceiling: int = 0,
        items: Iterable[DebtItem] = (),
    ) -> None:
        if isinstance(ceiling, bool) or not isinstance(ceiling, int) or ceiling < 0:
            raise ValueError("ceiling must be a non-negative integer")
        if (
            isinstance(protected_ceiling, bool)
            or not isinstance(protected_ceiling, int)
            or protected_ceiling < 0
        ):
            raise ValueError("protected_ceiling must be a non-negative integer")
        self.ceiling = ceiling
        self.protected_ceiling = protected_ceiling
        self._items: dict[str, DebtItem] = {}
        for item in items:
            self.add(item)

    def add(self, item: DebtItem) -> None:
        if item.debt_id in self._items:
            raise QualityDebtError("duplicate quality-debt identity")
        self._items[item.debt_id] = item

    def resolve(self, debt_id: str, *, round_index: int) -> DebtItem:
        item = self._items.get(debt_id)
        if item is None:
            raise QualityDebtError("unknown quality-debt identity")
        if not item.unresolved:
            raise QualityDebtError("quality debt is already resolved")
        if round_index < item.opened_round:
            raise QualityDebtError("resolution cannot predate debt creation")
        resolved = DebtItem(
            debt_id=item.debt_id,
            axis=item.axis,
            severity=item.severity,
            description=item.description,
            evidence_digest=item.evidence_digest,
            opened_round=item.opened_round,
            protected=item.protected,
            resolved_round=round_index,
        )
        self._items[debt_id] = resolved
        return resolved

    @property
    def unresolved(self) -> tuple[DebtItem, ...]:
        return tuple(
            self._items[key]
            for key in sorted(self._items)
            if self._items[key].unresolved
        )

    @property
    def total_score(self) -> int:
        return sum(int(item.severity) for item in self.unresolved)

    @property
    def protected_score(self) -> int:
        return sum(
            int(item.severity)
            for item in self.unresolved
            if item.protected or item.axis in PROTECTED_AXES
        )

    @property
    def critical_items(self) -> tuple[DebtItem, ...]:
        return tuple(
            item
            for item in self.unresolved
            if item.severity is DebtSeverity.CRITICAL
        )

    def promotion_allowed(self) -> bool:
        return (
            not self.critical_items
            and self.total_score <= self.ceiling
            and self.protected_score <= self.protected_ceiling
        )

    def blockers(self) -> tuple[str, ...]:
        blockers: list[str] = []
        if self.critical_items:
            blockers.append("critical unresolved quality debt")
        if self.total_score > self.ceiling:
            blockers.append(
                f"quality debt {self.total_score} exceeds ceiling {self.ceiling}"
            )
        if self.protected_score > self.protected_ceiling:
            blockers.append(
                "protected quality debt "
                f"{self.protected_score} exceeds ceiling {self.protected_ceiling}"
            )
        return tuple(blockers)

    def ratchet(
        self,
        *,
        ceiling: int | None = None,
        protected_ceiling: int | None = None,
    ) -> None:
        new_ceiling = self.ceiling if ceiling is None else ceiling
        new_protected = (
            self.protected_ceiling
            if protected_ceiling is None
            else protected_ceiling
        )
        if new_ceiling > self.ceiling or new_protected > self.protected_ceiling:
            raise QualityDebtError("quality-debt ceilings may only tighten")
        if new_ceiling < 0 or new_protected < 0:
            raise QualityDebtError("quality-debt ceilings cannot be negative")
        self.ceiling = new_ceiling
        self.protected_ceiling = new_protected

    def snapshot(self) -> dict[str, object]:
        rows = [
            {
                "axis": item.axis,
                "debt_id": item.debt_id,
                "description": item.description,
                "evidence_digest": item.evidence_digest,
                "opened_round": item.opened_round,
                "protected": item.protected,
                "resolved_round": item.resolved_round,
                "severity": int(item.severity),
            }
            for item in sorted(self._items.values(), key=lambda x: x.debt_id)
        ]
        core: dict[str, object] = {
            "ceiling": self.ceiling,
            "items": rows,
            "protected_ceiling": self.protected_ceiling,
            "schema": self.SCHEMA,
        }
        return {
            **core,
            "debt_digest": canonical_digest(core),
            "promotion_allowed": self.promotion_allowed(),
            "protected_score": self.protected_score,
            "total_score": self.total_score,
        }

    @classmethod
    def restore(cls, payload: Mapping[str, object]) -> "QualityDebtLedger":
        supplied = payload.get("debt_digest")
        core = {
            key: payload[key]
            for key in ("ceiling", "items", "protected_ceiling", "schema")
            if key in payload
        }
        if supplied != canonical_digest(core):
            raise QualityDebtError("quality-debt snapshot digest mismatch")
        if payload.get("schema") != cls.SCHEMA:
            raise QualityDebtError("unsupported quality-debt schema")
        raw_items = payload.get("items")
        if not isinstance(raw_items, list):
            raise QualityDebtError("quality-debt items must be a list")
        items: list[DebtItem] = []
        for raw in raw_items:
            if not isinstance(raw, Mapping):
                raise QualityDebtError("quality-debt item payload malformed")
            items.append(
                DebtItem(
                    debt_id=str(raw["debt_id"]),
                    axis=str(raw["axis"]),
                    severity=DebtSeverity(int(raw["severity"])),
                    description=str(raw["description"]),
                    evidence_digest=str(raw["evidence_digest"]),
                    opened_round=int(raw["opened_round"]),
                    protected=bool(raw["protected"]),
                    resolved_round=(
                        None
                        if raw.get("resolved_round") is None
                        else int(raw["resolved_round"])
                    ),
                )
            )
        ledger = cls(
            ceiling=int(payload["ceiling"]),
            protected_ceiling=int(payload["protected_ceiling"]),
            items=items,
        )
        if ledger.total_score != payload.get("total_score"):
            raise QualityDebtError("quality-debt total score drifted")
        if ledger.protected_score != payload.get("protected_score"):
            raise QualityDebtError("quality-debt protected score drifted")
        if ledger.promotion_allowed() != payload.get("promotion_allowed"):
            raise QualityDebtError("quality-debt promotion state drifted")
        return ledger
