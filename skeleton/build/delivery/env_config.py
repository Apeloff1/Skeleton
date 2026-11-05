"""Layered, validated deployment environment configuration.

Configs are plain JSON objects. A layer may declare ``extends`` to inherit
from another environment; child keys override parent keys with a deep merge.
Secrets must be ``secret://`` references. Each resolved config gets a digest
so deploy plans can pin exactly what they were computed from.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from skeleton.build.delivery._util import DeliveryError, require_env_name, sha256_json
from skeleton.build.delivery.secrets_guard import assert_clean, scan_mapping

TIERS = ("dev", "staging", "production")
REQUIRED_KEYS = ("tier", "replicas", "health", "rollout")
MAX_DEPTH = 8
MAX_REPLICAS = 512
MAX_LAYER_BYTES = 256_000


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any], *, _depth: int = 0) -> dict[str, Any]:
    if _depth > MAX_DEPTH:
        raise DeliveryError("config nesting too deep")
    merged: dict[str, Any] = {k: v for k, v in base.items()}
    for key, value in override.items():
        if value is None:
            merged.pop(key, None)
        elif isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = deep_merge(merged[key], value, _depth=_depth + 1)
        else:
            merged[key] = value
    return merged


@dataclass(frozen=True)
class EnvironmentConfig:
    name: str
    values: Mapping[str, Any]
    digest: str
    lineage: tuple[str, ...]

    @property
    def tier(self) -> str:
        return self.values["tier"]

    @property
    def replicas(self) -> int:
        return self.values["replicas"]

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.values
        for part in dotted.split("."):
            if not isinstance(node, Mapping) or part not in node:
                return default
            node = node[part]
        return node


def validate_values(name: str, values: Mapping[str, Any]) -> None:
    missing = [k for k in REQUIRED_KEYS if k not in values]
    if missing:
        raise DeliveryError(f"{name}: missing keys {missing}")
    if values["tier"] not in TIERS:
        raise DeliveryError(f"{name}: tier must be one of {TIERS}")
    replicas = values["replicas"]
    if isinstance(replicas, bool) or not isinstance(replicas, int) or not 1 <= replicas <= MAX_REPLICAS:
        raise DeliveryError(f"{name}: replicas must be 1..{MAX_REPLICAS}")
    if values["tier"] == "production" and replicas < 2:
        raise DeliveryError(f"{name}: production requires at least 2 replicas")
    health = values["health"]
    if not isinstance(health, Mapping) or not isinstance(health.get("path"), str) or not health["path"].startswith("/"):
        raise DeliveryError(f"{name}: health.path must be an absolute URL path")
    rollout = values["rollout"]
    if not isinstance(rollout, Mapping) or rollout.get("strategy") not in ("rolling", "blue-green", "canary"):
        raise DeliveryError(f"{name}: rollout.strategy must be rolling, blue-green or canary")
    assert_clean(scan_mapping(values, root=name))


def resolve(name: str, layers: Mapping[str, Mapping[str, Any]]) -> EnvironmentConfig:
    require_env_name(name)
    lineage: list[str] = []
    current: str | None = name
    while current is not None:
        if current in lineage:
            raise DeliveryError(f"config inheritance cycle: {' -> '.join(lineage + [current])}")
        if current not in layers:
            raise DeliveryError(f"unknown environment {current!r}")
        lineage.append(current)
        parent = layers[current].get("extends")
        if parent is not None and not isinstance(parent, str):
            raise DeliveryError("extends must be an environment name")
        current = parent
        if len(lineage) > MAX_DEPTH:
            raise DeliveryError("config inheritance too deep")
    values: dict[str, Any] = {}
    for layer_name in reversed(lineage):
        layer = {k: v for k, v in layers[layer_name].items() if k != "extends"}
        values = deep_merge(values, layer)
    validate_values(name, values)
    return EnvironmentConfig(name, values, sha256_json(values), tuple(lineage))


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject ambiguous JSON keys at every nesting level."""
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise DeliveryError(f"duplicate deployment config key {key!r}")
        obj[key] = value
    return obj


def _reject_nonfinite(value: str) -> None:
    raise DeliveryError(f"non-finite deployment config number {value}")


def load_layers(texts: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for name, text in texts.items():
        require_env_name(name)
        if type(text) is not str or len(text) > MAX_LAYER_BYTES:
            raise DeliveryError(f"{name}: config layer exceeds {MAX_LAYER_BYTES} characters")
        try:
            data = json.loads(text, object_pairs_hook=_unique_object,
                              parse_constant=_reject_nonfinite)
        except (json.JSONDecodeError, RecursionError) as exc:
            raise DeliveryError(f"{name}: invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise DeliveryError(f"{name}: config must be a JSON object")
        out[name] = data
    return out


def diff_configs(a: EnvironmentConfig, b: EnvironmentConfig) -> dict[str, tuple[Any, Any]]:
    out: dict[str, tuple[Any, Any]] = {}

    def walk(x: Any, y: Any, path: str) -> None:
        if isinstance(x, Mapping) and isinstance(y, Mapping):
            for key in sorted(set(x) | set(y)):
                walk(x.get(key), y.get(key), f"{path}.{key}" if path else key)
        elif x != y:
            out[path] = (x, y)

    walk(a.values, b.values, "")
    return out
