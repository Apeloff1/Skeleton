"""Read-only, deterministic registry of console, computer, arcade and homebrew targets.

Catalog records identify candidate design sources and port destinations, not working
SDKs or verified hardware specifications. Native compilation must be separately
qualified. No network, emulator, ROM, BIOS or binary loading occurs here.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from types import MappingProxyType
from typing import Mapping
import json
import re

REGISTRY_SCHEMA = 1
_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]+$")
_KINDS = frozenset({"console", "handheld", "computer", "arcade", "calculator", "mobile", "educational", "micro"})
_ALLOWED_LIFECYCLE = frozenset({"legacy", "current"})
_ALLOWED_RESEARCH = frozenset({"catalogued"})
_ALLOWED_TOOLCHAIN = frozenset({"unverified"})


class PlatformRegistryError(ValueError):
    """Fail-closed platform metadata error."""


@dataclass(frozen=True, slots=True)
class PlatformProfile:
    id: str
    name: str
    kind: str
    family: str
    preset: str
    lifecycle: str
    research_status: str
    toolchain_status: str
    tier: int
    render: str
    sound: str
    input: str
    artifact: str
    constraints: tuple[str, ...]

    @property
    def verified_for_native_export(self) -> bool:
        # A separate, independently verified toolchain/evidence pipeline is required.
        # This catalog is NOT an export-capability attestation.
        return False

    @property
    def is_legacy(self) -> bool:
        return self.lifecycle == "legacy"


@dataclass(frozen=True, slots=True)
class PlatformRegistry:
    profiles: Mapping[str, PlatformProfile]
    schema_version: int

    def get(self, platform_id: str) -> PlatformProfile:
        if not isinstance(platform_id, str):
            raise PlatformRegistryError("platform id must be a string")
        try:
            return self.profiles[platform_id]
        except KeyError as exc:
            raise PlatformRegistryError("unknown platform: " + platform_id) from exc

    def select(
        self, *, kind: str | None = None, family: str | None = None,
        legacy: bool | None = None, minimum_tier: int | None = None,
    ) -> tuple[PlatformProfile, ...]:
        return tuple(
            p for p in self.profiles.values()
            if (kind is None or p.kind == kind)
            and (family is None or p.family == family)
            and (legacy is None or p.is_legacy is legacy)
            and (minimum_tier is None or p.tier >= minimum_tier)
        )

    def summary(self) -> dict[str, object]:
        kinds: dict[str, int] = {}
        for platform in self.profiles.values():
            kinds[platform.kind] = kinds.get(platform.kind, 0) + 1
        return {
            "schema_version": self.schema_version,
            "platform_count": len(self.profiles),
            "kinds": dict(sorted(kinds.items())),
            "native_export_verified": 0,
            "research_only": len(self.profiles),
        }


def parse_registry(document: str | bytes) -> PlatformRegistry:
    """Validate untrusted, machine-readable registry before constructing profiles."""
    try:
        data = json.loads(document)
    except (TypeError, ValueError) as exc:
        raise PlatformRegistryError("invalid platform registry JSON") from exc
    if not isinstance(data, dict) or data.get("schema_version") != REGISTRY_SCHEMA:
        raise PlatformRegistryError("unsupported registry schema")
    presets = data.get("presets")
    records = data.get("platforms")
    if not isinstance(presets, dict) or not presets:
        raise PlatformRegistryError("missing capability presets")
    if not isinstance(records, list) or not records:
        raise PlatformRegistryError("missing platform records")

    required = {"id", "name", "kind", "family", "preset", "lifecycle", "research_status", "toolchain_status"}
    profiles: dict[str, PlatformProfile] = {}
    for item in records:
        if not isinstance(item, dict) or not required.issubset(item):
            raise PlatformRegistryError("malformed platform record")
        id_ = item["id"]
        if not isinstance(id_, str) or _ID_PATTERN.fullmatch(id_) is None or id_ in profiles:
            raise PlatformRegistryError("duplicate or invalid platform identifier")
        if any(not isinstance(item[k], str) or not item[k].strip() for k in required):
            raise PlatformRegistryError("empty platform metadata")
        if item["kind"] not in _KINDS or item["lifecycle"] not in _ALLOWED_LIFECYCLE:
            raise PlatformRegistryError("unknown category or lifecycle")
        if item["research_status"] not in _ALLOWED_RESEARCH or item["toolchain_status"] not in _ALLOWED_TOOLCHAIN:
            raise PlatformRegistryError("catalog cannot self-certify SDK or deployment capability")
        preset = presets.get(item["preset"])
        if not isinstance(preset, dict):
            raise PlatformRegistryError("missing preset: " + item["preset"])
        tier = preset.get("tier")
        if type(tier) is not int or not 0 <= tier <= 4:
            raise PlatformRegistryError("invalid capability tier")
        fields = ("render", "sound", "input", "artifact")
        if any(not isinstance(preset.get(k), str) or not preset[k] for k in fields):
            raise PlatformRegistryError("incomplete capability preset")
        constraints = preset.get("constraints")
        if (
            not isinstance(constraints, list) or not constraints
            or any(not isinstance(v, str) or not v.strip() for v in constraints)
        ):
            raise PlatformRegistryError("missing hardware-aware constraints")
        profiles[id_] = PlatformProfile(
            id=id_, name=item["name"], kind=item["kind"], family=item["family"],
            preset=item["preset"], lifecycle=item["lifecycle"],
            research_status=item["research_status"], toolchain_status=item["toolchain_status"],
            tier=tier, render=preset["render"], sound=preset["sound"],
            input=preset["input"], artifact=preset["artifact"], constraints=tuple(constraints),
        )
    # Sorted, immutable identifiers and values make results reproducible.
    return PlatformRegistry(MappingProxyType(dict(sorted(profiles.items()))), REGISTRY_SCHEMA)


@lru_cache(maxsize=1)
def default_registry() -> PlatformRegistry:
    raw = files("skeleton.ai.game_builder").joinpath("platform_catalog.json").read_text(encoding="utf-8")
    return parse_registry(raw)


def lookup_platform(platform_id: str) -> PlatformProfile:
    return default_registry().get(platform_id)


def list_platforms(
    *, kind: str | None = None, family: str | None = None, legacy: bool | None = None,
) -> tuple[PlatformProfile, ...]:
    return default_registry().select(kind=kind, family=family, legacy=legacy)
