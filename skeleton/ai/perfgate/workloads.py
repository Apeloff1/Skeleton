"""Built-in GameForge workloads for the soak harness (imported lazily)."""
from __future__ import annotations

from typing import Callable, Dict


def forge_walk(era: str = "soulslike") -> Callable[[], object]:
    def _run() -> object:
        from skeleton.forge.walk_cli import walk_once
        payload = walk_once(era)
        if isinstance(payload, dict) and payload.get("ok") is False:
            raise RuntimeError(f"walk failed for era {era}")
        return payload
    return _run


def noop() -> Callable[[], object]:
    return lambda: None


REGISTRY: Dict[str, Callable[..., Callable[[], object]]] = {
    "forge_walk": forge_walk,
    "noop": noop,
}


def resolve(spec: str) -> Callable[[], object]:
    """``name`` or ``name:arg`` e.g. ``forge_walk:soulslike``."""
    name, _, arg = spec.partition(":")
    if name not in REGISTRY:
        raise KeyError(f"unknown workload {name!r}; known: {sorted(REGISTRY)}")
    return REGISTRY[name](arg) if arg else REGISTRY[name]()
