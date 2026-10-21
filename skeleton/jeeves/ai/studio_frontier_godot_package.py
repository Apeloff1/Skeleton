"""Source-bound Godot 4 candidate compiled from Jeeves' REAL authored project.

This is a real Godot project builder, not a design-only manifest: it uses the
existing Forge Studio typed models, expedition world generation and route
simulation, and writes only independently verified engine source bytes. The
Godot runtime is not launched or certified by this module.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import Any

from skeleton.forge.game_frontier_studio import author_studio_expedition
from skeleton.jeeves.game_frontier_expedition import (
    ExpeditionError, Traveler, find_route, verify_route,
)
from skeleton.jeeves.game_frontier_expedition_generation import ArchipelagoProfile
from skeleton.jeeves.game_frontier_expedition_godot import (
    emit_expedition_godot_project, verify_expedition_godot_project,
)
from .studio_frontier_source_compile import (
    FrontierSourceError, materialize_persisted_frontier_source,
)
from .studio_interaction_contract import digest

SCHEMA = "skeleton.jeeves.frontier_godot_source.v1"
PROFILE_KEYS = frozenset((
    "kind", "seed", "islands", "spacing_m", "rise_m", "branch_factor",
    "caverns", "include_underwater", "include_portals",
))
TRAVELER_KEYS = frozenset((
    "kind", "permitted_modes", "flags", "equipment",
    "max_stamina", "carried_kg", "capacity_kg", "skill", "shelter",
))


def _profiles(
    records: Mapping[str, Mapping[str, Any]],
) -> tuple[ArchipelagoProfile, Traveler, tuple[str, str]]:
    found: dict[str, tuple[str, Mapping[str, Any]]] = {}
    for name, record in sorted(records.items()):
        data = record.get("document")
        if not isinstance(data, Mapping):
            raise FrontierSourceError("reviewed expedition source must be a document")
        kind = data.get("kind")
        if kind not in ("expedition_profile", "traveler_profile"):
            continue
        if kind in found:
            raise FrontierSourceError("duplicate authoring profile for original game")
        if record.get("facet") not in (
            ("world", "pathing") if kind == "expedition_profile"
            else ("cast", "movement", "progression")
        ):
            raise FrontierSourceError("expedition/traveler profile uses wrong Forge facet")
        found[kind] = (name, data)
    if set(found) != {"expedition_profile", "traveler_profile"}:
        raise FrontierSourceError(
            "real source must author both expedition and traveler capabilities"
        )
    world_id, world = found["expedition_profile"]
    player_id, player = found["traveler_profile"]
    if set(world) != PROFILE_KEYS or set(player) != TRAVELER_KEYS:
        raise FrontierSourceError("real game profiles require complete typed capability fields")
    for field in ("permitted_modes", "flags", "equipment"):
        values = player[field]
        if (type(values) is not list or len(values) > 128
                or not all(type(value) is str for value in values)
                or len(set(values)) != len(values)):
            raise FrontierSourceError("traveler capabilities must be distinct typed lists")
    try:
        profile = ArchipelagoProfile(
            seed=world["seed"], islands=world["islands"],
            spacing_m=world["spacing_m"], rise_m=world["rise_m"],
            branch_factor=world["branch_factor"], caverns=world["caverns"],
            include_underwater=world["include_underwater"],
            include_portals=world["include_portals"],
        )
        traveler = Traveler(
            permitted_modes=frozenset(player["permitted_modes"]),
            flags=frozenset(player["flags"]),
            equipment=frozenset(player["equipment"]),
            max_stamina=player["max_stamina"],
            carried_kg=player["carried_kg"],
            capacity_kg=player["capacity_kg"],
            skill=player["skill"], shelter=player["shelter"],
        )
    except (ValueError, TypeError, KeyError) as exc:
        raise FrontierSourceError("existing native world/capability types rejected source") from exc
    return profile, traveler, (world_id, player_id)


def compile_original_godot_candidate(
    project_id: str,
    records: Mapping[str, Mapping[str, Any]],
    *, source_head_sha256: str | None,
) -> dict[str, Any]:
    """Generate independently verified original .gd, .tscn, and world assets.

    Uses the real original game world state machine to exercise an authored
    route with the EXACT authored traveler, before producing a Godot candidate.
    """
    profile, player, profile_ids = _profiles(records)
    project, typed_receipt = materialize_persisted_frontier_source(
        project_id, records, source_head_sha256=source_head_sha256,
    )
    try:
        world = author_studio_expedition(project, profile)
        if not world.destinations:
            raise FrontierSourceError("original game lacks playable destination")
        route = find_route(world, player, world.destinations[0])
        playthrough = verify_route(world, player, route)
        if not playthrough["final_state"]["won"]:
            raise FrontierSourceError("authored traveler could not win actual route")
        files = emit_expedition_godot_project(world, player)
        godot_proof = verify_expedition_godot_project(files, world, player)
    except ExpeditionError as exc:
        raise FrontierSourceError(
            "real expedition route / Godot compiler refused authored source"
        ) from exc
    if (not isinstance(files, dict) or not files
            or "project.godot" not in files
            or "game/frontier/expedition.gd" not in files):
        raise FrontierSourceError("game exporter lacks actual runnable Godot source")
    file_hashes = {
        name: sha256(raw.encode("utf-8")).hexdigest()
        for name, raw in sorted(files.items())
    }
    if file_hashes != godot_proof["file_hashes"]:
        raise FrontierSourceError("Godot compiler proof does not match file bytes")
    metadata = {
        "schema_version": SCHEMA, "project_id": project_id,
        "source_head_sha256": source_head_sha256,
        "typed_forge_receipt_sha256": typed_receipt["receipt_sha256"],
        "profile_source_record_ids": list(profile_ids),
        "typed_forge_compiled_record_ids": typed_receipt["compiled_record_ids"],
        "uncompiled_record_ids": [
            name for name in typed_receipt["non_compilable_record_ids"]
            if name not in profile_ids
        ],
        "world_sha256": world.digest,
        "godot_verification_sha256": godot_proof["receipt_digest"],
        "godot_file_hashes": file_hashes,
        "gameplay_route_digest": route.digest,
        "gameplay_execution_head_sha256": playthrough["receipt_head"],
        "real_python_route_playtest_passed": True,
        "godot_engine_launched": False,
        "native_godot_playthrough_verified": False,
        "all_studio_facets_compiled": all(
            name in profile_ids
            for name in typed_receipt["non_compilable_record_ids"]
        ),
    }
    metadata["receipt_sha256"] = digest(metadata)
    return {"files": files, "receipt": metadata}


def run_original_game_native_playthrough(
    project_id: str,
    records: Mapping[str, Mapping[str, Any]],
    *, source_head_sha256: str | None,
    godot_executable: str,
    timeout_seconds: int = 90,
) -> dict[str, Any]:
    """Run REAL Godot 4 binary and cross-check its emitted gameplay against source.

    This is explicitly a privileged host action, never callable from local
    model-generated source or authorized merely by the existence of a plan.
    """
    if not isinstance(godot_executable, str) or not godot_executable.strip():
        raise FrontierSourceError("host must specify a real Godot 4 executable")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 300:
        raise FrontierSourceError("native playthrough deadline outside reviewed bounds")
    from skeleton.jeeves.game_frontier_expedition_native_runner import (
        run_headless_expedition,
    )

    before = compile_original_godot_candidate(
        project_id, records, source_head_sha256=source_head_sha256,
    )
    profile, traveler, _ = _profiles(records)
    project, _ = materialize_persisted_frontier_source(
        project_id, records, source_head_sha256=source_head_sha256,
    )
    try:
        world = author_studio_expedition(project, profile)
        result = run_headless_expedition(
            world, traveler, godot_executable=godot_executable,
            timeout_seconds=timeout_seconds,
        )
    except ExpeditionError as exc:
        raise FrontierSourceError("real Godot 4 execution or independent replay failed") from exc
    if (result.get("native_process_executed") is not True
            or result.get("native_gameplay_consistent") is not True
            or result.get("completed") is not True
            or result.get("world_digest") != before["receipt"]["world_sha256"]):
        raise FrontierSourceError("native engine failed to prove original world ownership")
    receipt = {
        "schema_version": "skeleton.jeeves.original_game_native_playthrough.v1",
        "project_id": project_id,
        "original_source_head_sha256": source_head_sha256,
        "authored_godot_candidate_sha256": before["receipt"]["receipt_sha256"],
        "native_engine_receipt_sha256": result["receipt_digest"],
        "native_executable_sha256": result["native_executable_sha256"],
        "native_log_sha256": result["native_log_sha256"],
        "observed_replay_receipt_sha256": result["observed_replay_receipt"],
        "real_godot4_process_executed": True,
        "native_gameplay_consistent": True,
        "complete_original_game_release_certified": False,
    }
    receipt["receipt_sha256"] = digest(receipt)
    return receipt


__all__ = [
    "compile_original_godot_candidate", "run_original_game_native_playthrough",
    "FrontierSourceError",
]
