"""Manifest-bound runtime loading for Skeleton's canonical capability planes.

The capability manifest is the authority for what may be resolved. Runtime
consumers therefore get one stable bridge across subsystem boundaries without
turning a user supplied string into an arbitrary Python import.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module, util as importlib_util
from threading import RLock
from types import ModuleType

from .capability_manifest import CAPABILITIES, CAPABILITY_MANIFEST_VERSION, get_capability

_CAPABILITY_IMPORTERS = {
    "application": ("skeleton.application", lambda: import_module("skeleton.application")),
    "gameforge": ("skeleton.forge", lambda: import_module("skeleton.forge")),
    "cortex": ("skeleton.cortex", lambda: import_module("skeleton.cortex")),
    "jeeves": ("skeleton.jeeves", lambda: import_module("skeleton.jeeves")),
    "organism": ("skeleton.organism", lambda: import_module("skeleton.organism")),
    "social": ("skeleton.social", lambda: import_module("skeleton.social")),
    "galaxy": ("skeleton.galaxy", lambda: import_module("skeleton.galaxy")),
    "kernel": ("skeleton.kernel", lambda: import_module("skeleton.kernel")),
    "memory": ("skeleton.memory", lambda: import_module("skeleton.memory")),
    "intelligence": ("skeleton.intelligence", lambda: import_module("skeleton.intelligence")),
    "swarm": ("skeleton.swarm", lambda: import_module("skeleton.swarm")),
    "resilience": ("skeleton.resilience", lambda: import_module("skeleton.resilience")),
    "observability": ("skeleton.observability", lambda: import_module("skeleton.observability")),
    "api": ("skeleton.api", lambda: import_module("skeleton.api")),
    "developer": ("skeleton.developer", lambda: import_module("skeleton.developer")),
    "deploy": ("skeleton.deploy", lambda: import_module("skeleton.deploy")),
    "testing": ("skeleton.testing", lambda: import_module("skeleton.testing")),
    "pipelines": ("skeleton.pipelines", lambda: import_module("skeleton.pipelines")),
    "vault": ("skeleton.vault", lambda: import_module("skeleton.vault")),
    "retrieval": ("skeleton.retrieval", lambda: import_module("skeleton.retrieval")),
    "agents": ("skeleton.agents", lambda: import_module("skeleton.agents")),
    "context": ("skeleton.context", lambda: import_module("skeleton.context")),
    "config": ("skeleton.config", lambda: import_module("skeleton.config")),
    "content": ("skeleton.content", lambda: import_module("skeleton.content")),
}


class CapabilityLoadError(RuntimeError):
    """Raised when a curated capability cannot be imported."""

    def __init__(self, capability_id: str) -> None:
        self.capability_id = capability_id
        super().__init__(f"failed to load capability: {capability_id}")


@dataclass(frozen=True, slots=True)
class CapabilityRuntimeStatus:
    """Side-effect-free runtime state for one manifest capability."""

    id: str
    module: str
    loaded: bool


class CapabilityLoader:
    """Thread-safe lazy loader restricted to the curated capability manifest."""

    def __init__(self) -> None:
        self._loaded: dict[str, ModuleType] = {}
        self._lock = RLock()

    def resolve(self, capability_id: str) -> ModuleType:
        """Resolve one stable capability ID to its canonical package module."""

        capability = get_capability(capability_id)
        with self._lock:
            cached = self._loaded.get(capability.id)
            if cached is not None:
                return cached
            try:
                expected_module, importer = _CAPABILITY_IMPORTERS[capability.id]
                if capability.module != expected_module:
                    raise RuntimeError("capability manifest/import allowlist mismatch")
                module = importer()
            except Exception as exc:
                raise CapabilityLoadError(capability.id) from exc
            self._loaded[capability.id] = module
            return module

    def is_loaded(self, capability_id: str) -> bool:
        """Return whether this loader already resolved the capability."""

        capability = get_capability(capability_id)
        with self._lock:
            return capability.id in self._loaded

    def loaded_ids(self) -> tuple[str, ...]:
        """Return loaded capability IDs in manifest order."""

        with self._lock:
            loaded = frozenset(self._loaded)
        return tuple(capability.id for capability in CAPABILITIES if capability.id in loaded)

    def status(self) -> tuple[CapabilityRuntimeStatus, ...]:
        """Return deterministic runtime status without importing new modules."""

        with self._lock:
            loaded = frozenset(self._loaded)
        return tuple(
            CapabilityRuntimeStatus(
                id=capability.id,
                module=capability.module,
                loaded=capability.id in loaded,
            )
            for capability in CAPABILITIES
        )

    def clear_cache(self) -> None:
        """Forget loader-local module references without mutating ``sys.modules``."""

        with self._lock:
            self._loaded.clear()


CAPABILITY_LOADER = CapabilityLoader()


def load_capability(capability_id: str) -> ModuleType:
    """Resolve a canonical subsystem through the shared application loader."""

    return CAPABILITY_LOADER.resolve(capability_id)


def capability_runtime_status() -> tuple[CapabilityRuntimeStatus, ...]:
    """Return the shared loader's side-effect-free capability status."""

    return CAPABILITY_LOADER.status()


def capability_lifecycle_snapshot() -> dict[str, object]:
    """Return manifest rows plus resolvable/loaded lifecycle flags.

    The identity manifest stays a three-field contract. Lifecycle is an additive
    snapshot so CLI/API consumers can inspect runtime readiness without changing
    ``schema_version`` or importing every plane.
    """

    statuses = {status.id: status for status in capability_runtime_status()}
    rows: list[dict[str, object]] = []
    for capability in CAPABILITIES:
        status = statuses[capability.id]
        rows.append(
            {
                "id": capability.id,
                "module": capability.module,
                "description": capability.description,
                "resolvable": importlib_util.find_spec(capability.module) is not None,
                "loaded": status.loaded,
            }
        )
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": "lifecycle",
        "capabilities": rows,
    }
