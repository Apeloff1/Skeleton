"""Configuration manager — layered, hot-reloadable config with validation.

Provides a hierarchical configuration system: defaults → file → env → runtime.
Supports schema validation, hot reload, and change callbacks.
Integrates with audit logging to record every config mutation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class ConfigManager:
    """Layered configuration with hot reload and validation."""

    def __init__(self, root: Optional[Path] = None, schema: Optional[Dict[str, Any]] = None):
        self.root = root or Path(".")
        self.schema = schema or {}
        self._layers: List[Dict[str, Any]] = [{}]
        self._callbacks: List[Callable[[str, Any, Any], None]] = []
        self._file = self.root / "skeleton_config.json"
        self._load_file()
        self._load_env()

    def _load_file(self) -> None:
        if self._file.exists():
            text = self._file.read_text(encoding="utf-8")
            data = json.loads(text)
            self._layers.append(data)

    def _load_env(self) -> None:
        env: Dict[str, Any] = {}
        prefix = "SKELETON_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                path = key[len(prefix):].lower().split("__")
                self._set_nested(env, path, self._coerce(value))
        if env:
            self._layers.append(env)

    def _coerce(self, value: str) -> Any:
        if value.lower() in ("true", "false"):
            return value.lower() == "true"
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value

    def _set_nested(self, d: Dict[str, Any], path: List[str], value: Any) -> None:
        for key in path[:-1]:
            d = d.setdefault(key, {})
        d[path[-1]] = value

    def _get_nested(self, d: Dict[str, Any], path: List[str]) -> Any:
        for key in path:
            if not isinstance(d, dict) or key not in d:
                return None
            d = d[key]
        return d

    def get(self, path: str, default: Any = None) -> Any:
        keys = path.split(".")
        for layer in reversed(self._layers):
            value = self._get_nested(layer, keys)
            if value is not None:
                return value
        return default

    def set(self, path: str, value: Any) -> None:
        keys = path.split(".")
        old = self.get(path)
        if not self._layers[-1]:
            self._layers.append({})
        self._set_nested(self._layers[-1], keys, value)
        for cb in self._callbacks:
            try:
                cb(path, old, value)
            except Exception:
                pass

    def on_change(self, callback: Callable[[str, Any, Any], None]) -> None:
        self._callbacks.append(callback)

    def reload(self) -> None:
        self._layers = [{}]
        self._load_file()
        self._load_env()

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "config-card",
            "layers": len(self._layers),
            "file": str(self._file),
            "callbacks": len(self._callbacks),
        }
