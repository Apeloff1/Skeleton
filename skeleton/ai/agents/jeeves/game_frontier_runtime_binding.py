"""GF-A runtime binding: scene candidate -> canonical Jeeves/Forge/Godot runtime.

Covers GF-P0-12 (wire scene-candidate output into the canonical runtime and UI
through existing authorisation) and GF-P0-34 (route soft-body, weather,
lifecycle and character-collision outputs into the authoritative Godot/era
runtime channels).

Authority model
---------------
* A ``FrontierSceneCandidate`` is never mutated and never self-approves.
* The candidate digest is recomputed from its manifest; a mismatch fails
  closed, so a tampered manifest cannot be bound.
* Binding requires a ``RuntimeAuthorisation`` signed (HMAC-SHA256) by an
  operator key the caller supplies. The key is never stored on any record.
* Each simulation output is routed only to the runtime channels the target
  era declares. Unsupported outputs are listed as ``dropped`` rather than
  silently discarded, so the UI can show exactly what did not land.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import hmac
import json
import math
from typing import Callable, Mapping

BINDING_SCHEMA = "skeleton.jeeves.frontier_runtime_binding.v1"
AUTH_SCHEMA = "skeleton.jeeves.frontier_runtime_authorisation.v1"
CANDIDATE_SCHEMA = "skeleton.game.frontier_scene_candidate.v1"

_HEX = frozenset("0123456789abcdef")


class RuntimeBindingError(ValueError):
    """Raised whenever binding cannot be proven safe; always fail closed."""


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest_of(value: object) -> str:
    return sha256(canonical_json(value).encode()).hexdigest()


def _is_sha(value: object) -> bool:
    return type(value) is str and len(value) == 64 and set(value) <= _HEX


# --------------------------------------------------------------------------
# Era runtime capability table (P0-34)
# --------------------------------------------------------------------------

#: Output channels a candidate manifest can carry into the runtime.
OUTPUT_CHANNELS = ("soft_body", "weather", "lifecycle", "character_collision")


@dataclass(frozen=True)
class EraRuntimeProfile:
    era: str
    channels: frozenset[str]
    max_soft_nodes: int
    max_structures: int
    max_impacts: int
    godot_node_root: str

    def __post_init__(self) -> None:
        if not self.era or len(self.era) > 64:
            raise RuntimeBindingError("era id required")
        if not self.channels <= set(OUTPUT_CHANNELS):
            raise RuntimeBindingError("unknown runtime channel in era profile")
        for name in ("max_soft_nodes", "max_structures", "max_impacts"):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= 65_536:
                raise RuntimeBindingError(f"{name} out of bounds")
        if not self.godot_node_root.startswith("/root/"):
            raise RuntimeBindingError("godot node root must be absolute")


ERA_RUNTIME_PROFILES: Mapping[str, EraRuntimeProfile] = {
    p.era: p for p in (
        EraRuntimeProfile("tile_8bit", frozenset({"weather", "lifecycle"}),
                          0, 64, 0, "/root/TileWorld"),
        EraRuntimeProfile("tile_16bit", frozenset({"weather", "lifecycle",
                                                   "character_collision"}),
                          0, 256, 16, "/root/TileWorld"),
        EraRuntimeProfile("early_3d", frozenset(OUTPUT_CHANNELS),
                          256, 512, 64, "/root/FrontierWorld"),
        EraRuntimeProfile("modern_3d", frozenset(OUTPUT_CHANNELS),
                          8192, 4096, 1024, "/root/FrontierWorld"),
    )
}


def era_profile(era: str) -> EraRuntimeProfile:
    try:
        return ERA_RUNTIME_PROFILES[era]
    except KeyError:
        raise RuntimeBindingError(f"no runtime profile for era {era!r}") from None


# --------------------------------------------------------------------------
# Output extraction
# --------------------------------------------------------------------------

def _finite(value: object, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise RuntimeBindingError(f"{label} must be finite")
    return float(value)


def _vec(value: object, label: str) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise RuntimeBindingError(f"{label} must be xyz")
    return tuple(_finite(v, label) for v in value)  # type: ignore[return-value]


@dataclass(frozen=True)
class RuntimeOutput:
    channel: str
    node_path: str
    payload: Mapping[str, object]

    @property
    def digest(self) -> str:
        return digest_of({"channel": self.channel, "node": self.node_path,
                          "payload": self.payload})


def _soft_body(manifest: Mapping, root: str, limit: int) -> list[RuntimeOutput]:
    nodes = manifest.get("soft_material_motion") or []
    if len(nodes) > limit:
        raise RuntimeBindingError("soft-body node budget exceeded for era")
    out = []
    for node in nodes:
        node_id = str(node["id"])
        out.append(RuntimeOutput("soft_body", f"{root}/SoftBody/{node_id}", {
            "material": str(node["material"]),
            "xyz": _vec(node["xyz"], "soft xyz"),
            "wetness": _finite(node["wetness"], "wetness"),
            "temperature_c": _finite(node["temperature_c"], "temperature"),
        }))
    return out


def _weather(manifest: Mapping, root: str) -> list[RuntimeOutput]:
    weather = manifest.get("weather_physics")
    if weather is None:
        return []
    return [RuntimeOutput("weather", f"{root}/Weather", {
        "temperature_c": _finite(weather["temperature_c"], "temperature"),
        "wind_xyz": _vec(weather["wind_xyz"], "wind"),
        "rain_mm_h": _finite(weather["rain_mm_h"], "rain"),
        "water_depth_m": _finite(weather["water_depth_m"], "water depth"),
        "snow_depth_m": _finite(weather["snow_depth_m"], "snow depth"),
    })]


def _lifecycle(manifest: Mapping, root: str, limit: int) -> list[RuntimeOutput]:
    structures = manifest.get("structures") or []
    if len(structures) > limit:
        raise RuntimeBindingError("structure budget exceeded for era")
    out = []
    for s in structures:
        integrity = _finite(s["integrity"], "integrity")
        if not 0.0 <= integrity <= 1.0:
            raise RuntimeBindingError("structure integrity outside 0..1")
        out.append(RuntimeOutput("lifecycle", f"{root}/Structures/{s['id']}", {
            "material": str(s["material"]),
            "built": bool(s["built"]),
            "age_days": _finite(s["age_days"], "age"),
            "integrity": integrity,
            "weathering": _finite(s["weathering"], "weathering"),
            "maintenance_debt": _finite(s["maintenance_debt"], "maintenance"),
        }))
    return out


def _character_collision(manifest: Mapping, root: str, limit: int) -> list[RuntimeOutput]:
    character = manifest.get("character_physics")
    if character is None:
        return []
    impacts = character.get("impacts") or []
    if len(impacts) > limit:
        raise RuntimeBindingError("impact budget exceeded for era")
    return [RuntimeOutput("character_collision", f"{root}/Player/Collision", {
        "position": _vec(character["position"], "position"),
        "velocity": _vec(character["velocity"], "velocity"),
        "traction": _finite(character["traction"], "traction"),
        "impacts": tuple({
            "surface": str(i["surface"]),
            "impulse_ns": _finite(i["impulse_ns"], "impulse"),
            "damage": _finite(i["damage"], "damage"),
            "material": str(i["material"]),
        } for i in impacts),
    })]


def route_runtime_outputs(manifest: Mapping, era: str) -> tuple[tuple[RuntimeOutput, ...], tuple[str, ...]]:
    """Return (routed outputs, dropped channel names) for ``era`` (P0-34)."""
    profile = era_profile(era)
    root = profile.godot_node_root
    available = {
        "soft_body": bool(manifest.get("soft_material_motion")),
        "weather": manifest.get("weather_physics") is not None,
        "lifecycle": bool(manifest.get("structures")),
        "character_collision": manifest.get("character_physics") is not None,
    }
    routed: list[RuntimeOutput] = []
    dropped: list[str] = []
    for channel in OUTPUT_CHANNELS:
        if not available[channel]:
            continue
        if channel not in profile.channels:
            dropped.append(channel)
            continue
        if channel == "soft_body":
            routed += _soft_body(manifest, root, profile.max_soft_nodes)
        elif channel == "weather":
            routed += _weather(manifest, root)
        elif channel == "lifecycle":
            routed += _lifecycle(manifest, root, profile.max_structures)
        else:
            routed += _character_collision(manifest, root, profile.max_impacts)
    return tuple(routed), tuple(dropped)


# --------------------------------------------------------------------------
# Authorisation (P0-12)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class RuntimeAuthorisation:
    candidate_digest: str
    operator_id: str
    era: str
    issued_ms: int
    expires_ms: int
    signature: str

    def body(self) -> dict:
        return {"schema": AUTH_SCHEMA, "candidate": self.candidate_digest,
                "operator": self.operator_id, "era": self.era,
                "issued_ms": self.issued_ms, "expires_ms": self.expires_ms}


def _sign(key: bytes, body: Mapping) -> str:
    if type(key) is not bytes or len(key) < 16:
        raise RuntimeBindingError("operator key must be >=16 bytes")
    return hmac.new(key, canonical_json(body).encode(), sha256).hexdigest()


def authorise_candidate(candidate_digest: str, *, operator_id: str, era: str,
                        issued_ms: int, ttl_ms: int, key: bytes) -> RuntimeAuthorisation:
    if not _is_sha(candidate_digest):
        raise RuntimeBindingError("candidate digest must be SHA-256")
    if not operator_id or len(operator_id) > 128:
        raise RuntimeBindingError("operator id required")
    era_profile(era)
    if type(issued_ms) is not int or issued_ms < 0:
        raise RuntimeBindingError("issued_ms invalid")
    if type(ttl_ms) is not int or not 1 <= ttl_ms <= 86_400_000:
        raise RuntimeBindingError("ttl must be 1ms..24h")
    unsigned = RuntimeAuthorisation(candidate_digest, operator_id, era,
                                    issued_ms, issued_ms + ttl_ms, "")
    return RuntimeAuthorisation(candidate_digest, operator_id, era, issued_ms,
                                issued_ms + ttl_ms, _sign(key, unsigned.body()))


def verify_authorisation(auth: RuntimeAuthorisation, *, key: bytes, now_ms: int) -> None:
    expected = _sign(key, auth.body())
    if not hmac.compare_digest(expected, auth.signature):
        raise RuntimeBindingError("authorisation signature invalid")
    if not auth.issued_ms <= now_ms < auth.expires_ms:
        raise RuntimeBindingError("authorisation not valid at this time")


# --------------------------------------------------------------------------
# Binding
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class RuntimeBinding:
    candidate_digest: str
    era: str
    fps: int
    operator_id: str
    authorisation_signature: str
    outputs: tuple[RuntimeOutput, ...]
    dropped_channels: tuple[str, ...]
    godot_files: Mapping[str, str]
    bound_ms: int
    binding_id: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "binding_id", digest_of({
            "schema": BINDING_SCHEMA,
            "candidate": self.candidate_digest,
            "era": self.era, "fps": self.fps,
            "operator": self.operator_id,
            "auth": self.authorisation_signature,
            "outputs": [o.digest for o in self.outputs],
            "dropped": list(self.dropped_channels),
            "files": {k: sha256(v.encode()).hexdigest()
                      for k, v in sorted(self.godot_files.items())},
            "bound_ms": self.bound_ms,
        }))


def _verify_candidate(candidate: object) -> Mapping:
    manifest = getattr(candidate, "manifest", None)
    claimed = getattr(candidate, "manifest_digest", None)
    if not isinstance(manifest, Mapping) or not _is_sha(claimed):
        raise RuntimeBindingError("FrontierSceneCandidate required")
    if getattr(candidate, "approved_for_runtime", None) is not False:
        raise RuntimeBindingError("candidate must arrive unadmitted")
    if manifest.get("schema") != CANDIDATE_SCHEMA:
        raise RuntimeBindingError("unsupported candidate schema")
    if digest_of(manifest) != claimed:
        raise RuntimeBindingError("candidate manifest digest mismatch")
    return manifest


GodotEmitter = Callable[[object], Mapping[str, str]]


def _default_emitter(candidate: object) -> Mapping[str, str]:
    from skeleton.forge.game_frontier_godot import emit_frontier_godot_overlay
    return emit_frontier_godot_overlay(candidate)  # type: ignore[arg-type]


def bind_scene_candidate(candidate: object, auth: RuntimeAuthorisation, *,
                         key: bytes, now_ms: int,
                         emitter: GodotEmitter | None = None) -> RuntimeBinding:
    """Bind a verified, authorised candidate into the canonical runtime."""
    manifest = _verify_candidate(candidate)
    verify_authorisation(auth, key=key, now_ms=now_ms)
    claimed = getattr(candidate, "manifest_digest")
    if auth.candidate_digest != claimed:
        raise RuntimeBindingError("authorisation is for a different candidate")
    render = manifest.get("render") or {}
    era = render.get("era")
    if era != auth.era:
        raise RuntimeBindingError("authorisation era does not match candidate")
    fps = render.get("fps")
    if type(fps) is not int or fps <= 0:
        raise RuntimeBindingError("candidate fps missing")
    outputs, dropped = route_runtime_outputs(manifest, era)
    files = dict((emitter or _default_emitter)(candidate))
    if not files or any(type(k) is not str or type(v) is not str for k, v in files.items()):
        raise RuntimeBindingError("Godot emitter returned no source files")
    files["frontier/data/runtime_binding.json"] = canonical_json({
        "schema": BINDING_SCHEMA, "candidate": claimed, "era": era,
        "outputs": [{"channel": o.channel, "node": o.node_path,
                     "payload": o.payload} for o in outputs],
        "dropped": list(dropped),
    })
    return RuntimeBinding(claimed, era, fps, auth.operator_id, auth.signature,
                          outputs, dropped, files, now_ms)


def binding_ui_status(binding: RuntimeBinding) -> Mapping[str, object]:
    """Compact status card consumed by the Jeeves runtime UI."""
    by_channel: dict[str, int] = {}
    for output in binding.outputs:
        by_channel[output.channel] = by_channel.get(output.channel, 0) + 1
    return {
        "binding_id": binding.binding_id,
        "candidate": binding.candidate_digest,
        "era": binding.era,
        "fps": binding.fps,
        "operator": binding.operator_id,
        "channels": dict(sorted(by_channel.items())),
        "dropped_channels": list(binding.dropped_channels),
        "files": sorted(binding.godot_files),
        "claim": "bound_pending_native_render_qa",
    }
