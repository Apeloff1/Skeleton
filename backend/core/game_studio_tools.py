"""Current application authority behind Jeeves' executable studio commands."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable, Mapping
from typing import Any

from core.game_learning import GameLearningError, _public, workspace
from skeleton.jeeves.game_studio_tools import OPERATIONS, StudioCommand, register_studio_tools


def _only(payload, allowed, *, required=()):
    if set(payload) - set(allowed) or set(required) - set(payload):
        raise GameLearningError(
            "studio_payload_invalid", "Studio command fields do not match this operation.", 422
        )


def _id(payload, name):
    value = payload.get(name)
    if not isinstance(value, str) or not 1 <= len(value) <= 128 or value != value.strip():
        raise GameLearningError(
            "studio_identity_required", "Studio operation requires its exact record identity.", 422
        )
    return value


def _page(payload):
    _only(payload, ("offset", "limit"))
    offset, limit = payload.get("offset", 0), payload.get("limit", 16)
    if type(offset) is not int or not 0 <= offset <= 100000 or type(limit) is not int or not 1 <= limit <= 32:
        raise GameLearningError(
            "studio_page_invalid", "Studio evidence pages are limited to 32 records.", 422
        )
    return offset, limit


def _model(model, payload):
    return model.model_validate(dict(payload)).model_dump(exclude_none=True)


def _project_summary(project):
    files = project.get("files", [])
    return {key: value for key, value in project.items() if key != "files"} | {
        "file_manifest": [
            {
                "path": item["path"],
                "utf8_bytes": len(item["content"].encode()),
                "sha256": hashlib.sha256(item["content"].encode()).hexdigest(),
            }
            for item in files
        ]
    }


def _mutation_receipt(value):
    """Keep successful mutation receipts usable without copying full frames/traces."""
    if not isinstance(value, dict):
        return value
    omitted = {"snapshot", "last_frame", "latest_frame", "transitions", "files", "policy_snapshot"}
    result = {key: item for key, item in value.items() if key not in omitted}
    for field in ("last_frame", "latest_frame"):
        frame = value.get(field)
        if isinstance(frame, dict):
            result["frame_receipt"] = {
                key: frame[key]
                for key in (
                    "runtime_kind",
                    "render_kind",
                    "width",
                    "height",
                    "pixel_digest",
                    "source_pixel_digest",
                    "native_runs",
                    "video_callbacks",
                    "core_id",
                    "content_digest",
                )
                if key in frame
            }
    transitions = value.get("transitions")
    if isinstance(transitions, list):
        from core.game_learning import _digest

        result["transition_count"] = len(transitions)
        result["transitions_digest"] = _digest(transitions)
    return result


async def execute_studio_command(scope: Mapping[str, str], command: StudioCommand) -> Any:
    """Every branch delegates scoped real owners; no user shell or authority flags."""
    if not isinstance(command, StudioCommand):
        raise TypeError("A typed studio command is required")
    scope = workspace._scope(scope["tenant_id"], scope["owner_id"])
    project = await workspace._project(command.project_id, scope)
    binding = await workspace._input(scope, project, require_execution=False)
    await workspace._authority(scope, binding)
    operation, payload = command.operation, dict(command.payload)
    if operation == "catalog":
        offset, limit = _page(payload)
        from core.game_console_studio import profiles
        from skeleton.jeeves.game_studio_tools import studio_command_catalog

        rows = profiles()
        return {
            **studio_command_catalog(),
            "profiles": rows[offset : offset + limit],
            "total_profiles": len(rows),
            "offset": offset,
        }
    if operation == "project.inspect":
        _only(payload, ("path",))
        result = _project_summary(_public(project))
        if "path" in payload:
            name = payload["path"]
            if not isinstance(name, str) or len(name) > 256:
                raise GameLearningError("studio_path_invalid", "Select an exact project file path.", 422)
            source = next((item for item in project["files"] if item["path"] == name), None)
            if source is None:
                raise GameLearningError(
                    "studio_file_absent", "This file does not belong to the current project.", 404
                )
            if len(source["content"].encode()) > 128000:
                raise GameLearningError(
                    "studio_file_large",
                    "Use the bounded visual editor for this large authoring document.",
                    422,
                )
            result["selected_file"] = source
        return result
    if operation == "source.inspect":
        _only(payload, ("source_id",), required=("source_id",))
        identifier = _id(payload, "source_id")
        source = await workspace.sources.find_one(
            {"_id": identifier, **scope, "project_id": command.project_id}
        )
        if source is None:
            raise GameLearningError("studio_source_absent", "Source does not belong to this project.", 404)
        source_binding = await workspace._input(scope, project, source_id=identifier, require_execution=False)
        await workspace._authority(scope, source_binding)
        return {
            key: source[key]
            for key in (
                "source_id",
                "kind",
                "digest",
                "filename",
                "metadata",
                "provenance",
                "status",
                "bundle_digest",
                "version",
            )
            if key in source
        }
    if operation.startswith("console."):
        from core import game_console_studio as console

        if operation == "console.inspect":
            _only(payload, ("section",))
            result = await console.document(scope, command.project_id)
            document = result["document"]
            section = payload.get("section")
            if section is not None and (not isinstance(section, str) or section not in document):
                raise GameLearningError(
                    "studio_section_unknown", "Select a current console authoring section.", 422
                )
            return {
                "project": _project_summary(result["project"]),
                "profile": result["profile"],
                "manifest_digest": result["manifest_digest"],
                "document": (
                    {section: document[section]}
                    if section
                    else {
                        key: value
                        for key, value in document.items()
                        if key not in {"tiles", "maps", "source_files"}
                    }
                ),
            }
        if operation == "console.handoff":
            _only(payload, ())
            return await console.handoff(scope, command.project_id)
        from routes.game_console_studio import EditConsoleProject

        result = await console.edit(scope, command.project_id, _model(EditConsoleProject, payload))
        return {
            "project": _project_summary(result["project"]),
            "manifest_digest": result["manifest_digest"],
            "changes": result["changes"],
            "validation": result["validation"],
        }
    if operation == "world.edit":
        from core.game_successor import edit_world
        from routes.game_successor import WorldRequest

        result = await edit_world(scope, command.project_id, _model(WorldRequest, payload))
        return {key: value for key, value in result.items() if key != "project"} | {
            "project": _project_summary(result["project"])
        }
    if operation == "successor.inspect":
        from core.game_successor import candidate

        _only(payload, ("candidate_id",), required=("candidate_id",))
        value = await candidate(scope, _id(payload, "candidate_id"))
        if value["project_id"] != command.project_id:
            raise GameLearningError("studio_project_mismatch", "Candidate belongs to another project.", 403)
        return {key: value for key, value in value.items() if key not in {"files", "source_files"}}
    if operation in {"job.inspect", "play.inspect", "play.input", "play.control"}:
        field = "job_id" if operation == "job.inspect" else "play_id"
        identifier = _id(payload, field)
        if operation == "job.inspect":
            _only(payload, (field,), required=(field,))
            result = await workspace.get_job(scope, identifier)
        else:
            from routes.game_learning import PlayInput, PlayControl, _play

            owner = _play()
            result = await owner.get(scope, identifier)
            if result.get("project_id") != command.project_id:
                raise GameLearningError(
                    "studio_project_mismatch", "Play session belongs to another project.", 403
                )
            if operation == "play.inspect":
                _only(payload, (field,), required=(field,))
            else:
                body = {key: value for key, value in payload.items() if key != field}
                result = await (
                    owner.input(scope, identifier, _model(PlayInput, body))
                    if operation == "play.input"
                    else owner.control(scope, identifier, _model(PlayControl, body))
                )
        if result.get("project_id") != command.project_id:
            raise GameLearningError(
                "studio_project_mismatch", "Operation record belongs to another project.", 403
            )
        return _mutation_receipt(result)
    if operation == "play.start":
        from routes.game_learning import PlayRequest, _play

        return _mutation_receipt(
            await _play().create(scope, command.project_id, _model(PlayRequest, payload))
        )
    if operation == "simulate":
        from routes.game_learning import SimulationRequest

        return _mutation_receipt(
            await workspace.simulate(scope, command.project_id, _model(SimulationRequest, payload))
        )
    if operation in {"build", "train", "successor.synthesize", "desktop.build"}:
        if operation == "build":
            from routes.game_console_build import ConsoleBuildBody as model

            kind = "build"
        elif operation == "train":
            from routes.game_learning import TrainRequest as model

            kind = "train"
        elif operation == "successor.synthesize":
            from routes.game_successor import SynthesisRequest as model

            kind = "successor"
        else:
            from routes.game_successor import DesktopRequest as model

            kind = "desktop"
        body = _model(model, payload)
        return await workspace.start_job(scope, command.project_id, kind, body)
    if operation == "successor.compare":
        from core.game_successor import candidate
        from routes.game_successor import CompareRequest

        identifier = _id(payload, "candidate_id")
        row = await candidate(scope, identifier)
        if row["project_id"] != command.project_id:
            raise GameLearningError("studio_project_mismatch", "Candidate belongs to another project.", 403)
        body = _model(CompareRequest, {key: value for key, value in payload.items() if key != "candidate_id"})
        return await workspace.start_job(
            scope, command.project_id, "successor_compare", {**body, "candidate_id": identifier}
        )
    if operation.startswith("campaign.") or operation == "lessons.search":
        from core import game_studio_learning as learning

        return await learning.execute_command(scope, command)
    raise GameLearningError("studio_operation_unknown", "This operation is unavailable.", 422)


def studio_agent_user_id(scope: Mapping[str, str]) -> str:
    """Canonical agent ID for a server-authenticated tenant/owner pair."""
    from core.game_learning import _digest

    admitted = workspace._scope(scope["tenant_id"], scope["owner_id"])
    return "studio-user-" + _digest(admitted)[:48]


def register_application_studio_tools(
    registry,
    *,
    scope: Mapping[str, str],
    project_ids: tuple[str, ...],
    loop: asyncio.AbstractEventLoop,
    authorize: Callable,
):
    """Inject request-scoped studio owners into an existing Jeeves registry.

    The exact-command host authorizer is required. Run the synchronous tool
    executor off the application's loop; database work stays on its owning loop.
    """
    scope = workspace._scope(scope["tenant_id"], scope["owner_id"])
    if (
        not isinstance(project_ids, tuple)
        or not 1 <= len(project_ids) <= 64
        or any(not isinstance(value, str) or not 1 <= len(value) <= 128 for value in project_ids)
    ):
        raise ValueError("Studio agent requires a bounded server-approved project allowlist")
    if not callable(authorize) or not isinstance(loop, asyncio.AbstractEventLoop):
        raise TypeError("Studio host authorizer and owning event loop are required")
    allowed = frozenset(project_ids)

    def permitted(command, context):
        return (
            context.user_id == studio_agent_user_id(scope)
            and command.project_id in allowed
            and authorize(command, context) is True
        )

    def dispatch(command, _context):
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            raise RuntimeError("Execute synchronous agent tools in the agent worker, not the database loop")
        future = asyncio.run_coroutine_threadsafe(execute_studio_command(scope, command), loop)
        try:
            from fastapi.encoders import jsonable_encoder

            return jsonable_encoder(future.result(timeout=24))
        except TimeoutError:
            future.cancel()
            raise

    return register_studio_tools(
        registry, handlers={name: dispatch for name in OPERATIONS}, authorize=permitted
    )
