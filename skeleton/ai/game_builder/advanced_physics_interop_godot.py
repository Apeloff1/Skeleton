"""Executable Godot physics encounters bound to original genre scene and replay.

This exports a *native physics laboratory* inspired by an original reviewed
platformer, racing or sandbox scene. The original genre simulator is
authoritative in Python; the independent Godot runtime executes its physical
encounter rules only. No claim of native full-genre port or commercial release.
"""
from __future__ import annotations

from hashlib import sha256

from .advanced_godot_export import (
    AdvancedGodotExportError, NativeAdvancedGamePackage, _json,
)
from .advanced_physics_interop import (
    SUPPORTED,verify_physics_encounter,
)
from .advanced_physics_godot import render_physics_godot_package
from .advanced_gameplay_runtime import verify_advanced_session
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.native_interop_encounter.v1"

# GDScript is not permitted to infer impact or mint unearned source points:
# it verifies exact source custody then independently checks physics replay.
SOURCE_CHECK = '''
    if original.has("interop"):
        var linked_raw: String=FileAccess.get_file_as_string("res://origin.json")
        if linked_raw.is_empty() or linked_raw.length()>120000:
            _fault("missing or oversized signed original genre provenance")
            return
        var linked: Variant=JSON.parse_string(linked_raw)
        if typeof(linked)!=TYPE_DICTIONARY or (
            str(linked.get("schema",""))!="skeleton.game_builder.native_interop_encounter.v1"
            or str(linked.get("source_editor",""))!=str(original["interop"]["source_editor"])
            or str(linked.get("source_scene_digest",""))!=str(
                original["interop"]["source_scene_digest"])
            or str(linked.get("physics_session_digest",""))!=str(
                original["interop"]["physics_session_digest"])
            or str(linked.get("interop_digest",""))!=str(
                original["interop"]["interop_digest"])):
            _fault("independent original source custody mismatch")
            return
'''


def render_interop_godot_package(proof, source_session, source_settings=None,
                                 *, authorized=False):
    if not authorized:
        raise PermissionError("native cross-family original game export requires consent")
    if type(source_session) is not dict or source_session.get("editor") not in SUPPORTED:
        raise AdvancedGodotExportError("unknown or unreviewed original source family")
    if type(proof) is not dict or proof.get("source_editor")!=source_session["editor"]:
        raise AdvancedGodotExportError("cross-family physics proof source mismatch")
    settings=make_editor_document(source_session["editor"],source_settings)["settings"]
    try:
        verify_advanced_session(source_session,settings)
        verify_physics_encounter(proof,source_session,settings)
    except (ValueError,KeyError,TypeError) as exc:
        raise AdvancedGodotExportError("original genre or physics proof is not reconstructable") from exc
    # The reviewed physics instance is independently executed by GDScript:
    # native protection is only for this actual supported one-body AABB lab.
    physics=proof["physics_session"]
    physics_rules=proof["physics_settings"]
    native=render_physics_godot_package(physics,physics_rules,authorized=True)
    origin={
        "schema":SCHEMA,
        "source_editor":source_session["editor"],
        "source_scene_digest":proof["source_scene_digest"],
        "source_session_digest":proof["source_session_digest"],
        "source_head_digest":proof["source_head_digest"],
        "source_settings_digest":make_editor_document(
            source_session["editor"],source_settings)["digest"],
        "source_actions":list(source_session["actions"]),
        "interop_digest":proof["digest"],
        "physics_session_digest":physics["digest"],
        "physical_witnesses":proof["witnesses"],
        "actual_fixture_impacts":proof["observed_fixture_impacts"],
        "linked_game_result_included":False,
        "whole_original_genre_native":False,
        "hardware_certified":False,
        "auto_release":False,
    }
    binding={
        "source_editor":origin["source_editor"],
        "source_scene_digest":origin["source_scene_digest"],
        "physics_session_digest":origin["physics_session_digest"],
        "interop_digest":origin["interop_digest"],
    }
    from json import loads
    game=loads(native.files["godot/game.json"])
    game["interop"]=binding
    script=native.files["godot/scripts/main.gd"].decode("utf-8")
    anchor="    cfg = original[\"settings\"]"
    if anchor not in script:
        raise AdvancedGodotExportError("unsupported native physics source provenance hook")
    script=script.replace(anchor,SOURCE_CHECK+anchor,1)
    if script.count(SOURCE_CHECK.strip())!=1:
        raise AdvancedGodotExportError("native source provenance validation not installed")
    files={**native.files,
           "godot/game.json":_json(game),
           "godot/scripts/main.gd":script.encode("utf-8"),
           "godot/origin.json":_json(origin),
           "README.md":(
               "# Original "+source_session["editor"]+" Physics Encounter\n\n"
               "This project plays independently executed original Godot 4 "
               "physics only. The source game family is recorded and verified "
               "in source receipts, not silently replaced.\n"
               "Native command: godot --headless --path godot -- --verify-physics\n"
               "Original scene: "+proof["source_scene_digest"]+"\n"
               "Native content is unlicensed for automatic public release, "
               "and no native game-family/hardware parity is claimed.\n"
           ).encode("utf-8")}
    manifest={**native.manifest,
              "native_adapter":"godot4_original_genre_physics_encounter",
              "source_editor":source_session["editor"],
              "source_scene_digest":proof["source_scene_digest"],
              "source_session_digest":proof["source_session_digest"],
              "source_interop_digest":proof["digest"],
              "whole_original_genre_native":False,
              "godot_executed":False,"publish_approved":False,
              "files":{path:sha256(blob).hexdigest()
                       for path,blob in sorted(files.items())
                       if path!="release.json"}}
    files["release.json"]=_json(manifest)
    return NativeAdvancedGamePackage(files,manifest)


__all__=["SCHEMA","SOURCE_CHECK","render_interop_godot_package"]
