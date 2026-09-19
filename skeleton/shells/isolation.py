"""Declarative isolation requirements for host command execution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class IsolationLevel(str, Enum):
    HOST = "host"
    WORKSPACE = "workspace"
    SANDBOXED = "sandboxed"


@dataclass(frozen=True)
class IsolationRequirement:
    level: IsolationLevel = IsolationLevel.WORKSPACE
    require_private_tmp: bool = True
    require_clean_environment: bool = True
    require_readonly_source: bool = False
    allow_network: bool = False
    allow_home: bool = False
    allowed_write_roots: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.level, IsolationLevel):
            object.__setattr__(self, "level", IsolationLevel(self.level))
        roots: list[str] = []
        for raw in self.allowed_write_roots:
            path = Path(raw).expanduser()
            if not path.is_absolute():
                raise ValueError("write roots must be absolute")
            roots.append(str(path.resolve(strict=False)))
        object.__setattr__(self, "allowed_write_roots", tuple(sorted(set(roots))))

    def no_wider_than(self, parent: "IsolationRequirement") -> bool:
        strength = {
            IsolationLevel.HOST: 0,
            IsolationLevel.WORKSPACE: 1,
            IsolationLevel.SANDBOXED: 2,
        }
        if strength[self.level] < strength[parent.level]:
            return False
        if parent.require_private_tmp and not self.require_private_tmp:
            return False
        if parent.require_clean_environment and not self.require_clean_environment:
            return False
        if parent.require_readonly_source and not self.require_readonly_source:
            return False
        if not parent.allow_network and self.allow_network:
            return False
        if not parent.allow_home and self.allow_home:
            return False
        parent_roots = tuple(Path(root) for root in parent.allowed_write_roots)
        for root in self.allowed_write_roots:
            candidate = Path(root)
            if parent_roots and not any(_within(candidate, allowed) for allowed in parent_roots):
                return False
        return True

    def to_dict(self) -> dict[str, object]:
        return {
            "level": self.level.value,
            "require_private_tmp": self.require_private_tmp,
            "require_clean_environment": self.require_clean_environment,
            "require_readonly_source": self.require_readonly_source,
            "allow_network": self.allow_network,
            "allow_home": self.allow_home,
            "allowed_write_roots": list(self.allowed_write_roots),
        }


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class IsolationDecision:
    allowed: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"allowed": self.allowed, "reasons": list(self.reasons)}


@dataclass(frozen=True)
class IsolationObservation:
    private_tmp: bool
    clean_environment: bool
    readonly_source: bool
    network_enabled: bool
    home_visible: bool
    write_roots: tuple[str, ...] = ()


class IsolationInspector:
    def inspect(
        self,
        requirement: IsolationRequirement,
        observation: IsolationObservation,
    ) -> IsolationDecision:
        reasons: list[str] = []
        if requirement.require_private_tmp and not observation.private_tmp:
            reasons.append("private temporary directory is required")
        if requirement.require_clean_environment and not observation.clean_environment:
            reasons.append("clean environment is required")
        if requirement.require_readonly_source and not observation.readonly_source:
            reasons.append("read-only source tree is required")
        if not requirement.allow_network and observation.network_enabled:
            reasons.append("network access is not allowed")
        if not requirement.allow_home and observation.home_visible:
            reasons.append("home directory visibility is not allowed")
        allowed_roots = tuple(Path(root) for root in requirement.allowed_write_roots)
        for raw in observation.write_roots:
            candidate = Path(raw).expanduser().resolve(strict=False)
            if allowed_roots and not any(_within(candidate, root) for root in allowed_roots):
                reasons.append("write root is outside allowed isolation roots")
                break
        return IsolationDecision(not reasons, tuple(reasons))
