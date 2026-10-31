"""Connect every game-builder part through Jeeves, Dragon, and an adversary.

The tool catalog stays fail-closed: a mirror actor does not gain authorship,
and a dragon observation does not gain promotion rights. Each installed tool
still receives one Jeeves route, one Dragon route, and one adversarial
counterpart. The exercise below calls those owners on original knowledge,
gameplay, assets, upscaling, and music. It does not train or promote weights.
"""
from __future__ import annotations

import gzip
import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

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

from .companion_curriculum import measure_original_practice
from .contracts import canonical_digest
from .dual_runtime_export import render_dual_runtime_package
from .mirror_room_runtime import MirrorRoomError, review_playable_project
from .playable_compiler import compile_original_game
from .playable_simulation import GameplayError, verify_replay
from .playable_world import GameBuildIntent
from .studio_tool_fabric import (
    BUILTIN_TOOLS,
    Actor,
    ToolFabric,
)

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
_MAX_CORPUS_COMPRESSED = 8 * 1024 * 1024
_MAX_CORPUS_DECODED = 64 * 1024 * 1024
_MAX_CORPUS_LINE = 4096
_MAX_CORPUS_ROWS = 500_000
_MAX_KNOWLEDGE_LAWS = 4096
_SOURCE_OWNERS = (
    "ai/game_builder/studio_role_triad.py",
    "ai/game_builder/contracts.py",
    "ai/game_builder/studio_tool_fabric.py",
    "ai/game_builder/playable_compiler.py",
    "ai/game_builder/playable_world.py",
    "ai/game_builder/playable_simulation.py",
    "ai/game_builder/playable_export.py",
    "ai/game_builder/tile_editor_export.py",
    "ai/game_builder/mirror_room_runtime.py",
    "ai/game_builder/companion_curriculum.py",
    "ai/game_builder/dual_runtime_export.py",
    "ai/game_builder/studio_native_psg.py",
    "ai/webcrawler/dragon_chip_music.py",
    "ai/webcrawler/dragon_game_blueprints.py",
    "ai/webcrawler/game_scale_assets.py",
    "developer/jeeves_game_upscale.py",
)


class RoleTriadError(ValueError):
    """A game-builder part has no Jeeves, Dragon, or adversarial route."""


def _lane(owner: str, evidence: dict) -> dict:
    if owner not in ROLES or type(evidence) is not dict:
        raise RoleTriadError("typed role evidence required")
    body = {
        "owner": owner,
        "evidence": evidence,
        "execution_kind": "deterministic_local_adapter",
        "model_call_performed": False,
        "independent_model_review": False,
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


def _source_lineage() -> dict:
    root = Path(__file__).resolve().parents[2]
    sources = []
    for relative in _SOURCE_OWNERS:
        target = root / relative
        if target.is_symlink() or not target.is_file():
            raise RoleTriadError("installed triad source owner is unavailable")
        with target.open("rb") as handle:
            raw = handle.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise RoleTriadError("triad source owner exceeds the identity budget")
        sources.append({"path": "skeleton/" + relative,
                        "sha256": sha256(raw).hexdigest(), "bytes": len(raw)})
    body = {"sources": sources, "identity_kind": "installed_source_bytes",
            "scope": "listed exercised owners and explicit domain dependencies",
            "arbitrary_transitive_dependency_closure_attested": False,
            "loaded_runtime_or_standard_library_attested": False}
    return {**body, "digest": canonical_digest(body)}


def _corpus_manifest() -> tuple[dict, str]:
    path = _CORPUS / "manifest.json"
    if path.is_symlink() or not path.is_file():
        raise RoleTriadError("installed game-knowledge manifest is missing")
    with path.open("rb") as handle:
        raw = handle.read(128 * 1024 + 1)
    if len(raw) > 128 * 1024:
        raise RoleTriadError("game-knowledge manifest exceeds the evidence budget")
    try:
        manifest = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise RoleTriadError("invalid game-knowledge manifest") from exc
    if (type(manifest) is not dict
            or manifest.get("schema_version") != "skeleton.reference_corpus_manifest.v1"
            or manifest.get("automatic_training_authorized") is not False
            or type(manifest.get("entries")) is not list
            or not 1 <= len(manifest["entries"]) <= 128):
        raise RoleTriadError("unsupported game-knowledge provenance contract")
    return manifest, sha256(raw).hexdigest()


def _read_knowledge(relative: str, manifest: dict, consume) -> dict:
    """Stream the pinned reference bytes with strict decompression limits.

    Parsed rows remain local until compressed and decoded identities agree with
    the installed manifest. Reference inclusion never authorizes model training.
    """
    path = _CORPUS / relative
    declared = "data/game_building/" + relative
    matches = [row for row in manifest["entries"]
               if type(row) is dict and row.get("path") == declared]
    if len(matches) != 1:
        raise RoleTriadError("game-knowledge manifest entry is missing or duplicated")
    entry = matches[0]
    for key, maximum in (("compressed_bytes", _MAX_CORPUS_COMPRESSED),
                         ("decoded_bytes", _MAX_CORPUS_DECODED),
                         ("newline_count", _MAX_CORPUS_ROWS)):
        if type(entry.get(key)) is not int or not 1 <= entry[key] <= maximum:
            raise RoleTriadError("game-knowledge manifest exceeds the stream budget")
    if path.is_symlink() or not path.is_file() or path.parent.is_symlink():
        raise RoleTriadError("installed game-knowledge corpus is unavailable")
    compressed_hash = sha256()
    compressed_size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            compressed_size += len(chunk)
            if compressed_size > entry["compressed_bytes"]:
                raise RoleTriadError("compressed game-knowledge size changed")
            compressed_hash.update(chunk)
    if (compressed_size != entry["compressed_bytes"]
            or compressed_hash.hexdigest() != entry.get("compressed_sha256")):
        raise RoleTriadError("compressed game-knowledge identity changed")
    decoded_hash = sha256()
    decoded_size = rows = 0
    try:
        with gzip.open(path, "rb") as handle:
            while True:
                raw = handle.readline(_MAX_CORPUS_LINE + 1)
                if not raw:
                    break
                decoded_size += len(raw)
                rows += 1
                if (len(raw) > _MAX_CORPUS_LINE
                        or decoded_size > entry["decoded_bytes"]
                        or rows > entry["newline_count"]):
                    raise RoleTriadError("decoded game-knowledge exceeds declared bounds")
                decoded_hash.update(raw)
                consume(raw.decode("utf-8"))
    except (OSError, EOFError, UnicodeError) as exc:
        raise RoleTriadError("game-knowledge stream is corrupt") from exc
    if (decoded_size != entry["decoded_bytes"]
            or rows != entry["newline_count"]
            or decoded_hash.hexdigest() != entry.get("decoded_sha256")):
        raise RoleTriadError("decoded game-knowledge identity changed")
    return {"path": declared, "compressed_sha256": compressed_hash.hexdigest(),
            "decoded_sha256": decoded_hash.hexdigest(), "decoded_bytes": decoded_size,
            "rows": rows, "training_authorized": False,
            "content_class": manifest.get("content_class"),
            "source_commit": manifest.get("source_commit")}


def _unique_knowledge() -> tuple[list[dict], list[dict], dict]:
    manifest, manifest_sha = _corpus_manifest()
    pareto: dict[str, int] = {}

    def consume_pareto(line):
            parts = line.rstrip("\n").split("|")
            if len(parts) < 5:
                raise RoleTriadError("malformed Pareto reference row")
            pareto[parts[3]] = pareto.get(parts[3], 0) + 1
            if len(pareto) > _MAX_KNOWLEDGE_LAWS:
                raise RoleTriadError("too many unique Pareto reference laws")

    math_laws: dict[str, int] = {}

    def consume_math(line):
            if "|Use in " not in line:
                raise RoleTriadError("malformed mathematical reference row")
            head, _note = line.rstrip("\n").rsplit("|Use in ", 1)
            bits = head.split("|", 2)
            if len(bits) < 3:
                raise RoleTriadError("malformed mathematical reference identity")
            math_laws[bits[1]] = math_laws.get(bits[1], 0) + 1
            if len(math_laws) > _MAX_KNOWLEDGE_LAWS:
                raise RoleTriadError("too many unique mathematical reference laws")

    receipts = [
        _read_knowledge("pareto/game_design_pareto_corpus.txt.gz", manifest, consume_pareto),
        _read_knowledge("math_physics/game_math_physics_corpus.txt.gz", manifest, consume_math),
    ]
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
    body = {"manifest_sha256": manifest_sha, "sources": receipts,
            "provenance_kind": "generated_design_reference",
            "measured_gameplay_evidence": False, "automatic_training_authorized": False}
    return pareto_rows, math_rows, {**body, "digest": canonical_digest(body)}


def _check_partition(admitted: list[dict], held: list[dict]) -> None:
    admitted_ids = [row["id"] for row in admitted]
    held_ids = [row["id"] for row in held]
    if (len(admitted_ids) != len(set(admitted_ids))
            or len(held_ids) != 2 or len(set(held_ids)) != 2
            or set(admitted_ids).intersection(held_ids)
            or any(row["text"] in {_HOLDOUT_PARETO, _HOLDOUT_MATH}
                   for row in admitted)):
        raise RoleTriadError("knowledge holdout leaked into the admitted set")


def _knowledge(pareto_rows: list[dict], math_rows: list[dict]) -> dict:
    admitted = [
        row for row in (*pareto_rows, *math_rows)
        if row["text"] not in {_HOLDOUT_PARETO, _HOLDOUT_MATH}
    ]
    held = [row for row in (*pareto_rows, *math_rows) if row not in admitted]
    admitted_ids = {row["id"] for row in admitted}
    held_ids = {row["id"] for row in held}
    _check_partition(admitted, held)
    injected_holdout_rejected = False
    try:
        _check_partition([*admitted, held[0]], held)
    except RoleTriadError:
        injected_holdout_rejected = True
    if not injected_holdout_rejected:
        raise RoleTriadError("adversarial holdout injection was accepted")
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
            "injected_holdout_rejected": injected_holdout_rejected,
            "verification_kind": "local_reference_partition_integrity",
            "independent_quality_or_originality_review": False,
            "rejected_tamper": injected_holdout_rejected,
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
    source_lineage = _source_lineage()
    catalog = tool_triad()
    tool_contracts = [spec.to_payload() for spec in
                      sorted(BUILTIN_TOOLS, key=lambda item: item.tool_id)]
    pareto_rows, math_rows, knowledge_lineage = _unique_knowledge()
    inputs = {"seed": seed, "mirror_attempts": mirror_attempts,
              "source_lineage_digest": source_lineage["digest"],
              "knowledge_lineage_digest": knowledge_lineage["digest"],
              "tool_catalog_digest": canonical_digest({
                  "routes": catalog, "contracts": tool_contracts})}
    input_digest = canonical_digest(inputs)
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
        bound = {key: value for key, value in parts[name].items() if key != "digest"}
        bound["input_digest"] = input_digest
        bound["source_lineage_digest"] = source_lineage["digest"]
        parts[name] = {**bound, "digest": canonical_digest(bound)}
    if _source_lineage()["digest"] != source_lineage["digest"]:
        raise RoleTriadError("triad source changed during the measured operation")
    body = {
        "schema": SCHEMA,
        "inputs": inputs,
        "input_digest": input_digest,
        "source_lineage": source_lineage,
        "knowledge_lineage": knowledge_lineage,
        "catalog": list(catalog),
        "tool_contracts": tool_contracts,
        "catalog_count": len(catalog),
        "parts": [parts[name] for name in PARTS],
        "part_count": len(PARTS),
        "roles": list(ROLES),
        "execution_kind": "deterministic_local_adapter_exercise",
        "independent_model_review": False,
        "model_calls_performed": 0,
        "catalog_binding_does_not_mean_every_tool_was_executed": True,
        "evidence_scope": "bounded original maze, procedural assets, music and reference integrity",
        "weights_changed": False,
        "reviewed_knowledge_promoted": False,
        "human_review_forged": False,
        "serving_transformers_updated": False,
        "perfect_builder_claimed": False,
    }
    return {**body, "digest": canonical_digest(body)}
