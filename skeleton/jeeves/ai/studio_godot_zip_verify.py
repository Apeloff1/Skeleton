"""Independent post-publication verifier for Jeeves' original Godot ZIP.

Checks actual disk bytes, SHA identity, every native source file against the
bundled signed-content receipt, Zip metadata/path safety, and project/source
ownership. No runtime test is inferred from checksums alone.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
from typing import Any
import zipfile

from .studio_interaction_contract import digest

MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_ENTRIES = 2048
MAX_FILE_BYTES = 8 * 1024 * 1024
PROOF_NAME = "jeeves_source_receipt.json"


class NativeSourceVerificationError(ValueError):
    """Published original Godot source ZIP failed independent verification."""


def verify_published_godot_zip(
    path: Path, *, project_id: str, source_head_sha256: str | None,
    expected_archive_sha256: str,
) -> dict[str, Any]:
    if (not isinstance(path, Path) or not path.is_absolute()
            or path.is_symlink() or not path.is_file()):
        raise NativeSourceVerificationError("Godot candidate must be a real local file")
    if not isinstance(expected_archive_sha256, str) or len(expected_archive_sha256) != 64:
        raise NativeSourceVerificationError("expected published bytes SHA-256 is required")
    size = path.stat().st_size
    if size < 128 or size > MAX_ARCHIVE_BYTES:
        raise NativeSourceVerificationError("published archive exceeds bounded size")
    raw = path.read_bytes()
    if len(raw) != size or sha256(raw).hexdigest() != expected_archive_sha256:
        raise NativeSourceVerificationError("published artifact bytes differ from expected")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            files = archive.infolist()
            names = [item.filename for item in files]
            if (len(files) < 4 or len(files) > MAX_ENTRIES
                    or len(names) != len(set(names))
                    or names.count(PROOF_NAME) != 1
                    or "project.godot" not in names
                    or "game/frontier/expedition.gd" not in names
                    or "game/frontier/expedition.tscn" not in names):
                raise NativeSourceVerificationError(
                    "Godot native game source archive is missing required files"
                )
            total = 0
            for item in files:
                name = item.filename
                pure = PurePosixPath(name)
                if (not name or pure.is_absolute() or ".." in pure.parts
                        or "\\" in name or name != pure.as_posix()
                        or name.endswith("/") or item.is_dir()
                        or item.file_size > MAX_FILE_BYTES
                        or item.compress_type != zipfile.ZIP_DEFLATED
                        or (item.external_attr >> 16) & 0o170000 != 0o100000):
                    raise NativeSourceVerificationError(
                        "Godot archive contains an unsafe or unsupported member"
                    )
                total += item.file_size
                if total > MAX_ARCHIVE_BYTES:
                    raise NativeSourceVerificationError("expanded Godot source exceeds bound")
            proof_raw = archive.read(PROOF_NAME)
            if len(proof_raw) > 96 * 1024:
                raise NativeSourceVerificationError("Godot source receipt is oversized")
            try:
                proof = json.loads(proof_raw)
            except (ValueError, UnicodeDecodeError) as exc:
                raise NativeSourceVerificationError(
                    "Godot source receipt cannot be parsed"
                ) from exc
            if (not isinstance(proof, dict)
                    or proof.get("schema_version") !=
                    "skeleton.jeeves.frontier_godot_source.v1"
                    or proof.get("project_id") != project_id
                    or proof.get("source_head_sha256") != source_head_sha256
                    or proof.get("godot_engine_launched") is not False
                    or proof.get("native_godot_playthrough_verified") is not False
                    or proof.get("real_python_route_playtest_passed") is not True):
                raise NativeSourceVerificationError(
                    "Godot source ownership or execution claims are invalid"
                )
            receipt_digest = proof.get("receipt_sha256")
            without = dict(proof)
            without.pop("receipt_sha256", None)
            if digest(without) != receipt_digest:
                raise NativeSourceVerificationError("embedded game-build evidence was changed")
            expected = proof.get("godot_file_hashes")
            if (not isinstance(expected, dict)
                    or set(expected) != set(names) - {PROOF_NAME}):
                raise NativeSourceVerificationError(
                    "native file evidence does not cover exact archive members"
                )
            for name in sorted(expected):
                source_bytes = archive.read(name)
                if sha256(source_bytes).hexdigest() != expected[name]:
                    raise NativeSourceVerificationError(
                        "published native game source does not match build proof"
                    )
            from .studio_asset_descriptors import (
                AssetDescriptorError, verify_asset_catalog,
            )
            descriptor_sprites: list[dict[str, Any]] = []
            descriptor_audio: list[dict[str, Any]] = []
            descriptor_meshes: list[dict[str, Any]] = []
            # Verify the genuinely authored NPC cast, not just its ZIP hash.
            from .studio_npc_cast_source import (
                OriginalNpcCastError, verify_original_npc_cast,
            )
            npc_cast_receipt = proof.get("original_npc_cast_receipt")
            npc_native_path = "game/frontier/npcs.json"
            if npc_cast_receipt is None:
                if npc_native_path in expected:
                    raise NativeSourceVerificationError(
                        "NPC cast exists without authored source receipts"
                    )
            else:
                if not isinstance(npc_cast_receipt, dict) or npc_native_path not in expected:
                    raise NativeSourceVerificationError(
                        "authored native NPC cast requires its exact project bytes"
                    )
                try:
                    native_cast_text = archive.read(npc_native_path).decode("utf-8")
                    npc_cast_check = verify_original_npc_cast(
                        native_cast_text, npc_cast_receipt,
                        world_digest=proof["world_sha256"],
                    )
                    world_source = json.loads(
                        archive.read("game/frontier/expedition.json")
                    )
                    world_waypoints = {
                        item["waypoint_id"]
                        for item in world_source["waypoints"]
                    }
                except (OriginalNpcCastError, KeyError, TypeError,
                        UnicodeDecodeError, ValueError) as exc:
                    raise NativeSourceVerificationError(
                        "NPC cast or native world topology source is invalid"
                    ) from exc
                for spawn in npc_cast_receipt["npc_source_records"]:
                    if (spawn["home_waypoint_id"] not in world_waypoints
                            or any(point not in world_waypoints
                                   for point in spawn["patrol_waypoint_ids"])):
                        raise NativeSourceVerificationError(
                            "NPC source patrol references missing native world waypoint"
                        )
                if not npc_cast_check["all_character_source_receipts_replayed"]:
                    raise NativeSourceVerificationError(
                        "original NPC character source failed independent replay"
                    )
            original_audio = proof.get("packaged_original_audio", [])
            if (type(original_audio) is not list or len(original_audio) > 64
                    or proof.get("audio_engine_playback_verified") is not False):
                raise NativeSourceVerificationError(
                    "original audio count or playback-claim evidence is untrusted"
                )
            if original_audio:
                from .studio_original_audio import (
                    OriginalAudioError, verify_original_sound,
                )
                heard: set[str] = set()
                for sound in original_audio:
                    if type(sound) is not dict or set(sound) != {
                        "asset_id", "source_record_id", "source_sha256",
                        "wav_sha256", "metadata_receipt_sha256",
                    }:
                        raise NativeSourceVerificationError(
                            "Godot original audio source proof is incomplete"
                        )
                    asset_id = sound["asset_id"]
                    if type(asset_id) is not str or asset_id in heard:
                        raise NativeSourceVerificationError(
                            "Godot original audio identity is duplicated or invalid"
                        )
                    heard.add(asset_id)
                    wav_path = "game/frontier/audio/" + asset_id + ".wav"
                    src_path = "game/frontier/audio/" + asset_id + ".source.json"
                    if wav_path not in expected or src_path not in expected:
                        raise NativeSourceVerificationError(
                            "authored original sound lacks its real WAV or source proof"
                        )
                    try:
                        source = json.loads(archive.read(src_path))
                        if type(source) is not dict or set(source) != {
                            "record", "metadata",
                        }:
                            raise OriginalAudioError("authored original sound proof malformed")
                        record, info = source["record"], source["metadata"]
                        checked = verify_original_sound(
                            record, archive.read(wav_path), info,
                        )
                    except (OriginalAudioError, KeyError, ValueError, TypeError) as exc:
                        raise NativeSourceVerificationError(
                            "Godot original WAV differs from independently reconstructed PCM"
                        ) from exc
                    descriptor_audio.append({
                        "wav": archive.read(wav_path), "metadata": info,
                    })
                    if (checked["wav_sha256"] != sound["wav_sha256"]
                            or checked["source_sha256"] != sound["source_sha256"]
                            or info["receipt_sha256"]
                            != sound["metadata_receipt_sha256"]
                            or info["asset_id"] != asset_id
                            or info["source_record_id"] != sound["source_record_id"]):
                        raise NativeSourceVerificationError(
                            "published original audio receipt loses source ownership"
                        )
            # Reconstruct every published indexed glTF 2.0 binary from its
            # reviewed original parametric source, not just the archive SHA.
            from .studio_original_mesh import OriginalMeshError, verify_original_mesh
            original_meshes = proof.get("packaged_original_meshes", [])
            if (type(original_meshes) is not list or len(original_meshes) > 64
                    or proof.get("native_mesh_import_verified") is not False):
                raise NativeSourceVerificationError(
                    "original 3D mesh inventory or execution claim is invalid"
                )
            seen_meshes: set[str] = set()
            for model in original_meshes:
                if type(model) is not dict or set(model) != {
                    "asset_id", "source_record_id", "source_sha256",
                    "glb_sha256", "metadata_receipt_sha256",
                }:
                    raise NativeSourceVerificationError("incomplete original GLB lineage")
                name = model["asset_id"]
                if type(name) is not str or name in seen_meshes:
                    raise NativeSourceVerificationError("duplicate original GLB asset")
                seen_meshes.add(name)
                model_path = "game/frontier/meshes/" + name + ".glb"
                source_path = "game/frontier/meshes/" + name + ".source.json"
                if model_path not in expected or source_path not in expected:
                    raise NativeSourceVerificationError("3D model source or GLB omitted")
                try:
                    source = json.loads(archive.read(source_path))
                    record, info = source["record"], source["metadata"]
                    replay = verify_original_mesh(record, archive.read(model_path), info)
                except (OriginalMeshError, KeyError, ValueError, TypeError) as exc:
                    raise NativeSourceVerificationError(
                        "indexed GLB differs from independently rebuilt mesh"
                    ) from exc
                if (replay["glb_sha256"] != model["glb_sha256"]
                        or info["receipt_sha256"] != model["metadata_receipt_sha256"]
                        or info["source_sha256"] != model["source_sha256"]
                        or record["record_id"] != model["source_record_id"]):
                    raise NativeSourceVerificationError(
                        "3D mesh evidence loses original source identity"
                    )
                descriptor_meshes.append({
                    "glb": archive.read(model_path), "metadata": info,
                })
            from .studio_original_mesh_lod_package_verify import (
                OriginalMeshArchiveError, verify_original_mesh_archive_resources,
            )
            try:
                mesh_scene_proof = verify_original_mesh_archive_resources(
                    archive, expected, proof, descriptor_meshes,
                )
            except OriginalMeshArchiveError as exc:
                raise NativeSourceVerificationError(
                    "published original mesh scenes and LOD binaries failed replay"
                ) from exc
            original_sprites = proof.get("packaged_original_sprites", [])
            if (not isinstance(original_sprites, list)
                    or len(original_sprites) > 128
                    or proof.get("native_sprite_scene_binding_verified") is not False):
                raise NativeSourceVerificationError(
                    "native sprite asset and runtime-binding claims are inconsistent"
                )
            if original_sprites:
                from .studio_sprite_forge import (
                    StudioSpriteError, _decode_verified_png,
                )
                for item in original_sprites:
                    if not isinstance(item, dict) or set(item) != {
                        "asset_id", "source_record_id", "source_sha256",
                        "frame_count", "animation_count", "animation_names",
                        "png_sha256", "normal_png_sha256",
                        "godot_spriteframes_resource_sha256",
                        "godot_preview_scene_path",
                        "original_hitbox_receipt_sha256",
                        "frame_cues_sha256", "godot_frame_cue_resource_sha256",
                        "frame_cue_event_ids",
                    }:
                        raise NativeSourceVerificationError(
                            "compiled sprite record has incomplete source references"
                        )
                    asset_name = item["asset_id"]
                    png_name = "game/frontier/sprites/" + asset_name + ".png"
                    json_name = "game/frontier/sprites/" + asset_name + ".json"
                    if png_name not in expected or json_name not in expected:
                        raise NativeSourceVerificationError(
                            "Godot candidate omitted authored sprite resources"
                        )
                    image = archive.read(png_name)
                    try:
                        sprite = json.loads(archive.read(json_name))
                    except (ValueError, TypeError, UnicodeDecodeError) as exc:
                        raise NativeSourceVerificationError(
                            "authored sprite metadata is corrupt"
                        ) from exc
                    if not isinstance(sprite, dict):
                        raise NativeSourceVerificationError(
                            "sprite metadata must be a typed original object"
                        )
                    complete = dict(sprite)
                    claim = complete.pop("receipt_sha256", None)
                    if (digest(complete) != claim
                            or sprite.get("asset_id") != asset_name
                            or sprite.get("source_sha256") != item["source_sha256"]
                            or sprite.get("record_id") != item["source_record_id"]
                            or sprite.get("png_sha256") != item["png_sha256"]
                            or len(sprite.get("frames", [])) != item["frame_count"]
                            or len(sprite.get("animations", [])) != item["animation_count"]
                            or [state["name"] for state in sprite["animations"]]
                            != item["animation_names"]
                            or (
                                [cue["event_id"] for cue in sprite["frame_cues"]["cues"]]
                                if sprite.get("frame_cues") else []
                            ) != item["frame_cue_event_ids"]):
                        raise NativeSourceVerificationError(
                            "Godot sprite source identity or animation receipt differs"
                        )
                    normal_id = item["normal_png_sha256"]
                    if (normal_id is not None) != bool(sprite.get("normal_map")):
                        raise NativeSourceVerificationError(
                            "normal map metadata and published sprite disagree"
                        )
                    if normal_id is not None:
                        from .studio_sprite_surface import (
                            SpriteSurfaceError, verify_normal_texture_bytes,
                        )
                        normal_path = (
                            "game/frontier/sprites/" + asset_name + ".normal.png"
                        )
                        if normal_path not in expected:
                            raise NativeSourceVerificationError(
                                "original sprite normal texture missing from Godot package"
                            )
                        try:
                            verified_normal = verify_normal_texture_bytes(
                                image, archive.read(normal_path),
                                sprite["normal_map"],
                                width=sprite["sheet_width_px"],
                                height=sprite["sheet_height_px"],
                            )
                        except (SpriteSurfaceError, KeyError, TypeError) as exc:
                            raise NativeSourceVerificationError(
                                "normal texture failed independent pixel or source proof"
                            ) from exc
                        if verified_normal["normal_png_sha256"] != normal_id:
                            raise NativeSourceVerificationError(
                                "normal texture differs from its source review"
                            )
                        source_path = (
                            "game/frontier/sprites/"
                            + asset_name + ".normal.source.json"
                        )
                        if source_path not in expected:
                            raise NativeSourceVerificationError(
                                "original lighting heightfield source absent"
                            )
                        try:
                            from .studio_sprite_surface import verify_authored_normals
                            original_heights = json.loads(archive.read(source_path))
                            replay = verify_authored_normals(
                                original_heights, metadata=sprite,
                                color_png=image,
                                normal_png=archive.read(normal_path),
                                normal_receipt=sprite["normal_map"],
                            )
                        except (SpriteSurfaceError, ValueError, TypeError, KeyError) as exc:
                            raise NativeSourceVerificationError(
                                "original authored normal heights cannot reproduce Godot image"
                            ) from exc
                        if replay["height_map_replayed"] is not True:
                            raise NativeSourceVerificationError(
                                "original normal map fails source reconstruction"
                            )
                    try:
                        pixels = _decode_verified_png(
                            image, sprite["sheet_width_px"],
                            sprite["sheet_height_px"],
                        )
                    except (StudioSpriteError, KeyError, TypeError) as exc:
                        raise NativeSourceVerificationError(
                            "embedded Godot PNG differs from authored sprite pixels"
                        ) from exc
                    if sha256(pixels).hexdigest() != sprite["pixel_content_sha256"]:
                        raise NativeSourceVerificationError(
                            "Godot sprite decoded pixel identity differs from source"
                        )
                    from .studio_sprite_verify import (
                        SpriteVerificationError, verify_published_sprite,
                    )
                    try:
                        inspected = verify_published_sprite(image, sprite)
                    except SpriteVerificationError as exc:
                        raise NativeSourceVerificationError(
                            "embedded Godot sprite fails independent pixel-atlas replay"
                        ) from exc
                    if not inspected["layout_and_padding_reproduced"]:
                        raise NativeSourceVerificationError(
                            "Godot sprite atlas verification did not replay source"
                        )
                    from .studio_sprite_hitboxes import (
                        SpriteCollisionError, verify_exact_sprite_hitboxes,
                    )
                    hitbox_path = "game/frontier/sprites/" + asset_name + ".hitboxes.json"
                    if hitbox_path not in expected:
                        raise NativeSourceVerificationError(
                            "packaged sprite omitted exact frame collision geometry"
                        )
                    try:
                        published_hitboxes = json.loads(archive.read(hitbox_path))
                        collision_proof = verify_exact_sprite_hitboxes(
                            sprite, published_hitboxes,
                        )
                    except (SpriteCollisionError, TypeError, ValueError) as exc:
                        raise NativeSourceVerificationError(
                            "Godot sprite collision shapes differ from source alpha pixels"
                        ) from exc
                    if (collision_proof["receipt_sha256"]
                            != item["original_hitbox_receipt_sha256"]):
                        raise NativeSourceVerificationError(
                            "original sprite collision receipt differs from game package"
                        )
                    descriptor_sprites.append({
                        "png": image, "metadata": sprite,
                    })
                    from .studio_sprite_godot_resources import (
                        SpriteResourceError, verify_godot_sprite_resources,
                    )
                    resource_paths = [
                        "game/frontier/sprites/" + asset_name + suffix
                        for suffix in (".tres", ".tscn")
                    ]
                    if sprite.get("normal_map") is not None:
                        resource_paths.append(
                            "game/frontier/sprites/" + asset_name + ".lit.tres"
                        )
                    if (item["godot_preview_scene_path"] != resource_paths[1]
                            or any(path not in expected for path in resource_paths)):
                        raise NativeSourceVerificationError(
                            "original animation frames lack bound Godot preview source"
                        )
                    resources = {
                        path: archive.read(path).decode("utf-8")
                        for path in resource_paths
                    }
                    try:
                        bound = verify_godot_sprite_resources(sprite, resources)
                    except SpriteResourceError as exc:
                        raise NativeSourceVerificationError(
                            "Godot SpriteFrames resource differs from authored frames"
                        ) from exc
                    if bound["receipt_sha256"] != item["godot_spriteframes_resource_sha256"]:
                        raise NativeSourceVerificationError(
                            "original source SpriteFrames resource hash differs"
                        )
                    from .studio_sprite_frame_cues import (
                        SpriteCueError, verify_godot_frame_cue_files,
                    )
                    cue_paths = [
                        "game/frontier/sprites/" + asset_name + suffix
                        for suffix in (".cues.gd", ".cues.json")
                    ]
                    cue_files = {
                        path: archive.read(path).decode("utf-8")
                        for path in cue_paths if path in expected
                    }
                    try:
                        cue_proof = verify_godot_frame_cue_files(sprite, cue_files)
                    except (SpriteCueError, ValueError, TypeError) as exc:
                        raise NativeSourceVerificationError(
                            "Godot frame cue sources differ from reviewed animation timeline"
                        ) from exc
                    if (cue_proof["receipt_sha256"]
                            != item["godot_frame_cue_resource_sha256"]
                            or (sprite.get("frame_cues") or {}).get("receipt_sha256")
                            != item["frame_cues_sha256"]):
                        raise NativeSourceVerificationError(
                            "original frame-cue signaling lineage differs"
                        )
            # Rebuild the FULL Godot game entrypoint from the trusted
            skins = proof.get("original_palette_variant_receipts", [])
            if not isinstance(skins, list) or len(skins) > 128:
                raise NativeSourceVerificationError("unbounded original game palette variants")
            if skins:
                from .studio_sprite_palette_variants import (
                    SpritePaletteVariantError, verify_original_palette_variant,
                )
                indexed = {item["asset_id"]: item for item in original_sprites}
                if len(indexed) != len(original_sprites):
                    raise NativeSourceVerificationError("duplicate original sprite names")
                checked: set[str] = set()
                for skin in skins:
                    if not isinstance(skin, dict):
                        raise NativeSourceVerificationError("palette proof is not a source object")
                    base_id, target_id = skin.get("base_asset_id"), skin.get("asset_id")
                    if (base_id not in indexed or target_id not in indexed
                            or target_id in checked or base_id == target_id):
                        raise NativeSourceVerificationError("unresolved original sprite skin")
                    checked.add(target_id)
                    if indexed[target_id]["source_record_id"] != skin.get("variant_source_record_id"):
                        raise NativeSourceVerificationError("palette skin source record mismatch")
                    original = {
                        "metadata": json.loads(archive.read(
                            "game/frontier/sprites/" + base_id + ".json")),
                        "png": archive.read("game/frontier/sprites/" + base_id + ".png"),
                    }
                    variant = {
                        "metadata": json.loads(archive.read(
                            "game/frontier/sprites/" + target_id + ".json")),
                        "png": archive.read("game/frontier/sprites/" + target_id + ".png"),
                    }
                    try:
                        verify_original_palette_variant(original, variant, skin)
                    except (SpritePaletteVariantError, KeyError, TypeError) as exc:
                        raise NativeSourceVerificationError(
                            "published Godot original color skin differs from source pixels"
                        ) from exc
            # exporter script, then replay exact player and NPC source edits.
            # Hashes alone cannot authorize injected script contents.
            from skeleton.jeeves.game_frontier_expedition_godot import _GODOT_SCRIPT
            from .studio_sprite_actor_binding import (
                SpriteBindingError, bind_sprite_to_expedition_script,
                verify_actor_sprite_binding,
            )
            from .studio_sprite_npc_binding import (
                NpcSpriteBindingError, bind_npc_sprites_to_expedition_script,
                verify_native_npc_binding_script, _npc_cast_names,
            )
            original_avatar = proof.get("authored_player_avatar_binding")
            actor_script_proof = proof.get("player_avatar_game_script_receipt")
            reconstructed = _GODOT_SCRIPT
            if original_avatar is None:
                if proof.get("original_player_audio_cue_routes_compiled") != 0:
                    raise NativeSourceVerificationError(
                        "unbound game claims generated live audio cue routes"
                    )
                if (actor_script_proof is not None
                        or proof.get("animated_sprite3d_player_script_compiled") is not False):
                    raise NativeSourceVerificationError(
                        "Godot archive claims a compiled actor visual without source"
                    )
            else:
                if (not isinstance(original_avatar, dict)
                        or not isinstance(actor_script_proof, dict)
                        or proof.get("animated_sprite3d_player_script_compiled") is not True):
                    raise NativeSourceVerificationError(
                        "player avatar lacks exact approved actor script proof"
                    )
                try:
                    player_script = bind_sprite_to_expedition_script(
                        reconstructed, original_avatar,
                    )
                    recomputed = verify_actor_sprite_binding(
                        reconstructed, player_script, original_avatar,
                    )
                except SpriteBindingError as exc:
                    raise NativeSourceVerificationError(
                        "player avatar game script deviates from compiled source"
                    ) from exc
                if recomputed != actor_script_proof:
                    raise NativeSourceVerificationError(
                        "player visual game script certificate differs"
                    )
                matches = [
                    sprite for sprite in original_sprites
                    if sprite["asset_id"] == original_avatar.get("asset_id")
                ]
                if (len(matches) != 1
                        or original_avatar.get("sprite_source_record_id")
                        != matches[0]["source_record_id"]
                        or original_avatar.get("animation")
                        not in matches[0]["animation_names"]):
                    raise NativeSourceVerificationError(
                        "real player sprite binding lost its source or animation"
                    )
                audio_routes = original_avatar.get("audio_cue_bindings", {})
                audio_heads = original_avatar.get("audio_source_sha256_by_event", {})
                if (type(audio_routes) is not dict
                        or type(audio_heads) is not dict
                        or set(audio_routes) != set(audio_heads)
                        or proof.get("original_player_audio_cue_routes_compiled")
                        != len(audio_routes)):
                    raise NativeSourceVerificationError(
                        "player audio frame-cue binding count or source claims differ"
                    )
                audio_catalog = {
                    sound["asset_id"]: sound for sound in original_audio
                }
                if len(audio_catalog) != len(original_audio):
                    raise NativeSourceVerificationError(
                        "player sound routes are ambiguous across original WAV assets"
                    )
                for cue_id, sound_id in audio_routes.items():
                    assigned = audio_catalog.get(sound_id)
                    if (assigned is None
                            or cue_id not in matches[0]["frame_cue_event_ids"]
                            or audio_heads[cue_id] != assigned["source_sha256"]):
                        raise NativeSourceVerificationError(
                            "player audio event lost original sprite or WAV source identity"
                        )
                reconstructed = player_script

            from .studio_sprite_direction import (
                SpriteDirectionError, compile_eight_way_actor_facing,
                verify_eight_way_actor_facing,
            )
            compass_receipt = proof.get("player_compass_godot_source_receipt")
            authored_compass = (
                original_avatar.get("directional_animations", {})
                if isinstance(original_avatar, dict) else {}
            )
            if not authored_compass:
                if (compass_receipt is not None
                        or proof.get("native_player_eight_way_facing_compiled") is not False):
                    raise NativeSourceVerificationError(
                        "Godot source falsely claims reviewed compass animation"
                    )
            else:
                if (not isinstance(compass_receipt, dict)
                        or proof.get("native_player_eight_way_facing_compiled") is not True):
                    raise NativeSourceVerificationError(
                        "source-bound player facing lacks independent certificate"
                    )
                try:
                    compass_script = compile_eight_way_actor_facing(
                        reconstructed, original_avatar,
                    )
                    reproduced = verify_eight_way_actor_facing(
                        reconstructed, compass_script, original_avatar,
                    )
                except SpriteDirectionError as exc:
                    raise NativeSourceVerificationError(
                        "native player facing script differs from source"
                    ) from exc
                if reproduced != compass_receipt:
                    raise NativeSourceVerificationError(
                        "original compass direction GDScript certificate differs"
                    )
                reconstructed = compass_script

            source_sensor = proof.get("player_collision_sensor_receipt")
            sensor_flag = proof.get("native_player_alpha_sensor_script_compiled")
            if original_avatar is None or original_avatar.get("collision_sensor") is not True:
                if source_sensor is not None or sensor_flag is not False:
                    raise NativeSourceVerificationError(
                        "a native collision sensor was claimed without authored permission"
                    )
                if any(name.endswith(".sensor.gd") for name in expected):
                    raise NativeSourceVerificationError(
                        "unapproved sprite collision script present in Godot game"
                    )
            else:
                if not isinstance(source_sensor, dict) or sensor_flag is not True:
                    raise NativeSourceVerificationError(
                        "source-approved player sensor lacks native shape proof"
                    )
                asset = original_avatar["asset_id"]
                sensor_file = "game/frontier/sprites/" + asset + ".sensor.gd"
                source_file = "game/frontier/sprites/" + asset + ".json"
                hitboxes_file = "game/frontier/sprites/" + asset + ".hitboxes.json"
                if (sensor_file not in expected
                        or source_file not in expected
                        or hitboxes_file not in expected
                        or [name for name in expected if name.endswith(".sensor.gd")]
                        != [sensor_file]):
                    raise NativeSourceVerificationError(
                        "original native player collision source files are incomplete"
                    )
                from .studio_sprite_native_sensor import (
                    SpriteSensorError, verify_sprite_sensor_source,
                )
                try:
                    reviewed_meta = json.loads(archive.read(source_file))
                    reviewed_masks = json.loads(archive.read(hitboxes_file))
                    compiled_script = archive.read(sensor_file).decode("utf-8")
                    verified_sensor = verify_sprite_sensor_source(
                        reviewed_meta, reviewed_masks, compiled_script,
                        source_sensor,
                    )
                except (SpriteSensorError, UnicodeDecodeError, ValueError, TypeError) as exc:
                    raise NativeSourceVerificationError(
                        "native collision sensor script differs from original masks"
                    ) from exc
                if verified_sensor != source_sensor:
                    raise NativeSourceVerificationError(
                        "published native collision source changed after review"
                    )

            npc_bindings = proof.get("authored_npc_sprite_bindings", [])
            npc_receipt = proof.get("npc_sprite_game_script_receipt")
            if (type(npc_bindings) is not list or len(npc_bindings) > 64):
                raise NativeSourceVerificationError(
                    "NPC visual source receipts exceed the reviewed cast limits"
                )
            if not npc_bindings:
                if (npc_receipt is not None
                        or proof.get("animated_npc_sprite3d_source_compiled") is not False):
                    raise NativeSourceVerificationError(
                        "game claims NPC sprite execution without original source"
                    )
            else:
                if (not isinstance(npc_receipt, dict)
                        or proof.get("animated_npc_sprite3d_source_compiled") is not True):
                    raise NativeSourceVerificationError(
                        "compiled NPC visuals lack independent game-script provenance"
                    )
                try:
                    source_cast = {
                        "game/frontier/npcs.json":
                        archive.read("game/frontier/npcs.json").decode("utf-8")
                    }
                    allowed_cast = _npc_cast_names(source_cast)
                    npc_script = bind_npc_sprites_to_expedition_script(
                        reconstructed, npc_bindings,
                    )
                    replay = verify_native_npc_binding_script(
                        reconstructed, npc_script, npc_bindings,
                    )
                except (NpcSpriteBindingError, UnicodeDecodeError, KeyError) as exc:
                    raise NativeSourceVerificationError(
                        "NPC game sprite source or cast cannot be reproduced"
                    ) from exc
                if replay != npc_receipt:
                    raise NativeSourceVerificationError(
                        "NPC native Godot script certificate differs"
                    )
                seen_npcs: set[str] = set()
                for npc in npc_bindings:
                    npc_id = npc.get("npc_id")
                    if npc_id not in allowed_cast or npc_id in seen_npcs:
                        raise NativeSourceVerificationError(
                            "NPC sprite source refers to duplicate or absent real character"
                        )
                    seen_npcs.add(npc_id)
                    matches = [
                        sprite for sprite in original_sprites
                        if sprite["asset_id"] == npc.get("asset_id")
                    ]
                    if (len(matches) != 1
                            or npc.get("sprite_source_record_id")
                            != matches[0]["source_record_id"]
                            or npc.get("sprite_png_sha256") != matches[0]["png_sha256"]
                            or npc.get("sprite_frames_resource_sha256")
                            != matches[0]["godot_spriteframes_resource_sha256"]
                            or npc.get("animation") not in matches[0]["animation_names"]):
                        raise NativeSourceVerificationError(
                            "NPC visual lost its original sprite or animation lineage"
                        )
                reconstructed = npc_script
            # Descriptor catalog must be regenerated from actual published
            # sprites/WAVs. Derivative skin lineage is bound by the palette
            # proof, not guessed from the compiler's generated metadata.
            variant_map = {
                item["asset_id"]: item
                for item in proof.get("original_palette_variant_receipts", [])
            }
            if len(variant_map) != len(proof.get("original_palette_variant_receipts", [])):
                raise NativeSourceVerificationError("duplicate palette provenance")
            for sprite in descriptor_sprites:
                evidence = variant_map.get(sprite["metadata"]["asset_id"])
                if evidence is not None:
                    sprite["palette_variant_receipt"] = evidence
            catalog_path = "game/frontier/assets/catalog.json"
            if catalog_path not in expected:
                raise NativeSourceVerificationError("compiled original assets lack catalog")
            try:
                raw_catalog = archive.read(catalog_path)
                catalog_proof = verify_asset_catalog(
                    raw_catalog, project_id=project_id,
                    source_head_sha256=source_head_sha256,
                    sprites=descriptor_sprites, sounds=descriptor_audio,
                    meshes=descriptor_meshes,
                )
                metadata_catalog = json.loads(raw_catalog)
                if (catalog_proof["catalog_sha256"]
                        != proof.get("asset_catalog_sha256")
                        or catalog_proof["descriptor_count"]
                        != proof.get("asset_descriptor_count")
                        or metadata_catalog.get("receipt_sha256")
                        != proof.get("asset_catalog_receipt_sha256")):
                    raise AssetDescriptorError(
                        "published asset catalog differs from game-build manifest"
                    )
            except (AssetDescriptorError, ValueError, KeyError, TypeError) as exc:
                raise NativeSourceVerificationError(
                    "original asset descriptors cannot be replayed from native bytes"
                ) from exc
            try:
                actual_script = archive.read("game/frontier/expedition.gd").decode("utf-8")
            except UnicodeDecodeError as exc:
                raise NativeSourceVerificationError("native game script is not UTF-8") from exc
            if actual_script != reconstructed:
                raise NativeSourceVerificationError(
                    "published native Godot player/NPC script differs from trusted source"
                )
    except (zipfile.BadZipFile, RuntimeError, OSError, UnicodeError) as exc:
        raise NativeSourceVerificationError("published Godot archive is unreadable") from exc
    return {
        "schema_version": "skeleton.jeeves.native_source_disk_verification.v1",
        "project_id": project_id,
        "source_head_sha256": source_head_sha256,
        "archive_sha256": expected_archive_sha256,
        "archive_bytes": size,
        "verified_file_count": len(expected),
        "asset_descriptor_count": catalog_proof["descriptor_count"],
        "asset_catalog_sha256": catalog_proof["catalog_sha256"],
        "original_glb_scenes_replayed": mesh_scene_proof["mesh_scenes_replayed"],
        "original_lod_levels_replayed": mesh_scene_proof["lod_levels_replayed"],
        "embedded_evidence_sha256": receipt_digest,
        "all_emitted_file_hashes_verified": True,
        "actual_godot_execution_verified": False,
    }


__all__ = ["NativeSourceVerificationError", "verify_published_godot_zip"]
