"""
Skeleton Configuration System

Layered configuration with:
- defaults:    Built-in base settings
- project:     Project-level config (config/settings.yaml)
- user:        User overrides (~/.skeleton/config.yaml)
- environment: Environment variables (SKELETON_*)
- runtime:     In-memory overrides

Access pattern:
    from skeleton.config import cfg
    value = cfg.get("memory.rag.top_k", default=5)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULTS: Dict[str, Any] = {
    "kernel": {
        "entropy_seed": None,
        "event_bus_buffer": 1000,
    },
    "memory": {
        "rag": {"top_k": 5, "min_score": 0.3},
        "cag": {"capacity": 1000},
        "mag": {"episodes_max": 500},
        "trinity": {"fusion_strategy": "rrf"},
    },
    "intelligence": {
        "orchestrator": {"max_agents": 16},
        "adaptive": {"learning_rate": 0.01},
    },
    "swarm": {
        "mesh": {"max_nodes": 64},
        "pheromone_decay": 0.95,
    },
    "forge": {
        "default_era": "extraction_now",
        "default_target": "json",
        "repair_max_rounds": 3,
    },
    "api": {
        "host": "0.0.0.0",
        "port": 8000,
        "cors_origins": ["*"],
    },
    "observability": {
        "sampling_rate": 0.1,
        "metrics_retention": 86400,
    },
}


@dataclass
class ConfigLayer:
    """A single configuration layer."""
    name: str
    data: Dict[str, Any] = field(default_factory=dict)
    mutable: bool = True


class Config:
    """Layered configuration manager."""

    def __init__(self):
        self._layers: List[ConfigLayer] = [
            ConfigLayer(name="defaults", data=self._deep_copy(DEFAULTS), mutable=False),
        ]
        self._load_project_config()
        self._load_user_config()
        self._load_environment()

    @staticmethod
    def _deep_copy(data: Dict[str, Any]) -> Dict[str, Any]:
        import copy
        return copy.deepcopy(data)

    def _load_project_config(self) -> None:
        """Load config/settings.yaml from project root."""
        project_file = Path("config/settings.yaml")
        if project_file.exists():
            try:
                import yaml
                with open(project_file) as f:
                    data = yaml.safe_load(f) or {}
                self._layers.append(ConfigLayer(name="project", data=data))
            except Exception:
                pass  # YAML not available or file invalid

    def _load_user_config(self) -> None:
        """Load ~/.skeleton/config.yaml."""
        user_file = Path.home() / ".skeleton" / "config.yaml"
        if user_file.exists():
            try:
                import yaml
                with open(user_file) as f:
                    data = yaml.safe_load(f) or {}
                self._layers.append(ConfigLayer(name="user", data=data))
            except Exception:
                pass

    def _load_environment(self) -> None:
        """Load SKELETON_* environment variables."""
        env_data: Dict[str, Any] = {}
        for key, value in os.environ.items():
            if key.startswith("SKELETON_"):
                path = key[9:].lower().replace("__", ".")
                self._set_path(env_data, path, value)
        if env_data:
            self._layers.append(ConfigLayer(name="environment", data=env_data))

    @staticmethod
    def _set_path(data: Dict[str, Any], path: str, value: str) -> None:
        """Set a dotted path in nested dict."""
        keys = path.split(".")
        for key in keys[:-1]:
            data = data.setdefault(key, {})
        # Try to parse as int/float/bool
        parsed: Any = value
        if value.lower() in ("true", "false"):
            parsed = value.lower() == "true"
        else:
            try:
                parsed = int(value)
            except ValueError:
                try:
                    parsed = float(value)
                except ValueError:
                    pass
        keys[-1] = keys[-1].replace("_", ".")
        # Handle nested key
        final = keys[-1].split(".")
        for key in final[:-1]:
            data = data.setdefault(key, {})
        data[final[-1]] = parsed

    def get(self, path: str, default: Any = None) -> Any:
        """Get configuration value by dotted path."""
        for layer in reversed(self._layers):
            value = self._get_path(layer.data, path)
            if value is not None:
                return value
        return default

    @staticmethod
    def _get_path(data: Dict[str, Any], path: str) -> Any:
        keys = path.split(".")
        value: Any = data
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        return value

    def set(self, path: str, value: Any) -> None:
        """Set runtime configuration value."""
        # Ensure runtime layer exists
        runtime = next((l for l in self._layers if l.name == "runtime"), None)
        if runtime is None:
            runtime = ConfigLayer(name="runtime", data={})
            self._layers.append(runtime)
        keys = path.split(".")
        data = runtime.data
        for key in keys[:-1]:
            data = data.setdefault(key, {})
        data[keys[-1]] = value

    def all(self) -> Dict[str, Any]:
        """Merge all layers into a single dict."""
        result: Dict[str, Any] = {}
        for layer in self._layers:
            result = self._merge(result, layer.data)
        return result

    @staticmethod
    def _merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(base)
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = Config._merge(result[key], value)
            else:
                result[key] = value
        return result

    def dump(self) -> str:
        """Dump merged configuration as YAML string."""
        try:
            import yaml
            return yaml.safe_dump(self.all(), default_flow_style=False)
        except Exception:
            import json
            return json.dumps(self.all(), indent=2)


# Global configuration instance
_cfg: Optional[Config] = None


def get_config() -> Config:
    """Get or create the global configuration instance."""
    global _cfg
    if _cfg is None:
        _cfg = Config()
    return _cfg


# Convenience shortcuts
cfg = get_config()
