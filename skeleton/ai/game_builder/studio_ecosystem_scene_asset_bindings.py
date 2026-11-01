"""Original authored scene asset-to-recipe binding and production work orders.

This module resolves exact scene object and asset references to existing
original visual design recipes. It never invents meshes, textures, licensing,
runtime imports or delivery evidence. Bindings are operator-authored edits
and are source/session leased before an exclusive private publication.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
from typing import Any, Mapping

from .studio_ecosystem_canon_proof import audit_canon_source
from .studio_ecosystem_quest import StudioQuestError, compile_quest_program, replay_quest
from .studio_ecosystem_scene_schedule import _open_directory, _write_all

SCHEMA = "skeleton.game_builder.studio_scene_asset_binding.v1"
FILENAME = "scene_asset_bindings.json"
MAX_BINDINGS = 512
MAX_BYTES = 256 * 1024


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical scene asset binding") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def _lease(value: object, label: str) -> str:
    if type(value) is not str or len(value) != 64 or any(
            c not in "0123456789abcdef" for c in value):
        raise StudioQuestError("invalid " + label + " digest lease")
    return value


def _ident(value: object, label: str) -> str:
    if (type(value) is not str or not 1 <= len(value) <= 128
            or value != value.strip() or any(ord(c) < 32 for c in value)):
        raise StudioQuestError("invalid authored " + label)
    return value


def _visual_recipes(visual: object) -> dict[str, dict[str, Any]]:
    if type(visual) is not dict or visual.get("release_certified") is not False:
        raise StudioQuestError("invalid original visual source")
    jobs, recipes = visual.get("jobs"), visual.get("asset_recipes")
    if (bool(jobs) == bool(recipes)
            or type(jobs if jobs else recipes) is not list):
        raise StudioQuestError("visual source requires one original recipe inventory")
    source = jobs if jobs else recipes
    if not 1 <= len(source) <= 64:
        raise StudioQuestError("visual source recipe budget exceeded")
    found: dict[str, dict[str, Any]] = {}
    for record in source:
        if type(record) is not dict:
            raise StudioQuestError("invalid original visual recipe")
        key = _ident(record.get("id"), "visual recipe")
        if key in found:
            raise StudioQuestError("ambiguous duplicate original visual recipe")
        kind = record.get("kind", record.get("type"))
        _ident(kind, "visual recipe kind")
        description = record.get("recipe", record.get("description"))
        if type(description) is not str or not description.strip():
            raise StudioQuestError("original visual recipe has no authored description")
        found[key] = {
            "recipe_id": key, "kind": kind, "description_digest": _digest(description),
            "source_status": record.get("status", "design_only"),
            "native_asset_verified": False, "rights_verified": False,
        }
    return found


def _scene_refs(scenes: object) -> dict[str, dict[str, object]]:
    if type(scenes) is not list or not 1 <= len(scenes) <= 64:
        raise StudioQuestError("invalid authored scene inventory")
    result: dict[str, dict[str, object]] = {}
    for scene in scenes:
        if type(scene) is not dict:
            raise StudioQuestError("invalid authored scene record")
        sid = _ident(scene.get("id"), "scene ID")
        if sid in result:
            raise StudioQuestError("duplicate authored scene ID")
        refs: list[str] = []
        for field in ("assets", "interactive_objects"):
            raw = scene.get(field, [])
            if type(raw) is not list or len(raw) > 64:
                raise StudioQuestError("invalid authored scene asset references")
            refs.extend(_ident(item, "scene asset") for item in raw)
        if not refs or len(refs) != len(set(refs)):
            raise StudioQuestError("missing or duplicated scene asset reference")
        result[sid] = {"quest_stage": _ident(scene.get("quest_stage"), "quest stage"),
                       "refs": refs}
    return result


def compile_scene_asset_bindings(
    documents: Mapping[str, Any], actions: list[list[str]], assignments: object, *,
    authorized: bool, expected_source_digest: str,
    expected_visual_digest: str,
    expected_session_digest: str | None = None,
) -> dict[str, object]:
    """Verify all original scene references and produce exact source work orders."""
    if authorized is not True:
        raise PermissionError("original scene asset binding requires operator authorization")
    _lease(expected_source_digest, "scene asset source")
    _lease(expected_visual_digest, "visual recipe source")
    if expected_session_digest is not None:
        _lease(expected_session_digest, "scene asset session")
    if type(actions) is not list or len(actions) > 64 or len(_canonical(actions)) > 16384:
        raise StudioQuestError("invalid scene asset replay history")
    proof = audit_canon_source(documents, authorized=True)
    if not proof["canon_consistent"] or proof["source_digest"] != expected_source_digest:
        raise StudioQuestError("stale or contradictory scene asset source")
    visual = documents.get("visual")
    if type(visual) is not dict or _digest(visual) != expected_visual_digest:
        raise StudioQuestError("stale original visual recipe lease")
    recipes = _visual_recipes(visual)
    scenes = _scene_refs(documents.get("scene", {}).get("episode_plan"))
    program = compile_quest_program(documents)
    session = replay_quest(documents, actions, authorized=True)
    if expected_session_digest is not None and session.digest != expected_session_digest:
        raise StudioQuestError("stale scene asset quest session")
    if (type(assignments) is not dict or set(assignments) != set(scenes)
            or len(_canonical(assignments)) > 32768):
        raise StudioQuestError("scene asset binding must cover every original scene")
    by_stage = {stage.key: stage for stage in program.stages}
    work_orders: dict[str, dict[str, object]] = {}
    scene_cards: list[dict[str, object]] = []
    binding_count = 0
    completed = set(session.completed)
    for sid, scene in scenes.items():
        assigned = assignments[sid]
        if type(assigned) is not dict or set(assigned) != set(scene["refs"]):
            raise StudioQuestError("scene asset assignment has missing or forged references")
        stage = by_stage.get(scene["quest_stage"])
        if stage is None:
            raise StudioQuestError("scene asset assignment has unknown quest stage")
        cards: list[dict[str, object]] = []
        for asset_id in scene["refs"]:
            recipe_id = assigned[asset_id]
            if type(recipe_id) is not str or recipe_id not in recipes:
                raise StudioQuestError("scene asset assignment references unknown recipe")
            recipe = recipes[recipe_id]
            binding_count += 1
            if binding_count > MAX_BINDINGS:
                raise StudioQuestError("scene asset binding budget exceeded")
            card = {
                "asset_id": asset_id, "recipe_id": recipe_id,
                "recipe_kind": recipe["kind"],
                "recipe_description_digest": recipe["description_digest"],
                "source_recipe_status": recipe["source_status"],
                "native_asset_verified": False, "rights_verified": False,
            }
            card["binding_digest"] = _digest(card)
            cards.append(card)
            order = work_orders.setdefault(recipe_id, {
                "recipe_id": recipe_id, "recipe_kind": recipe["kind"],
                "description_digest": recipe["description_digest"],
                "referenced_by": [], "source_status": recipe["source_status"],
                "production_artifact_verified": False, "rights_verified": False,
            })
            order["referenced_by"].append({"scene_id": sid, "asset_id": asset_id})
        status = ("completed" if stage.key in completed else
                  "available" if set(stage.prerequisites).issubset(completed)
                  else "locked")
        scene_card = {
            "scene_id": sid, "quest_stage": stage.key,
            "quest_status": status, "asset_count": len(cards),
            "bindings": cards, "native_scene_binding_verified": False,
        }
        scene_card["scene_digest"] = _digest(scene_card)
        scene_cards.append(scene_card)
    for order in work_orders.values():
        order["work_order_digest"] = _digest(order)
    result: dict[str, object] = {
        "schema": SCHEMA, "project_id": program.project_id,
        "source_digest": proof["source_digest"],
        "visual_digest": expected_visual_digest,
        "quest_source_digest": program.source_digest,
        "session_digest": session.digest,
        "assignments": assignments, "assignments_digest": _digest(assignments),
        "scene_count": len(scene_cards), "binding_count": binding_count,
        "recipe_count": len(recipes), "used_recipe_count": len(work_orders),
        "unreferenced_recipe_ids": sorted(set(recipes) - set(work_orders)),
        "scenes": scene_cards,
        "production_work_orders": [work_orders[key] for key in sorted(work_orders)],
        "source_unchanged": True, "replay_verified": True,
        "file_write_performed": False, "native_asset_verified": False,
        "rights_verified": False, "release_certified": False,
    }
    if len(_canonical(result)) > MAX_BYTES:
        raise StudioQuestError("scene asset plan exceeds result budget")
    result["asset_binding_digest"] = _digest(result)
    return result


def publish_scene_asset_bindings(receipt: dict[str, Any], directory: Path, *,
                                 authorized: bool) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("scene asset publication requires operator authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid original asset binding receipt")
    digest = _lease(receipt.get("asset_binding_digest"), "asset binding")
    if _digest({k: v for k, v in receipt.items() if k != "asset_binding_digest"}) != digest:
        raise StudioQuestError("forged original asset binding receipt")
    raw = _canonical(receipt) + b"\n"
    if len(raw) > MAX_BYTES:
        raise StudioQuestError("scene asset publication exceeds byte budget")
    directory_fd = _open_directory(directory)
    temporary = ".scene-assets-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        output = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory_fd)
        created = True
        try:
            _write_all(output, raw)
            os.fsync(output)
        finally:
            os.close(output)
        os.link(temporary, FILENAME, src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd, follow_symlinks=False)
        os.fsync(directory_fd)
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=directory_fd)
        finally:
            os.close(directory_fd)
    return {"path": str(Path(directory) / FILENAME), "asset_binding_digest": digest,
            "bytes": len(raw), "file_write_performed": True,
            "native_asset_verified": False, "release_certified": False}


def verify_scene_asset_bindings(
    documents: Mapping[str, Any], actions: list[list[str]], directory: Path, *,
    authorized: bool, expected_source_digest: str, expected_visual_digest: str,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("asset binding restore requires operator authorization")
    directory_fd = _open_directory(directory)
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        try:
            import stat
            info = os.fstat(handle)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                raise StudioQuestError("invalid asset binding receipt file")
            raw = os.read(handle, MAX_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(directory_fd)
    if not raw or len(raw) > MAX_BYTES:
        raise StudioQuestError("invalid bounded asset binding receipt")
    try:
        def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            out: dict[str, Any] = {}
            for key, value in pairs:
                if key in out:
                    raise StudioQuestError("duplicate asset binding JSON key")
                out[key] = value
            return out
        stored = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                StudioQuestError("nonfinite asset binding receipt")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StudioQuestError("invalid asset binding receipt JSON") from exc
    if type(stored) is not dict:
        raise StudioQuestError("invalid asset binding receipt object")
    verified = compile_scene_asset_bindings(
        documents, actions, stored.get("assignments"), authorized=True,
        expected_source_digest=expected_source_digest,
        expected_visual_digest=expected_visual_digest,
        expected_session_digest=stored.get("session_digest"))
    if stored != verified:
        raise StudioQuestError("asset binding receipt fails canonical replay")
    return verified
