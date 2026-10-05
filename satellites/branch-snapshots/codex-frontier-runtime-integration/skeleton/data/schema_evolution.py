"""Schema evolution guard — compatibility checking for schema changes.

Validates proposed schema changes against compatibility modes
(backward, forward, full, none) before registration: adding optional
fields is backward-safe, removing fields or tightening types is
breaking. Blocks unsafe evolutions and suggests safe alternatives.
Works on top of the schema registry.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


MODES = ["backward", "forward", "full", "none"]


@dataclass
class CompatibilityIssue:
    kind: str
    field: str
    detail: str
    severity: str

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "field": self.field, "detail": self.detail, "severity": self.severity}


class SchemaEvolutionGuard:
    """Compatibility checker for schema evolution."""

    def __init__(self, mode: str = "backward"):
        self.mode = mode if mode in MODES else "backward"
        self._checks_run = 0
        self._blocked = 0

    def check(self, old: Dict[str, Any], new: Dict[str, Any],
              mode: Optional[str] = None) -> Dict[str, Any]:
        active_mode = mode or self.mode
        self._checks_run += 1
        if active_mode == "none":
            return {"compatible": True, "mode": "none", "issues": []}
        issues: List[CompatibilityIssue] = []
        old_props = old.get("properties", {})
        new_props = new.get("properties", {})
        old_required = set(old.get("required", []))
        new_required = set(new.get("required", []))

        if active_mode in ("backward", "full"):
            for fname in old_props:
                if fname not in new_props:
                    issues.append(CompatibilityIssue(
                        "removed_field", fname,
                        f"field '{fname}' removed — old data unreadable by new schema",
                        "breaking"))
            for fname in new_required - old_required:
                if fname not in old_props:
                    issues.append(CompatibilityIssue(
                        "new_required", fname,
                        f"new required field '{fname}' missing in old data",
                        "breaking"))

        if active_mode in ("forward", "full"):
            for fname in new_props:
                if fname not in old_props and fname in new_required:
                    issues.append(CompatibilityIssue(
                        "removed_field", fname,
                        f"new required field '{fname}' not present in old schema",
                        "warning"))

        for fname in set(old_props) & set(new_props):
            old_type = old_props[fname].get("type")
            new_type = new_props[fname].get("type")
            if old_type and new_type and old_type != new_type:
                issues.append(CompatibilityIssue(
                    "type_change", fname,
                    f"type changed {old_type} → {new_type}",
                    "breaking"))

        breaking = [i for i in issues if i.severity == "breaking"]
        compatible = len(breaking) == 0
        if not compatible:
            self._blocked += 1
        return {
            "compatible": compatible,
            "mode": active_mode,
            "issues": [i.to_dict() for i in issues],
            "breaking_count": len(breaking),
            "suggestion": self._suggest(issues) if not compatible else None,
        }

    def _suggest(self, issues: List[CompatibilityIssue]) -> str:
        kinds = {i.kind for i in issues if i.severity == "breaking"}
        suggestions = []
        if "removed_field" in kinds:
            suggestions.append("deprecate fields instead of removing (keep optional)")
        if "new_required" in kinds:
            suggestions.append("add new fields as optional with defaults")
        if "type_change" in kinds:
            suggestions.append("register a migration instead of changing types in place")
        return "; ".join(suggestions) if suggestions else "review changes manually"

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "schema-evolution-card",
            "mode": self.mode,
            "checks_run": self._checks_run,
            "blocked": self._blocked,
        }
