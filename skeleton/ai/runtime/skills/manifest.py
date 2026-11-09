"""Serializable, validated skill identity and promotion state.

Skill manifests are deliberately declarative. They may describe bounded
instructions and capability metadata, but never executable entry points.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import re
from typing import Any, Dict, Mapping, List

_VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?$")
_CAPABILITY_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._:/-]{0,62}[a-z0-9])?$")
_FORBIDDEN_EXEC_FIELDS = frozenset(
    {"entrypoint", "command", "commands", "module", "script", "code", "exec", "executable"}
)
_ALLOWED_FIELDS = frozenset(
    {
        "name",
        "id",
        "version",
        "capabilities",
        "preconditions",
        "invariants",
        "evaluation",
        "provenance",
        "description",
        "instructions",
        "priority",
        "enabled",
    }
)


class SkillValidationError(ValueError):
    """A skill manifest violated a schema or safety invariant."""


@dataclass(frozen=True, order=True)
class SkillVersion:
    """Strict three-component semantic version used for deterministic selection."""

    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> "SkillVersion":
        if not isinstance(value, str):
            raise SkillValidationError("skill version must be a string")
        match = _VERSION_RE.fullmatch(value)
        if match is None:
            raise SkillValidationError(
                f"invalid skill version {value!r}; expected MAJOR.MINOR.PATCH"
            )
        return cls(*(int(part) for part in match.groups()))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass
class SkillManifest:
    """Canonical skill manifest shared by storage, lifecycle, and activation."""

    name: str
    version: str = "0.1.0"
    capabilities: List[str] = field(default_factory=list)
    preconditions: List[str] = field(default_factory=list)
    invariants: List[str] = field(default_factory=list)
    evaluation: List[str] = field(default_factory=list)
    provenance: str = "local"
    description: str = ""
    instructions: str = ""
    priority: int = 0
    enabled: bool = True

    def validate(self, *, max_instruction_chars: int = 8192) -> "SkillManifest":
        if not isinstance(self.name, str) or _NAME_RE.fullmatch(self.name) is None:
            raise SkillValidationError(
                "skill name must be 1-64 lowercase characters using letters, digits, '.', '_', or '-'"
            )
        SkillVersion.parse(self.version)
        if not isinstance(self.description, str) or len(self.description) > 1024:
            raise SkillValidationError("skill description must be at most 1024 characters")
        if not isinstance(self.instructions, str):
            raise SkillValidationError("skill instructions must be a string")
        if len(self.instructions) > max_instruction_chars:
            raise SkillValidationError(
                f"skill instructions exceed {max_instruction_chars} character limit"
            )
        if isinstance(self.priority, bool) or not isinstance(self.priority, int) or not -100 <= self.priority <= 100:
            raise SkillValidationError("skill priority must be an integer from -100 through 100")
        if not isinstance(self.enabled, bool):
            raise SkillValidationError("skill enabled must be a boolean")
        if not isinstance(self.provenance, str) or len(self.provenance) > 1024:
            raise SkillValidationError("skill provenance must be a string of at most 1024 characters")

        for field_name in ("preconditions", "invariants", "evaluation"):
            values = getattr(self, field_name)
            if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
                raise SkillValidationError(f"skill {field_name} must be a list of strings")
            if len(values) > 64:
                raise SkillValidationError(f"skill {field_name} may contain at most 64 items")

        if not isinstance(self.capabilities, list):
            raise SkillValidationError("skill capabilities must be a list")
        if len(self.capabilities) > 32:
            raise SkillValidationError("a skill may declare at most 32 capabilities")
        seen: set[str] = set()
        for capability in self.capabilities:
            if not isinstance(capability, str) or _CAPABILITY_RE.fullmatch(capability) is None:
                raise SkillValidationError(f"invalid skill capability {capability!r}")
            if capability in seen:
                raise SkillValidationError(f"duplicate skill capability {capability!r}")
            seen.add(capability)
        return self

    def instruction_text(self) -> str:
        """Return declarative guidance without interpreting any field as code."""
        if self.instructions.strip():
            return self.instructions.strip()
        sections: list[str] = []
        if self.preconditions:
            sections.append("Preconditions: " + "; ".join(self.preconditions))
        if self.invariants:
            sections.append("Invariants: " + "; ".join(self.invariants))
        if self.evaluation:
            sections.append("Evaluation: " + "; ".join(self.evaluation))
        return "\n".join(sections)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def dumps(self) -> str:
        self.validate()
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        max_instruction_chars: int = 8192,
    ) -> "SkillManifest":
        if not isinstance(data, Mapping):
            raise SkillValidationError("skill manifest root must be an object")
        keys = {str(key) for key in data}
        forbidden = sorted(keys & _FORBIDDEN_EXEC_FIELDS)
        if forbidden:
            raise SkillValidationError(
                "skill manifests are declarative; executable fields are forbidden: "
                + ", ".join(forbidden)
            )
        unknown = sorted(keys - _ALLOWED_FIELDS)
        if unknown:
            raise SkillValidationError("unknown skill manifest fields: " + ", ".join(unknown))

        payload = dict(data)
        alias = payload.pop("id", None)
        if alias is not None:
            if "name" in payload and payload["name"] != alias:
                raise SkillValidationError("skill id and name disagree")
            payload.setdefault("name", alias)
        try:
            manifest = cls(**payload)
        except TypeError as exc:
            raise SkillValidationError(f"invalid skill manifest shape: {exc}") from exc
        return manifest.validate(max_instruction_chars=max_instruction_chars)

    @classmethod
    def loads(cls, text: str, *, max_instruction_chars: int = 8192) -> "SkillManifest":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SkillValidationError("invalid skill manifest JSON") from exc
        return cls.from_dict(data, max_instruction_chars=max_instruction_chars)


@dataclass
class SkillState:
    status: str = "draft"
    attempts: int = 0
    successes: int = 0
    regressions: int = 0
    last_trace: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        return self.successes / self.attempts if self.attempts else 0.0

    def record(self, success: bool, trace: str = "") -> None:
        self.attempts += 1
        if success:
            self.successes += 1
        else:
            self.regressions += 1
        self.last_trace = trace

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
