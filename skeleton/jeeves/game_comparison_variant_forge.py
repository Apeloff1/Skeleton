"""Generate original earlier/middle/after console-editor projects from review evidence.

This authoring step creates independent homebrew project files using Skeleton's
existing ConsoleProject validation. Observed source games are used as evidence
references, never copied ROMs, characters, maps, music or protected dialogue.
It does not train an LLM or claim a platform ROM compiled successfully.
"""
from __future__ import annotations

import hashlib
import json
from collections import deque
from collections.abc import Mapping
from typing import Any

from .game_comparison_schema import digest

SCHEMA = "skeleton.game.comparison_original_variant_forge.v1"
PHASES = ("earlier", "middle", "after")
MAX_SOURCE_GAMES = 30
MAX_REVIEWED_PARAMETERS = 40

class ComparativeVariantError(ValueError):
    """Unqualified source evidence or unsupported original project request."""


def _evidence(report: Mapping[str, Any], ids: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if (not isinstance(report, dict)
        or report.get("schema_version") != "skeleton.game.comparative_study_result.v1"
        or digest({k: v for k, v in report.items() if k != "result_sha256"}) != report.get("result_sha256")):
        raise ComparativeVariantError("Exact, intact comparative native evidence is required")
    if (not isinstance(ids, list) or not 2 <= len(ids) <= MAX_SOURCE_GAMES
        or any(type(i) is not str for i in ids) or len(set(ids)) != len(ids)):
        raise ComparativeVariantError("Forge uses 2–30 distinct explicitly selected original sources")
    games = report.get("games", {})
    for i in ids:
        game = games.get(i)
        if not isinstance(game, dict) or game.get("status") != "actual_native_observations_captured":
            raise ComparativeVariantError("Every selected game must have actual native observations")
        if not isinstance(game.get("phases"), dict) or set(game["phases"]) != set(PHASES):
            raise ComparativeVariantError("Selected game lacks a complete observed timepoint series")
    notes = [
        n for n in report.get("observer_notes", [])
        if n.get("knowledge_status") == "reviewed_observation_candidate"
        and n.get("review_status") == "reviewed"
        and all(i in ids for i in n.get("game_ids", []))
        and bool(n.get("evidence"))
    ]
    if len(notes) > 1500:
        raise ComparativeVariantError("Source review exceeds note budget")
    return games, notes


def _route_exists(cells: list[dict[str, Any]], width: int, height: int) -> bool:
    sx, sy, gx, gy = 2, 2, width-4, height-4
    if any(not 1 <= x < width-1 or not 1 <= y < height-1 for x, y in ((sx,sy),(gx,gy))):
        return False
    blocked = {idx for idx, cell in enumerate(cells) if cell["collision"] == "solid"}
    todo=deque([(sx,sy)])
    seen = {(sx,sy)}
    while todo:
        x,y=todo.popleft()
        if (x,y) == (gx,gy):
            return True
        for nx,ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
            if not 0 <= nx < width or not 0 <= ny < height or (nx,ny) in seen or ny*width+nx in blocked:
                continue
            seen.add((nx,ny))
            todo.append((nx,ny))
    return False


def _original_geometry(document: dict[str, Any], phase: str, entropy: int) -> dict[str, Any]:
    """Create brand-new authored barriers and alternate routes without source maps."""
    import copy
    doc = copy.deepcopy(document)
    layer = doc["layers"][0]
    width, height = layer["width"], layer["height"]
    cells = layer["cells"]
    if len(cells) != width * height:
        raise ComparativeVariantError("Canonical editor tilemap differs from its typed dimensions")
    # Never modify the canonical exterior walls, spawn, or goal corridor.
    # Early design: one short traversal. Mid: two decision barriers.
    # Advanced: three partial barriers and openings from both ends.
    bands = {"earlier": 1, "middle": 2, "after": 3}[phase]
    for n in range(bands):
        x = 4 + (n+1)*(width-10)//(bands+1)
        if not 3 <= x < width-3:
            continue
        gap = 3 + (entropy + n*7) % max(1, height-7)
        for y in range(3,height-3):
            if abs(y-gap) <= 2 or y in (height-4, 3):
                continue
            cell = cells[y*width+x]
            cell["collision"] = "solid"
            cell["tile"] = 2
    if not _route_exists(cells,width,height):
        raise ComparativeVariantError("Original candidate geometry did not preserve a reachable goal")
    palette=doc["palettes"][0]["colors"]
    # The editor palette is original authored colors; these are an authored
    # controlled progression, not samples from a protected source frame.
    if len(palette) >= 4:
        palettes = {
            "earlier": ["#162e42ff","#427c9cff","#bbd7e5ff","#f2f4edff"],
            "middle": ["#242448ff","#6472b0ff","#c6a3d7ff","#f4ecddff"],
            "after": ["#183a32ff","#53a49aff","#e5ce83ff","#fff0ddff"],
        }
        palette[:4] = palettes[phase]
    # No source game positions, sprites, story or audio ever enter this
    # original project. Basic entities come from create_console_project.
    return doc


def forge_original_comparison_variants(
    report: Mapping[str, Any],
    *,
    game_ids: list[str],
    target_id: str,
    project_prefix: str = "comparative_original",
    author_seed: int = 100,
) -> dict[str, Any]:
    from .game_console_editor import ConsoleProject, console_profile, create_console_project
    if type(project_prefix) is not str or not project_prefix or len(project_prefix)>48 or not all(
        c in "abcdefghijklmnopqrstuvwxyz0123456789_" for c in project_prefix
    ):
        raise ComparativeVariantError("Project prefix must be a bounded lowercase editor ID")
    if type(author_seed) is not int or not 0 <= author_seed < 2**63:
        raise ComparativeVariantError("Original project seed must be an exact bounded integer")
    games, notes = _evidence(report, game_ids)
    profile=console_profile(target_id)
    if not profile:
        raise ComparativeVariantError("Requested destination lacks a canonical console editor")
    reviewed_parameters = [
        {
            "note_id": n["note_id"], "name": n["build_parameter_candidate"]["name"],
            "proposal": n["build_parameter_candidate"]["value"],
            "units": n["build_parameter_candidate"]["units"],
            "evidence_refs": n["evidence"],
            "implemented_in_generated_project": False,
            "verified_by_gameplay": False,
        }
        for n in notes if n.get("build_parameter_candidate") is not None
    ][:MAX_REVIEWED_PARAMETERS]
    variants = []
    for index, phase in enumerate(PHASES):
        salt = int.from_bytes(hashlib.sha256(
            (str(author_seed)+":"+report["result_sha256"]+":"+phase+":"+target_id).encode()
        ).digest()[:7],"big")
        project_id = project_prefix+"_"+phase
        base = create_console_project(
            target_id, project_id=project_id,
            title="Original comparative "+phase+" version",
            seed=salt,
        )
        doc = _original_geometry(base.as_dict(), phase, salt)
        original = ConsoleProject(doc)
        validation = original.validate()
        if not validation.valid:
            raise ComparativeVariantError("Generated project failed canonical ConsoleProject validation")
        files=original.export_files()
        variants.append({
            "variant_id": project_id, "design_era": phase,
            "seed": salt, "target_id": target_id,
            "original_project_sha256": original.digest,
            "project_file_manifest_sha256": original.manifest_digest,
            "project_document": original.as_dict(),
            "project_files": files,
            "validation": validation.as_dict(),
            "source_game_evidence": [
                {
                    "game_id": game_id,
                    "original_rom_sha256": games[game_id]["source_sha256"],
                    "actual_checkpoint_sha256": games[game_id]["phases"][phase]["evidence_sha256"],
                    "source_content_reused": False,
                } for game_id in game_ids
            ],
            "reviewed_numeric_parameters_not_automatically_applied": reviewed_parameters,
            "rendered_or_compiled_into_native_rom": False,
            "training_or_model_weights_modified": False,
        })
    result = {
        "schema_version": SCHEMA,
        "source_study_id": report["study_id"],
        "source_result_sha256": report["result_sha256"],
        "source_game_count": len(game_ids),
        "destination_target_id": target_id,
        "authored_variants": variants,
        "new_original_scene_variations": 3,
        "source_game_bytes_or_assets_copied": False,
        "builder_status": "three canonical, validated editor source projects; no native compilation claimed",
        "protected_story_music_dialogue_or_licensed_assets_reproduced": False,
    }
    result["forge_sha256"]=digest(result)
    return result
