"""Source-bound, sparse cockpit tuning for eight authored Godot mini-games.

Only explicit slider edits tune a prototype. Untouched sliders keep the
original generated source byte-for-byte unchanged; GameForge's existing
10-axis tensor remains the sole authority for all other build planning.

Supported direct effects:
  tempo -> player movement speed (all 8)
  risk -> extraction heat, racing deadline, stealth detection radius
  scarcity -> survival hydration depletion
  lethality -> arena-combat starting health

Other axes remain in the canonical tensor and are explicitly identified as
not yet connected to a native mini-game mechanic; they are never silently
reinterpreted as a different kind of player control.
"""
from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any

SCHEMA = "skeleton.gameforge.playable_tuning.v1"
SOURCE_PATH = "data/playable_tuning.json"
_AXES = frozenset((
    "risk", "tempo", "lethality", "opacity", "scarcity",
    "agency", "spectacle", "intimacy", "grind", "authorial",
))


def _fixed(value: float, digits: int = 2) -> float:
    # Bounds are small and finite; native numeric constants are generated only
    # by our templates, never by user-provided text or expressions.
    return round(value, digits)


def _replace_exact(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError("Godot playable tuning template contract changed")
    return source.replace(old, new, 1)


def compile_playable_tuning(
    name: str,
    source_axes: Mapping[str, float] | None,
    *,
    speed: float,
    player: str,
    loop: str,
) -> tuple[str, str, dict[str, Any] | None]:
    """Compile controlled scalar tuning into real Godot source, if edited.

    Does not substitute arbitrary source, scene paths, snippets, game IDs,
    or shaders. Parameter values cannot bypass fixed code locations.
    """
    if source_axes is None:
        return player, loop, None
    if not isinstance(source_axes, Mapping) or len(source_axes) > 10:
        raise ValueError("invalid bounded playable tuning payload")
    if not source_axes:
        return player, loop, None

    axes: dict[str, float] = {}
    for key, value in source_axes.items():
        if type(key) is not str or key not in _AXES:
            raise ValueError("unsupported playable tuning axis")
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("playable tuning axes must be finite and in [0,1]")
        axes[key] = _fixed(float(value))
    axes = dict(sorted(axes.items()))

    effects: dict[str, float] = {}
    used: set[str] = set()

    if "tempo" in axes:
        effective = _fixed(speed * (0.75 + axes["tempo"] * 0.5))
        player = _replace_exact(
            player,
            f"@export var speed: float = {speed}",
            f"@export var speed: float = {effective:.2f}",
        )
        effects["player.speed"] = effective
        used.add("tempo")

    if "risk" in axes and name == "extraction":
        # Risk 0.5 is neutral, 0 lowers heat pressure, 1 raises it.
        effective = _fixed(6.0 * (0.75 + 0.5 * axes["risk"]))
        loop = _replace_exact(
            loop, "const HEAT_PER_SECOND := 6.0",
            f"const HEAT_PER_SECOND := {effective:.2f}",
        )
        effects["extraction.heat_per_second"] = effective
        used.add("risk")
    elif "risk" in axes and name == "racing":
        # Narrow, real deadline changes; no false vehicle physics claim.
        effective = _fixed(45.0 * (1.2 - 0.4 * axes["risk"]))
        loop = _replace_exact(
            loop, "const TIME_LIMIT := 45.0",
            f"const TIME_LIMIT := {effective:.2f}",
        )
        effects["racing.time_limit_seconds"] = effective
        used.add("risk")
    elif "risk" in axes and name == "stealth":
        effective = _fixed(64.0 * (0.75 + 0.5 * axes["risk"]))
        loop = _replace_exact(
            loop, "const DETECTION_RADIUS := 64.0",
            f"const DETECTION_RADIUS := {effective:.2f}",
        )
        effects["stealth.detection_radius"] = effective
        used.add("risk")

    if "scarcity" in axes and name == "survival":
        effective = _fixed(2.0 * (0.5 + axes["scarcity"]))
        loop = _replace_exact(
            loop, "const DRAIN_PER_SECOND := 2.0",
            f"const DRAIN_PER_SECOND := {effective:.2f}",
        )
        effects["survival.hydration_drain_per_second"] = effective
        used.add("scarcity")

    if "lethality" in axes and name == "combat_loop":
        effective = int(round(100 * (1.25 - 0.5 * axes["lethality"])))
        loop = _replace_exact(
            loop, "var player_hp: int = 100",
            f"var player_hp: int = {effective}",
        )
        effects["combat_loop.starting_hp"] = effective
        used.add("lethality")

    return player, loop, {
        "schema": SCHEMA,
        "mode": name,
        "axes": axes,
        "applied": dict(sorted(effects.items())),
        "mapped_axes": sorted(used),
        "unmapped_axes": sorted(set(axes) - used),
    }


def tuning_source(doc: Mapping[str, Any]) -> str:
    """A reproducible inert project artifact; no executable user input."""
    if doc.get("schema") != SCHEMA:
        raise ValueError("unsupported playable tuning schema")
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
