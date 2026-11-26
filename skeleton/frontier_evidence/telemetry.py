"""Telemetry adapters for collision, lighting, audio, and mesh LOD.

Each sample must cite a chunk id and a frame index. Fields outside the
channel schema are rejected, including a missing frame index. This is a
typed software snapshot, not a device capture.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

from skeleton.jeeves.game_engine_lab import ERA_PROFILES, EngineEra

from skeleton.frontier_evidence.common import EvidenceRejected, seal

SCHEMA = "skeleton.frontier_evidence.telemetry.v1"
CHANNELS = ("collision", "lighting", "audio", "mesh_lod")

_SCHEMAS = {
    "collision": frozenset({"chunk_id", "frame_index", "normal", "force"}),
    "lighting": frozenset({"chunk_id", "frame_index", "luminance", "light_ids"}),
    "audio": frozenset({"chunk_id", "frame_index", "rms_db", "bus"}),
    "mesh_lod": frozenset({"chunk_id", "frame_index", "lod", "triangles"}),
}


class TelemetryRejected(EvidenceRejected):
    """Telemetry sample failed the closed schema."""


def _era(value: EngineEra | str) -> EngineEra:
    try:
        key = value if isinstance(value, EngineEra) else EngineEra(str(value))
    except (ValueError, TypeError) as exc:
        raise TelemetryRejected(f"unknown era: {value!r}") from exc
    if key not in ERA_PROFILES:
        raise TelemetryRejected(f"unknown era: {value!r}")
    return key


@dataclass(frozen=True)
class TelemetryAdapter:
    channel: str
    era: str

    def __post_init__(self) -> None:
        if self.channel not in CHANNELS:
            raise TelemetryRejected(f"unknown telemetry channel {self.channel!r}")
        object.__setattr__(self, "era", _era(self.era).value)


def adapters_for_era(era: EngineEra | str) -> tuple[TelemetryAdapter, ...]:
    selected = _era(era)
    return tuple(TelemetryAdapter(channel, selected.value) for channel in CHANNELS)


def _chunk_id(value: object) -> list[int]:
    if isinstance(value, (list, tuple)) and len(value) == 2 and all(type(part) is int for part in value):
        return [int(value[0]), int(value[1])]
    raise TelemetryRejected("chunk id must be an integer pair")


def _frame_index(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TelemetryRejected("frame index must be a non-negative int")
    return value


def _finite_vector(value: object, name: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise TelemetryRejected(f"{name} must be a 3D vector")
    out = []
    for coord in value:
        if isinstance(coord, bool) or not isinstance(coord, (int, float)) or not math.isfinite(coord):
            raise TelemetryRejected(f"{name} must be finite")
        out.append(float(coord))
    return out


def _normalize(channel: str, sample: Mapping) -> dict:
    if channel == "collision":
        normal = _finite_vector(sample["normal"], "collision.normal")
        force = _finite_vector(sample["force"], "collision.force")
        length = math.sqrt(sum(coord * coord for coord in normal))
        if abs(length - 1.0) > 1e-3:
            raise TelemetryRejected("collision normal must be unit length")
        return {"normal": normal, "force": force}
    if channel == "lighting":
        lux = sample["luminance"]
        if isinstance(lux, bool) or not isinstance(lux, (int, float)) or not math.isfinite(lux) or lux < 0:
            raise TelemetryRejected("luminance must be a non-negative finite number")
        lights = sample["light_ids"]
        if (
            not isinstance(lights, (list, tuple))
            or any(not isinstance(item, str) or not item for item in lights)
        ):
            raise TelemetryRejected("light_ids must be source ids")
        return {"luminance": float(lux), "light_ids": sorted(lights)}
    if channel == "audio":
        rms = sample["rms_db"]
        bus = sample["bus"]
        if isinstance(rms, bool) or not isinstance(rms, (int, float)) or not math.isfinite(rms):
            raise TelemetryRejected("audio rms_db must be finite")
        if not isinstance(bus, str) or not bus or len(bus) > 64:
            raise TelemetryRejected("audio bus required")
        return {"rms_db": float(rms), "bus": bus}
    if channel == "mesh_lod":
        lod = sample["lod"]
        triangles = sample["triangles"]
        if isinstance(lod, bool) or not isinstance(lod, int) or lod < 0:
            raise TelemetryRejected("mesh_lod.lod must be a non-negative int")
        if isinstance(triangles, bool) or not isinstance(triangles, int) or triangles < 0:
            raise TelemetryRejected("mesh_lod.triangles must be a non-negative int")
        return {"lod": lod, "triangles": triangles}
    raise TelemetryRejected(f"unknown telemetry channel {channel!r}")


def ingest_sample(adapter: TelemetryAdapter, sample: Mapping) -> dict:
    """Seal one channel sample. Extra fields and a missing frame index are rejected."""
    if not isinstance(adapter, TelemetryAdapter):
        raise TelemetryRejected("telemetry adapter required")
    if not isinstance(sample, Mapping):
        raise TelemetryRejected("telemetry sample required")
    allowed = _SCHEMAS[adapter.channel]
    keys = set(sample)
    if "frame_index" not in keys:
        raise TelemetryRejected("missing frame index")
    extra = keys - allowed
    missing = allowed - keys
    if extra:
        raise TelemetryRejected(f"unknown fields {sorted(extra)}")
    if missing:
        raise TelemetryRejected(f"missing fields {sorted(missing)}")
    chunk_id = _chunk_id(sample["chunk_id"])
    frame_index = _frame_index(sample["frame_index"])
    normalized = _normalize(adapter.channel, sample)
    return seal(
        {
            "schema": SCHEMA,
            "channel": adapter.channel,
            "era": adapter.era,
            "chunk_id": chunk_id,
            "frame_index": frame_index,
            "parameters": normalized,
            "authority": "typed_telemetry_snapshot_not_device_capture",
        }
    )
