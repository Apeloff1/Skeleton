"""Execution-governance kernel mined from the Rust GameForge governance crate.

This module is intentionally framework-free. It governs consequential actions
before they reach executors, while the existing HTTP governance routes continue
to handle catalogue moderation and community trust workflows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import threading
import uuid


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    action: str
    min_weight: int = 0
    requires_quorum: bool = False


@dataclass(slots=True)
class Charter:
    id: str
    domain: str
    rules: list[Rule]
    ratified_at: str
    amendments: int = 0


@dataclass(slots=True)
class Edict:
    id: str
    charter_id: str
    rule: Rule
    proposed_by: str
    proposed_at: str
    in_force: bool = False


@dataclass(frozen=True, slots=True)
class Decision:
    permitted: bool
    cited_rule: str | None
    reason: str
    quorum_required: bool = False


@dataclass(slots=True)
class GovernanceSnapshot:
    charters: list[Charter] = field(default_factory=list)
    edicts: list[Edict] = field(default_factory=list)


class CharterPolicy:
    """Thread-safe, fail-closed policy gate for runtime actions."""

    def __init__(self) -> None:
        self._charters: dict[str, Charter] = {}
        self._edicts: dict[str, Edict] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def ratify(self, domain: str, rules: list[Rule]) -> Charter:
        domain = domain.strip()
        if not domain:
            raise ValueError("domain is required")
        normalized: list[Rule] = []
        seen_actions: set[str] = set()
        for rule in rules:
            if not rule.id or not rule.action:
                raise ValueError("rule id and action are required")
            if rule.min_weight < 0:
                raise ValueError("min_weight cannot be negative")
            if rule.action in seen_actions:
                raise ValueError(f"duplicate action in charter: {rule.action}")
            seen_actions.add(rule.action)
            normalized.append(rule)
        charter = Charter(
            id=uuid.uuid4().hex,
            domain=domain,
            rules=normalized,
            ratified_at=self._now(),
        )
        with self._lock:
            self._charters[domain] = charter
        return charter

    def propose_edict(self, domain: str, rule: Rule, proposed_by: str) -> Edict | None:
        with self._lock:
            charter = self._charters.get(domain)
            if charter is None:
                return None
            edict = Edict(
                id=uuid.uuid4().hex,
                charter_id=charter.id,
                rule=rule,
                proposed_by=proposed_by,
                proposed_at=self._now(),
            )
            self._edicts[edict.id] = edict
            return edict

    def enforce_edict(self, edict_id: str) -> bool:
        with self._lock:
            edict = self._edicts.get(edict_id)
            if edict is None:
                return False
            if edict.in_force:
                return True
            charter = next(
                (c for c in self._charters.values() if c.id == edict.charter_id),
                None,
            )
            if charter is None:
                return False
            # An amendment replaces an earlier rule for the same action so the
            # policy surface stays deterministic rather than first-match-wins.
            charter.rules = [r for r in charter.rules if r.action != edict.rule.action]
            charter.rules.append(edict.rule)
            charter.amendments += 1
            edict.in_force = True
            return True

    def decide(self, domain: str, action: str, actor_weight: int) -> Decision:
        if actor_weight < 0:
            return Decision(False, None, "actor weight cannot be negative")
        with self._lock:
            charter = self._charters.get(domain)
            if charter is None:
                return Decision(False, None, f"no charter ratified for domain '{domain}'")
            rule = next((r for r in charter.rules if r.action == action), None)
            if rule is None:
                return Decision(False, None, f"action '{action}' is not chartered in '{domain}'")
            if actor_weight < rule.min_weight:
                return Decision(
                    False,
                    rule.id,
                    f"actor weight {actor_weight} below required {rule.min_weight}",
                    quorum_required=rule.requires_quorum,
                )
            return Decision(
                True,
                rule.id,
                "permitted by charter; quorum still required"
                if rule.requires_quorum
                else "permitted by charter",
                quorum_required=rule.requires_quorum,
            )

    def snapshot(self) -> GovernanceSnapshot:
        """Return detached copies so callers cannot mutate live policy state."""
        with self._lock:
            charters = [
                Charter(
                    id=charter.id,
                    domain=charter.domain,
                    rules=list(charter.rules),
                    ratified_at=charter.ratified_at,
                    amendments=charter.amendments,
                )
                for charter in self._charters.values()
            ]
            edicts = [
                Edict(
                    id=edict.id,
                    charter_id=edict.charter_id,
                    rule=edict.rule,
                    proposed_by=edict.proposed_by,
                    proposed_at=edict.proposed_at,
                    in_force=edict.in_force,
                )
                for edict in self._edicts.values()
            ]
            return GovernanceSnapshot(charters=charters, edicts=edicts)
