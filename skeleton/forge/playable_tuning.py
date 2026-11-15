"""Source-bound, sparse cockpit tuning for eight authored Godot mini-games.

Only explicit slider edits tune a prototype. Untouched sliders keep the
original generated source byte-for-byte unchanged; GameForge's existing
10-axis tensor remains the sole authority for all other build planning.

Supported direct effects:
  tempo -> player movement speed (all 8)
  risk -> extraction heat, racing deadline, stealth detection radius
  scarcity -> survival hydration depletion
  lethality -> arena-combat starting health
  grind -> racing lap count, arena waves, factory shipment quota
  opacity -> puzzle switch hints and stealth danger-zone visibility

  agency -> interaction/checkpoint radius (five expanded modes)
  grind -> puzzle switch count, survival supply count, crafting material count

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


# Fixed, original bounded routes. These coordinates are compiler data,
# never arbitrary Galaxy-provided GDScript. Retain the original first points.
_ROUTE_POINTS = {
    "puzzle": ("switches", ((180, 0), (180, 150), (-40, 150), (-180, -20),
                               (-170, -150), (40, -165))),
    "survival": ("supplies", ((160, 80), (90, 220), (-160, 180),
                                 (-210, 80), (-80, -60), (65, -130))),
    "stealth": ("objectives", ((160, 20), (260, 170), (-20, 200),
                                  (-90, 110), (-130, -50), (25, 65))),
    "crafting": ("materials", ((160, -80), (240, 170), (-80, 210),
                                  (-230, 40), (-30, -150), (125, 40))),
}
_ORIGINAL_ROUTE = {
    "puzzle": "Vector2(180, 0), Vector2(180, 150),\n\tVector2(-40, 150), Vector2(-180, -20)",
    "survival": "Vector2(160, 80), Vector2(90, 220), Vector2(-160, 180)",
    "stealth": "Vector2(160, 20), Vector2(260, 170), Vector2(-20, 200)",
    "crafting": "Vector2(160, -80), Vector2(240, 170), Vector2(-80, 210)",
}


def _tune_objectives(loop: str, name: str, value: float) -> tuple[str, int]:
    # Always supply exactly the number of required, accessible targets.
    # No expansion of engine work beyond six bounded route points.
    count = 2 + int(round(4 * value))
    _, points = _ROUTE_POINTS[name]
    replacement = ", ".join(f"Vector2({x}, {y})" for x, y in points[:count])
    loop = _replace_exact(loop, _ORIGINAL_ROUTE[name], replacement)
    if name == "survival":
        loop = _replace_exact(loop, "Supplies %d/3 |", f"Supplies %d/{count} |")
    elif name == "stealth":
        loop = _replace_exact(loop, "Intel %d/3 |", f"Intel %d/{count} |")
    elif name == "crafting":
        loop = _replace_exact(loop, "crafted = collected == 3", f"crafted = collected == {count}")
        loop = _replace_exact(loop, "Materials %d/3 |", f"Materials %d/{count} |")
    # Puzzle completion and HUD already use switches.size().
    return loop, count


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

    if "agency" in axes and name in {"puzzle", "racing", "survival", "stealth", "crafting"}:
        constants = {
            "puzzle": ("USE_RADIUS", 18.0), "racing": ("LAP_RADIUS", 24.0),
            "survival": ("PICKUP_RADIUS", 19.0), "stealth": ("USE_RADIUS", 18.0),
            "crafting": ("USE_RADIUS", 19.0),
        }
        constant, base = constants[name]
        radius = _fixed(base * (0.75 + 0.5 * axes["agency"]))
        loop = _replace_exact(loop, f"const {constant} := {base:.1f}",
                              f"const {constant} := {radius:.2f}")
        effects[f"{name}.interaction_radius"] = radius
        used.add("agency")

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

    if "risk" in axes and name == "survival":
        exposure = _fixed(1.0 + 4.0 * axes["risk"])
        loop = _replace_exact(loop, "const EXPOSURE_DRAIN := 3.0",
                              f"const EXPOSURE_DRAIN := {exposure:.2f}")
        effects["survival.exposure_drain_per_second"] = exposure
        used.add("risk")

    if "lethality" in axes and name == "stealth":
        rise = _fixed(0.55 + 0.8 * axes["lethality"])
        loop = _replace_exact(loop, "const ALERT_RISE := 0.95",
                              f"const ALERT_RISE := {rise:.2f}")
        effects["stealth.alert_rise_per_second"] = rise
        used.add("lethality")

    if "risk" in axes and name == "crafting":
        duration = _fixed(0.6 + 1.2 * axes["risk"])
        loop = _replace_exact(loop, "const ASSEMBLY_SECONDS := 1.2",
                              f"const ASSEMBLY_SECONDS := {duration:.2f}")
        effects["crafting.assembly_seconds"] = duration
        used.add("risk")

    if "scarcity" in axes and name == "racing":
        recharge = _fixed(20.0 - 15.0 * axes["scarcity"])
        player = _replace_exact(player, "const BOOST_RECHARGE := 12.5",
                                f"const BOOST_RECHARGE := {recharge:.2f}")
        effects["racing.boost_recharge_per_second"] = recharge
        used.add("scarcity")

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

    if "grind" in axes:
        # A bounded progression-depth axis changes the *real* win condition,
        # not only its HUD copy. 0.5 is the original challenge length.
        if name == "combat_loop":
            waves = 2 + round(2 * axes["grind"])
            loop = _replace_exact(loop, "const WAVES := 3", f"const WAVES := {waves}")
            effects["combat_loop.waves"] = float(waves)
            used.add("grind")
        elif name == "racing":
            laps = 2 + round(2 * axes["grind"])
            loop = _replace_exact(loop, "const GOAL_LAPS := 3", f"const GOAL_LAPS := {laps}")
            effects["racing.goal_laps"] = float(laps)
            used.add("grind")
        elif name == "pipeline":
            quota = 2 + round(4 * axes["grind"])
            loop = _replace_exact(loop, "const QUOTA := 4", f"const QUOTA := {quota}")
            effects["pipeline.shipment_quota"] = float(quota)
            used.add("grind")
        elif name in _ROUTE_POINTS:
            loop, count = _tune_objectives(loop, name, axes["grind"])
            effects[f"{name}.{_ROUTE_POINTS[name][0]}_required"] = float(count)
            used.add("grind")

    if "opacity" in axes:
        show_hints = axes["opacity"] < 0.67
        if name == "puzzle":
            loop = _replace_exact(
                loop, "const SHOW_ACTIVE_SWITCH := true",
                f"const SHOW_ACTIVE_SWITCH := {str(show_hints).lower()}",
            )
            effects["puzzle.active_switch_hint_visible"] = float(show_hints)
            used.add("opacity")
        elif name == "stealth":
            loop = _replace_exact(
                loop, "const SHOW_GUARD_ZONES := true",
                f"const SHOW_GUARD_ZONES := {str(show_hints).lower()}",
            )
            effects["stealth.guard_zones_visible"] = float(show_hints)
            used.add("opacity")

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
