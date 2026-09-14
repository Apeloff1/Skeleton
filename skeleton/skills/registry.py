"""Declarative, file-backed skill discovery and activation.

Skill files are data, never executable plugins. A ``*.skill.json`` file may
carry bounded instructions and capability metadata, but cannot name code,
commands, modules, scripts, or entry points.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

_SKILL_SUFFIX = ".skill.json"
_VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?$")
_CAP_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._:/-]{0,62}[a-z0-9])?$")
_FORBIDDEN_EXEC_FIELDS = frozenset(
    {"entrypoint", "command", "commands", "module", "script", "code", "exec", "executable"}
)
_ALLOWED_FIELDS = frozenset(
    {"id", "version", "description", "instructions", "capabilities", "priority", "enabled"}
)


class SkillValidationError(ValueError):
    """A skill manifest violated a safety or schema invariant."""


@dataclass(frozen=True, order=True)
class SkillVersion:
    """Strict three-component semantic version."""

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


@dataclass(frozen=True)
class SkillManifest:
    """Validated declarative skill metadata."""

    skill_id: str
    version: SkillVersion
    description: str
    instructions: str
    capabilities: tuple[str, ...] = ()
    priority: int = 0
    enabled: bool = True
    source: str = ""

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any],
        *,
        source: str = "",
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

        skill_id = data.get("id")
        if not isinstance(skill_id, str) or _ID_RE.fullmatch(skill_id) is None:
            raise SkillValidationError(
                "skill id must be 1-64 lowercase characters using letters, digits, '.', '_', or '-'"
            )
        version = SkillVersion.parse(data.get("version"))

        description = data.get("description", "")
        if not isinstance(description, str) or len(description) > 1024:
            raise SkillValidationError("skill description must be at most 1024 characters")
        instructions = data.get("instructions")
        if not isinstance(instructions, str) or not instructions.strip():
            raise SkillValidationError("skill instructions must be a non-empty string")
        if len(instructions) > max_instruction_chars:
            raise SkillValidationError(
                f"skill instructions exceed {max_instruction_chars} character limit"
            )

        raw_caps = data.get("capabilities", [])
        if not isinstance(raw_caps, list):
            raise SkillValidationError("skill capabilities must be a list")
        caps: list[str] = []
        for raw in raw_caps:
            if not isinstance(raw, str) or _CAP_RE.fullmatch(raw) is None:
                raise SkillValidationError(f"invalid skill capability {raw!r}")
            if raw not in caps:
                caps.append(raw)
        if len(caps) > 32:
            raise SkillValidationError("a skill may declare at most 32 capabilities")

        priority = data.get("priority", 0)
        if isinstance(priority, bool) or not isinstance(priority, int) or not -100 <= priority <= 100:
            raise SkillValidationError("skill priority must be an integer from -100 through 100")
        enabled = data.get("enabled", True)
        if not isinstance(enabled, bool):
            raise SkillValidationError("skill enabled must be a boolean")

        return cls(
            skill_id=skill_id,
            version=version,
            description=description.strip(),
            instructions=instructions.strip(),
            capabilities=tuple(caps),
            priority=priority,
            enabled=enabled,
            source=source,
        )


@dataclass(frozen=True)
class SkillActivation:
    """Bounded deterministic selection for one context."""

    manifests: tuple[SkillManifest, ...]
    instructions: str
    omitted: tuple[str, ...] = ()

    @property
    def skill_ids(self) -> tuple[str, ...]:
        return tuple(item.skill_id for item in self.manifests)


class SkillRegistry:
    """Discover, validate, version, select, and render declarative skills."""

    def __init__(
        self,
        roots: Iterable[str | Path],
        *,
        max_files: int = 128,
        max_file_bytes: int = 65536,
        max_instruction_chars: int = 8192,
        max_render_chars: int = 16384,
    ) -> None:
        if min(max_files, max_file_bytes, max_instruction_chars, max_render_chars) <= 0:
            raise ValueError("skill registry limits must be positive")
        self.roots = tuple(Path(root) for root in roots)
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes
        self.max_instruction_chars = max_instruction_chars
        self.max_render_chars = max_render_chars
        self._versions: dict[str, dict[SkillVersion, SkillManifest]] = {}
        self._discovered = False

    def discover(self) -> tuple[SkillManifest, ...]:
        versions: dict[str, dict[SkillVersion, SkillManifest]] = {}
        paths: list[tuple[Path, Path]] = []
        for root in self.roots:
            resolved_root = root.resolve()
            if not resolved_root.exists():
                continue
            if not resolved_root.is_dir():
                raise SkillValidationError(f"skill root is not a directory: {root}")
            for path in sorted(resolved_root.rglob(f"*{_SKILL_SUFFIX}")):
                paths.append((resolved_root, path))
        if len(paths) > self.max_files:
            raise SkillValidationError(
                f"discovered {len(paths)} skill files; limit is {self.max_files}"
            )

        for root, path in paths:
            if path.is_symlink():
                raise SkillValidationError(f"symlink skill manifests are forbidden: {path}")
            resolved = path.resolve()
            try:
                relative = resolved.relative_to(root)
            except ValueError as exc:
                raise SkillValidationError(f"skill manifest escaped configured root: {path}") from exc
            if not resolved.is_file():
                continue
            payload = resolved.read_bytes()
            if len(payload) > self.max_file_bytes:
                raise SkillValidationError(
                    f"skill manifest {relative} exceeds {self.max_file_bytes} byte limit"
                )
            try:
                data = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise SkillValidationError(f"invalid UTF-8 JSON skill manifest: {relative}") from exc
            manifest = SkillManifest.from_mapping(
                data,
                source=str(relative),
                max_instruction_chars=self.max_instruction_chars,
            )
            by_version = versions.setdefault(manifest.skill_id, {})
            if manifest.version in by_version:
                first = by_version[manifest.version]
                raise SkillValidationError(
                    f"duplicate skill {manifest.skill_id}@{manifest.version}: "
                    f"{first.source} and {manifest.source}"
                )
            by_version[manifest.version] = manifest

        self._versions = versions
        self._discovered = True
        return self.all()

    def _ensure_discovered(self) -> None:
        if not self._discovered:
            self.discover()

    def all(self, *, include_disabled: bool = False) -> tuple[SkillManifest, ...]:
        self._ensure_discovered()
        values = [
            manifest
            for versions in self._versions.values()
            for manifest in versions.values()
            if include_disabled or manifest.enabled
        ]
        return tuple(sorted(values, key=lambda item: (item.skill_id, item.version)))

    def resolve(
        self,
        skill_id: str,
        *,
        version: str | SkillVersion | None = None,
        include_disabled: bool = False,
    ) -> SkillManifest:
        self._ensure_discovered()
        versions = self._versions.get(skill_id)
        if not versions:
            raise KeyError(skill_id)
        if version is None:
            candidates = [
                manifest for manifest in versions.values() if include_disabled or manifest.enabled
            ]
            if not candidates:
                raise KeyError(skill_id)
            return max(candidates, key=lambda item: item.version)
        parsed = version if isinstance(version, SkillVersion) else SkillVersion.parse(version)
        manifest = versions.get(parsed)
        if manifest is None or (not include_disabled and not manifest.enabled):
            raise KeyError(f"{skill_id}@{parsed}")
        return manifest

    def select(
        self,
        *,
        skill_ids: Sequence[str] = (),
        capabilities: Sequence[str] = (),
    ) -> tuple[SkillManifest, ...]:
        """Select highest enabled versions using OR semantics across ids/capabilities."""
        self._ensure_discovered()
        requested_caps = frozenset(capabilities)
        chosen: dict[str, SkillManifest] = {}
        for skill_id in dict.fromkeys(skill_ids):
            chosen[skill_id] = self.resolve(skill_id)
        if requested_caps:
            for skill_id in sorted(self._versions):
                manifest = self.resolve(skill_id)
                if requested_caps.intersection(manifest.capabilities):
                    chosen[skill_id] = manifest
        return tuple(
            sorted(chosen.values(), key=lambda item: (-item.priority, item.skill_id, item.version))
        )

    def activate(
        self,
        *,
        skill_ids: Sequence[str] = (),
        capabilities: Sequence[str] = (),
        max_chars: int | None = None,
    ) -> SkillActivation:
        """Render whole skill blocks inside a hard context budget."""
        budget = self.max_render_chars if max_chars is None else min(max_chars, self.max_render_chars)
        if budget < 0:
            raise ValueError("max_chars must be non-negative")
        selected = self.select(skill_ids=skill_ids, capabilities=capabilities)
        rendered: list[str] = []
        active: list[SkillManifest] = []
        omitted: list[str] = []
        used = 0
        for manifest in selected:
            block = f"[skill:{manifest.skill_id}@{manifest.version}]\n{manifest.instructions}"
            separator = 2 if rendered else 0
            if used + separator + len(block) > budget:
                omitted.append(manifest.skill_id)
                continue
            rendered.append(block)
            active.append(manifest)
            used += separator + len(block)
        return SkillActivation(
            manifests=tuple(active),
            instructions="\n\n".join(rendered),
            omitted=tuple(omitted),
        )
