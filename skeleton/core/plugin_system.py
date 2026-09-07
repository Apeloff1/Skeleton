"""Plugin system — dynamic subsystem extension with lifecycle hooks.

Plugins declare a name, version, and lifecycle hooks (on_load,
on_unload, on_command). The plugin manager validates manifests,
tracks dependencies between plugins, and isolates failures so a
broken plugin cannot take down the deck.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class PluginManifest:
    name: str
    version: str
    description: str = ""
    dependencies: List[str] = field(default_factory=list)
    commands: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "dependencies": self.dependencies,
            "commands": self.commands,
        }


@dataclass
class Plugin:
    manifest: PluginManifest
    on_load: Optional[Callable[[Any], None]] = None
    on_unload: Optional[Callable[[], None]] = None
    handlers: Dict[str, Callable[..., Any]] = field(default_factory=dict)
    loaded: bool = False
    error: Optional[str] = None
    loaded_at_ns: int = 0


class PluginManager:
    """Plugin lifecycle manager with dependency ordering."""

    def __init__(self):
        self._plugins: Dict[str, Plugin] = {}
        self._load_order: List[str] = []

    def register(self, manifest: PluginManifest, *,
                 on_load: Optional[Callable[[Any], None]] = None,
                 on_unload: Optional[Callable[[], None]] = None,
                 handlers: Optional[Dict[str, Callable[..., Any]]] = None) -> Plugin:
        plugin = Plugin(manifest=manifest, on_load=on_load, on_unload=on_unload, handlers=handlers or {})
        self._plugins[manifest.name] = plugin
        return plugin

    def _resolve_order(self, name: str, seen: Optional[set] = None) -> List[str]:
        seen = seen or set()
        if name in seen:
            raise ValueError(f"circular plugin dependency: {name}")
        seen.add(name)
        order: List[str] = []
        for dep in self._plugins[name].manifest.dependencies:
            if dep not in self._plugins:
                raise KeyError(f"missing plugin dependency: {dep}")
            order.extend(self._resolve_order(dep, seen))
        if name not in order:
            order.append(name)
        return order

    def load(self, name: str, context: Any = None) -> bool:
        plugin = self._plugins.get(name)
        if not plugin:
            raise KeyError(f"unknown plugin: {name}")
        if plugin.loaded:
            return True
        for dep_name in self._resolve_order(name)[:-1]:
            self.load(dep_name, context)
        try:
            if plugin.on_load:
                plugin.on_load(context)
            plugin.loaded = True
            plugin.error = None
            plugin.loaded_at_ns = time.time_ns()
            self._load_order.append(name)
            return True
        except Exception as exc:  # noqa: BLE001
            plugin.error = str(exc)
            plugin.loaded = False
            return False

    def unload(self, name: str) -> bool:
        plugin = self._plugins.get(name)
        if not plugin or not plugin.loaded:
            return False
        dependents = [p for p in self._plugins.values() if p.loaded and name in p.manifest.dependencies]
        if dependents:
            raise ValueError(f"plugin {name} has loaded dependents: {[d.manifest.name for d in dependents]}")
        try:
            if plugin.on_unload:
                plugin.on_unload()
        finally:
            plugin.loaded = False
            if name in self._load_order:
                self._load_order.remove(name)
        return True

    def dispatch(self, command: str, *args: Any, **kwargs: Any) -> Any:
        for name in reversed(self._load_order):
            plugin = self._plugins[name]
            if plugin.loaded and command in plugin.handlers:
                return plugin.handlers[command](*args, **kwargs)
        raise KeyError(f"no loaded plugin handles command: {command}")

    def handles(self, command: str) -> List[str]:
        return [p.manifest.name for p in self._plugins.values() if p.loaded and command in p.handlers]

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "plugin-card",
            "plugins": {name: {
                "version": p.manifest.version,
                "loaded": p.loaded,
                "error": p.error,
                "commands": list(p.handlers.keys()),
            } for name, p in self._plugins.items()},
            "load_order": self._load_order,
        }
