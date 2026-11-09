"""Console authoring composed through the existing governed project revision owner."""

from __future__ import annotations

import json
from typing import Any

from pymongo.errors import DuplicateKeyError

from core.game_learning import GameLearningError, _digest, _json, _key, _now, workspace


def profiles() -> list[dict[str, Any]]:
    from skeleton.jeeves.game_console_editor import console_editor_catalog

    return list(console_editor_catalog())


async def _prepare(scope, project_id, kind, body):
    operation_id = _key(project_id, kind, body["idempotency_key"])
    digest = _digest(body)
    existing = await workspace.revisions.find_one({"_id": operation_id, **scope})
    if existing is None:
        await workspace._project(project_id, scope)
        reserved = await workspace.projects.update_one(
            {
                "_id": project_id,
                **scope,
                "state": "active",
                "$or": [
                    {"_console_operation_count": {"$exists": False}},
                    {"_console_operation_count": {"$lt": 512}},
                ],
            },
            {"$inc": {"_console_operation_count": 1}},
        )
        if not reserved.modified_count:
            raise GameLearningError(
                "authoring_operation_limit", "Authoring operation budget is reached.", 413
            )
        receipt = await workspace._admit(scope, "game-console-operation", operation_id, len(_json(body)))
        try:
            await workspace.revisions.insert_one(
                {
                    "_id": operation_id,
                    **scope,
                    "project_id": project_id,
                    "kind": kind,
                    "request_digest": digest,
                    "_request": body,
                    "created_at": _now(),
                    "storage_receipt": receipt,
                }
            )
        except DuplicateKeyError:
            await workspace.projects.update_one(
                {"_id": project_id, **scope}, {"$inc": {"_console_operation_count": -1}}
            )
        existing = await workspace.revisions.find_one({"_id": operation_id, **scope})
    if existing is None or existing["request_digest"] != digest:
        raise GameLearningError("idempotency_conflict", "Authoring key binds different input.", 409)
    return existing


async def document(scope, project_id):
    from skeleton.jeeves.game_console_editor import ConsoleProject, console_profile, file_manifest_digest

    project = await workspace.get_project(scope, project_id)
    binding = await workspace._input(
        scope, await workspace._project(project_id, scope, project["version"]), require_execution=False
    )
    await workspace._authority(scope, binding)
    files = {item["path"]: item["content"] for item in project["files"]}
    authored = ConsoleProject.from_files(files, target_id=project["console_id"])
    return {
        "project": project,
        "document": authored.as_dict(),
        "scene_graph": authored.scene_graph.as_dict(),
        "native_graph_compatibility": authored.native_graph_compatibility(),
        "profile": console_profile(project["console_id"]).as_dict(),
        "manifest_digest": file_manifest_digest(files),
    }


async def _save_prepared(scope, operation, save_body):
    _json({"request": operation["_request"], "save_body": save_body})
    issued = await workspace.revisions.find_one_and_update(
        {"_id": operation["_id"], **scope, "_save_body": {"$exists": False}},
        {"$set": {"_save_body": save_body}},
    )
    # Another exact retry may have prepared the same operation concurrently.
    stored = await workspace.revisions.find_one({"_id": operation["_id"], **scope})
    if stored is None or _digest(stored["_save_body"]) != _digest(save_body):
        raise GameLearningError("operation_conflict", "Prepared authoring result changed.", 409)
    del issued
    await workspace.save_editor(scope, operation["project_id"], stored["_save_body"])


async def create(scope, body):
    from skeleton.jeeves.game_console_editor import console_profile, create_console_project
    from skeleton.jeeves.game_console_catalog import resolve_console

    target = resolve_console(body["target_id"])
    project_id = _key(scope["tenant_id"] + ":" + scope["owner_id"], "project", body["idempotency_key"])
    await workspace.create_project(
        scope,
        {"name": body["title"], "console_id": target.target_id, "idempotency_key": body["idempotency_key"]},
    )
    operation = await _prepare(scope, project_id, "console-create", body)
    save_body = operation.get("_save_body")
    if save_body is None:
        profile = console_profile(target.target_id).as_dict()
        native_files, source_handoff = {}, {
            "target_id": profile["target_id"],
            "status": "native_source_unavailable",
            "source_generation": False,
            "binary_compiled": False,
            "hardware_execution_verified": False,
        }
        if profile["available_capabilities"]["source_generation"]:
            from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
            from skeleton.ai.webcrawler.dragon_native_projects import render_native_project

            style = body.get("style_id", "arcade_score_attack")
            if style not in profile["toolchain_readiness"]["source_styles"]:
                raise GameLearningError(
                    "native_style_unavailable",
                    "This target has no source emitter for the selected style.",
                    409,
                )
            native = render_native_project(
                title=(
                    body["title"].strip()[:80] if len(body["title"].strip()) >= 2 else "Original console game"
                ),
                target_id=profile["target_id"],
                style=style,
                candidate_id=_digest(body),
                mechanics=(Mechanic.MOVEMENT, Mechanic.EXPLORATION),
                authorized=True,
            )
            native_files = {
                "game/generated/native/" + profile["target_id"] + "/" + path: text
                for path, text in native.files.items()
            }
            source_handoff.update(
                status=native.status,
                source_generation=True,
                source_digest=native.digest,
                style_id=style,
                toolchain=native.toolchain,
                supported_mechanics=list(native.supported_mechanics),
                deferred_mechanics=list(native.deferred_mechanics),
            )
        native_files["game/editor/source_handoff.json"] = _json(source_handoff).decode()
        authored = create_console_project(
            target.target_id,
            project_id=project_id,
            title=body["title"],
            seed=body.get("seed", 1),
            files=native_files,
        )
        files = authored.export_files()
        save_body = {
            "expected_version": 1,
            "idempotency_key": "console-create:" + operation["_id"],
            "files": [{"path": path, "content": text} for path, text in files.items()],
            "entrypoint": "game/editor/console.json",
        }
    await _save_prepared(scope, operation, save_body)
    return await document(scope, project_id)


async def edit(scope, project_id, body):
    from skeleton.jeeves.game_console_editor import apply_console_edits

    operation = await _prepare(scope, project_id, "console-edit", body)
    save_body = operation.get("_save_body")
    changes = operation.get("changes", [])
    validation = operation.get("validation", {})
    if save_body is None:
        project = await workspace._project(project_id, scope, body["expected_version"])
        if any(item["path"] == "game/successor/spec.json" for item in project["files"]):
            raise GameLearningError(
                "successor_world_active",
                "Edit the active successor through its world editor; the console scene is a separate inactive design.",
                409,
            )
        result = apply_console_edits(
            {item["path"]: item["content"] for item in project["files"]},
            target_id=project["console_id"],
            edits=body["edits"],
            expected_manifest_digest=body["expected_manifest_digest"],
            project_id=project_id,
        )
        changes, validation = list(result.changes), result.validation.as_dict()
        save_body = {
            "expected_version": body["expected_version"],
            "idempotency_key": "console-edit:" + operation["_id"],
            "files": [{"path": path, "content": text} for path, text in result.files.items()],
            "entrypoint": "game/editor/console.json",
        }
        await workspace.revisions.update_one(
            {"_id": operation["_id"], **scope}, {"$set": {"changes": changes, "validation": validation}}
        )
    await _save_prepared(scope, operation, save_body)
    return {**await document(scope, project_id), "changes": changes, "validation": validation}


async def handoff(scope, project_id):
    from skeleton.jeeves.game_console_editor import ConsoleProject, console_profile

    project = await workspace._project(project_id, scope)
    binding = await workspace._input(scope, project, require_execution=False)
    await workspace._authority(scope, binding)
    authored = ConsoleProject.from_files(
        {item["path"]: item["content"] for item in project["files"]}, target_id=project["console_id"]
    )
    return {
        "project_id": project_id,
        "project_version": project["version"],
        "source_digest": binding["tree_digest"],
        "target_id": project["console_id"],
        "build_handoff": authored.build_handoff(),
        "source_handoff": json.loads(
            next(
                (
                    item["content"]
                    for item in project["files"]
                    if item["path"] == "game/editor/source_handoff.json"
                ),
                "{}",
            )
        ),
        "toolchain": console_profile(project["console_id"]).as_dict()["toolchain_readiness"],
    }
