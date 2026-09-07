"""Feature store — versioned ML feature registry with point-in-time lookups.

Registers feature definitions (name, entity, computation), serves
latest values for online inference, and reconstructs point-in-time
feature sets for training without leakage. Tracks freshness and
lineage per feature group.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


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
    """Online/offline feature registry with point-in-time correctness."""

    def __init__(self):
        self._defs: Dict[str, FeatureDef] = {}
        self._values: Dict[str, List[FeatureValue]] = {}

    def _key(self, feature: str, entity_id: str) -> str:
        return f"{feature}:{entity_id}"

    def register(self, name: str, entity: str,
                 compute: Optional[Callable[[Dict[str, Any]], Any]] = None,
                 ttl_s: float = 3600.0, description: str = "") -> FeatureDef:
        existing = self._defs.get(name)
        fd = FeatureDef(
            name=name, entity=entity, compute=compute, ttl_s=ttl_s,
            version=(existing.version + 1) if existing else 1,
            description=description,
        )
        self._defs[name] = fd
        return fd

    def write(self, feature: str, entity_id: str, value: Any,
              timestamp_ns: Optional[int] = None) -> FeatureValue:
        if feature not in self._defs:
            raise KeyError(f"unregistered feature: {feature}")
        fv = FeatureValue(entity_id=entity_id, value=value, timestamp_ns=timestamp_ns or time.time_ns())
        buf = self._values.setdefault(self._key(feature, entity_id), [])
        buf.append(fv)
        buf.sort(key=lambda x: x.timestamp_ns)
        return fv

    def online(self, feature: str, entity_id: str) -> Optional[Any]:
        fd = self._defs.get(feature)
        buf = self._values.get(self._key(feature, entity_id), [])
        if not fd or not buf:
            return None
        latest = buf[-1]
        if (time.time_ns() - latest.timestamp_ns) / 1e9 > fd.ttl_s:
            return None
        return latest.value

    def point_in_time(self, feature: str, entity_id: str, as_of_ns: int) -> Optional[Any]:
        buf = self._values.get(self._key(feature, entity_id), [])
        eligible = [v for v in buf if v.timestamp_ns <= as_of_ns]
        return eligible[-1].value if eligible else None

    def training_set(self, features: List[str], entities: List[str],
                     as_of_ns: int) -> List[Dict[str, Any]]:
        rows = []
        for entity_id in entities:
            row: Dict[str, Any] = {"entity_id": entity_id}
            for feature in features:
                row[feature] = self.point_in_time(feature, entity_id, as_of_ns)
            rows.append(row)
        return rows

    def freshness(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        now = time.time_ns()
        for key, buf in self._values.items():
            if buf:
                age_s = (now - buf[-1].timestamp_ns) / 1e9
                feature = key.split(":")[0]
                fd = self._defs.get(feature)
                ttl = fd.ttl_s if fd else 0
                out[key] = {"age_s": round(age_s, 1), "stale": age_s > ttl, "values": len(buf)}
        return out

    def card(self) -> Dict[str, Any]:
        fresh = self.freshness()
        return {
            "kind": "feature-store-card",
            "features": {n: {"entity": d.entity, "version": d.version, "ttl_s": d.ttl_s} for n, d in self._defs.items()},
            "series": len(self._values),
            "stale_series": len([k for k, v in fresh.items() if v["stale"]]),
        }
