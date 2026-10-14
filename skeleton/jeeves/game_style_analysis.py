"""Bounded, explicitly labelled game feel profiles and measured trace summaries.

Original-game names in authored analog profiles describe inspirations. They are
not cartridge analyses, rights grants, or measurements of those games. Numeric
measurements come only from the supplied, structurally validated transitions;
application admission owns current source rights and trusted replay provenance.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

PROFILE_SCHEMA = "skeleton.game.source_profile.v1"
STYLE_SCHEMA = "skeleton.game.style_analysis.v1"
MAX_PROFILE_BYTES = 131072
MAX_ANALYSIS_BYTES = 8 * 1024 * 1024
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
FAMILIES = ("adventure", "fishing", "farming", "platformer", "arena")

# path: (minimum, maximum, original default, physical unit, integer)
MECHANIC_CATALOG = {
    "movement.acceleration": (60.0, 4000.0, 1100.0, "pixels/second^2", False),
    "movement.max_speed": (30.0, 600.0, 160.0, "pixels/second", False),
    "movement.friction": (60.0, 4000.0, 1300.0, "pixels/second^2", False),
    "movement.gravity": (100.0, 4000.0, 1200.0, "pixels/second^2", False),
    "movement.max_fall_speed": (100.0, 1400.0, 700.0, "pixels/second", False),
    "jump.velocity": (-1000.0, -60.0, -420.0, "pixels/second", False),
    "jump.coyote_seconds": (0.0, 0.3, 0.1, "seconds", False),
    "jump.buffer_seconds": (0.0, 0.3, 0.12, "seconds", False),
    "jump.air_jumps": (0, 2, 0, "count", True),
    "combat.projectile_speed": (100.0, 1000.0, 420.0, "pixels/second", False),
    "combat.damage": (1, 10, 1, "health", True),
    "combat.cooldown": (0.08, 2.0, 0.35, "seconds", False),
    "combat.enemy_damage": (1, 5, 1, "health", True),
    "combat.invulnerability_seconds": (0.1, 3.0, 0.75, "seconds", False),
    "resources.max_health": (1, 12, 6, "health", True),
    "resources.max_energy": (1, 100, 40, "energy", True),
    "camera.lookahead": (0.0, 400.0, 72.0, "pixels", False),
    "camera.smoothing": (0.01, 1.0, 0.14, "ratio", False),
    "pacing.enemy_density": (0.0, 1.0, 0.25, "ratio", False),
    "pacing.room_length": (320.0, 1600.0, 640.0, "pixels", False),
    "pacing.rest_frequency": (1, 8, 3, "rooms", True),
    "adventure.interact_radius": (24.0, 128.0, 48.0, "pixels", False),
    "adventure.melee_damage": (1, 10, 2, "health", True),
    "adventure.melee_cooldown": (0.1, 2.0, 0.4, "seconds", False),
    "adventure.dungeon_count": (1, 8, 3, "count", True),
    "fishing.cast_range": (24.0, 256.0, 96.0, "pixels", False),
    "fishing.bite_min_seconds": (0.25, 15.0, 1.5, "seconds", False),
    "fishing.bite_max_seconds": (0.5, 30.0, 4.0, "seconds", False),
    "fishing.reel_speed": (0.05, 2.0, 0.45, "progress/second", False),
    "fishing.tension_gain": (0.05, 2.0, 0.9, "tension/second", False),
    "fishing.tension_release": (0.05, 2.0, 0.55, "tension/second", False),
    "fishing.catch_window_seconds": (2.0, 30.0, 8.0, "seconds", False),
    "fishing.fish_variants": (2, 8, 8, "count", True),
    "fishing.rod_strength": (0.2, 3.0, 1.0, "ratio", False),
    "farming.growth_days": (1, 14, 3, "days", True),
    "farming.water_decay": (0.01, 1.0, 0.2, "water/day", False),
    "farming.soil_quality": (0.1, 1.0, 1.0, "ratio", False),
    "farming.crop_variants": (2, 8, 6, "count", True),
    "farming.season_days": (4, 32, 12, "days", True),
    "farming.day_seconds": (15.0, 600.0, 90.0, "seconds", False),
    "farming.harvest_value": (2, 100, 18, "coins", True),
    "farming.seed_cost": (1, 100, 4, "coins", True),
    "farming.weather_wet_probability": (0.0, 1.0, 0.25, "ratio", False),
}


class GameStyleError(ValueError):
    """Invalid or unsupported source profile/measurement evidence."""


def canonical(value: Any, *, limit: int = MAX_ANALYSIS_BYTES) -> bytes:
    stack = [(value, 0)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if depth > 24 or nodes > 600000:
            raise GameStyleError("style evidence exceeds structural bounds")
        if isinstance(item, Mapping):
            if len(item) > 4096 or any(not isinstance(k, str) for k in item):
                raise GameStyleError("style evidence object keys differ")
            stack.extend((v, depth + 1) for v in item.values())
        elif isinstance(item, (list, tuple)):
            if len(item) > 131072:
                raise GameStyleError("style evidence sequence exceeds bounds")
            stack.extend((v, depth + 1) for v in item)
        elif isinstance(item, str):
            if len(item.encode("utf-8")) > limit:
                raise GameStyleError("style evidence text exceeds bounds")
        elif type(item) is int:
            if abs(item) > 2**64 - 1:
                raise GameStyleError("style evidence integers exceed64-bit bounds")
        elif type(item) is float:
            if not math.isfinite(item) or abs(item) > 1e15:
                raise GameStyleError("style evidence numbers must be finite and bounded")
        elif item is not None and type(item) is not bool:
            raise GameStyleError("style evidence contains unsupported values")
    try:
        data = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise GameStyleError("style evidence must be finite JSON") from exc
    if len(data) > limit:
        raise GameStyleError("style evidence exceeds byte bounds")
    return data


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise GameStyleError(f"{label} must be a bounded identity")
    return value


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise GameStyleError(f"{label} must be an exact SHA-256 identity")
    return value


def _number(value: Any, label: str, low: float, high: float) -> float:
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        raise GameStyleError(f"{label} is outside its finite declared bounds")
    return float(value)


def _text(value: Any, label: str, maximum: int = 256) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or any(ord(c) < 32 for c in value):
        raise GameStyleError(f"{label} must be bounded printable text")
    return value


@dataclass(frozen=True, slots=True)
class SourceGameProfile:
    """Detached exact profile; source provenance is descriptive, never authority."""

    payload_json: str

    def __post_init__(self) -> None:
        try:
            raw = json.loads(self.payload_json)
        except (ValueError, TypeError, RecursionError) as exc:
            raise GameStyleError("source profile JSON differs") from exc
        required = {
            "schema_version",
            "profile_id",
            "title",
            "family",
            "origin",
            "mechanics",
            "palette",
            "loops",
            "notes",
            "profile_digest",
        }
        if not isinstance(raw, dict) or set(raw) != required or raw["schema_version"] != PROFILE_SCHEMA:
            raise GameStyleError("source profile schema/fields differ")
        _name(raw["profile_id"], "profile id")
        _text(raw["title"], "profile title", 120)
        if raw["family"] not in FAMILIES:
            raise GameStyleError("source profile family is undeclared")
        origin = raw["origin"]
        fields = {
            "source_id",
            "source_digest",
            "bundle_digest",
            "source_kind",
            "rights_refs",
            "license_ref",
            "tenant_id",
            "owner_id",
            "reference_game",
            "reference_platform",
            "rights_status",
        }
        if not isinstance(origin, dict) or set(origin) != fields:
            raise GameStyleError("source profile origin fields differ")
        _text(origin["source_id"], "source id")
        _sha(origin["source_digest"], "source digest")
        _sha(origin["bundle_digest"], "source bundle digest")
        if origin["source_kind"] not in ("authored_reference", "ingested", "dragon"):
            raise GameStyleError("source kind differs")
        if origin["rights_status"] not in ("original_design", "attested_requires_current_authority"):
            raise GameStyleError("source rights status differs")
        if (
            origin["source_kind"] != "authored_reference"
            and origin["rights_status"] != "attested_requires_current_authority"
        ):
            raise GameStyleError("ingested profile cannot grant original-design rights")
        for key in ("license_ref", "tenant_id", "owner_id", "reference_game", "reference_platform"):
            if origin[key] is not None:
                _text(origin[key], key)
        rights = origin["rights_refs"]
        if not isinstance(rights, list) or len(rights) > 16 or len(set(rights)) != len(rights):
            raise GameStyleError("source rights references differ")
        for ref in rights:
            _text(ref, "rights reference")
        if origin["source_kind"] != "authored_reference" and not rights:
            raise GameStyleError("ingested profile requires explicit rights references")
        mechanics = raw["mechanics"]
        if not isinstance(mechanics, dict) or set(mechanics) - set(MECHANIC_CATALOG):
            raise GameStyleError("source mechanic fields differ")
        if not mechanics:
            raise GameStyleError("source profile requires explicit mechanics")
        for path, item in mechanics.items():
            if not isinstance(item, dict) or set(item) != {
                "value",
                "unit",
                "classification",
                "confidence",
                "evidence_refs",
            }:
                raise GameStyleError("source mechanic evidence fields differ")
            low, high, _, unit, integer = MECHANIC_CATALOG[path]
            _number(item["value"], path, low, high)
            if integer and type(item["value"]) is not int:
                raise GameStyleError("discrete mechanics must be integers")
            if item["unit"] != unit or item["classification"] not in ("authored", "declared", "measured"):
                raise GameStyleError("mechanic units/evidence classification differ")
            _number(item["confidence"], "evidence confidence", 0, 1)
            refs = item["evidence_refs"]
            if not isinstance(refs, list) or not 1 <= len(refs) <= 16:
                raise GameStyleError("mechanic evidence references are required")
            for ref in refs:
                _text(ref, "mechanic evidence reference")
        palette = raw["palette"]
        if (
            not isinstance(palette, list)
            or not 3 <= len(palette) <= 12
            or any(not isinstance(c, str) or not _COLOR.fullmatch(c) for c in palette)
        ):
            raise GameStyleError("profile palette must contain authored color swatches")
        if not isinstance(raw["loops"], list) or not 1 <= len(raw["loops"]) <= 12:
            raise GameStyleError("profile gameplay loops differ")
        for loop in raw["loops"]:
            _name(loop, "gameplay loop")
        if not isinstance(raw["notes"], list) or len(raw["notes"]) > 16:
            raise GameStyleError("profile notes differ")
        for note in raw["notes"]:
            _text(note, "profile note", 1024)
        unsigned = {k: v for k, v in raw.items() if k != "profile_digest"}
        if (
            raw["profile_digest"] != digest(unsigned)
            or canonical(raw, limit=MAX_PROFILE_BYTES).decode() != self.payload_json
        ):
            raise GameStyleError("source profile digest or canonical representation differs")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SourceGameProfile:
        if not isinstance(value, Mapping):
            raise GameStyleError("source profile must be an object")
        return cls(canonical(dict(value), limit=MAX_PROFILE_BYTES).decode())

    @classmethod
    def from_bundle(
        cls,
        bundle: Any,
        *,
        profile_id: str,
        title: str,
        family: str | None = None,
        authored_mechanics: Mapping[str, int | float] | None = None,
    ) -> SourceGameProfile:
        return profile_from_bundle(
            bundle, profile_id=profile_id, title=title, family=family, authored_mechanics=authored_mechanics
        )

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self.payload_json)

    @property
    def digest(self) -> str:
        return self.as_dict()["profile_digest"]

    @property
    def profile_id(self) -> str:
        return self.as_dict()["profile_id"]


def authored_game_profile(
    *,
    profile_id: str,
    title: str,
    family: str,
    mechanics: Mapping[str, int | float] | None = None,
    palette: Iterable[str] = ("#173b35", "#5caa72", "#e8d1a2", "#c87961", "#92bed4"),
    reference_game: str | None = None,
    reference_platform: str | None = None,
    loops: Iterable[str] | None = None,
) -> SourceGameProfile:
    """Create an original authored analog, never measured copyrighted behavior."""
    values = dict(mechanics or {})
    if set(values) - set(MECHANIC_CATALOG):
        raise GameStyleError("authored mechanic field is undeclared")
    source = {
        "profile_id": profile_id,
        "title": title,
        "family": family,
        "values": values,
        "reference_game": reference_game,
        "reference_platform": reference_platform,
    }
    identity = digest(source)
    evidence_ref = f"authored:{profile_id}:{identity}"
    evidence = {}
    for path, (_, _, default, unit, integer) in MECHANIC_CATALOG.items():
        value = values.get(path, int(default) if integer else float(default))
        direct = path.split(".", 1)[0] == family or path in values
        evidence[path] = {
            "value": value,
            "unit": unit,
            "classification": "authored",
            "confidence": 0.8 if direct else 0.35,
            "evidence_refs": [evidence_ref],
        }
    raw = {
        "schema_version": PROFILE_SCHEMA,
        "profile_id": profile_id,
        "title": title,
        "family": family,
        "origin": {
            "source_id": f"authored:{profile_id}",
            "source_digest": identity,
            "bundle_digest": identity,
            "source_kind": "authored_reference",
            "rights_refs": [],
            "license_ref": "original-generated-design",
            "tenant_id": None,
            "owner_id": None,
            "reference_game": reference_game,
            "reference_platform": reference_platform,
            "rights_status": "original_design",
        },
        "mechanics": evidence,
        "palette": list(palette),
        "loops": list(loops or ("explore", "practice", "progress")),
        "notes": [
            "Authored original design analogy; no source ROM, code, assets or measured original-game behavior."
        ],
    }
    raw["profile_digest"] = digest(raw)
    return SourceGameProfile.from_dict(raw)


def profile_from_bundle(
    bundle: Any,
    *,
    profile_id: str,
    title: str,
    family: str | None = None,
    authored_mechanics: Mapping[str, int | float] | None = None,
) -> SourceGameProfile:
    """Project canonical source provenance and explicit design, without asset/code copies.

    Lexical cues remain notes. Numeric source hints are not silently interpreted
    as physical gameplay parameters; a caller must supply authored values.
    """
    from .game_learning_ingestion import GameSourceBundle

    if not isinstance(bundle, GameSourceBundle):
        if not isinstance(bundle, Mapping):
            raise GameStyleError("canonical ingested source bundle is required")
        bundle = GameSourceBundle(canonical(dict(bundle), limit=16 * 1024 * 1024).decode())
    source = bundle.to_dict()
    provenance = source["provenance"]
    if provenance.get("rights_acknowledged") is not True:
        raise GameStyleError("source profile cannot omit rights attestation")
    cues = []
    role_scores: Counter[str] = Counter()
    associations = {
        "platformer": "platformer",
        "jumping": "platformer",
        "shooter": "arena",
        "ranged_combat": "arena",
        "fighting": "arena",
        "fishing": "fishing",
        "farming": "farming",
        "agriculture": "farming",
        "adventure": "adventure",
        "role_playing": "adventure",
        "quest": "adventure",
    }
    for kind in ("genres", "mechanics"):
        for cue in source.get("features", {}).get(kind, [])[:64]:
            if not isinstance(cue, Mapping) or not isinstance(cue.get("value"), str):
                continue
            label = cue["value"]
            if label in associations:
                role_scores[associations[label]] += 1
            if len(cues) < 12:
                classification = str(cue.get("classification", "source_claim"))[:64]
                ref = str(cue.get("evidence_ref", source["bundle_id"]))[:256]
                text = f"Source cue {label[:64]} ({classification}), evidence {ref}; not measured physics."
                cues.append("".join(c if ord(c) >= 32 else " " for c in text))
    if family is None:
        if not role_scores:
            raise GameStyleError("source lacks classified role cues; an explicit authored family is required")
        family = min(role_scores, key=lambda name: (-role_scores[name], name))
    raw = authored_game_profile(
        profile_id=profile_id, title=title, family=family, mechanics=authored_mechanics
    ).as_dict()
    raw["origin"] = {
        "source_id": source["bundle_id"],
        "source_digest": source["source_digest"],
        "bundle_digest": source["bundle_digest"],
        "source_kind": "dragon" if source["source_kind"] == "dragon" else "ingested",
        "rights_refs": list(provenance["rights_refs"]),
        "license_ref": provenance["license_ref"],
        "tenant_id": provenance["tenant_id"],
        "owner_id": provenance["owner_id"],
        "reference_game": title,
        "reference_platform": source.get("metadata", {}).get("platform"),
        "rights_status": "attested_requires_current_authority",
    }
    raw["notes"] = [
        "Canonical source identity retained; current authorization belongs to application admission.",
        "Mechanics are explicit authored projections. Lexical cues and cartridge layout do not measure game feel.",
    ] + cues
    raw.pop("profile_digest")
    raw["profile_digest"] = digest(raw)
    return SourceGameProfile.from_dict(raw)


def _quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def analyze_play_traces(
    traces: Iterable[Mapping[str, Any]],
    *,
    sample_interval_seconds: float = 1 / 60,
    coordinate_units: str = "normalized",
    coordinate_scale: Mapping[str, float] | None = None,
    verified_trace_digests: Iterable[str] = (),
) -> dict[str, Any]:
    """Summarize validated real or supplied transitions with explicit trust/units.

    ``verified_trace_digests`` is application-owned replay metadata. This
    function never turns an uploaded digest into issuer proof. No metrics infer
    completion from positive rewards, or fishing/farming skill from headers.
    """
    from .game_learning import GameLearningConfig, GamePolicyLearner
    from .game_learning_runtime import GameEnvironmentSpec

    dt = _number(sample_interval_seconds, "sample interval", 1 / 240, 1)
    if coordinate_units not in ("normalized", "pixels"):
        raise GameStyleError("coordinate units must be explicit normalized or pixels")
    scale = dict(coordinate_scale or {"x": 1.0, "y": 1.0})
    if set(scale) != {"x", "y"}:
        raise GameStyleError("coordinate scale must declare both x and y axes")
    for axis, value in scale.items():
        _number(value, f"coordinate scale {axis}", 0.000001, 8192)
    if coordinate_units == "normalized" and scale != {"x": 1.0, "y": 1.0}:
        raise GameStyleError("scaled physical coordinates must be labelled pixels")
    verified = set(verified_trace_digests)
    if len(verified) > 64:
        raise GameStyleError("verified trace metadata exceeds bounds")
    for value in verified:
        _sha(value, "verified trace")
    accepted = []
    environment_digest = None
    total_steps = 0
    total_bytes = 0
    identities = set()
    episode_ids = set()
    for index, item in enumerate(traces):
        if index >= 64:
            raise GameStyleError("style trace count exceeds64")
        raw = json.loads(canonical(dict(item), limit=MAX_ANALYSIS_BYTES))
        total_bytes += len(canonical(raw))
        if total_bytes > MAX_ANALYSIS_BYTES:
            raise GameStyleError("style input trace bytes exceed8MiB")
        descriptor = raw.get("environment", {})
        try:
            spec = GameEnvironmentSpec(
                environment_id=descriptor["environment_id"],
                environment_digest=descriptor["environment_digest"],
                actions=tuple(descriptor["actions"]),
                observation_bins={k: tuple(v) for k, v in descriptor["observation_bins"].items()},
                reward_components=tuple(descriptor["reward_components"]),
                max_episode_steps=descriptor["max_episode_steps"],
            )
            validator = GamePolicyLearner(
                spec,
                GameLearningConfig(),
                policy_id="style-trace-validator",
                source_lineage=raw["source_lineage"],
            )
            trace = validator.validate_trace(raw)
        except (KeyError, TypeError, ValueError) as exc:
            raise GameStyleError("style trace schema, chain, rewards or identity differs") from exc
        if trace["trace_digest"] in identities or trace["episode_id"] in episode_ids:
            raise GameStyleError("style episodes must have distinct identities and trace digests")
        identities.add(trace["trace_digest"])
        episode_ids.add(trace["episode_id"])
        if environment_digest is None:
            environment_digest = spec.environment_digest
        elif environment_digest != spec.environment_digest:
            raise GameStyleError("style traces must use one exact environment")
        total_steps += trace["steps"]
        if total_steps > 131072:
            raise GameStyleError("style transition count exceeds131072")
        accepted.append(trace)
    if not accepted:
        raise GameStyleError("style analysis requires actual transition data")
    if verified - {t["trace_digest"] for t in accepted}:
        raise GameStyleError("verified trace metadata references missing traces")
    actions: Counter[str] = Counter()
    speeds: list[float] = []
    accelerations: list[float] = []
    intervals: list[float] = []
    jump_durations: list[float] = []
    combat_intervals: list[float] = []
    bite_delays: list[float] = []
    catch_delays: list[float] = []
    returns = []
    distances = []
    successes = 0
    deaths = 0
    fishing_attempts = catches = harvests = 0
    action_changes = 0
    for trace in accepted:
        last_fire = last_jump = last_combat = last_cast = last_bite = None
        last_action = None
        last_velocity = None
        distance = 0.0
        previous_grounded = True
        for step in trace["transitions"]:
            action = step["action"]
            actions[action] += 1
            if last_action is not None and action != last_action:
                action_changes += 1
            last_action = action
            before, after = step["observation"], step["next_observation"]
            if "x" in before and "x" in after:
                dx = (after["x"] - before["x"]) * scale["x"]
                dy = (after.get("y", after.get("z", 0)) - before.get("y", before.get("z", 0))) * scale["y"]
                speed = math.hypot(dx, dy) / dt
                speeds.append(speed)
                distance += math.hypot(dx, dy)
                if last_velocity is not None:
                    accelerations.append(abs(speed - last_velocity) / dt)
                last_velocity = speed
            if "fire" in action or action == "attack":
                if last_fire is not None:
                    intervals.append((step["sequence"] - last_fire) * dt)
                last_fire = step["sequence"]
            grounded = after.get("grounded", 1) >= 0.5
            if previous_grounded and not grounded:
                last_jump = step["sequence"]
            if grounded and not previous_grounded and last_jump is not None:
                jump_durations.append((step["sequence"] - last_jump) * dt)
                last_jump = None
            previous_grounded = grounded
            info = step.get("info", {})
            events = info.get("events", [])
            if not isinstance(events, list):
                events = []
            if "fire" in events or "attack" in events:
                if last_combat is not None:
                    combat_intervals.append((step["sequence"] - last_combat) * dt)
                last_combat = step["sequence"]
            if "cast" in events:
                last_cast = step["sequence"]
            if "bite" in events:
                if last_cast is not None:
                    bite_delays.append((step["sequence"] - last_cast) * dt)
                last_bite = step["sequence"]
            if "catch" in events and last_bite is not None:
                catch_delays.append((step["sequence"] - last_bite) * dt)
                last_bite = None
            fishing_attempts += int("cast" in events)
            catches += int("catch" in events)
            harvests += int("harvest" in events)
        final_info = trace["transitions"][-1].get("info", {})
        successes += int(final_info.get("success") is True or final_info.get("won") is True)
        deaths += int(final_info.get("dead") is True)
        returns.append(trace["return"])
        distances.append(distance)
    probabilities = [n / total_steps for n in actions.values()]
    metrics = {
        "speed_median": _quantile(speeds, 0.5),
        "speed_p95": _quantile(speeds, 0.95),
        "acceleration_p95": _quantile(accelerations, 0.95),
        "action_interval_median": _quantile(intervals, 0.5),
        "jump_airtime_median": _quantile(jump_durations, 0.5),
        "combat_cadence_median": _quantile(combat_intervals, 0.5),
        "bite_delay_median": _quantile(bite_delays, 0.5),
        "catch_reel_seconds_median": _quantile(catch_delays, 0.5),
        "distance_mean": statistics.fmean(distances),
        "action_change_rate": action_changes / max(1, total_steps - len(accepted)),
        "idle_fraction": (actions["noop"] + actions["idle"]) / total_steps,
        "action_entropy_bits": -math.fsum(p * math.log2(p) for p in probabilities),
        "return_mean": statistics.fmean(returns),
        "return_min": min(returns),
        "completion_fraction": successes / len(accepted),
        "death_fraction": deaths / len(accepted),
        "fishing_attempts": fishing_attempts,
        "catches": catches,
        "harvests": harvests,
    }
    result = {
        "schema_version": STYLE_SCHEMA,
        "environment_digest": environment_digest,
        "trace_digests": [t["trace_digest"] for t in accepted],
        "verified_trace_digests": sorted(verified),
        "evidence_status": "replay_metadata_supplied" if verified else "validated_supplied_transitions",
        "coordinate_units": coordinate_units,
        "coordinate_scale": scale,
        "source_lineage_digests": [digest(t["source_lineage"]) for t in accepted],
        "sample_interval_seconds": dt,
        "episodes": len(accepted),
        "transitions": total_steps,
        "simulation_seconds": total_steps * dt,
        "input_bytes": total_bytes,
        "metrics": metrics,
        "action_counts": dict(sorted(actions.items())),
        "limits": [
            "Metrics describe these trajectories, not original-game mastery or player satisfaction.",
            "Action cadence is input cadence; successful projectile or rod timing requires native event evidence.",
        ],
    }
    result["analysis_digest"] = digest(result)
    return result
