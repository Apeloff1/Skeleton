"""Deterministic discovery and bounded activation for declarative skills.

The registry consumes the canonical :mod:`skeleton.skills.manifest` model and
supports both standalone ``*.skill.json`` files and the existing
``SkillStore`` ``*/manifest.json`` layout. Skill files are data only; manifest
validation rejects executable fields before activation.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable, Sequence

from .manifest import SkillManifest, SkillValidationError, SkillVersion

_SKILL_SUFFIX = ".skill.json"
_STORE_MANIFEST = "manifest.json"


@dataclass(frozen=True)
class SkillActivation:
    """Bounded deterministic skill selection rendered for one context."""

    manifests: tuple[SkillManifest, ...]
    instructions: str
    omitted: tuple[str, ...] = ()

    @property
    def skill_ids(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.manifests)


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
        self._sources: dict[tuple[str, SkillVersion], str] = {}
        self._discovered = False

    def _candidate_paths(self) -> list[tuple[Path, Path]]:
        candidates: dict[str, tuple[Path, Path]] = {}
        for root in self.roots:
            resolved_root = root.resolve()
            if not resolved_root.exists():
                continue
            if not resolved_root.is_dir():
                raise SkillValidationError(f"skill root is not a directory: {root}")
            for pattern in (f"*{_SKILL_SUFFIX}", _STORE_MANIFEST):
                for path in resolved_root.rglob(pattern):
                    resolved = path.resolve()
                    candidates[str(resolved)] = (resolved_root, path)
        paths = [candidates[key] for key in sorted(candidates)]
        if len(paths) > self.max_files:
            raise SkillValidationError(
                f"discovered {len(paths)} skill files; limit is {self.max_files}"
            )
        return paths

    def discover(self) -> tuple[SkillManifest, ...]:
        versions: dict[str, dict[SkillVersion, SkillManifest]] = {}
        sources: dict[tuple[str, SkillVersion], str] = {}
        for root, path in self._candidate_paths():
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
            manifest = SkillManifest.from_dict(
                data,
                max_instruction_chars=self.max_instruction_chars,
            )
            version = SkillVersion.parse(manifest.version)
            key = (manifest.name, version)
            if key in sources:
                raise SkillValidationError(
                    f"duplicate skill {manifest.name}@{manifest.version}: "
                    f"{sources[key]} and {relative}"
                )
            versions.setdefault(manifest.name, {})[version] = manifest
            sources[key] = str(relative)

        self._versions = versions
        self._sources = sources
        self._discovered = True
        return self.all()

    def refresh(self) -> tuple[SkillManifest, ...]:
        """Force deterministic rediscovery after files change."""
        self._discovered = False
        return self.discover()

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
        return tuple(
            sorted(values, key=lambda item: (item.name, SkillVersion.parse(item.version)))
        )

    def source_for(self, manifest: SkillManifest) -> str:
        """Return the root-relative source path recorded at discovery."""
        self._ensure_discovered()
        return self._sources[(manifest.name, SkillVersion.parse(manifest.version))]

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
                (parsed, manifest)
                for parsed, manifest in versions.items()
                if include_disabled or manifest.enabled
            ]
            if not candidates:
                raise KeyError(skill_id)
            return max(candidates, key=lambda item: item[0])[1]
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
            sorted(
                chosen.values(),
                key=lambda item: (-item.priority, item.name, SkillVersion.parse(item.version)),
            )
        )

    def activate(
        self,
        *,
        skill_ids: Sequence[str] = (),
        capabilities: Sequence[str] = (),
        max_chars: int | None = None,
    ) -> SkillActivation:
        """Render whole skill blocks inside a hard context budget.

        Blocks are never truncated mid-instruction. A skill that cannot fit is
        reported in ``omitted`` and the remaining skills continue to be
        considered, making activation deterministic and budget-safe.
        """
        budget = self.max_render_chars if max_chars is None else min(max_chars, self.max_render_chars)
        if budget < 0:
            raise ValueError("max_chars must be non-negative")
        selected = self.select(skill_ids=skill_ids, capabilities=capabilities)
        rendered: list[str] = []
        active: list[SkillManifest] = []
        omitted: list[str] = []
        used = 0
        for manifest in selected:
            guidance = manifest.instruction_text()
            if not guidance:
                omitted.append(manifest.name)
                continue
            block = f"[skill:{manifest.name}@{manifest.version}]\n{guidance}"
            separator = 2 if rendered else 0
            if used + separator + len(block) > budget:
                omitted.append(manifest.name)
                continue
            rendered.append(block)
            active.append(manifest)
            used += separator + len(block)
        return SkillActivation(
            manifests=tuple(active),
            instructions="\n\n".join(rendered),
            omitted=tuple(omitted),
        )
