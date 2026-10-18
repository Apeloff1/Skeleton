"""Connect every game-builder part through Jeeves, Dragon, and an adversary.

The tool catalog stays fail-closed: a mirror actor does not gain authorship,
and a dragon observation does not gain promotion rights. Each installed tool
still receives one Jeeves route, one Dragon route, and one adversarial
counterpart. The exercise below calls those owners on original knowledge,
gameplay, assets, upscaling, and music. It does not train or promote weights.
"""
from __future__ import annotations

from dataclasses import replace
import gzip
from hashlib import sha256
from pathlib import Path

from .companion_curriculum import measure_original_practice
from .contracts import canonical_digest
from .dual_runtime_export import render_dual_runtime_package
from .mirror_room_runtime import MirrorRoomError, review_playable_project
from .playable_compiler import compile_original_game
from .playable_simulation import GameplayError, verify_replay
from .playable_world import GameBuildIntent
from .studio_tool_fabric import (
    Actor, BUILTIN_TOOLS, ToolFabric,
)
from skeleton.ai.webcrawler.dragon_chip_music import GAME_MODES, compose
from skeleton.ai.webcrawler.game_scale_assets import (
    animate_sprite,
    compose_game_melody,
    generate_game_palette,
    pack_sprite_atlas,
    procedural_sprite,
    render_game_melody,
    sprite_to_svg,
    synthesize_game_effect,
)
from skeleton.developer.jeeves_game_upscale import _expand, fidelity_plan

SCHEMA = "skeleton.game_builder.role_triad.v1"
ROLES = ("jeeves", "dragon", "adversarial")
PARTS = (
    "game_logic",
    "game_knowledge",
    "gameplay",
    "asset_style",
    "asset_generation",
    "asset_upscale",
    "music_generation",
    "music_timing",
)
# tool_id -> (jeeves tool, dragon tool, adversarial counterpart)
TOOL_TRIAD = {
    "knowledge.search": ("knowledge.search", "knowledge.search", "mirror.originality"),
    "rights.check": ("rights.check", "knowledge.search", "rights.check"),
    "world.generate": ("world.generate", "world.generate", "mirror.fuzz"),
    "world.authored": ("world.authored", "world.authored", "mirror.fuzz"),
    "world.tiled": ("world.tiled", "world.tiled", "mirror.fuzz"),
    "game.simulate": ("game.simulate", "game.simulate", "mirror.fuzz"),
    "game.browser": ("game.browser", "game.browser", "mirror.fuzz"),
    "game.godot": ("game.godot", "game.godot", "mirror.fuzz"),
    "game.editor": ("game.editor", "game.editor", "mirror.fuzz"),
    "story.generate": ("story.generate", "story.generate", "story.mirror"),
    "story.simulate": ("story.simulate", "story.simulate", "story.mirror"),
    "story.native": ("story.native", "story.native", "story.mirror"),
    "story.mirror": ("story.mirror", "story.simulate", "story.mirror"),
    "game.native_recipe": ("game.native_recipe", "game.simulate", "mirror.fuzz"),
    "mirror.fuzz": ("mirror.fuzz", "game.simulate", "mirror.fuzz"),
    "mirror.originality": ("mirror.originality", "knowledge.search", "mirror.originality"),
    "release.assess": ("release.assess", "companion.practice", "mirror.fuzz"),
    "companion.practice": ("companion.practice", "companion.practice", "mirror.fuzz"),
    "package.source": ("package.source", "game.godot", "mirror.fuzz"),
}
_ROLE_ACTOR = {
    "jeeves": Actor.JEEVES,
    "dragon": Actor.DRAGON,
    "adversarial": Actor.MIRROR,
}
_HOLDOUT_PARETO = "scope cut line at vertical slice"
_HOLDOUT_MATH = "fixed_timestep"
_CORPUS = Path(__file__).resolve().parents[3] / "data" / "game_building"
_SPRITE_KINDS = ("hero", "enemy", "collectible", "plant", "rock", "portal", "chest")
_THEMES = ("fantasy", "cyber", "desert", "ice", "forest", "space")
_TEMPOS = (84, 120, 174)


class RoleTriadError(ValueError):
    """A game-builder part has no Jeeves, Dragon, or adversarial route."""


def _lane(owner: str, evidence: dict) -> dict:
    if owner not in ROLES or type(evidence) is not dict:
        raise RoleTriadError("typed role evidence required")
    body = {
        "owner": owner,
        "evidence": evidence,
        "weights_changed": False,
        "promotion": False,
        "human_review_forged": False,
    }
    return {**body, "digest": canonical_digest(body)}


def _part(name: str, lanes: dict[str, dict]) -> dict:
    if name not in PARTS or set(lanes) != set(ROLES):
        raise RoleTriadError("every exercised part needs three role lanes")
    body = {
        "part": name,
        "lanes": {role: lanes[role] for role in ROLES},
        "connected": True,
    }
    return {**body, "digest": canonical_digest(body)}


def tool_triad() -> tuple[dict, ...]:
    """Return the Jeeves, Dragon, and adversarial route for every builtin tool."""
    specs = {spec.tool_id: spec for spec in BUILTIN_TOOLS}
    if set(specs) != set(TOOL_TRIAD):
        missing = sorted(set(specs) - set(TOOL_TRIAD))
        extra = sorted(set(TOOL_TRIAD) - set(specs))
        raise RoleTriadError(f"tool triad drifted from the builtin catalog: {missing} {extra}")
    fabric = ToolFabric()
    rows = []
    for tool_id in sorted(TOOL_TRIAD):
        jeeves, dragon, adversarial = TOOL_TRIAD[tool_id]
        binding = {"jeeves": jeeves, "dragon": dragon, "adversarial": adversarial}
        for role, counterpart in binding.items():
            spec = specs.get(counterpart)
            actor = _ROLE_ACTOR[role]
            if spec is None or actor not in spec.actors:
                raise RoleTriadError(f"{tool_id} {role} counterpart is not owned by {actor.value}")
            if not any(counterpart == item.tool_id for phase in spec.phases
                       for item in fabric.discover(actor=actor, phase=phase)):
                raise RoleTriadError(f"{counterpart} is not discoverable by {actor.value}")
        rows.append({"tool_id": tool_id, **binding})
    return tuple(rows)


def _colors(buf: bytes) -> set[bytes]:
    return {buf[i:i + 4] for i in range(0, len(buf), 4)}


def _sprite_rgba(sprite) -> bytes:
    raw = bytearray()
    for row in sprite.pixels:
        for index in row:
            raw.extend(bytes.fromhex(sprite.palette[index].lstrip("#") + "ff"))
    return bytes(raw)


def _quarter_aligned(notes: tuple, tempo: int) -> bool:
    """True when every note starts on the rounded beat grid of 60/bpm."""
    if len(notes) < 2 or not 40 <= tempo <= 240:
        return False
    quarter = 60 / tempo
    return all(notes[index][1] == round(index * quarter, 5) for index in range(len(notes)))


def _frames_aligned(score) -> bool:
    expected = max(4, min(13, round(900 / score.beats_per_minute)))
    return score.frames_per_step == expected and score.mode in GAME_MODES


def _unique_knowledge() -> tuple[list[dict], list[dict]]:
    pareto_path = _CORPUS / "pareto" / "game_design_pareto_corpus.txt.gz"
    math_path = _CORPUS / "math_physics" / "game_math_physics_corpus.txt.gz"
    if not pareto_path.is_file() or not math_path.is_file():
        raise RoleTriadError("installed game-knowledge corpora are missing")
    pareto: dict[str, int] = {}
    with gzip.open(pareto_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("|")
            if len(parts) < 5:
                continue
            pareto[parts[3]] = pareto.get(parts[3], 0) + 1
    math_laws: dict[str, int] = {}
    with gzip.open(math_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if "|Use in " not in line:
                continue
            head, _note = line.rstrip("\n").rsplit("|Use in ", 1)
            bits = head.split("|", 2)
            if len(bits) < 3:
                continue
            math_laws[bits[1]] = math_laws.get(bits[1], 0) + 1
    if _HOLDOUT_PARETO not in pareto or _HOLDOUT_MATH not in math_laws:
        raise RoleTriadError("knowledge holdout is not present in the installed corpora")
    pareto_rows = [
        {"id": "pareto-" + sha256(text.encode()).hexdigest()[:8], "text": text, "repeats": count}
        for text, count in sorted(pareto.items())
    ]
    math_rows = [
        {"id": "math-" + topic, "text": topic, "repeats": count}
        for topic, count in sorted(math_laws.items())
    ]
    return pareto_rows, math_rows


def _knowledge(pareto_rows: list[dict], math_rows: list[dict]) -> dict:
    admitted = [
        row for row in (*pareto_rows, *math_rows)
        if row["text"] not in {_HOLDOUT_PARETO, _HOLDOUT_MATH}
    ]
    held = [row for row in (*pareto_rows, *math_rows) if row not in admitted]
    admitted_ids = {row["id"] for row in admitted}
    held_ids = {row["id"] for row in held}
    if held_ids & admitted_ids or len(held) != 2:
        raise RoleTriadError("knowledge holdout leaked into the admitted set")
    return _part("game_knowledge", {
        "jeeves": _lane("jeeves", {
            "admitted_laws": len(admitted),
            "admitted_digest": canonical_digest([row["id"] for row in admitted]),
            "serving_transformers_updated": False,
        }),
        "dragon": _lane("dragon", {
            "observed_terms": len({word for row in admitted for word in row["text"].split()}),
            "crawl_performed": False,
            "training_authorized": False,
            "almanac_promoted": False,
        }),
        "adversarial": _lane("adversarial", {
            "holdout_ids": sorted(held_ids),
            "holdout_absent_from_admitted": held_ids.isdisjoint(admitted_ids),
            "rejected_tamper": held_ids.isdisjoint(admitted_ids),
        }),
    })


def _assets(seed: int) -> tuple[dict, dict, dict]:
    palettes = {theme: generate_game_palette(seed, theme=theme) for theme in _THEMES}
    plan = fidelity_plan("game_boy")
    foreign_color = "#010203"
    foreign_rejected = all(foreign_color not in colors for colors in palettes.values())
    style = _part("asset_style", {
        "jeeves": _lane("jeeves", {
            "target_id": plan["target_id"],
            "techniques": list(plan["techniques"]),
            "model_super_resolution": plan["model_super_resolution"],
            "native_hardware_qualified": plan["native_hardware_qualified"],
        }),
        "dragon": _lane("dragon", {
            "themes": sorted(palettes),
            "colors_per_theme": sorted({len(colors) for colors in palettes.values()}),
            "commercial_sprite_sheet_copied": False,
        }),
        "adversarial": _lane("adversarial", {
            "foreign_color_rejected": foreign_rejected,
            "rejected_tamper": foreign_rejected,
        }),
    })
    sprites = tuple(
        procedural_sprite(seed, kind=kind, size=16, palette=palettes["fantasy"])
        for kind in _SPRITE_KINDS
    )
    native = sprite_to_svg(sprites[0], pixel_size=1)
    displayed = sprite_to_svg(sprites[0], pixel_size=8)
    atlas, coords = pack_sprite_atlas(sprites)
    rebuilt = procedural_sprite(seed, kind="hero", size=16, palette=palettes["fantasy"])
    rebuild_ok = rebuilt.pixels == sprites[0].pixels
    other_rejected = procedural_sprite(
        seed + 1, kind="hero", size=16, palette=palettes["fantasy"],
    ).pixels != sprites[0].pixels
    generation = _part("asset_generation", {
        "jeeves": _lane("jeeves", {
            "native_svg_digest": sha256(native.encode()).hexdigest(),
            "display_svg_digest": sha256(displayed.encode()).hexdigest(),
            "display_scale": 8,
            "viewbox_unchanged": 'viewBox="0 0 16 16"' in native and 'viewBox="0 0 16 16"' in displayed,
        }),
        "dragon": _lane("dragon", {
            "kinds": list(_SPRITE_KINDS),
            "frames": len(animate_sprite(sprites[0], frames=4, shift=1)),
            "atlas_sprites": len(coords),
            "atlas_digest": sha256(atlas.encode()).hexdigest(),
        }),
        "adversarial": _lane("adversarial", {
            "seed_rebuild_matches": rebuild_ok,
            "other_seed_rejected": other_rejected,
            "rejected_tamper": rebuild_ok and other_rejected,
        }),
    })
    hero = procedural_sprite(seed, kind="hero", size=8, palette=palettes["fantasy"])
    raw = _sprite_rgba(hero)
    nearest = _expand(raw, 8, 8, 4, "nearest")
    scaled = _expand(raw, 8, 8, 4, "scale2x")
    source = _colors(raw)
    forged = bytearray(nearest)
    forged[0:4] = b"\x01\x02\x03\x80"
    forged_rejected = not (_colors(bytes(forged)) <= source)
    if not (_colors(nearest) <= source and _colors(scaled) <= source):
        raise RoleTriadError("upscaler introduced a color outside the source palette")
    upscale = _part("asset_upscale", {
        "jeeves": _lane("jeeves", {
            "nearest_bytes": len(nearest),
            "scale2x_bytes": len(scaled),
            "factor": 4,
            "palette_preserved": _colors(nearest) <= source and _colors(scaled) <= source,
        }),
        "dragon": _lane("dragon", {
            "source_colors": len(source),
            "output_dimension": 32,
            "new_colors_observed": len(_colors(nearest) - source) + len(_colors(scaled) - source),
        }),
        "adversarial": _lane("adversarial", {
            "forged_color_rejected": forged_rejected,
            "rejected_tamper": forged_rejected,
        }),
    })
    return style, generation, upscale


def _music(seed: int) -> tuple[dict, dict]:
    melodies = {}
    for tempo in _TEMPOS:
        notes = compose_game_melody(seed, bars=4, tempo=tempo)
        melodies[str(tempo)] = {
            "notes": len(notes),
            "quarter_seconds": round(60 / tempo, 5),
            "aligned": _quarter_aligned(notes, tempo),
            "wav_bytes": len(render_game_melody(notes, rate=16000)),
        }
    scores = [compose(mode, seed, steps=16) for mode in GAME_MODES]
    if sum(row["aligned"] for row in melodies.values()) != len(_TEMPOS):
        raise RoleTriadError("melody timing drifted from the quarter note")
    if not all(_frames_aligned(score) for score in scores):
        raise RoleTriadError("chip score frames do not follow tempo")
    if len({score.fingerprint for score in scores}) != len(GAME_MODES):
        raise RoleTriadError("dragon chip modes did not stay distinct")
    drifted = list(compose_game_melody(seed, bars=1, tempo=120))
    drifted[1] = (drifted[1][0], round(drifted[1][1] + 0.05, 5), drifted[1][2])
    drifted_gap = not _quarter_aligned(tuple(drifted), 120)
    drifted_frames = not _frames_aligned(
        replace(scores[0], frames_per_step=scores[0].frames_per_step + 1),
    )
    unknown_rejected = False
    try:
        compose("copied-soundtrack", seed, steps=16)
    except ValueError:
        unknown_rejected = True
    generation = _part("music_generation", {
        "jeeves": _lane("jeeves", {
            "tempos": melodies,
            "effects": {kind: len(synthesize_game_effect(kind))
                        for kind in ("pickup", "hit", "jump", "win", "dash")},
            "commercial_stem_copied": False,
        }),
        "dragon": _lane("dragon", {
            "modes": [
                {"mode": score.mode, "bpm": score.beats_per_minute, "notes": score.note_events}
                for score in scores
            ],
            "distinct_fingerprints": len({score.fingerprint for score in scores}),
        }),
        "adversarial": _lane("adversarial", {
            "unknown_mode_rejected": unknown_rejected,
            "rejected_tamper": unknown_rejected,
        }),
    })
    timing = _part("music_timing", {
        "jeeves": _lane("jeeves", {
            "quarter_note_rule": "60/bpm",
            "aligned_tempos": sum(row["aligned"] for row in melodies.values()),
        }),
        "dragon": _lane("dragon", {
            "frames_follow_bpm": all(_frames_aligned(score) for score in scores),
            "frames_per_step": {score.mode: score.frames_per_step for score in scores},
        }),
        "adversarial": _lane("adversarial", {
            "drifted_gap_rejected": drifted_gap,
            "drifted_frame_step_rejected": drifted_frames,
            "rejected_tamper": drifted_gap and drifted_frames,
        }),
    })
    return generation, timing


def _play(seed: int, mirror_attempts: int) -> tuple[dict, dict]:
    intent = GameBuildIntent(
        project_id="role-triad-" + str(seed),
        title="Role Triad Circuit",
        subtitle="Original maze exercised by Jeeves, Dragon, and the mirror.",
        seed=seed,
        width=11,
        height=11,
        levels=1,
        collectibles_per_level=1,
        hazards_per_level=1,
        theme="arcade",
        starting_health=3,
    )
    project = compile_original_game(intent, authorized=True)
    verify_replay(project.world, project.proof, authorized=True)
    insight = measure_original_practice(
        project.world, project.proof, authorized=True, distinct_themes=1,
    )
    package = render_dual_runtime_package(project, authorized=True)
    report = review_playable_project(
        project, package, authorized=True, attempts=mirror_attempts,
    )
    forged_replay_rejected = False
    try:
        verify_replay(
            project.world,
            replace(project.proof, world_digest="0" * 64),
            authorized=True,
        )
    except GameplayError:
        forged_replay_rejected = True
    forged_package_rejected = False
    original = package.files["index.html"]
    try:
        package.files["index.html"] = original + b"/* tamper */"
        try:
            review_playable_project(
                project, package, authorized=True, attempts=mirror_attempts,
            )
        except MirrorRoomError:
            forged_package_rejected = True
    finally:
        package.files["index.html"] = original
    if not report.passed or not forged_replay_rejected or not forged_package_rejected:
        raise RoleTriadError("adversarial lane accepted a forged gameplay artifact")
    logic = _part("game_logic", {
        "jeeves": _lane("jeeves", {
            "world_digest": project.world.digest,
            "proof_status": project.proof.final_state.status,
            "actions": len(project.proof.action_receipts),
        }),
        "dragon": _lane("dragon", {
            "insight_digest": insight.digest,
            "learned_model_weights": False,
            "verified_experience": insight.verified_experience,
        }),
        "adversarial": _lane("adversarial", {
            "forged_replay_rejected": forged_replay_rejected,
            "rejected_tamper": True,
        }),
    })
    gameplay = _part("gameplay", {
        "jeeves": _lane("jeeves", {
            "package_digest": package.manifest["manifest_digest"],
            "levels": len(project.world.levels),
        }),
        "dragon": _lane("dragon", {
            "safe_solution_turns": insight.safe_solution_turns,
            "observation": insight.observation,
        }),
        "adversarial": _lane("adversarial", {
            "mirror_passed": report.passed,
            "attempts": len(report.probes),
            "failed_count": len(report.failures),
            "families": sorted({probe.family for probe in report.probes}),
            "forged_package_rejected": forged_package_rejected,
            "human_ux_reviewed": False,
            "native_hardware_reviewed": False,
            "rejected_tamper": True,
        }),
    })
    return logic, gameplay


def connect_system_triad(*, seed: int = 17, mirror_attempts: int = 64,
                         authorized: bool) -> dict:
    """Exercise every declared part through Jeeves, Dragon, and the adversary."""
    if authorized is not True:
        raise PermissionError("role triad execution requires operator authorization")
    if type(seed) is not int or isinstance(seed, bool) or not 0 <= seed < 2**31:
        raise RoleTriadError("triad seed must be a 31-bit integer")
    if type(mirror_attempts) is not int or isinstance(mirror_attempts, bool) or not 64 <= mirror_attempts <= 512:
        raise RoleTriadError("adversarial attempts must be 64 to 512")
    catalog = tool_triad()
    pareto_rows, math_rows = _unique_knowledge()
    logic, gameplay = _play(seed, mirror_attempts)
    style, generation, upscale = _assets(seed)
    music, timing = _music(seed)
    knowledge = _knowledge(pareto_rows, math_rows)
    parts = {
        row["part"]: row
        for row in (logic, knowledge, gameplay, style, generation, upscale, music, timing)
    }
    if set(parts) != set(PARTS):
        raise RoleTriadError("exercised parts drifted")
    for name in PARTS:
        attack = parts[name]["lanes"]["adversarial"]["evidence"]
        if attack.get("rejected_tamper") is not True:
            raise RoleTriadError(name + " adversarial lane accepted a tampered artifact")
    body = {
        "schema": SCHEMA,
        "catalog": list(catalog),
        "catalog_count": len(catalog),
        "parts": [parts[name] for name in PARTS],
        "part_count": len(PARTS),
        "roles": list(ROLES),
        "weights_changed": False,
        "reviewed_knowledge_promoted": False,
        "human_review_forged": False,
        "serving_transformers_updated": False,
        "perfect_builder_claimed": False,
    }
    return {**body, "digest": canonical_digest(body)}
