"""Bridge: config settings → kernel ConfigStore snapshots.

`skeleton.config.settings` validates env-driven values once at boot, but
the kernel wants versioned, auditable snapshots: propose, validate,
activate, rollback. This module flattens a settings object into a plain
mapping and drives a ConfigStore with it.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from skeleton.kernel.config_snapshots import ConfigSnapshot, ConfigStore
from skeleton.kernel.errors import KernelError


class SettingsBridgeError(KernelError):
    code = "CFG.BRIDGE"


def flatten(settings: Any, *, prefix: str = "") -> Dict[str, Any]:
    """Turn pydantic/dataclass-style settings into a flat dotted map."""
    out: Dict[str, Any] = {}
    if hasattr(settings, "model_dump"):
        data = settings.model_dump()
    elif hasattr(settings, "__dict__"):
        data = dict(settings.__dict__)
    else:
        raise SettingsBridgeError(
            "cannot flatten settings object",
            context={"type": type(settings).__name__},
        )

    def walk(obj: Any, path: str) -> None:
        if isinstance(obj, Mapping):
            for k, v in obj.items():
                walk(v, f"{path}.{k}" if path else str(k))
        else:
            out[path] = obj

    walk(data, prefix)
    return out


class SettingsSnapshotBridge:
    """Propose/activate/rollback settings versions via kernel ConfigStore."""

    def __init__(self, store: Optional[ConfigStore] = None) -> None:
        self.store = store or ConfigStore()

    def propose(
        self, settings: Any, *, actor: str, reason: str = ""
    ) -> ConfigSnapshot:
        values = flatten(settings)
        return self.store.propose(values, actor=actor, reason=reason)

    def activate(self, version: int, *, actor: str, reason: str = "") -> ConfigSnapshot:
        return self.store.activate(version, actor=actor, reason=reason)

    def rollback(self, version: int, *, actor: str, reason: str = "") -> ConfigSnapshot:
        return self.store.rollback(version, actor=actor, reason=reason)

    def current(self) -> Optional[ConfigSnapshot]:
        return self.store.current()
