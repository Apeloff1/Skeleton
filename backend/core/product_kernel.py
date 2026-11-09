"""Canonical product boundary for the consolidated Skeleton application.

The codebase contains many specialized routers and engines. ProductKernel gives
those internals a small stable vocabulary so frontend, automation, health checks,
and future migrations do not couple themselves to the historical module graph.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ProductPillar(StrEnum):
    CREATE = "create"
    PLAY = "play"
    LEARN = "learn"
    OPERATE = "operate"


@dataclass(frozen=True, slots=True)
class Capability:
    id: str
    pillar: ProductPillar
    title: str
    api_prefixes: tuple[str, ...]
    critical: bool = False


CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        "studio",
        ProductPillar.CREATE,
        "Studio",
        ("/api/gameforge-studio", "/api/gameforge-build", "/api/game-router"),
        critical=True,
    ),
    Capability(
        "world-forge",
        ProductPillar.CREATE,
        "World Forge",
        ("/api/worldforge", "/api/godot-engine", "/api/asset-forge"),
    ),
    Capability(
        "playables",
        ProductPillar.PLAY,
        "Play",
        ("/api/playable", "/api/playable-pipeline", "/api/liveops"),
        critical=True,
    ),
    Capability(
        "jeeves",
        ProductPillar.LEARN,
        "Jeeves",
        ("/api/jeeves", "/api/jeeves-core", "/api/jeeves-compose"),
        critical=True,
    ),
    Capability(
        "academy",
        ProductPillar.LEARN,
        "Academy",
        ("/api/academy", "/api/math-academy", "/api/language-academy"),
    ),
    Capability(
        "operations",
        ProductPillar.OPERATE,
        "Operations",
        ("/api/ops", "/api/swarm", "/api/gameforge-runtime"),
        critical=True,
    ),
    Capability(
        "governance",
        ProductPillar.OPERATE,
        "Governance",
        ("/api/governance",),
    ),
)


class ProductKernel:
    def __init__(self, capabilities: tuple[Capability, ...] = CAPABILITIES) -> None:
        ids = [capability.id for capability in capabilities]
        if len(ids) != len(set(ids)):
            raise ValueError("capability ids must be unique")
        self._capabilities = capabilities
        self._by_id = {capability.id: capability for capability in capabilities}

    def all(self) -> tuple[Capability, ...]:
        return self._capabilities

    def by_id(self, capability_id: str) -> Capability | None:
        return self._by_id.get(capability_id)

    def for_pillar(self, pillar: ProductPillar | str) -> tuple[Capability, ...]:
        normalized = ProductPillar(pillar)
        return tuple(c for c in self._capabilities if c.pillar is normalized)

    def owner_for_path(self, path: str) -> Capability | None:
        """Return the product capability owning an API path, longest prefix wins."""
        candidates: list[tuple[int, Capability]] = []
        for capability in self._capabilities:
            for prefix in capability.api_prefixes:
                if path == prefix or path.startswith(prefix + "/"):
                    candidates.append((len(prefix), capability))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def critical_ids(self) -> tuple[str, ...]:
        return tuple(c.id for c in self._capabilities if c.critical)


PRODUCT_KERNEL = ProductKernel()
