"""Safe command templates with fixed argv prefixes and explicit variable slots."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from types import MappingProxyType
from typing import Mapping, Sequence

from skeleton.shells.arguments import ValueConstraint
from skeleton.shells.runner import ShellCommand

_SLOT = re.compile(r"^\{([A-Za-z_][A-Za-z0-9_]*)\}$")


@dataclass(frozen=True)
class TemplateSlot:
    name: str
    constraint: ValueConstraint = field(default_factory=ValueConstraint)
    required: bool = True
    default: str | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.name):
            raise ValueError("invalid template slot name")
        if self.default is not None and not self.constraint.accepts(self.default):
            raise ValueError("template slot default violates constraint")
        if self.required and self.default is not None:
            object.__setattr__(self, "required", False)


@dataclass(frozen=True)
class CommandTemplate:
    name: str
    command: str
    argv: tuple[str, ...]
    slots: Mapping[str, TemplateSlot] = field(default_factory=dict)
    allow_cwd_override: bool = False
    allow_env_override: bool = False

    def __post_init__(self) -> None:
        slots = dict(self.slots)
        for name, slot in slots.items():
            if name != slot.name:
                raise ValueError("slot mapping key must match slot name")
        referenced: set[str] = set()
        for token in self.argv:
            match = _SLOT.fullmatch(token)
            if match:
                referenced.add(match.group(1))
        unknown = referenced - set(slots)
        if unknown:
            raise ValueError("template references undeclared slots")
        unused = set(slots) - referenced
        if unused:
            raise ValueError("template declares unused slots")
        object.__setattr__(self, "argv", tuple(self.argv))
        object.__setattr__(self, "slots", MappingProxyType(slots))

    def build(
        self,
        values: Mapping[str, str] | None = None,
        *,
        cwd=None,
        env: Mapping[str, str] | None = None,
        stdin: bytes | None = None,
        timeout: float | None = None,
    ) -> ShellCommand:
        supplied = dict(values or {})
        extras = set(supplied) - set(self.slots)
        if extras:
            raise ValueError("unknown template slot values")
        resolved: dict[str, str] = {}
        for name, slot in self.slots.items():
            value = supplied.get(name, slot.default)
            if value is None:
                if slot.required:
                    raise ValueError(f"required template slot missing: {name}")
                value = ""
            if not isinstance(value, str) or not slot.constraint.accepts(value):
                raise ValueError(f"template slot rejected: {name}")
            resolved[name] = value
        args: list[str] = []
        for token in self.argv:
            match = _SLOT.fullmatch(token)
            args.append(resolved[match.group(1)] if match else token)
        if cwd is not None and not self.allow_cwd_override:
            raise ValueError("template does not allow cwd override")
        if env and not self.allow_env_override:
            raise ValueError("template does not allow environment override")
        return ShellCommand(
            self.command,
            tuple(args),
            cwd=cwd,
            env=dict(env or {}),
            stdin=stdin,
            timeout=timeout,
        )


class TemplateCatalog:
    def __init__(self, templates: Sequence[CommandTemplate] = ()) -> None:
        self._templates: dict[str, CommandTemplate] = {}
        for template in templates:
            self.register(template)

    def register(self, template: CommandTemplate, *, replace: bool = False) -> None:
        if template.name in self._templates and not replace:
            raise ValueError(f"template already registered: {template.name}")
        self._templates[template.name] = template

    def get(self, name: str) -> CommandTemplate:
        try:
            return self._templates[name]
        except KeyError as exc:
            raise KeyError(f"unknown command template: {name!r}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._templates))
