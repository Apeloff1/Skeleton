"""Generic conditional discovery engine for recipes, lore, locations, and features.

Promotes Newmove2's recipe-discovery idea into a data-driven predicate system that
can unlock arbitrary content from runtime facts without React coupling.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True, slots=True)
class DiscoveryRule:
    id: str
    fact: str
    operator: str
    value: Any
    unlocks: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    newly_discovered: tuple[str, ...]
    newly_unlocked: tuple[str, ...]


class DiscoveryEngine:
    OPERATORS = {"eq", "gte", "lte", "contains", "contains_all", "truthy"}

    def __init__(self, rules: Iterable[DiscoveryRule]) -> None:
        self.rules = {rule.id: rule for rule in rules}
        if not self.rules:
            raise ValueError("discovery engine requires rules")
        if any(not rid.strip() for rid in self.rules):
            raise ValueError("blank discovery rule id")
        if len(self.rules) != len(tuple(rules)) if not isinstance(rules, (list, tuple)) else False:
            raise ValueError("duplicate discovery rule id")
        for rule in self.rules.values():
            if not rule.fact.strip():
                raise ValueError("discovery fact cannot be blank")
            if rule.operator not in self.OPERATORS:
                raise ValueError(f"unsupported discovery operator: {rule.operator}")
            if not rule.unlocks:
                raise ValueError("discovery rule must unlock content")
        self.discovered: set[str] = set()
        self.unlocked: set[str] = set()

    @staticmethod
    def _resolve(facts: Mapping[str, Any], path: str) -> Any:
        current: Any = facts
        for part in path.split("."):
            if not isinstance(current, Mapping) or part not in current:
                return None
            current = current[part]
        return current

    @classmethod
    def _matches(cls, actual: Any, operator: str, expected: Any) -> bool:
        if operator == "eq":
            return actual == expected
        if operator == "gte":
            return actual is not None and actual >= expected
        if operator == "lte":
            return actual is not None and actual <= expected
        if operator == "contains":
            return actual is not None and expected in actual
        if operator == "contains_all":
            if actual is None:
                return False
            return set(expected).issubset(set(actual))
        if operator == "truthy":
            return bool(actual) is bool(expected)
        raise ValueError(operator)

    def evaluate(self, facts: Mapping[str, Any]) -> DiscoveryResult:
        new_rules: list[str] = []
        new_unlocks: list[str] = []
        for rule in self.rules.values():
            if rule.id in self.discovered:
                continue
            actual = self._resolve(facts, rule.fact)
            if not self._matches(actual, rule.operator, rule.value):
                continue
            self.discovered.add(rule.id)
            new_rules.append(rule.id)
            for unlock in rule.unlocks:
                if unlock not in self.unlocked:
                    self.unlocked.add(unlock)
                    new_unlocks.append(unlock)
        return DiscoveryResult(tuple(new_rules), tuple(new_unlocks))

    def snapshot(self) -> dict[str, list[str]]:
        return {
            "discovered": sorted(self.discovered),
            "unlocked": sorted(self.unlocked),
        }
