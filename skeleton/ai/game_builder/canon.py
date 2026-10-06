"""Branch-aware long-form canon and character epistemic state.

The ledger is deliberately small and deterministic. It is a control-plane
primitive for detecting accidental contradictions and knowledge leaks; it is
not a story generator.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import EvaluatorProvenance, canonical_digest, canonical_json


class CanonError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BranchRecord:
    branch_id: str
    parent_id: str | None
    fork_tick: int

    def __post_init__(self) -> None:
        if not self.branch_id.strip():
            raise ValueError("branch_id must be non-empty")
        if self.fork_tick < 0:
            raise ValueError("fork_tick must be non-negative")


@dataclass(frozen=True, slots=True)
class CanonAssertion:
    assertion_id: str
    subject: str
    predicate: str
    value: Any
    branch_id: str
    valid_from_tick: int
    valid_to_tick: int | None = None
    evaluator_provenance: EvaluatorProvenance
    intentional_contradiction: bool = False
    evidence_digests: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for label in ("assertion_id", "subject", "predicate", "branch_id"):
            if not getattr(self, label).strip():
                raise ValueError(f"{label} must be non-empty")
        if self.valid_from_tick < 0:
            raise ValueError("valid_from_tick must be non-negative")
        if self.valid_to_tick is not None and self.valid_to_tick < self.valid_from_tick:
            raise ValueError("valid_to_tick cannot precede valid_from_tick")
        canonical_json(self.value)
        if not isinstance(self.intentional_contradiction, bool):
            raise TypeError("intentional_contradiction must be boolean")
        if not isinstance(self.evaluator_provenance, EvaluatorProvenance):
            raise TypeError("canon assertion evaluator_provenance must be EvaluatorProvenance")
        if not self.evidence_digests:
            raise CanonError("canon assertion requires evidence")
        if any(not isinstance(item, str) or len(item) < 16 for item in self.evidence_digests):
            raise ValueError("evidence digests must be stable")
        if len(self.evidence_digests) != len(set(self.evidence_digests)):
            raise ValueError("evidence digests must be unique")
        if set(self.evidence_digests) - set(self.evaluator_provenance.output_evidence_refs):
            raise CanonError("canon evidence must be referenced by assertion authority")

    @property
    def value_digest(self) -> str:
        return canonical_digest(self.value)

    @property
    def evidence_binding_digest(self) -> str:
        return canonical_digest(
            {
                "assertion_id": self.assertion_id,
                "branch_id": self.branch_id,
                "evaluator_provenance_digest": self.evaluator_provenance.digest,
                "evidence_digests": list(self.evidence_digests),
                "intentional_contradiction": self.intentional_contradiction,
                "predicate": self.predicate,
                "subject": self.subject,
                "valid_from_tick": self.valid_from_tick,
                "valid_to_tick": self.valid_to_tick,
                "value_digest": self.value_digest,
            }
        )

    def active_at(self, tick: int) -> bool:
        return self.valid_from_tick <= tick and (
            self.valid_to_tick is None or tick <= self.valid_to_tick
        )

    def overlaps(self, other: "CanonAssertion") -> bool:
        left_end = self.valid_to_tick if self.valid_to_tick is not None else 2**63 - 1
        right_end = other.valid_to_tick if other.valid_to_tick is not None else 2**63 - 1
        return self.valid_from_tick <= right_end and other.valid_from_tick <= left_end

    def to_payload(self) -> dict[str, object]:
        return {
            "assertion_id": self.assertion_id,
            "branch_id": self.branch_id,
            "evidence_digests": list(self.evidence_digests),
            "evidence_binding_digest": self.evidence_binding_digest,
            "evaluator_provenance_digest": self.evaluator_provenance.digest,
            "intentional_contradiction": self.intentional_contradiction,
            "predicate": self.predicate,
            "subject": self.subject,
            "valid_from_tick": self.valid_from_tick,
            "valid_to_tick": self.valid_to_tick,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class CharacterKnowledge:
    character_id: str
    assertion_id: str
    branch_id: str
    learned_tick: int
    source_id: str
    certainty: float = 1.0

    def __post_init__(self) -> None:
        for label in ("character_id", "assertion_id", "branch_id", "source_id"):
            if not getattr(self, label).strip():
                raise ValueError(f"{label} must be non-empty")
        if self.learned_tick < 0:
            raise ValueError("learned_tick must be non-negative")
        if not 0.0 <= self.certainty <= 1.0:
            raise ValueError("certainty must be within [0,1]")


class CanonLedger:
    """Versionable branch-aware canon with knowledge-leak checks."""

    def __init__(self) -> None:
        self._branches: dict[str, BranchRecord] = {
            "root": BranchRecord("root", None, 0)
        }
        self._assertions: dict[str, CanonAssertion] = {}
        self._knowledge: list[CharacterKnowledge] = []

    def add_branch(self, branch_id: str, *, parent_id: str = "root", fork_tick: int) -> None:
        if branch_id in self._branches:
            raise CanonError(f"branch already exists: {branch_id}")
        if parent_id not in self._branches:
            raise CanonError(f"unknown parent branch: {parent_id}")
        parent = self._branches[parent_id]
        if fork_tick < parent.fork_tick:
            raise CanonError("branch cannot fork before its parent exists")
        self._branches[branch_id] = BranchRecord(branch_id, parent_id, fork_tick)

    def lineage(self, branch_id: str) -> tuple[str, ...]:
        if branch_id not in self._branches:
            raise CanonError(f"unknown branch: {branch_id}")
        chain: list[str] = []
        current: str | None = branch_id
        seen: set[str] = set()
        while current is not None:
            if current in seen:
                raise CanonError("branch cycle detected")
            seen.add(current)
            chain.append(current)
            current = self._branches[current].parent_id
        return tuple(reversed(chain))

    def _visible_ticks(self, branch_id: str, tick: int) -> tuple[tuple[str, int], ...]:
        if tick < 0:
            raise ValueError("tick must be non-negative")
        lineage = self.lineage(branch_id)
        target = self._branches[branch_id]
        if tick < target.fork_tick:
            raise CanonError("branch queried before its fork")
        visible: list[tuple[str, int]] = []
        for index, current in enumerate(lineage):
            if index + 1 < len(lineage):
                child = self._branches[lineage[index + 1]]
                visible.append((current, min(tick, child.fork_tick)))
            else:
                visible.append((current, tick))
        return tuple(visible)

    def add_assertion(self, assertion: CanonAssertion) -> None:
        if assertion.assertion_id in self._assertions:
            raise CanonError(f"assertion already exists: {assertion.assertion_id}")
        if assertion.branch_id not in self._branches:
            raise CanonError(f"unknown assertion branch: {assertion.branch_id}")
        for existing in self._assertions.values():
            if (
                existing.branch_id == assertion.branch_id
                and existing.subject == assertion.subject
                and existing.predicate == assertion.predicate
                and existing.overlaps(assertion)
                and existing.value_digest != assertion.value_digest
                and not existing.intentional_contradiction
                and not assertion.intentional_contradiction
            ):
                raise CanonError(
                    "accidental canon contradiction: "
                    f"{assertion.subject}.{assertion.predicate}"
                )
        self._assertions[assertion.assertion_id] = assertion

    def add_knowledge(self, knowledge: CharacterKnowledge) -> None:
        assertion = self._assertions.get(knowledge.assertion_id)
        if assertion is None:
            raise CanonError(f"unknown assertion: {knowledge.assertion_id}")
        if knowledge.branch_id not in self._branches:
            raise CanonError(f"unknown knowledge branch: {knowledge.branch_id}")
        if assertion.branch_id not in self.lineage(knowledge.branch_id):
            raise CanonError("character knowledge crosses an unrelated branch")
        if knowledge.learned_tick < assertion.valid_from_tick:
            raise CanonError("character cannot learn an assertion before it exists")
        duplicate = any(
            item.character_id == knowledge.character_id
            and item.assertion_id == knowledge.assertion_id
            and item.branch_id == knowledge.branch_id
            and item.learned_tick == knowledge.learned_tick
            for item in self._knowledge
        )
        if duplicate:
            raise CanonError("duplicate character knowledge event")
        self._knowledge.append(knowledge)

    def effective(
        self,
        *,
        subject: str,
        predicate: str,
        branch_id: str,
        tick: int,
    ) -> CanonAssertion | None:
        visible = self._visible_ticks(branch_id, tick)
        for candidate_branch, visible_tick in reversed(visible):
            matches = [
                row
                for row in self._assertions.values()
                if row.branch_id == candidate_branch
                and row.subject == subject
                and row.predicate == predicate
                and row.active_at(visible_tick)
                and not row.intentional_contradiction
            ]
            if not matches:
                continue
            digests = {row.value_digest for row in matches}
            if len(digests) > 1:
                raise CanonError("ambiguous effective canon value")
            return max(matches, key=lambda row: (row.valid_from_tick, row.assertion_id))
        return None

    def character_knows(
        self,
        *,
        character_id: str,
        assertion_id: str,
        branch_id: str,
        tick: int,
    ) -> bool:
        visible = dict(self._visible_ticks(branch_id, tick))
        return any(
            item.character_id == character_id
            and item.assertion_id == assertion_id
            and item.branch_id in visible
            and item.learned_tick <= visible[item.branch_id]
            for item in self._knowledge
        )

    def contradictions(self) -> tuple[tuple[str, str], ...]:
        rows = list(self._assertions.values())
        conflicts: set[tuple[str, str]] = set()
        for i, left in enumerate(rows):
            if left.intentional_contradiction:
                continue
            for right in rows[i + 1 :]:
                if right.intentional_contradiction:
                    continue
                if (
                    left.branch_id == right.branch_id
                    and left.subject == right.subject
                    and left.predicate == right.predicate
                    and left.overlaps(right)
                    and left.value_digest != right.value_digest
                ):
                    conflicts.add(tuple(sorted((left.assertion_id, right.assertion_id))))
        return tuple(sorted(conflicts))

    def snapshot(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "assertions": [
                self._assertions[key].to_payload() for key in sorted(self._assertions)
            ],
            "branches": [
                {
                    "branch_id": row.branch_id,
                    "fork_tick": row.fork_tick,
                    "parent_id": row.parent_id,
                }
                for row in sorted(self._branches.values(), key=lambda x: x.branch_id)
            ],
            "knowledge": [
                {
                    "assertion_id": item.assertion_id,
                    "branch_id": item.branch_id,
                    "certainty": item.certainty,
                    "character_id": item.character_id,
                    "learned_tick": item.learned_tick,
                    "source_id": item.source_id,
                }
                for item in sorted(
                    self._knowledge,
                    key=lambda x: (
                        x.character_id,
                        x.branch_id,
                        x.learned_tick,
                        x.assertion_id,
                    ),
                )
            ],
        }
        return {**payload, "digest": canonical_digest(payload)}
