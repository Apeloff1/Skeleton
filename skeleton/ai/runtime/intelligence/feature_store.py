"""Point-in-time feature store.

A training row is emitted only when every requested feature existed at
``as_of``. A later write cannot fill an earlier row, and a missing feature
is not stored as null for a model to treat as a value.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


class FeatureStoreError(ValueError):
    """A feature write or lookup violates the store contract."""


_JSON_SCALARS = (str, int, float, bool, type(None))


def _json_value(value: Any) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise FeatureStoreError("feature values must be finite")
        return
    if isinstance(value, list):
        for item in value:
            _json_value(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise FeatureStoreError("feature object keys must be strings")
            _json_value(item)
        return
    raise FeatureStoreError("feature values must be JSON values")


def _token(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FeatureStoreError(f"{label} is required")
    return value


def _timestamp(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FeatureStoreError("timestamp_ns must be a non-negative integer")
    return value


@dataclass
class FeatureValue:
    entity_id: str
    value: Any
    timestamp_ns: int


@dataclass
class FeatureDef:
    name: str
    entity: str
    compute: Optional[Callable[[Dict[str, Any]], Any]] = None
    ttl_s: float = 3600.0
    version: int = 1
    description: str = ""


class FeatureStore:
    """Online values and leakage-free training rows."""

    def __init__(self) -> None:
        self._defs: Dict[str, FeatureDef] = {}
        self._values: Dict[str, List[FeatureValue]] = {}
        self._feature_of: Dict[str, str] = {}

    def _key(self, feature: str, entity_id: str) -> str:
        return f"{feature}:{entity_id}"

    def register(
        self,
        name: str,
        entity: str,
        compute: Optional[Callable[[Dict[str, Any]], Any]] = None,
        ttl_s: float = 3600.0,
        description: str = "",
    ) -> FeatureDef:
        name = _token(name, "feature name")
        entity = _token(entity, "entity")
        if isinstance(ttl_s, bool) or not isinstance(ttl_s, (int, float)) or not math.isfinite(float(ttl_s)) or float(ttl_s) < 0:
            raise FeatureStoreError("ttl_s must be a non-negative finite number")
        if not isinstance(description, str):
            raise FeatureStoreError("description must be a string")
        if compute is not None and not callable(compute):
            raise FeatureStoreError("compute must be callable")
        existing = self._defs.get(name)
        definition = FeatureDef(
            name=name,
            entity=entity,
            compute=compute,
            ttl_s=float(ttl_s),
            version=(existing.version + 1) if existing else 1,
            description=description,
        )
        self._defs[name] = definition
        return definition

    def write(
        self,
        feature: str,
        entity_id: str,
        value: Any,
        timestamp_ns: Optional[int] = None,
    ) -> FeatureValue:
        if feature not in self._defs:
            raise KeyError(f"unregistered feature: {feature}")
        entity_id = _token(entity_id, "entity_id")
        _json_value(value)
        stamped = _timestamp(time.time_ns() if timestamp_ns is None else timestamp_ns)
        stored = FeatureValue(entity_id=entity_id, value=value, timestamp_ns=stamped)
        key = self._key(feature, entity_id)
        self._feature_of[key] = feature
        series = self._values.setdefault(key, [])
        series.append(stored)
        series.sort(key=lambda item: item.timestamp_ns)
        return stored

    def online(self, feature: str, entity_id: str) -> Optional[Any]:
        if feature not in self._defs:
            raise KeyError(f"unregistered feature: {feature}")
        definition = self._defs[feature]
        series = self._values.get(self._key(feature, entity_id), [])
        if not series:
            return None
        latest = series[-1]
        if (time.time_ns() - latest.timestamp_ns) / 1e9 > definition.ttl_s:
            return None
        return latest.value

    def point_in_time(self, feature: str, entity_id: str, as_of_ns: int) -> Optional[Any]:
        if feature not in self._defs:
            raise KeyError(f"unregistered feature: {feature}")
        as_of = _timestamp(as_of_ns)
        series = self._values.get(self._key(feature, _token(entity_id, "entity_id")), [])
        eligible = [item for item in series if item.timestamp_ns <= as_of]
        if not eligible:
            return None
        return eligible[-1].value

    def training_set(
        self,
        features: List[str],
        entities: List[str],
        as_of_ns: int,
    ) -> List[Dict[str, Any]]:
        if not isinstance(features, list) or not features or any(feature not in self._defs for feature in features):
            raise FeatureStoreError("training features must be registered")
        if not isinstance(entities, list) or not entities:
            raise FeatureStoreError("training entities are required")
        rows: List[Dict[str, Any]] = []
        for entity_id in entities:
            values = {feature: self.point_in_time(feature, entity_id, as_of_ns) for feature in features}
            if any(value is None for value in values.values()):
                continue
            rows.append({"entity_id": entity_id, **values})
        return rows

    def freshness(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        now = time.time_ns()
        for key, series in self._values.items():
            if not series:
                continue
            feature = self._feature_of[key]
            definition = self._defs.get(feature)
            age_s = (now - series[-1].timestamp_ns) / 1e9
            ttl = definition.ttl_s if definition is not None else 0
            out[key] = {"age_s": round(age_s, 1), "stale": age_s > ttl, "values": len(series)}
        return out

    def card(self) -> Dict[str, Any]:
        fresh = self.freshness()
        return {
            "kind": "feature-store-card",
            "features": {
                name: {"entity": definition.entity, "version": definition.version, "ttl_s": definition.ttl_s}
                for name, definition in self._defs.items()
            },
            "series": len(self._values),
            "stale_series": len([key for key, row in fresh.items() if row["stale"]]),
        }


__all__ = ["FeatureDef", "FeatureStore", "FeatureStoreError", "FeatureValue"]
