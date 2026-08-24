"""Blueprint validation — prove a forge blueprint is buildable before materialisation.

The forge synthesises composable system blueprints; the validator is the
gate that keeps a malformed blueprint from reaching materialisation. It
checks structure (required blocks, reference integrity), constraints
(numeric ranges, enum membership), and composition (cycles, dangling
dependencies) — and returns a machine-readable verdict the API can return
verbatim.

Validation is pure: a blueprint is data, a verdict is data, and the
validator holds no state between calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.kernel.errors import BlueprintError


@dataclass(frozen=True)
class ConstraintViolation:
    path: str            # dotted location, e.g. "systems[2].throughput"
    rule: str            # which rule fired, e.g. "range", "required", "cycle"
    detail: str


@dataclass
class ValidationVerdict:
    valid: bool
    violations: List[ConstraintViolation] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def raise_if_invalid(self) -> None:
        if not self.valid:
            raise BlueprintError(
                "blueprint failed validation",
                context={
                    "violations": [
                        {"path": v.path, "rule": v.rule, "detail": v.detail}
                        for v in self.violations
                    ],
                },
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "violations": [
                {"path": v.path, "rule": v.rule, "detail": v.detail}
                for v in self.violations
            ],
            "warnings": self.warnings,
        }


@dataclass(frozen=True)
class FieldRule:
    """One declarative constraint on a blueprint field."""
    path: str
    kind: str                       # "required" | "range" | "enum" | "type"
    arg: Any = None                 # (min, max) for range; choices for enum; type for type


class BlueprintValidator:
    """Stateless validator over forge blueprint dicts."""

    REQUIRED_TOP_LEVEL = ("name", "version", "systems")

    def __init__(self, rules: Optional[List[FieldRule]] = None) -> None:
        self._rules = rules or []

    def validate(self, blueprint: Dict[str, Any]) -> ValidationVerdict:
        violations: List[ConstraintViolation] = []
        warnings: List[str] = []

        # ---- structure -----------------------------------------------------
        for key in self.REQUIRED_TOP_LEVEL:
            if key not in blueprint:
                violations.append(ConstraintViolation(key, "required",
                                                      f"missing top-level key {key!r}"))

        systems = blueprint.get("systems", [])
        if not isinstance(systems, list) or not systems:
            violations.append(ConstraintViolation("systems", "type",
                                                  "must be a non-empty list"))
            systems = []

        ids: List[str] = []
        for i, system in enumerate(systems):
            path = f"systems[{i}]"
            sid = system.get("id")
            if not sid:
                violations.append(ConstraintViolation(f"{path}.id", "required",
                                                      "every system needs an id"))
                continue
            if sid in ids:
                violations.append(ConstraintViolation(f"{path}.id", "unique",
                                                      f"duplicate system id {sid!r}"))
            ids.append(sid)

        # ---- reference integrity + cycles ----------------------------------
        edges = {
            s.get("id"): list(s.get("depends_on", []))
            for s in systems if s.get("id")
        }
        for sid, deps in edges.items():
            for dep in deps:
                if dep not in ids:
                    violations.append(ConstraintViolation(
                        f"systems[{sid}].depends_on", "reference",
                        f"unknown dependency {dep!r}"))
        cycle = self._find_cycle(edges)
        if cycle:
            violations.append(ConstraintViolation("systems", "cycle",
                                                  "dependency cycle: " + " -> ".join(cycle)))

        # ---- declarative field rules ---------------------------------------
        for rule in self._rules:
            violations.extend(self._apply_rule(blueprint, rule))

        # ---- advisory warnings ---------------------------------------------
        for i, system in enumerate(systems):
            if "description" not in system:
                warnings.append(f"systems[{i}] ({system.get('id', '?')}) has no description")

        return ValidationVerdict(valid=not violations,
                                 violations=violations, warnings=warnings)

    # ------------------------------------------------------------------

    def _apply_rule(self, bp: Dict[str, Any], rule: FieldRule) -> List[ConstraintViolation]:
        value: Any = bp
        for part in rule.path.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                if rule.kind == "required":
                    return [ConstraintViolation(rule.path, "required", "field missing")]
                return []
        if rule.kind == "range":
            lo, hi = rule.arg
            if not (isinstance(value, (int, float)) and lo <= value <= hi):
                return [ConstraintViolation(rule.path, "range",
                                            f"{value!r} outside [{lo}, {hi}]")]
        elif rule.kind == "enum":
            if value not in rule.arg:
                return [ConstraintViolation(rule.path, "enum",
                                            f"{value!r} not in {rule.arg!r}")]
        elif rule.kind == "type":
            if not isinstance(value, rule.arg):
                return [ConstraintViolation(rule.path, "type",
                                            f"expected {rule.arg}, got {type(value).__name__}")]
        return []

    def _find_cycle(self, edges: Dict[str, List[str]]) -> Optional[List[str]]:
        WHITE, GREY, BLACK = 0, 1, 2
        colour = {n: WHITE for n in edges}
        stack: List[str] = []

        def visit(node: str) -> Optional[List[str]]:
            colour[node] = GREY
            stack.append(node)
            for dep in edges.get(node, []):
                if dep not in colour:
                    continue
                if colour[dep] == GREY:
                    return stack[stack.index(dep):] + [dep]
                if colour[dep] == WHITE:
                    found = visit(dep)
                    if found:
                        return found
            stack.pop()
            colour[node] = BLACK
            return None

        for node in edges:
            if colour[node] == WHITE:
                found = visit(node)
                if found:
                    return found
        return None
