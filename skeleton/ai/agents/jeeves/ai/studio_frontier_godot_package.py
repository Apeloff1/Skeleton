"""Source-bound Godot 4 candidate compiled from Jeeves' REAL authored project.

This is a real Godot project builder, not a design-only manifest: it uses the
existing Forge Studio typed models, expedition world generation and route
simulation, and writes only independently verified engine source bytes. The
Godot runtime is not launched or certified by this module.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
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
from .studio_sprite_bound_native_runner import (
    SpriteBoundNativeError, run_sprite_bound_native_expedition,
)

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
    from .studio_npc_cast_source import (
        compile_original_npc_cast, verify_original_npc_cast,
    )
    compiled_npc_cast = compile_original_npc_cast(
        records, world, world_source_record_id=profile_ids[0],
    )
    npc_cast_receipt = None
    if compiled_npc_cast is not None:
        native_cast_path = "game/frontier/npcs.json"
        if native_cast_path in files:
            raise FrontierSourceError("NPC cast may not replace native engine assets")
        native_cast = compiled_npc_cast["content"]
        npc_cast_receipt = compiled_npc_cast["receipt"]
        verify_original_npc_cast(
            native_cast, npc_cast_receipt, world_digest=world.digest,
        )
        files[native_cast_path] = native_cast
        file_hashes[native_cast_path] = sha256(native_cast.encode("utf-8")).hexdigest()
    # The authored original PCM samples become genuine bounded WAV resources.
    # A native sound event is only possible after separate reviewed cue routing.
    from .studio_original_audio import (
        compile_original_sound_collection, verify_original_sound,
    )
    audio = compile_original_sound_collection(records)
    authored_audio: list[dict[str, Any]] = []
    # Keep original image resources in the REAL Godot project directory.
    # They are explicitly marked not yet bound to engine actor render nodes:
    # a PNG present on disk does not prove animated asset presentation.
    binary_assets: dict[str, bytes] = {}
    for sound in audio["assets"]:
        proof = sound["metadata"]
        asset_id = proof["asset_id"]
        original = next(
            (record for record in records.values()
             if record.get("record_id") == proof["source_record_id"]),
            None,
        )
        if original is None:
            raise FrontierSourceError("published sound lost original source record")
        replay = verify_original_sound(original, sound["wav"], proof)
        if not replay["reconstructed_all_pcm_samples"]:
            raise FrontierSourceError("WAV sound cannot be replayed from authored source")
        path = "game/frontier/audio/" + asset_id + ".wav"
        source_path = "game/frontier/audio/" + asset_id + ".source.json"
        if path in files or source_path in files:
            raise FrontierSourceError("authored original sound collides with engine source")
        source_bytes = json.dumps(
            {"record": original, "metadata": proof},
            ensure_ascii=True, sort_keys=True, allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        binary_assets[path] = sound["wav"]
        binary_assets[source_path] = source_bytes
        file_hashes[path] = sha256(sound["wav"]).hexdigest()
        file_hashes[source_path] = sha256(source_bytes).hexdigest()
        authored_audio.append({
            "asset_id": asset_id,
            "source_record_id": proof["source_record_id"],
            "source_sha256": proof["source_sha256"],
            "wav_sha256": proof["wav_sha256"],
            "metadata_receipt_sha256": proof["receipt_sha256"],
        })
    authored_sprites: list[dict[str, Any]] = []
    sprite_names: list[str] = []
    compiled_sprites: list[dict[str, Any]] = []
    original_hitboxes: dict[str, dict[str, Any]] = {}
    original_metadata: dict[str, dict[str, Any]] = {}
    if any(
        isinstance(record.get("document"), dict)
        and record["document"].get("kind") == "pixel_sprite"
        for record in records.values()
    ):
        from .studio_sprite_palette_variants import compile_original_palette_collection
        from .studio_sprite_godot_resources import (
            compile_godot_sprite_resources, verify_godot_sprite_resources,
        )
        artwork = compile_original_palette_collection(records)
        for sprite in artwork["assets"]:
            compiled_sprites.append(sprite)
            info = sprite["metadata"]
            name = info["asset_id"]
            sprite_names.append(info["record_id"])
            png_path = "game/frontier/sprites/" + name + ".png"
            json_path = "game/frontier/sprites/" + name + ".json"
            metadata_bytes = json.dumps(
                info, ensure_ascii=True, sort_keys=True,
                separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")
            binary_assets[png_path] = sprite["png"]
            binary_assets[json_path] = metadata_bytes
            file_hashes[png_path] = sha256(sprite["png"]).hexdigest()
            file_hashes[json_path] = sha256(metadata_bytes).hexdigest()
            normal_png = sprite.get("normal_png")
            if normal_png is not None:
                from .studio_sprite_surface import verify_normal_texture_bytes
                verify_normal_texture_bytes(
                    sprite["png"], normal_png, info.get("normal_map"),
                    width=info["sheet_width_px"],
                    height=info["sheet_height_px"],
                )
                normal_path = "game/frontier/sprites/" + name + ".normal.png"
                if normal_path in binary_assets or normal_path in files:
                    raise FrontierSourceError("authored sprite normal map path collides")
                original_heights = sprite.get("normal_source")
                if original_heights is None:
                    raise FrontierSourceError("authored sprite lighting lacks heightfield source")
                source_bytes = json.dumps(
                    original_heights, ensure_ascii=True, sort_keys=True,
                    separators=(",", ":"), allow_nan=False,
                ).encode("utf-8")
                source_path = (
                    "game/frontier/sprites/" + name + ".normal.source.json"
                )
                if source_path in binary_assets or source_path in files:
                    raise FrontierSourceError("original normal source path collides")
                binary_assets[source_path] = source_bytes
                file_hashes[source_path] = sha256(source_bytes).hexdigest()
                binary_assets[normal_path] = normal_png
                file_hashes[normal_path] = sha256(normal_png).hexdigest()
            from .studio_sprite_hitboxes import verify_exact_sprite_hitboxes
            hitboxes = verify_exact_sprite_hitboxes(
                info, sprite["collision_rectangles"],
            )
            collision_path = (
                "game/frontier/sprites/" + name + ".hitboxes.json"
            )
            original_hitboxes[name] = hitboxes
            original_metadata[name] = info
            collision_bytes = json.dumps(
                hitboxes, ensure_ascii=True, sort_keys=True,
                separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")
            binary_assets[collision_path] = collision_bytes
            file_hashes[collision_path] = sha256(collision_bytes).hexdigest()
            engine_resources = compile_godot_sprite_resources(info)
            resource_proof = verify_godot_sprite_resources(info, engine_resources)
            from .studio_sprite_frame_cues import (
                emit_godot_frame_cue_files, verify_godot_frame_cue_files,
            )
            cue_resources = emit_godot_frame_cue_files(info)
            cue_proof = verify_godot_frame_cue_files(info, cue_resources)
            engine_resources.update(cue_resources)
            if set(engine_resources) & set(files):
                raise FrontierSourceError("sprite scene resource would replace native world file")
            for path, content in engine_resources.items():
                files[path] = content
                file_hashes[path] = sha256(content.encode("utf-8")).hexdigest()
            authored_sprites.append({
                "godot_spriteframes_resource_sha256": resource_proof["receipt_sha256"],
                "godot_preview_scene_path": (
                    "game/frontier/sprites/" + name + ".tscn"
                ),
                "asset_id": name, "source_record_id": info["record_id"],
                "source_sha256": info["source_sha256"],
                "frame_count": len(info["frames"]),
                "animation_count": len(info["animations"]),
                "animation_names": [state["name"] for state in info["animations"]],
                "frame_cues_sha256": (
                    info["frame_cues"]["receipt_sha256"]
                    if info.get("frame_cues") else None
                ),
                "frame_cue_event_ids": [
                    cue["event_id"] for cue in info["frame_cues"]["cues"]
                ] if info.get("frame_cues") else [],
                "godot_frame_cue_resource_sha256": cue_proof["receipt_sha256"],
                "png_sha256": info["png_sha256"],
                "normal_png_sha256": (
                    info["normal_map"]["normal_png_sha256"]
                    if info.get("normal_map") else None
                ),
                "original_hitbox_receipt_sha256": hitboxes["receipt_sha256"],
            })
    from .studio_sprite_actor_binding import (
        binding_from_source, bind_sprite_to_expedition_script,
        verify_actor_sprite_binding,
    )
    avatar = binding_from_source(records, authored_sprites, authored_audio)
    actor_script_receipt = None
    player_sensor_receipt = None
    if avatar is not None and avatar.get("collision_sensor") is True:
        from .studio_sprite_native_sensor import (
            compile_sprite_sensor_source, verify_sprite_sensor_source,
        )
        name = avatar["asset_id"]
        compiled_sensor = compile_sprite_sensor_source(
            original_metadata[name], original_hitboxes[name],
        )
        player_sensor_receipt = verify_sprite_sensor_source(
            original_metadata[name], original_hitboxes[name],
            compiled_sensor["script"], compiled_sensor["receipt"],
        )
        sensor_path = "game/frontier/sprites/" + name + ".sensor.gd"
        if sensor_path in files or sensor_path in binary_assets:
            raise FrontierSourceError("native player collision file path was overwritten")
        files[sensor_path] = compiled_sensor["script"]
        file_hashes[sensor_path] = sha256(
            compiled_sensor["script"].encode("utf-8")
        ).hexdigest()
    if avatar is not None:
        original_script = files["game/frontier/expedition.gd"]
        updated_script = bind_sprite_to_expedition_script(original_script, avatar)
        actor_script_receipt = verify_actor_sprite_binding(
            original_script, updated_script, avatar,
        )
        files["game/frontier/expedition.gd"] = updated_script
        file_hashes["game/frontier/expedition.gd"] = sha256(
            updated_script.encode("utf-8")
        ).hexdigest()
    compass_receipt = None
    if avatar is not None and avatar.get("directional_animations"):
        from .studio_sprite_direction import (
            compile_eight_way_actor_facing, verify_eight_way_actor_facing,
        )
        original_script = files["game/frontier/expedition.gd"]
        oriented_script = compile_eight_way_actor_facing(
            original_script, avatar,
        )
        compass_receipt = verify_eight_way_actor_facing(
            original_script, oriented_script, avatar,
        )
        files["game/frontier/expedition.gd"] = oriented_script
        file_hashes["game/frontier/expedition.gd"] = sha256(
            oriented_script.encode("utf-8")
        ).hexdigest()
    from .studio_sprite_npc_binding import (
        authored_npc_sprite_bindings, bind_npc_sprites_to_expedition_script,
        verify_native_npc_binding_script,
    )
    npc_sprite_bindings = authored_npc_sprite_bindings(
        records, authored_sprites, files,
    )
    npc_script_receipt = None
    if npc_sprite_bindings:
        prior_npc_script = files["game/frontier/expedition.gd"]
        bound_npc_script = bind_npc_sprites_to_expedition_script(
            prior_npc_script, npc_sprite_bindings,
        )
        npc_script_receipt = verify_native_npc_binding_script(
            prior_npc_script, bound_npc_script, npc_sprite_bindings,
        )
        files["game/frontier/expedition.gd"] = bound_npc_script
        file_hashes["game/frontier/expedition.gd"] = sha256(
            bound_npc_script.encode("utf-8")
        ).hexdigest()
    # Produce one machine-searchable descriptor catalog for real compiled
    # sprite and WAV bytes, including reviewed human semantics and rights.
    # Its full verified bytes belong to the native project; the main receipt
    # carries only its immutable hash and descriptor count.
    from .studio_asset_descriptors import compile_asset_catalog, catalog_bytes
    asset_catalog = compile_asset_catalog(
        project_id=project_id, source_head_sha256=source_head_sha256,
        records=records, sprites=compiled_sprites, sounds=audio["assets"],
    )
    catalog_raw = catalog_bytes(asset_catalog)
    catalog_path = "game/frontier/assets/catalog.json"
    if catalog_path in files or catalog_path in binary_assets:
        raise FrontierSourceError("asset catalog overlaps existing game resource")
    binary_assets[catalog_path] = catalog_raw
    file_hashes[catalog_path] = sha256(catalog_raw).hexdigest()
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
        "original_npc_cast_receipt": npc_cast_receipt,
        "godot_verification_sha256": godot_proof["receipt_digest"],
        "godot_file_hashes": file_hashes,
        "asset_catalog_sha256": sha256(catalog_raw).hexdigest(),
        "asset_catalog_receipt_sha256": asset_catalog["receipt_sha256"],
        "asset_descriptor_count": asset_catalog["descriptor_count"],
        "packaged_original_sprites": authored_sprites,
        "packaged_original_audio": authored_audio,
        "audio_engine_playback_verified": False,
        "original_player_audio_cue_routes_compiled": (
            len(avatar.get("audio_cue_bindings", {})) if avatar is not None
            else 0
        ),
        "original_palette_variant_receipts": (
            artwork["palette_variant_receipts"]
            if authored_sprites else []
        ),
        "source_sprite_record_ids": sprite_names,
        "animated_sprite2d_preview_scenes_authored": bool(authored_sprites),
        "authored_player_avatar_binding": avatar,
        "player_avatar_game_script_receipt": actor_script_receipt,
        "player_compass_godot_source_receipt": compass_receipt,
        "native_player_eight_way_facing_compiled": compass_receipt is not None,
        "player_collision_sensor_receipt": player_sensor_receipt,
        "native_player_alpha_sensor_script_compiled": player_sensor_receipt is not None,
        "authored_npc_sprite_bindings": npc_sprite_bindings,
        "npc_sprite_game_script_receipt": npc_script_receipt,
        "animated_npc_sprite3d_source_compiled": bool(npc_sprite_bindings),
        "animated_sprite3d_player_script_compiled": avatar is not None,
        "native_sprite_scene_binding_verified": False,
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
    return {
        "files": files, "binary_assets": binary_assets,
        "receipt": metadata,
    }


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
        if (before["receipt"]["authored_player_avatar_binding"] is not None
                or before["receipt"]["authored_npc_sprite_bindings"]):
            # The legacy runner regenerates baseline Godot files, so using it
            # here would falsely attest a game whose ACTUAL avatar never ran.
            # Execute the exact generated sprite-bound project instead.
            result = run_sprite_bound_native_expedition(
                before, world, traveler, godot_executable=godot_executable,
                timeout_seconds=timeout_seconds,
            )
        else:
            result = run_headless_expedition(
                world, traveler, godot_executable=godot_executable,
                timeout_seconds=timeout_seconds,
            )
    except (ExpeditionError, SpriteBoundNativeError) as exc:
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
        "native_compass_route_replay_receipt_sha256": result.get(
            "compass_replay_receipt_sha256",
        ),
        "native_compass_direction_transitions_observed": result.get(
            "observed_compass_transitions", 0,
        ),
        "native_compass_animation_observed": result.get(
            "native_player_heading_observed", False,
        ),
        "native_player_avatar_script_executed": (
            before["receipt"]["authored_player_avatar_binding"] is not None
        ),
        "native_npc_sprite_game_script_executed": bool(
            before["receipt"]["authored_npc_sprite_bindings"]
        ),
        "native_visual_output_independently_observed": False,
        "complete_original_game_release_certified": False,
    }
    receipt["receipt_sha256"] = digest(receipt)
    return receipt


__all__ = [
    "compile_original_godot_candidate", "run_original_game_native_playthrough",
    "FrontierSourceError",
]
