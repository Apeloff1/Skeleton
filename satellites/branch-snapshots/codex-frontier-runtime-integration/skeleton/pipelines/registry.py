"""Pipeline registry — map names to registered pipeline constructors.

The API server needs a factory, not direct imports of every pipeline;
the registry keeps a name → class map and returns instances on demand.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from skeleton.kernel.errors import PipelineError


class RegistryError(PipelineError):
    code = "PPL.REGISTRY"


class PipelineRegistry:
    """Name keyed lookup of pipeline factories."""

    def __init__(self) -> None:
        self._factories: Dict[str, Callable[[], Any]] = {}

    def register(self, name: str, factory: Callable[[], Any]) -> None:
        if not name:
            raise RegistryError("pipeline name must be non-empty")
        self._factories[name] = factory

    def get(self, name: str) -> Callable[[], Any]:
        factory = self._factories.get(name)
        if factory is None:
            raise RegistryError(
                "unknown pipeline",
                context={"name": name, "known": sorted(self._factories)},
            )
        return factory

    def names(self) -> List[str]:
        return sorted(self._factories)

    def create(self, name: str) -> Any:
        return self.get(name)()
