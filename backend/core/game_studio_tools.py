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
    value = model.model_validate(dict(payload))
    admitted = getattr(value, "admitted_request", None)
    return admitted() if callable(admitted) else value.model_dump(exclude_none=True)


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
    omitted = {
        "snapshot",
        "last_frame",
        "latest_frame",
        "transitions",
        "files",
        "policy_snapshot",
        "control_token",
    }
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


def _authoring_summary(row, *, inventory=False):
    if not isinstance(row, dict):
        return row
    result = {}
    for key, value in row.items():
        if key in {"cells", "tiles", "data_base64", "source_files"}:
            result[key + "_count"] = len(value) if isinstance(value, (list, dict, str)) else None
        elif inventory and isinstance(value, list):
            result[key + "_count"] = len(value)
            result[key + "_ids"] = [
                item["id"] for item in value[:256] if isinstance(item, dict) and "id" in item
            ]
        else:
            result[key] = value
    return result


def _world_projection(value, payload):
    """Expose exact authoring identities and small pages, never generated code."""
    _only(payload, ("section", "record_id", "field", "offset", "limit"))
    offset, limit = _page({key: payload[key] for key in ("offset", "limit") if key in payload})
    spec = value["spec"]
    section = payload.get("section")
    sections = {key: spec[key] for key in value["editable_sections"] if key in spec}
    sections.update({"world." + key: item for key, item in spec["world"].items()})
    sections.update({"mechanics." + key: item for key, item in spec["mechanics"].items()})
    for parent, item in list(sections.items()):
        if isinstance(item, dict):
            sections.update(
                {parent + "." + key: child for key, child in item.items() if isinstance(child, list)}
            )
    result = {
        "project": _project_summary(value["project"]),
        "spec_digest": value["spec_digest"],
        "environment": value["environment"],
        "sections": sorted(sections),
        "editable_sections": value["editable_sections"],
    }
    if section is None:
        if "record_id" in payload or "field" in payload:
            raise GameLearningError(
                "studio_section_required", "Select a world section before its record or field.", 422
            )
        result["spec"] = {
            key: item
            for key, item in spec.items()
            if key not in {"world", "assets", "sprite_atlas", "source_files"}
        }
        result["world"] = {
            key: ({"count": len(item)} if isinstance(item, list) else item)
            for key, item in spec["world"].items()
        }
        return result
    if not isinstance(section, str) or section not in sections:
        raise GameLearningError(
            "studio_section_unknown", "Select an exact saved world or mechanic section.", 422
        )
    selected = sections[section]
    if "record_id" in payload:
        identifier = _id(payload, "record_id")
        selected = (
            next((row for row in selected if isinstance(row, dict) and row.get("id") == identifier), None)
            if isinstance(selected, list)
            else None
        )
        if selected is None:
            raise GameLearningError("studio_record_absent", "The requested world record is unavailable.", 404)
    if "field" in payload:
        field = payload["field"]
        if not isinstance(selected, dict) or not isinstance(field, str) or field not in selected:
            raise GameLearningError(
                "studio_field_absent", "Select an existing field of the inspected record.", 404
            )
        selected = selected[field]
    if isinstance(selected, list):
        result["selected"] = {
            "rows": selected[offset : offset + limit],
            "total": len(selected),
            "offset": offset,
            "limit": limit,
        }
    elif isinstance(selected, str):
        result["selected"] = {
            "text": selected[offset : offset + 1500],
            "total_characters": len(selected),
            "offset": offset,
            "sha256": hashlib.sha256(selected.encode()).hexdigest(),
        }
    elif isinstance(selected, dict):
        result["selected"] = {
            key: (
                {"count": len(item), "inspect_section": section + "." + key}
                if isinstance(item, list)
                else item
            )
            for key, item in selected.items()
        }
    else:
        result["selected"] = selected
    return result


async def execute_studio_command(scope: Mapping[str, str], command: StudioCommand) -> Any:
    """Every branch delegates scoped real owners; no user shell or authority flags."""
    if not isinstance(command, StudioCommand):
        raise TypeError("A typed studio command is required")
    scope = workspace._scope(scope["tenant_id"], scope["owner_id"])
    project = await workspace._project(command.project_id, scope)
    operation, payload = command.operation, dict(command.payload)
    # Stopping owned issued work remains possible after its source is withdrawn.
    if operation not in {"job.cancel", "play.stop", "campaign.pause", "campaign.cancel"}:
        binding = await workspace._input(scope, project, require_execution=False)
        await workspace._authority(scope, binding)
    if operation.startswith("game.studio.curriculum.") or operation == "game.studio.book.manifest":
        # Existing game-learning project and source authority were checked
        # above; this is a real Jeeves tool surface, not an independent
        # model runtime, queue, provider or persistence owner.
        from skeleton.jeeves import game_frontier_book_curriculum as books
        from skeleton.forge.game_frontier_studio import StudioError
        from core import game_frontier_authoring as forge_author

        if operation in {"game.studio.curriculum.path", "game.studio.curriculum.worklist"}:
            from skeleton.jeeves.game_frontier_curriculum_path import (
                learning_path, batch_program,
            )
            _only(payload, ("generation", "index", "sessions", "stride"),
                  required=("generation", "index"))
            if operation == "game.studio.curriculum.path":
                _only(payload, ("generation", "index"),
                      required=("generation", "index"))
                return learning_path(payload["generation"], payload["index"])
            return batch_program(payload["generation"], payload["index"],
                                 sessions=payload.get("sessions", 8),
                                 stride=payload.get("stride", 1))
        if operation == "game.studio.curriculum.catalog":
            _only(payload, ())
            return books.curriculum_catalog()
        if operation in {"game.studio.curriculum.reference", "game.studio.curriculum.lesson",
                         "game.studio.book.manifest"}:
            _only(payload, ("generation", "index"), required=("generation", "index"))
            if operation == "game.studio.curriculum.reference":
                return books.reference(payload["generation"], payload["index"])
            if operation == "game.studio.curriculum.lesson":
                return books.lesson(payload["generation"], payload["index"])
            # The actual Markdown plus verifiable SHA is returned. Physical
            # download is offered separately by the authenticated API.
            return books.manifest(payload["generation"], payload["index"])
        if operation == "game.studio.curriculum.assess":
            _only(payload, ("generation", "index", "answers"),
                  required=("generation", "index", "answers"))
            return books.assessment(payload["generation"], payload["index"],
                                    payload["answers"])
        if operation in {
            "game.studio.curriculum.automation.plan",
            "game.studio.curriculum.automation.preview",
            "game.studio.curriculum.automation.commit",
            "game.studio.curriculum.practice",
        }:
            fields = ("books", "parameters", "expected_revision", "expected_sha256",
                      "idempotency_key", "approved_candidate_sha256")
            if operation == "game.studio.curriculum.practice":
                _only(payload, fields, required=("books", "parameters",
                                                "expected_revision", "expected_sha256"))
            elif operation == "game.studio.curriculum.automation.plan":
                _only(payload, fields[:2], required=fields[:2])
            elif operation == "game.studio.curriculum.automation.preview":
                _only(payload, fields, required=fields[:4])
            else:
                _only(payload, fields, required=fields)
            requested = payload["books"]
            if type(requested) is not list or not 1 <= len(requested) <= 4:
                raise StudioError("Jeeves automation requires 1..4 exact books per action")
            chosen = []
            seen = set()
            for item in requested:
                if type(item) is not dict or set(item) != {"generation", "index"}:
                    raise StudioError("Jeeves source book reference must be exact")
                generation, index = item["generation"], item["index"]
                book = books.reference(generation, index)
                if book["ref"] in seen:
                    raise StudioError("Duplicated book source in one automated edit")
                seen.add(book["ref"])
                chosen.append((book, books.exemplar(generation, index)))
            params = payload["parameters"]
            if (type(params) is not dict or len(params) > 32
                    or not all(type(v) is str for v in params.keys())):
                raise StudioError("Training source parameters must be bounded typed map")
            # Each book gives one real exact operation; generation is never
            # inferred from a free-text LLM response or trusted shell code.
            steps = [{"action": action, "parameters": dict(params)} for _, action in chosen]
            doc = await forge_author.document(scope, command.project_id)
            approved = {
                "expected_version": doc["expected_version"],
                "expected_sha256": doc["source_sha256"],
                "idempotency_key": payload.get("idempotency_key", "jeeves-book-preview"),
                "steps": steps,
            }
            if operation == "game.studio.curriculum.automation.plan":
                return {
                    "schema": "skeleton.jeeves.forge_automation_plan.v1",
                    "project_id": command.project_id,
                    "source_sha256": doc["source_sha256"],
                    "expected_revision": doc["expected_version"],
                    "books": [book["ref"] for book, _ in chosen],
                    "operations": [action for _, action in chosen],
                    "planned_steps": len(steps),
                    "approved": False, "persisted": False,
                    "needs_explicit_preview": True,
                    "needs_operator_commit_approval": True,
                    "neural_training_complete": False,
                }
            if (type(payload["expected_revision"]) is not int
                    or doc["expected_version"] != payload["expected_revision"]
                    or doc["source_sha256"] != payload["expected_sha256"]):
                raise StudioError("Source changed since approved Jeeves curriculum plan")
            proof = await forge_author.edit(
                scope, command.project_id, approved, preview=True)
            candidate = proof["candidate_sha256"]
            base = {
                "schema": "skeleton.jeeves.forge_practical_training.v1",
                "source_sha256": doc["source_sha256"],
                "candidate_sha256": candidate,
                "books": [book["ref"] for book, _ in chosen],
                "operations": [action for _, action in chosen],
                "batch_receipt": proof["batch_receipt"],
                "measured_changed": candidate != doc["source_sha256"],
                "native_executed": False, "trained_weights": False,
                "candidate_only": True,
            }
            if operation != "game.studio.curriculum.automation.commit":
                return {**base, "persisted": False,
                        "requires_explicit_operator_approval": True}
            if (type(payload["approved_candidate_sha256"]) is not str
                    or payload["approved_candidate_sha256"] != candidate
                    or not base["measured_changed"]
                    or type(payload["idempotency_key"]) is not str
                    or not payload["idempotency_key"]):
                raise StudioError("Jeeves may not commit without approved exact preview hash")
            actual = await forge_author.edit(
                scope, command.project_id, approved, preview=False)
            if (actual.get("source_sha256") != candidate
                    or actual.get("persisted") is not True):
                raise StudioError("Host did not commit the exact verified Jeeves source")
            return {**base,
                    "schema": "skeleton.jeeves.forge_automation_committed.v1",
                    "candidate_only": False, "persisted": True,
                    "saved_source_sha256": actual["source_sha256"],
                    "saved_revision": actual["expected_version"],
                    "requires_separate_native_qualification": True}

    if operation.startswith("game.studio.author."):
        # Real Forge editor operations use the canonical authenticated project
        # workspace. No model-injected database, project owner or file path.
        from core import game_frontier_authoring as forge_author
        if operation == "game.studio.author.inspect":
            _only(payload, ())
            return await forge_author.document(scope, command.project_id)
        if operation == "game.studio.author.copy":
            _only(payload, ("layer", "x", "y", "width", "height"),
                  required=("layer", "x", "y", "width", "height"))
            return await forge_author.copy_tiles(
                scope, command.project_id, **payload)
        if operation in {"game.studio.author.preview", "game.studio.author.edit"}:
            writer = operation.endswith(".edit")
            allowed = ("expected_revision", "expected_sha256", "steps", "idempotency_key")
            _only(payload, allowed, required=allowed if writer else allowed[:-1])
            command_body = {
                "expected_version": payload["expected_revision"],
                "expected_sha256": payload["expected_sha256"],
                "steps": payload["steps"],
                "idempotency_key": payload.get("idempotency_key", "preview-only"),
            }
            return await forge_author.edit(
                scope, command.project_id, command_body, preview=not writer)
        if operation == "game.studio.author.compile":
            _only(payload, ())
            return await forge_author.document(scope, command.project_id)
        if operation == "game.studio.author.game":
            _only(payload, ("seed", "islands"))
            return await forge_author.compile_game(
                scope, command.project_id,
                seed=payload.get("seed", 42),
                islands=payload.get("islands", 12),
                include_godot=False,
            )
        if operation == "game.studio.author.gameplay":
            _only(payload, ("position_xyz_m", "mass_kg", "now_ms",
                            "current_signals", "previous_signals", "flags"),
                  required=("position_xyz_m",))
            return await forge_author.simulate_gameplay(
                scope, command.project_id, {
                    "position_xyz_m": payload["position_xyz_m"],
                    "mass_kg": payload.get("mass_kg", 75.0),
                    "now_ms": payload.get("now_ms", 0),
                    "current_signals": payload.get("current_signals", {}),
                    "previous_signals": payload.get("previous_signals", {}),
                    "flags": payload.get("flags", {}),
                })
        if operation == "game.studio.author.export":
            required = ("expected_revision", "expected_sha256", "idempotency_key")
            _only(payload, (*required, "seed", "islands"), required=required)
            return await forge_author.export_native_project(
                scope, command.project_id, {
                    "expected_version": payload["expected_revision"],
                    "expected_sha256": payload["expected_sha256"],
                    "idempotency_key": payload["idempotency_key"],
                    "seed": payload.get("seed", 42),
                    "islands": payload.get("islands", 12),
                })
        raise GameLearningError("studio_operation_unknown",
                                "Unknown original Forge Studio authoring action.", 422)
    if operation in {"job.resume", "job.cancel"}:
        identifier = _id(payload, "job_id")
        _only(payload, ("job_id",), required=("job_id",))
        issued = await workspace.jobs.find_one({"_id": identifier, **scope, "project_id": command.project_id})
        if issued is None or identifier not in project["job_ids"]:
            raise GameLearningError(
                "studio_job_absent", "This issued job does not belong to this project.", 404
            )
        return await (
            workspace.resume_job(scope, identifier)
            if operation == "job.resume"
            else workspace.cancel_job(scope, identifier)
        )
    if operation in {"play.resume", "play.stop"}:
        from routes.game_learning import PlayControl, _plays

        identifier = _id(payload, "play_id")
        _only(
            payload, ("play_id", "expected_control_version"), required=("play_id", "expected_control_version")
        )
        owner = _plays()
        issued = await owner.plays.find_one({"_id": identifier, **scope, "project_id": command.project_id})
        if issued is None or identifier not in project.get("play_ids", []):
            raise GameLearningError(
                "studio_play_absent", "This issued play does not belong to this project.", 404
            )
        return _mutation_receipt(
            await owner.control(
                scope,
                identifier,
                _model(
                    PlayControl,
                    {
                        "expected_control_version": payload["expected_control_version"],
                        "action": "resume" if operation == "play.resume" else "stop",
                    },
                ),
            )
        )
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
        _only(payload, ("path", "offset", "limit"))
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
            offset, limit = payload.get("offset", 0), payload.get("limit", 1500)
            if (
                type(offset) is not int
                or not 0 <= offset <= len(source["content"])
                or type(limit) is not int
                or not 1 <= limit <= 1500
            ):
                raise GameLearningError(
                    "studio_file_page_invalid",
                    "Source inspection pages contain at most1500Unicodecharacters.",
                    422,
                )
            result["selected_file"] = {
                **source,
                "content": source["content"][offset : offset + limit],
                "offset": offset,
                "limit": limit,
                "total_characters": len(source["content"]),
                "sha256": hashlib.sha256(source["content"].encode()).hexdigest(),
            }
        elif "offset" in payload or "limit" in payload:
            raise GameLearningError(
                "studio_path_required", "Select an exact file before paging source text.", 422
            )
        return result
    if operation == "build.inspect":
        from core.game_console_build import inspect_build_plan
        from routes.game_console_build import ConsoleBuildPlanBody

        return await inspect_build_plan(scope, command.project_id, _model(ConsoleBuildPlanBody, payload))
    if operation == "project.export":
        from core.game_console_build import prepare_project_export

        _only(payload, ("expected_version",), required=("expected_version",))
        if type(payload["expected_version"]) is not int or payload["expected_version"] < 1:
            raise GameLearningError(
                "studio_version_invalid", "Select the exact current project version.", 422
            )
        return await prepare_project_export(scope, command.project_id, payload["expected_version"])
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
        projection = {
            key: source[key]
            for key in (
                "source_id",
                "kind",
                "source_digest",
                "authority_epoch",
                "state",
                "filename",
                "metadata",
                "version",
            )
            if key in source
        }
        bundle = workspace._source_bundle(scope, source).to_dict()
        projection["bundle_digest"] = bundle["bundle_digest"]
        projection["provenance"] = bundle["provenance"]
        return projection
    if operation == "knowledge.search":
        from core.dragon_runtime import reviewed_scope_from_workspace, search_reviewed_references

        _only(payload, ("query", "limit"), required=("query",))
        query, limit = payload["query"], payload.get("limit", 8)
        if (
            not isinstance(query, str)
            or not query.strip()
            or len(query) > 300
            or type(limit) is not int
            or not 1 <= limit <= 8
        ):
            raise GameLearningError(
                "studio_knowledge_query",
                "Select a bounded design query and at most 8 reviewed references.",
                422,
            )
        return await search_reviewed_references(reviewed_scope_from_workspace(scope), query, limit=limit)
    if operation == "knowledge.practice":
        from core.dragon_runtime import inspect_reference_practice, reviewed_scope_from_workspace

        _only(payload, ("candidate_id", "practice_id"), required=("candidate_id", "practice_id"))
        return await inspect_reference_practice(
            reviewed_scope_from_workspace(scope), _id(payload, "candidate_id"), _id(payload, "practice_id")
        )
    if operation.startswith("console."):
        from core import game_console_studio as console

        if operation == "console.inspect":
            _only(payload, ("section", "record_id", "field", "offset", "limit"))
            result = await console.document(scope, command.project_id)
            document = result["document"]
            section = payload.get("section")
            graph = result.get("scene_graph", {})
            sections = {**document, "scene_graph": graph}
            sections.update({"scene_graph." + key: value for key, value in graph.items()})
            if section is not None and (not isinstance(section, str) or section not in sections):
                raise GameLearningError(
                    "studio_section_unknown", "Select a current console authoring section.", 422
                )
            offset, limit = _page({key: payload[key] for key in ("offset", "limit") if key in payload})
            selected = None
            if section is not None:
                selected = sections[section]
                if "record_id" in payload:
                    identifier = _id(payload, "record_id")
                    selected = (
                        next(
                            (
                                row
                                for row in selected
                                if isinstance(row, dict) and row.get("id") == identifier
                            ),
                            None,
                        )
                        if isinstance(selected, list)
                        else None
                    )
                    if selected is None:
                        raise GameLearningError(
                            "studio_record_absent", "Select an exact record in the requested section.", 404
                        )
                if "field" in payload:
                    field = payload["field"]
                    if not isinstance(field, str) or not isinstance(selected, dict) or field not in selected:
                        raise GameLearningError(
                            "studio_field_absent", "Select an existing field in this authoring record.", 422
                        )
                    selected = selected[field]
                if isinstance(selected, list):
                    selected = {
                        "rows": [_authoring_summary(row) for row in selected[offset : offset + limit]],
                        "total": len(selected),
                        "offset": offset,
                        "limit": limit,
                    }
                else:
                    selected = _authoring_summary(selected)
            elif "record_id" in payload or "field" in payload:
                raise GameLearningError(
                    "studio_section_required", "Choose a section before selecting its records.", 422
                )
            return {
                "project": _project_summary(result["project"]),
                "profile": result["profile"],
                "manifest_digest": result["manifest_digest"],
                "sections": list(sections),
                "document": {section: selected} if section else _authoring_summary(document, inventory=True),
                "scene_graph": _authoring_summary(graph, inventory=True) if section is None else None,
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
    if operation == "world.inspect":
        from core.game_successor import world

        return _world_projection(await world(scope, command.project_id), payload)
    if operation == "desktop.inspect":
        from core.game_successor import desktop_catalog

        _only(payload, ())
        targets = await desktop_catalog()
        return {
            **targets,
            "project_id": command.project_id,
            "project_version": project["version"],
            "adopted_world": any(item["path"] == "game/successor/spec.json" for item in project["files"]),
            "compilation_executed": False,
            "foreign_os_execution_verified": False,
        }
    if operation == "successor.adopt":
        from core.game_successor import adopt, candidate
        from routes.game_learning import WriteRequest

        identifier = _id(payload, "candidate_id")
        issued = await candidate(scope, identifier)
        if issued["project_id"] != command.project_id:
            raise GameLearningError("studio_project_mismatch", "Candidate belongs to another project.", 403)
        body = _model(WriteRequest, {key: item for key, item in payload.items() if key != "candidate_id"})
        result = await adopt(scope, identifier, body)
        return {key: item for key, item in result.items() if key != "project"} | {
            "project": _project_summary(result["project"])
        }
    if operation in {"successor.inspect", "successor.export"}:
        from core.game_successor import candidate, export_candidate

        _only(payload, ("candidate_id",), required=("candidate_id",))
        value = await candidate(scope, _id(payload, "candidate_id"))
        if value["project_id"] != command.project_id:
            raise GameLearningError("studio_project_mismatch", "Candidate belongs to another project.", 403)
        if operation == "successor.export":
            exported = await export_candidate(scope, value["candidate_id"])
            return {
                "project_id": command.project_id,
                "candidate_id": value["candidate_id"],
                "recipe_digest": value["recipe_digest"],
                "filename": exported["filename"],
                "content_digest": exported["content_digest"],
                "bytes": len(exported["content"].encode()),
                "media_type": exported["media_type"],
                "download_path": f"/game-successor/candidates/{value['candidate_id']}/export",
                "state": "export_prepared",
                "client_download_verified": False,
            }
        result = {key: item for key, item in value.items() if key not in {"files", "source_files", "recipe"}}
        result["recipe"] = {key: item for key, item in value["recipe"].items() if key != "files"}
        result["generated_file_count"] = len(value["recipe"]["files"])
        return result
    if operation in {"job.inspect", "play.inspect", "play.input", "play.control"}:
        field = "job_id" if operation == "job.inspect" else "play_id"
        identifier = _id(payload, field)
        if operation == "job.inspect":
            _only(payload, (field,), required=(field,))
            result = await workspace.get_job(scope, identifier)
            issued = await workspace.jobs.find_one({"_id": identifier, **scope})
            if issued is None:
                raise GameLearningError("studio_job_absent", "This job is unavailable.", 404)
            await workspace._authority(scope, issued["input"])
        else:
            from routes.game_learning import PlayInput, PlayControl, _plays

            owner = _plays()
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
        from routes.game_learning import PlayRequest, _plays

        return _mutation_receipt(
            await _plays().create(scope, command.project_id, _model(PlayRequest, payload))
        )
    if operation.startswith("artifact."):
        from core import game_console_build as builds
        from routes.game_console_build import (
            ArtifactAdmission,
            ArtifactPlay,
            ArtifactTrain,
            ArtifactCampaign,
            ArtifactPreview,
        )

        artifact_id = _id(payload, "artifact_id")
        body = {key: value for key, value in payload.items() if key != "artifact_id"}
        if operation == "artifact.inspect":
            _only(body, ())
            return await builds.artifact_playback(scope, command.project_id, artifact_id)
        if operation == "artifact.export":
            _only(body, ())
            return await builds.prepare_artifact_export(scope, command.project_id, artifact_id)
        model, handler = {
            "artifact.admit": (ArtifactAdmission, builds.admit_artifact_source),
            "artifact.train": (ArtifactTrain, builds.start_artifact_training),
            "artifact.play": (ArtifactPlay, builds.start_artifact_play),
            "artifact.campaign": (ArtifactCampaign, builds.start_artifact_campaign),
            "artifact.preview": (ArtifactPreview, builds.preview_artifact),
        }[operation]
        result = await handler(scope, command.project_id, artifact_id, _model(model, body))
        if operation == "artifact.preview":
            result = dict(result)
            result["last_frame"] = result.pop("frame", None)
            return _mutation_receipt(result)
        if isinstance(result, dict) and "play" in result:
            result = {**result, "play": _mutation_receipt(result["play"])}
        return result
    if operation == "simulate":
        from routes.game_learning import SimulationRequest

        project, receipt = await workspace.simulate(
            scope, command.project_id, _model(SimulationRequest, payload)
        )
        return {"project": _project_summary(project), "result": _mutation_receipt(receipt)}
    if operation in {"build", "train", "successor.synthesize", "desktop.build", "project.review"}:
        if operation == "build":
            from routes.game_console_build import ConsoleBuildBody as model

            kind = "build"
        elif operation == "train":
            from routes.game_learning import TrainRequest as model

            kind = "train"
        elif operation == "successor.synthesize":
            from routes.game_successor import SynthesisRequest as model

            kind = "successor"
        elif operation == "desktop.build":
            from routes.game_successor import DesktopRequest as model

            kind = "desktop"
        else:
            from routes.game_studio_review import StudioReviewBody as model

            kind = "review"
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
    if operation in {
        "campaign.champion.handoff",
        "campaign.champion.adopt",
        "campaign.attempts",
        "campaign.authorization",
    }:
        from core import game_studio_learning as learning
        from routes.game_studio_learning import CampaignAuthorization, ChampionAdopt

        identifier = _id(payload, "campaign_id")
        issued = await learning.campaigns.find_one(
            {"_id": identifier, **scope, "project_id": command.project_id}
        )
        if issued is None:
            raise GameLearningError(
                "studio_campaign_absent", "This campaign does not belong to this project.", 404
            )
        body = {key: value for key, value in payload.items() if key != "campaign_id"}
        if operation == "campaign.champion.handoff":
            _only(body, ())
            return await learning.champion(scope, identifier)
        if operation == "campaign.attempts":
            _only(body, ("after_epoch", "limit"))
            after, limit = body.get("after_epoch", 0), body.get("limit", 16)
            if (
                type(after) is not int
                or not 0 <= after <= 100000
                or type(limit) is not int
                or not 1 <= limit <= 32
            ):
                raise GameLearningError(
                    "studio_attempt_page_invalid", "Attempt pages are bounded to32 actual records.", 422
                )
            return await learning.attempts(scope, identifier, after, limit)
        if operation == "campaign.champion.adopt":
            result = await learning.adopt_champion(scope, identifier, _model(ChampionAdopt, body))
            return (
                {**result, "project": _project_summary(result["project"])} if "project" in result else result
            )
        return {
            "campaign": await learning.authorize_campaign(
                scope, identifier, _model(CampaignAuthorization, body)
            )
        }
    if operation.startswith("campaign.") or operation == "lessons.search":
        from core import game_studio_learning as learning

        return await learning.execute_command(scope, command)
    raise GameLearningError("studio_operation_unknown", "This operation is unavailable.", 422)


def studio_agent_user_id(scope: Mapping[str, str]) -> str:
    """Canonical agent ID for a server-authenticated tenant/owner pair."""
    from core.game_learning import _digest

    admitted = workspace._scope(scope["tenant_id"], scope["owner_id"])
    return "studio-user-" + _digest(admitted)[:48]


def studio_application_schemas() -> dict[str, Any]:
    """Discover exact application request shapes without delegating authority."""
    from routes.game_console_build import (
        ConsoleBuildBody,
        ConsoleBuildPlanBody,
        ArtifactAdmission,
        ArtifactPlay,
        ArtifactTrain,
        ArtifactCampaign,
        ArtifactPreview,
    )
    from routes.game_console_studio import EditConsoleProject
    from routes.game_learning import PlayRequest, SimulationRequest, TrainRequest, WriteRequest
    from routes.game_studio_learning import (
        CampaignCreate,
        CampaignControl,
        CampaignAuthorization,
        ChampionAdopt,
    )
    from routes.game_studio_review import StudioReviewBody
    from routes.game_successor import CompareRequest, DesktopRequest, SynthesisRequest, WorldRequest

    models = {
        "console.edit": EditConsoleProject,
        "world.edit": WorldRequest,
        "simulate": SimulationRequest,
        "train": TrainRequest,
        "play.start": PlayRequest,
        "build": ConsoleBuildBody,
        "build.inspect": ConsoleBuildPlanBody,
        "project.review": StudioReviewBody,
        "desktop.build": DesktopRequest,
        "successor.synthesize": SynthesisRequest,
        "successor.compare": CompareRequest,
        "campaign.create": CampaignCreate,
        "artifact.admit": ArtifactAdmission,
        "artifact.play": ArtifactPlay,
        "artifact.train": ArtifactTrain,
        "artifact.campaign": ArtifactCampaign,
        "artifact.preview": ArtifactPreview,
        "campaign.champion.adopt": ChampionAdopt,
        "campaign.authorization": CampaignAuthorization,
    }
    shapes = {name: model.model_json_schema() for name, model in models.items()}
    for name in (
        "artifact.admit",
        "artifact.play",
        "artifact.train",
        "artifact.campaign",
        "artifact.preview",
    ):
        shapes[name]["properties"]["artifact_id"] = {"type": "string", "maxLength": 128}
        shapes[name].setdefault("required", []).append("artifact_id")
    shapes["artifact.inspect"] = {
        "required": ["artifact_id"],
        "properties": {"artifact_id": {"type": "string", "maxLength": 128}},
    }
    shapes["artifact.export"] = {
        "required": ["artifact_id"],
        "additionalProperties": False,
        "properties": {"artifact_id": {"type": "string", "minLength": 1, "maxLength": 128}},
        "description": "Read and verify exact completed binary bytes; return the scoped download reference, SHA and size.",
    }
    shapes["project.export"] = {
        "required": ["expected_version"],
        "additionalProperties": False,
        "properties": {"expected_version": {"type": "integer", "minimum": 1}},
        "description": "Prepare the genuine current canonical project JSON export; no source assets or arbitrary paths.",
    }
    shapes["successor.adopt"] = WriteRequest.model_json_schema()
    shapes["successor.adopt"]["properties"]["candidate_id"] = {
        "type": "string",
        "minLength": 1,
        "maxLength": 128,
    }
    shapes["successor.adopt"].setdefault("required", []).append("candidate_id")
    shapes["successor.adopt"][
        "description"
    ] = "Adopt an exact owned completed successor candidate into the current saved project through source-authorized revision CAS."
    shapes["successor.export"] = {
        "required": ["candidate_id"],
        "additionalProperties": False,
        "properties": {"candidate_id": {"type": "string", "minLength": 1, "maxLength": 128}},
        "description": "Prepare exact candidate recipe/source JSON; this is distinct from a compiled binary and a client download.",
    }
    shapes["world.inspect"] = {
        "additionalProperties": False,
        "properties": {
            "section": {"type": "string", "maxLength": 128},
            "record_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "field": {"type": "string", "maxLength": 128},
            "offset": {"type": "integer", "minimum": 0, "maximum": 100000},
            "limit": {"type": "integer", "minimum": 1, "maximum": 32},
        },
        "description": "Read actual saved original-world identity and controls. No section returns mechanic values and entity counts. Select world.ponds, world.farm_plots, world.terrain or mechanics.fishing, then exact record_id/field; lists page at32 records, strings at1500Unicodecharacters.",
    }
    shapes["world.edit"][
        "x-invariants"
    ] = "Select exactly one of complete changes,1..64 typed edits,or restore_review_job_id referencing an actual completed scoped original review. Restoration rechecks live source/teacher/policy authority and preserves immutable world identity/origins, including removal of optional sections absent in the reference; source revisions remain monotonic. set_field targets only an existing editable field; upsert_entity uses a complete inspected entity; remove_entity uses exact ID; paint_terrain changes at most256 existing cells. Full canonical geometry/mechanics validation and exact spec/version CAS still apply."
    shapes["world.edit"]["x-owner-edit-examples"] = [
        {"op": "set_field", "path": ["mechanics", "movement", "max_speed"], "value": 175},
        {"op": "set_field", "path": ["fidelity"], "value": {"profile": "enhanced"}},
        {"op": "paint_terrain", "x": 1, "y": 1, "width": 2, "height": 2, "tile": "1"},
    ]
    shapes["desktop.inspect"] = {
        "additionalProperties": False,
        "properties": {},
        "description": "Inspect actual approved desktop toolchain/sandbox prerequisites for five OS/architecture targets. No compilation or target-OS execution is performed.",
    }
    for name in ("campaign.champion.adopt", "campaign.authorization"):
        shapes[name]["properties"]["campaign_id"] = {"type": "string", "maxLength": 128}
        shapes[name].setdefault("required", []).append("campaign_id")
    shapes["campaign.champion.handoff"] = {
        "required": ["campaign_id"],
        "properties": {"campaign_id": {"type": "string", "maxLength": 128}},
    }
    shapes["campaign.attempts"] = {
        "required": ["campaign_id"],
        "properties": {
            "campaign_id": {"type": "string", "maxLength": 128},
            "after_epoch": {"type": "integer", "minimum": 0, "maximum": 100000},
            "limit": {"type": "integer", "minimum": 1, "maximum": 32},
        },
    }
    for name in ("job.resume", "job.cancel"):
        shapes[name] = {
            "required": ["job_id"],
            "properties": {"job_id": {"type": "string", "maxLength": 128}},
        }
    for name in ("play.resume", "play.stop"):
        shapes[name] = {
            "required": ["play_id", "expected_control_version"],
            "properties": {
                "play_id": {"type": "string", "maxLength": 128},
                "expected_control_version": {"type": "integer", "minimum": 1},
            },
        }
    # This discovery projection describes real owner operations; the editor
    # still validates all nested hardware/scene invariants before committing.
    fields = {
        "set_tile": ["tileset_id", "tile_index", "pixels"],
        "paint_tile": ["tileset_id", "tile_index", "x", "y", "color"],
        "set_palette": ["palette_id", "colors"],
        "set_map_cell": ["layer_id", "x", "y", "cell"],
        "fill_map": ["layer_id", "x", "y", "width", "height", "cell"],
        "upsert_palette": ["palette"],
        "upsert_tileset": ["tileset"],
        "upsert_layer": ["layer"],
        "upsert_entity": ["entity"],
        "transform_tile": ["tileset_id", "tile_index", "flip_x", "flip_y", "quarter_turns"],
        "set_controls": ["controls"],
        "set_audio": ["audio"],
        "set_config": ["config"],
        "put_asset": ["asset"],
        "transform_asset": ["id", "flip_x", "flip_y", "quarter_turns"],
        "image_to_tiles": ["asset_id", "tileset_id", "palette_id", "bank"],
        "bind_native_starter": [],
        "unbind_native_starter": [],
        "materialize_assets": [],
        "replace_source": ["path", "content"],
        "set_scene_graph": ["graph"],
        "upsert_graph_node": ["node"],
        "upsert_animation": ["animation"],
        "upsert_rule": ["rule"],
        "upsert_variable": ["variable"],
    }
    for op in (
        "remove_layer",
        "remove_entity",
        "delete_asset",
        "remove_palette",
        "remove_tileset",
        "remove_graph_node",
        "remove_animation",
        "remove_rule",
        "remove_variable",
    ):
        fields[op] = ["id"]
    shapes["console.edit"]["x-owner-edit-fields"] = {op: ["op", *keys] for op, keys in fields.items()}
    shapes["console.edit"]["x-invariants"] = (
        "Inspect existing exact section/record first. Upserts/settings use the complete validated record, "
        "not a partial patch. Native graph execution requires an explicit source port."
    )
    shapes["console.edit"]["x-graph-record-examples"] = {
        "node": {
            "id": "node1",
            "parent_id": None,
            "entity_id": None,
            "x": 0,
            "y": 0,
            "visible": True,
            "frames": [],
        },
        "atlas_frame": {"asset_id": "existing_image_id", "x": 0, "y": 0, "width": 8, "height": 8},
        "animation": {
            "id": "anim1",
            "node_id": "node1",
            "property": "x",
            "duration_ticks": 120,
            "loop": True,
            "interpolation": "linear",
            "keyframes": [{"tick": 0, "value": 0}, {"tick": 120, "value": 16}],
        },
        "variable": {"id": "visits", "initial": 0, "min": 0, "max": 1000},
        "rule": {
            "id": "visit",
            "trigger": {"kind": "region_enter", "x": 32, "y": 32, "width": 16, "height": 16},
            "conditions": [],
            "actions": [{"kind": "add_variable", "variable_id": "visits", "value": 1}],
            "cooldown_ticks": 60,
            "once": False,
            "enabled": True,
        },
        "action_fields": {
            "set_variable": ["variable_id", "value"],
            "add_variable": ["variable_id", "value"],
            "set_metric": ["metric", "value"],
            "add_metric": ["metric", "value"],
            "trade": ["cost", "resource", "amount"],
            "set_node_visibility": ["node_id", "visible"],
            "set_node_offset": ["node_id", "x", "y"],
            "emit_event": ["event"],
            "play_audio": ["cue_id"],
            "dialogue": ["text"],
            "teleport": ["x", "y"],
            "win": [],
            "reward": ["value"],
        },
    }
    for name in ("campaign.pulse", "campaign.pause", "campaign.resume", "campaign.cancel"):
        shapes[name] = CampaignControl.model_json_schema()
        shapes[name]["properties"]["campaign_id"] = {"type": "string", "maxLength": 128}
    shapes.update(
        {
            "project.inspect": {
                "properties": {
                    "path": {"type": "string", "maxLength": 256},
                    "offset": {"type": "integer", "minimum": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 1500},
                },
                "description": "Read exact owned source in1500-character Unicode pages; includes full original source SHA.",
            },
            "console.inspect": {
                "properties": {
                    "section": {"type": "string"},
                    "record_id": {"type": "string"},
                    "field": {"type": "string"},
                    "offset": {"type": "integer", "minimum": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 32},
                },
                "description": "No section returns bounded IDs/counts. Select exact sections or scene_graph.nodes/animations/rules/variables; record_id selects one record, field pages cells/tiles/frames.",
            },
            "console.handoff": {"properties": {}},
            "job.inspect": {"required": ["job_id"], "properties": {"job_id": {"type": "string"}}},
            "source.inspect": {"required": ["source_id"], "properties": {"source_id": {"type": "string"}}},
            "successor.inspect": {
                "required": ["candidate_id"],
                "properties": {"candidate_id": {"type": "string"}},
            },
            "campaign.inspect": {
                "required": ["campaign_id"],
                "properties": {"campaign_id": {"type": "string"}},
            },
            "campaign.rounds": {
                "required": ["campaign_id"],
                "properties": {
                    "campaign_id": {"type": "string"},
                    "after": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
            },
            "lessons.search": {"properties": {"q": {"type": "string"}, "limit": {"type": "integer"}}},
            "knowledge.search": {
                "type": "object",
                "additionalProperties": False,
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 300},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 8},
                },
                "description": "Current human-reviewed design references with exact source/review/consent provenance. Untrusted text, not verified truth or training permission.",
            },
            "knowledge.practice": {
                "type": "object",
                "additionalProperties": False,
                "required": ["candidate_id", "practice_id"],
                "properties": {
                    "candidate_id": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "practice_id": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                },
                "description": "Inspect a genuine completed measured practice receipt for an owned current reviewed source. Bounded factual observations only; no truth, XP or training permission.",
            },
        }
    )
    return shapes


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
