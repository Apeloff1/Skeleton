"""Original-homebrew destination adaptation: native Windows visual evolution.

Cleansed content domain: ONE independently-authored homebrew capsule.
The exported blueprint never claims that copying a commercial game
and swapping skins is lawful. Style-fidelity means preserving the
author's tile/physics/topology and intent, not a copyrighted reference
game's characters, title, music, or expressive map.

Windows can add originally generated visual complexity and optional
real hybrid gameplay mechanics that classic hardware did not support.
Runtime and source checks are independently reproducible; no LLM, ROM
import, licensed game modification, SDK bypass, or training data.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .game_project_capsule import GameCapsuleError, verify_game_capsule
from .gameplay_capabilities import compile_level, GameplayError
from .game_playability import check_game_playability
from .game_rights import admit_homebrew_project, GameRightsError

SCHEMA = "skeleton.game.homebrew_port.v1"
DESTINATIONS = ("windows-native",)
ART_DIRECTIONS = {
    "pixel_heritage": ("#111a2a", "#425a75", "#a7dfa9", "#f2cf75", "#99a8bf"),
    "neon_noir": ("#080d24", "#37519a", "#3ff1cc", "#f8a85e", "#5b70bc"),
    "storybook": ("#27263b", "#68638e", "#d7eab5", "#f7d88c", "#a2a0d2"),
    "handheld_amber": ("#292018", "#7c5e39", "#ffc96e", "#fff0ae", "#ad8350"),
    "vector_celestial": ("#0b1832", "#3a709f", "#a1d9ff", "#fcdaaa", "#4d91b6"),
    "monochrome_ink": ("#171923", "#636677", "#f0f0e8", "#dadbd7", "#94969c"),
    "soft_pastel": ("#273b45", "#749eaf", "#d8eeef", "#ffdcb8", "#90bdc5"),
}
HYBRID_MODES = (
    "collectathon", "keyquest", "speedrun", "exploration", "combo",
)
CREATIVE_MODES = (
    "faithful_homebrew", "enhanced_homebrew",
    "hybrid_original", "clean_room_spiritual_successor",
)
QUALITY = ("balanced", "enhanced", "cinematic")
MAX_DECOR = 96


class HomebrewPortError(ValueError):
    """Homebrew source, destination or generated port mismatch."""


def _json(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, ensure_ascii=True, allow_nan=False,
            separators=(",", ":"),
        ).encode("ascii")
    except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
        raise HomebrewPortError("port contains noncanonical metadata") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


def _integer(v: Any, lo: int, hi: int, name: str) -> int:
    if type(v) is not int or not lo <= v <= hi:
        raise HomebrewPortError(f"{name} must be an integer {lo}..{hi}")
    return v


def _route(tiles: list[str]) -> tuple[list[dict[str, bool]], list[tuple[int, int]]]:
    """Replay the exact platformer inputs and keep cell positions as evidence."""
    evidence = check_game_playability({"tiles": tiles, "max_frames": 96})
    if evidence["status"] != "playable":
        raise HomebrewPortError("Windows enhancement requires controller-proven playable source")
    from skeleton.app.offline_game_preview import OfflineGamePreview
    game = OfflineGamePreview(project_tiles=tiles)
    route = [(game.avatar["x"], game.avatar["y"])]
    for keys in evidence["controller_actions"]:
        frame = game.tick(**keys)
        route.append((frame.avatar[0], frame.avatar[1]))
    if not game.won:
        raise HomebrewPortError("original winning trajectory could not be replayed")
    return evidence["controller_actions"], route


def _collectibles(
    source_tiles: list[str], route: list[tuple[int, int]],
    seed: int, count: int,
) -> list[dict[str, int]]:
    occupied = []
    for x, y in route[1:-1]:
        if source_tiles[y][x] == "." and (x, y) not in occupied:
            occupied.append((x, y))
    # Never spawn unreachable rewards or fake a keyquest win.
    if len(occupied) < count:
        return []
    scored = sorted(
        occupied,
        key=lambda p: hashlib.sha256(
            f"original-port-reward-v1:{seed}:{p[0]}:{p[1]}".encode("ascii")
        ).digest(),
    )[:count]
    return [
        {"x": x, "y": y}
        for x, y in sorted(scored, key=lambda p: (p[1], p[0]))
    ]


def _decor(
    tiles: list[str], theme: str, seed: int, quantity: int,
) -> list[dict[str, int]]:
    valid = [
        (x, y) for y, row in enumerate(tiles)
        for x, tile in enumerate(row) if tile == "."
    ]
    hashed = sorted(
        valid, key=lambda p: hashlib.sha256(
            f"original-decor-v1:{theme}:{seed}:{p[0]}:{p[1]}".encode("ascii")
        ).digest(),
    )
    return [
        {"x": x, "y": y, "variant": k % 4}
        for k, (x, y) in enumerate(hashed[:quantity])
    ]


def _admit_source(capsule: dict[str, Any]) -> dict[str, Any]:
    try:
        verified = verify_game_capsule(capsule)
        rights = admit_homebrew_project(
            capsule["rights_manifest"], action=capsule["action"],
            jurisdiction=capsule["jurisdiction"],
        )
    except (GameCapsuleError, GameRightsError, TypeError, KeyError) as exc:
        raise HomebrewPortError("port source must be a verified original homebrew capsule") from exc
    if (
        rights["homebrew_only"] is not True
        or capsule.get("homebrew_only") is not True
        or capsule.get("third_party_game_porting_supported") is not False
    ):
        raise HomebrewPortError("third-party games cannot be used as port sources")
    return verified


def make_homebrew_port(
    capsule: dict[str, Any], *,
    destination: str = "windows-native",
    creative_mode: str = "enhanced_homebrew",
    art_direction: str = "neon_noir",
    quality: str = "enhanced",
    hybrids: list[str] | None = None,
    seed: int = 42,
    scale: int = 32,
    reduced_motion: bool = False,
    high_contrast: bool = False,
    colorblind_safe: bool = False,
    decor_budget: int = 24,
    hud: bool = True,
    parallax: bool = True,
) -> dict[str, Any]:
    original = _admit_source(capsule)
    if destination not in DESTINATIONS:
        raise HomebrewPortError("native destination exporter is not implemented")
    if creative_mode not in CREATIVE_MODES:
        raise HomebrewPortError("unsupported original creative mode")
    if art_direction not in ART_DIRECTIONS or quality not in QUALITY:
        raise HomebrewPortError("unsupported homebrew palette or visual quality")
    if hybrids is None:
        hybrids = []
    if (not isinstance(hybrids, list) or len(hybrids) > 5
            or any(not isinstance(h, str) or h not in HYBRID_MODES for h in hybrids)
            or len(set(hybrids)) != len(hybrids)):
        raise HomebrewPortError("hybrid combinations must be known and unique")
    if (creative_mode == "faithful_homebrew" and hybrids
            or creative_mode == "clean_room_spiritual_successor"
            and art_direction == "pixel_heritage"):
        # A clean-room successor must have distinct original art direction.
        # This is only a *design differentiation* control, not legal proof.
        raise HomebrewPortError("chosen creative mode conflicts with fidelity constraints")
    for value in (reduced_motion, high_contrast, colorblind_safe, hud, parallax):
        if type(value) is not bool:
            raise HomebrewPortError("visual and accessibility toggles must be Boolean")
    seed = _integer(seed, 0, 2**31 - 1, "seed")
    scale = _integer(scale, 16, 56, "Windows tile pixel scale")
    decor_budget = _integer(decor_budget, 0, MAX_DECOR, "decor budget")
    tiles = capsule["tilemap"]
    level = compile_level({"tiles": tiles})
    controls, route = _route(tiles)
    requested_coins = min(5, len(set(route)) - 2) if (
        any(item in hybrids for item in ("collectathon", "keyquest", "combo"))
    ) else 0
    if requested_coins < 0:
        requested_coins = 0
    coins = _collectibles(tiles, route, seed, requested_coins)
    if "keyquest" in hybrids and not coins:
        raise HomebrewPortError("keyquest requires original reachable key placements")
    # The source tiles and colliders MUST remain unchanged by enhancement.
    # The Windows destination can use many more colors/effects and overlay
    # mechanics without smuggling in commercial game content.
    effects = {
        "tile_size": scale,
        "palette": list(ART_DIRECTIONS[art_direction]),
        "quality": quality,
        "ambient_decorations": _decor(tiles, art_direction, seed, decor_budget),
        "parallax_enabled": parallax and not reduced_motion,
        "layered_tile_shading": quality != "balanced",
        "soft_goal_glow": quality == "cinematic" and not reduced_motion,
        "motion_reduced": reduced_motion,
        "high_contrast": high_contrast,
        "colorblind_safe": colorblind_safe,
        "hud_enabled": hud,
        "pixels_per_source_tile": scale,
        "source_collision_map_unchanged": True,
    }
    preserved = {
        "source_tile_sha256": level["tile_digest"],
        "source_capsule_sha256": original["capsule_sha256"],
        "original_spawn": level["spawn"],
        "original_goal": level["goal"],
        "original_physics_rules": "integer_platformer_v1",
        "original_colliders_preserved": True,
        "baseline_win_trace_sha256": _digest(controls),
        "baseline_frames": len(controls),
    }
    body = {
        "schema_version": SCHEMA,
        "destination": destination,
        "creative_mode": creative_mode,
        "art_direction": art_direction,
        "quality": quality,
        "hybrids": sorted(hybrids),
        "seed": seed,
        "scale": scale,
        "reduced_motion": reduced_motion,
        "high_contrast": high_contrast,
        "colorblind_safe": colorblind_safe,
        "decor_budget": decor_budget,
        "hud": hud,
        "parallax": parallax,
        "source": preserved,
        "render": effects,
        "gameplay": {
            "collectibles": coins,
            "keyquest_gate": "keyquest" in hybrids,
            "speedrun_par_frames": len(controls) if "speedrun" in hybrids else None,
            "exploration_fog": "exploration" in hybrids,
            "combo_on_collectible_pickup": "combo" in hybrids,
            "collectathon_score": "collectathon" in hybrids,
        },
        "original_homebrew_only": True,
        "third_party_game_cloning_or_skin_swap_allowed": False,
        "independent_mechanics_allowed": True,
        "third_party_asset_import_allowed": False,
        "commercial_game_source_used": False,
        "source_character_artwork_reused": False,
        "source_music_reused": False,
        "source_trademarks_reused": False,
        "legal_review_completed": False,
        "publish_approved": False,
        "native_windows_package_built": False,
        "training_examples_added": 0,
    }
    return {
        **body,
        "port_sha256": _digest(body),
    }


def verify_homebrew_port(
    capsule: dict[str, Any], blueprint: dict[str, Any],
) -> dict[str, Any]:
    _admit_source(capsule)
    if not isinstance(blueprint, dict) or (
        set(blueprint) != {
            "schema_version", "destination", "creative_mode",
            "art_direction", "quality", "hybrids", "seed", "scale",
            "reduced_motion", "high_contrast", "colorblind_safe",
            "decor_budget", "hud", "parallax", "source", "render",
            "gameplay", "original_homebrew_only",
            "third_party_game_cloning_or_skin_swap_allowed",
            "independent_mechanics_allowed", "third_party_asset_import_allowed",
            "commercial_game_source_used", "source_character_artwork_reused",
            "source_music_reused", "source_trademarks_reused",
            "legal_review_completed", "publish_approved",
            "native_windows_package_built", "training_examples_added",
            "port_sha256",
        }
    ):
        raise HomebrewPortError("port blueprint schema has extra or missing fields")
    if (not isinstance(blueprint["port_sha256"], str) or
        blueprint["port_sha256"] != _digest({
            k: v for k, v in blueprint.items() if k != "port_sha256"
        })):
        raise HomebrewPortError("port blueprint content hash changed")
    try:
        expected = make_homebrew_port(
            capsule, destination=blueprint["destination"],
            creative_mode=blueprint["creative_mode"],
            art_direction=blueprint["art_direction"],
            quality=blueprint["quality"],
            hybrids=blueprint["hybrids"],
            seed=blueprint["seed"],
            scale=blueprint["scale"],
            reduced_motion=blueprint["reduced_motion"],
            high_contrast=blueprint["high_contrast"],
            colorblind_safe=blueprint["colorblind_safe"],
            decor_budget=blueprint["decor_budget"],
            hud=blueprint["hud"],
            parallax=blueprint["parallax"],
        )
    except (HomebrewPortError, ValueError, KeyError, TypeError) as exc:
        raise HomebrewPortError("port cannot be regenerated from original project") from exc
    if blueprint != expected:
        raise HomebrewPortError("port source, hybrids, graphics or provenance were forged")
    return {
        "schema_version": "skeleton.game.homebrew_port.verify.v1",
        "port_sha256": expected["port_sha256"],
        "original_source_sha256": capsule["edited_tile_sha256"],
        "destination": "windows-native",
        "mechanics_preserved": True,
        "art_assets_generated_from_original_rules": True,
        "hybrid_modes_verified": expected["hybrids"],
        "rights_independently_verified": False,
        "third_party_reproduction_allowed": False,
        "ready_for_installed_native_game_preview": True,
        "native_package_built": False,
        "training_examples_added": 0,
    }


class PortedHomebrewSession:
    """Wrapper preserving original physics with genuinely active hybrid rules."""

    def __init__(self, capsule: dict[str, Any], port: dict[str, Any]) -> None:
        verify_homebrew_port(capsule, port)
        from skeleton.app.offline_game_preview import OfflineGamePreview
        self.game = OfflineGamePreview(project_tiles=capsule["tilemap"])
        self.port = port
        self.pending = {
            (x["x"], x["y"]) for x in port["gameplay"]["collectibles"]
        }
        self.score = 0
        self.combo = 0
        self.visited = {(self.game.avatar["x"], self.game.avatar["y"])}
        self.win = False
        self.frames = 0
        self.earned_speedrun_medal = False

    def tick(self, *, left: bool = False, right: bool = False,
             jump: bool = False) -> dict[str, Any]:
        frame = self.game.tick(left=left, right=right, jump=jump)
        pos = frame.avatar
        self.frames = frame.frame
        self.visited.add(pos)
        if pos in self.pending:
            self.pending.remove(pos)
            self.combo = self.combo + 1 if self.port["gameplay"]["combo_on_collectible_pickup"] else 1
            self.score += self.combo * 100 if self.port["gameplay"]["collectathon_score"] else 10
        elif self.port["gameplay"]["combo_on_collectible_pickup"]:
            self.combo = 0
        self.win = frame.won and (
            not self.port["gameplay"]["keyquest_gate"] or not self.pending
        )
        par = self.port["gameplay"]["speedrun_par_frames"]
        self.earned_speedrun_medal = (
            par is not None and self.win and self.frames <= par
        )
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        state = self.game.snapshot()
        return {
            "schema_version": "skeleton.game.homebrew_port.frame.v1",
            "frame": state.frame,
            "avatar": {"x": state.avatar[0], "y": state.avatar[1]},
            "original_game_goal_reached": state.won,
            "hybrid_win": self.win,
            "score": self.score,
            "combo": self.combo,
            "remaining_items": [
                {"x": x, "y": y} for x, y in sorted(self.pending, key=lambda p: (p[1], p[0]))
            ],
            "visited_cells": len(self.visited),
            "visible_cells": len(self.visited) if self.port["gameplay"]["exploration_fog"] else None,
            "speedrun_medal": self.earned_speedrun_medal,
            "port_sha256": self.port["port_sha256"],
            "source_tile_sha256": self.port["source"]["source_tile_sha256"],
            "underlying_physics_unchanged": True,
            "training_examples_added": 0,
        }


def verify_port_gameplay(
    capsule: dict[str, Any], blueprint: dict[str, Any],
) -> dict[str, Any]:
    """Proof: baseline winning inputs must still win enhanced hybrid variant."""
    verify_homebrew_port(capsule, blueprint)
    controls, _ = _route(capsule["tilemap"])
    traces = []
    for _ in range(2):
        game = PortedHomebrewSession(capsule, blueprint)
        snapshots = [game.snapshot()]
        for control in controls:
            snapshots.append(game.tick(**control))
        if not game.win:
            raise HomebrewPortError("destination port broke original gameplay win trace")
        traces.append(snapshots)
    if traces[0] != traces[1]:
        raise HomebrewPortError("enhanced port gameplay was nondeterministic")
    return {
        "schema_version": "skeleton.game.homebrew_port.acceptance.v1",
        "port_sha256": blueprint["port_sha256"],
        "destination": blueprint["destination"],
        "original_gameplay_proven": True,
        "hybrid_gameplay_proven": True,
        "score": traces[0][-1]["score"],
        "visited_cells": traces[0][-1]["visited_cells"],
        "remaining_collectibles": len(traces[0][-1]["remaining_items"]),
        "speedrun_medal": traces[0][-1]["speedrun_medal"],
        "input_frames": len(controls),
        "trace_sha256": _digest(traces[0]),
        "deterministic": True,
        "native_window_opened": False,
        "real_windows_display_validated": False,
        "legal_release_authorized": False,
        "training_examples_added": 0,
    }


__all__ = [
    "SCHEMA", "DESTINATIONS", "ART_DIRECTIONS", "HYBRID_MODES",
    "CREATIVE_MODES", "QUALITY", "HomebrewPortError",
    "make_homebrew_port", "verify_homebrew_port",
    "PortedHomebrewSession", "verify_port_gameplay",
]
