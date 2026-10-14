"""Original successor candidates under the existing scoped workspace job owner."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any

from core.game_learning import GameLearningError, _digest, _json, workspace


def _default_profiles():
    from skeleton.jeeves.game_successor import default_successor_profiles

    return {value.profile_id: value for value in default_successor_profiles()}


def _profile(scope, row, *, family="adventure", authored_mechanics=None):
    from skeleton.jeeves.game_style_analysis import profile_from_bundle

    return profile_from_bundle(
        workspace._source_bundle(scope, row),
        profile_id="source-" + row["source_id"],
        title=str(row.get("filename") or "Admitted source")[:120],
        family=family,
        authored_mechanics=authored_mechanics,
    )


async def sources(scope):
    from skeleton.jeeves.game_style_analysis import MECHANIC_CATALOG
    from skeleton.jeeves.game_successor import MECHANIC_GROUPS, STYLE_PRIORITIES, optimization_metric_catalog

    projects = await workspace.projects.find({**scope, "state": "active"}).limit(64).to_list(length=64)
    result = []
    for project in projects:
        rows = (
            await workspace.sources.find(
                {
                    **scope,
                    "project_id": project["project_id"],
                    "source_id": {"$in": project["source_ids"]},
                    "state": "active",
                    "rights_acknowledged": True,
                }
            )
            .limit(64)
            .to_list(length=64)
        )
        for row in rows:
            if row["kind"] in {"content_bundle", "build_artifact"}:
                # Media descriptors are playable source authority, not numeric game-feel evidence.
                continue
            reference = await _reference(scope, project, row)
            await workspace._external_authority(scope, {"derived_sources": [reference]})
            result.append(
                {
                    "kind": "owned_source",
                    "project_id": project["project_id"],
                    "project_version": project["version"],
                    "source_id": row["source_id"],
                    "source_digest": row["source_digest"],
                    "title": row.get("filename", "Admitted source"),
                    "state": "active",
                    "rights": row["rights_refs"],
                    "profile": _profile(scope, row).as_dict(),
                }
            )
            if len(result) >= 128:
                break
        if len(result) >= 128:
            break
    return {
        "sources": result,
        "authored_profiles": [p.as_dict() for p in _default_profiles().values()],
        "mechanic_catalog": {
            path: {
                "min": values[0],
                "max": values[1],
                "default": values[2],
                "unit": values[3],
                "integer": values[4],
            }
            for path, values in MECHANIC_CATALOG.items()
        },
        "mechanic_groups": list(MECHANIC_GROUPS),
        "style_priorities": list(STYLE_PRIORITIES),
        "optimization_metrics": optimization_metric_catalog(),
    }


async def _reference(scope, project, row):
    bundle = workspace._source_bundle(scope, row)
    return {
        "project_id": project["project_id"],
        "project_version": project["version"],
        "input_epoch": project.get("_input_epoch", 0),
        "source_id": row["source_id"],
        "source_digest": row["source_digest"],
        "authority_epoch": row["authority_epoch"],
        "bundle_digest": bundle.bundle_digest,
    }


async def _synthesis_input(scope, project, binding, body):
    references, profiles = [], []
    requested = body["sources"]
    if len(requested) not in (1, 3):
        raise GameLearningError("source_cardinality", "Select exactly one or three distinct origins.")
    authored = _default_profiles()
    for source in requested:
        if source["kind"] == "authored_profile":
            value = authored.get(source["profile_id"])
            if value is None:
                raise GameLearningError("authored_profile_unknown", "Select a registered inspiration.")
            profiles.append(value.as_dict())
        else:
            origin = await workspace._project(source["project_id"], scope, source["project_version"])
            row = await workspace.sources.find_one(
                {
                    "_id": source["source_id"],
                    **scope,
                    "project_id": origin["project_id"],
                    "state": "active",
                    "rights_acknowledged": True,
                }
            )
            if (
                row is None
                or row["source_id"] not in origin["source_ids"]
                or row["source_digest"] != source["source_digest"]
            ):
                raise GameLearningError(
                    "origin_source_unavailable", "Select a currently owned admitted source.", 403
                )
            if row["kind"] in {"content_bundle", "build_artifact"}:
                raise GameLearningError(
                    "source_profile_unavailable",
                    "Use an admitted analysed source or authored inspiration; media bytes and compiler output alone have no measured game profile.",
                )
            references.append(await _reference(scope, origin, row))
            profiles.append(
                _profile(
                    scope,
                    row,
                    family=source.get("family", "adventure"),
                    authored_mechanics=source.get("authored_mechanics"),
                ).as_dict()
            )
    if len({p["origin"]["source_id"] for p in profiles}) != len(profiles):
        raise GameLearningError("origin_duplicate", "Choose distinct exact source origins.")
    binding["external_sources"], binding["successor_profiles"] = references, profiles
    await workspace._external_authority(scope, binding)
    return binding


def _dependencies(job):
    values = list(job["input"].get("derived_sources", [])) + list(job["input"].get("external_sources", []))
    values += [
        {
            **source,
            "project_id": job["project_id"],
            "project_version": job["input"]["project_version"],
            "input_epoch": job["input"]["input_epoch"],
        }
        for source in job["input"]["sources"]
    ]
    result = list({(item["project_id"], item["source_id"]): item for item in values}.values())
    if len(result) > 64:
        raise GameLearningError("origin_lineage_limit", "Derived source lineage exceeds 64 origins.", 413)
    return result


async def _candidate_job(scope, candidate_id):
    from skeleton.jeeves.game_successor import SuccessorRecipe

    job = await workspace.jobs.find_one(
        {
            "_id": candidate_id,
            **scope,
            "kind": {"$in": ["successor", "successor_compare"]},
            "status": "completed",
            "cancel_requested": False,
            "input_changed": False,
        }
    )
    if job is None:
        raise GameLearningError(
            "candidate_unavailable", "A completed owned successor candidate is required.", 404
        )
    project = await workspace._project(job["project_id"], scope)
    if job["job_id"] not in project["job_ids"]:
        raise GameLearningError("candidate_uncommitted", "Candidate is not a committed project job.", 409)
    recipe = SuccessorRecipe.from_dict(job["result"]["recipe"])
    if job["result"]["candidate_id"] != job["job_id"] or recipe.digest != job["result"]["recipe_digest"]:
        raise GameLearningError("candidate_identity_invalid", "Candidate receipt identity differs.", 503)
    await workspace._external_authority(scope, {"derived_sources": _dependencies(job)})
    await workspace._derived_demonstration_authority(scope, job["input"])
    return job, recipe


async def candidate(scope, candidate_id):
    job, recipe = await _candidate_job(scope, candidate_id)
    project = await workspace._project(job["project_id"], scope)
    raw = recipe.as_dict()
    return {
        "candidate_id": job["job_id"],
        "project_id": job["project_id"],
        "job_id": job["job_id"],
        "status": "adopted" if project.get("successor_candidate_id") == candidate_id else "ready",
        "title": raw["spec"]["title"],
        "recipe": raw,
        "spec_digest": _digest(raw["spec"]),
        "recipe_digest": recipe.digest,
        "files": [{"path": path, "content": text} for path, text in raw["files"].items()],
        "source_lineage": raw["lineage"],
        "decisions": raw["decisions"],
        "comparisons": job["result"].get("comparison"),
        "controller_lineage": job["result"].get("controller_lineage"),
        "promotion_authorized": False,
    }


async def candidates(scope, project_id):
    project = await workspace._project(project_id, scope)
    rows = (
        await workspace.jobs.find(
            {
                **scope,
                "project_id": project_id,
                "job_id": {"$in": project["job_ids"]},
                "kind": {"$in": ["successor", "successor_compare"]},
                "status": "completed",
            }
        )
        .sort("created_at", -1)
        .limit(24)
        .to_list(length=24)
    )
    output = []
    for row in rows:
        try:
            value = await candidate(scope, row["job_id"])
        except GameLearningError as exc:
            if exc.status == 403 or exc.code in {"candidate_unavailable", "origin_revision_changed"}:
                continue
            raise
        value.pop("files")
        value.pop("recipe")
        output.append(value)
    return {"candidates": output}


async def _candidate_input(scope, project, binding, body):
    if not body.get("candidate_id"):
        value = await world(scope, project["project_id"])
        binding["desktop_source"] = {
            "spec_digest": value["spec_digest"],
            "tree_digest": binding["tree_digest"],
        }
        return binding
    job, recipe = await _candidate_job(scope, body["candidate_id"])
    if job["project_id"] != project["project_id"]:
        raise GameLearningError("candidate_project_mismatch", "Candidate belongs to another project.", 403)
    binding["derived_sources"] = _dependencies(job)
    binding["derived_demonstrations"] = list(job["input"].get("derived_demonstrations", []))
    binding["candidate"] = {
        "candidate_id": job["job_id"],
        "recipe_digest": recipe.digest,
        "result_digest": _digest(job["result"]),
    }
    if body.get("policy_id"):
        from skeleton.jeeves.game_learning import GamePolicyLearner
        from skeleton.jeeves.game_successor_runtime import SuccessorEnvironment

        saved = await workspace._admitted_policy(scope, project["project_id"], body["policy_id"])
        original = SuccessorEnvironment(
            recipe.spec, max_steps=saved["snapshot"]["environment"]["max_episode_steps"]
        )
        try:
            # The original candidate must be the actual environment taught to
            # this policy before any explicit transfer to candidate parameters.
            GamePolicyLearner.from_snapshot(saved["snapshot"], expected_spec=original.spec)
            current_input = {
                **binding,
                "episode_steps": saved["snapshot"]["environment"]["max_episode_steps"],
            }
            factory = await workspace._factory(scope, current_input)
            current = await asyncio.to_thread(factory)
            try:
                GamePolicyLearner.from_snapshot(saved["snapshot"], expected_spec=current.spec)
            finally:
                current.close()
        finally:
            original.close()
        binding["generation_policy"] = {
            "policy_id": body["policy_id"],
            "snapshot_digest": saved["snapshot"]["snapshot_digest"],
        }
        teachers = list(saved["input"].get("derived_demonstrations", []))
        for ref in saved["input"].get("demonstrations", []) + saved["input"].get(
            "inherited_demonstrations", []
        ):
            recorded = await workspace.database["game_learning_recordings"].find_one(
                {"_id": ref["recording_id"], **scope, "status": "completed", "consent": True}
            )
            if recorded is None:
                raise GameLearningError("teacher_unavailable", "A policy teacher withdrew consent.", 403)
            teachers.append(
                {
                    "project_id": recorded["project_id"],
                    "recording_id": ref["recording_id"],
                    "demonstration_digest": ref["demonstration_digest"],
                    "tree_digest": recorded["input"]["tree_digest"],
                }
            )
        binding["derived_demonstrations"] = list(
            {
                (ref["project_id"], ref["recording_id"]): ref
                for ref in binding["derived_demonstrations"] + teachers
            }.values()
        )
        await workspace._derived_demonstration_authority(scope, binding)
    return binding


async def _execute_thread(scope, job, cancelled, emit_event, operation):
    loop, deadline = asyncio.get_running_loop(), time.monotonic() + 300

    def call_bounded(awaitable):
        future = asyncio.run_coroutine_threadsafe(awaitable, loop)
        try:
            return future.result(timeout=max(0.001, min(10.0, deadline - time.monotonic())))
        except TimeoutError as exc:
            cancelled.set()
            future.cancel()
            raise GameLearningError(
                "job_deadline", "Successor authority or event publication exceeded its bounded deadline.", 409
            ) from exc

    def authorize(_origin=None):
        if cancelled.is_set() or time.monotonic() >= deadline:
            cancelled.set()
            raise GameLearningError("job_cancelled", "Bounded successor work was cancelled.", 409)
        call_bounded(workspace._authority(scope, job["input"]))

    def event(payload):
        if cancelled.is_set():
            raise GameLearningError("job_cancelled", "Successor work was cancelled.", 409)
        call_bounded(emit_event(dict(payload)))

    worker = asyncio.create_task(asyncio.to_thread(operation, authorize, event))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        cancelled.set()
        # Repeated shutdown cancellation cannot release admission capacity while
        # the numerical/compiler thread still owns a live process or callback.
        cleanup = asyncio.ensure_future(asyncio.gather(worker, return_exceptions=True))
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                cancelled.set()
        raise


async def handle_successor(scope, job, cancelled, emit_event):
    from skeleton.jeeves.game_successor import compile_successor

    def compile_candidate(authorize, event):
        authorize()
        body = job["request"]
        recipe = compile_successor(
            job["input"]["successor_profiles"],
            project_id=job["project_id"],
            title=body["title"],
            seed=body.get("seed", 1),
            weights=body.get("weights"),
            mechanic_priorities=body.get("mechanic_priorities"),
            style_priorities=body.get("style_priorities"),
            authorize_source=authorize,
        )
        authorize()
        event({"type": "log", "phase": "original_project_emitted", "recipe_digest": recipe.digest})
        return {
            "candidate_id": job["job_id"],
            "recipe": recipe.as_dict(),
            "recipe_digest": recipe.digest,
            "promotion_authorized": False,
        }

    return await _execute_thread(scope, job, cancelled, emit_event, compile_candidate)


async def handle_comparison(scope, job, cancelled, emit_event):
    from skeleton.jeeves.game_successor import optimize_successor

    issuer, recipe = await _candidate_job(scope, job["request"]["candidate_id"])
    if (
        recipe.digest != job["input"]["candidate"]["recipe_digest"]
        or _digest(issuer["result"]) != job["input"]["candidate"]["result_digest"]
    ):
        raise GameLearningError("candidate_changed", "Admitted candidate identity changed.", 503)
    snapshot = None
    if job["request"].get("policy_id"):
        saved = await workspace._admitted_policy(scope, job["project_id"], job["request"]["policy_id"])
        snapshot = saved["snapshot"]
        if snapshot["snapshot_digest"] != job["input"]["generation_policy"]["snapshot_digest"]:
            raise GameLearningError("controller_identity_changed", "Admitted controller changed.", 403)

    def compare(authorize, event):
        from skeleton.jeeves.game_learning import GamePolicyLearner, _descriptor
        from skeleton.jeeves.game_successor_runtime import SuccessorEnvironment

        body = job["request"]
        policy, controller = None, None
        if snapshot is not None:
            base = SuccessorEnvironment(recipe.spec, max_steps=snapshot["environment"]["max_episode_steps"])
            try:
                controller = GamePolicyLearner.from_snapshot(snapshot, expected_spec=base.spec)
                controller_class = type(base)
            finally:
                base.close()
            policy = lambda observation, _index, _spec: controller.predict(observation)["action"]

        def environment_factory(spec, limit):
            environment = SuccessorEnvironment(spec, max_steps=limit)
            if controller is not None:
                descriptor = _descriptor(environment.spec)
                if type(environment) is not controller_class or any(
                    descriptor[key] != controller.descriptor[key]
                    for key in ("actions", "observation_bins", "reward_components")
                ):
                    environment.close()
                    raise GameLearningError(
                        "controller_transfer_rejected",
                        "Candidate changed the frozen controller's action or observation semantics.",
                        409,
                    )
            return environment

        report = optimize_successor(
            recipe,
            target_metrics=body["target_metrics"],
            candidates=body.get("candidates", 4),
            episodes=body.get("episodes", 2),
            max_steps=body.get("max_steps", 256),
            seed=body.get("seed", 7),
            policy=policy,
            environment_factory=environment_factory,
            authorize_source=authorize,
            cancel=cancelled.is_set,
            on_progress=lambda value: event({"type": "log", "phase": "measured_candidate", **value}),
        )
        optimized = report.pop("optimized_recipe")
        controller_lineage = None
        if snapshot is not None:
            controller_lineage = {
                **job["input"]["generation_policy"],
                "original_environment_digest": snapshot["environment"]["environment_digest"],
                "transfer": "frozen_controller_on_distinct_candidate_environments_with_checked_action_reward_observation_semantics",
                "fresh_candidate_training_required": True,
                "production_generalization_authorized": False,
            }
        return {
            "candidate_id": job["job_id"],
            "recipe": optimized,
            "recipe_digest": optimized["recipe_digest"],
            "comparison": report,
            "controller_lineage": controller_lineage,
            "promotion_authorized": False,
        }

    return await _execute_thread(scope, job, cancelled, emit_event, compare)


async def adopt(scope, candidate_id, body):
    from core.game_console_studio import _prepare, _save_prepared

    issuer, recipe = await _candidate_job(scope, candidate_id)
    project_id = issuer["project_id"]
    operation = await _prepare(scope, project_id, "successor-adopt", {**body, "candidate_id": candidate_id})
    save_body = operation.get("_save_body")
    if save_body is None:
        project = await workspace._project(project_id, scope, body["expected_version"])
        files = {item["path"]: item["content"] for item in project["files"]}
        files.update(recipe.as_dict()["files"])
        save_body = {
            "expected_version": body["expected_version"],
            "idempotency_key": "successor-adopt:" + operation["_id"],
            "files": [{"path": path, "content": text} for path, text in files.items()],
            "entrypoint": "game/successor/spec.json",
            "_derived_sources": _dependencies(issuer),
            "_derived_demonstrations": issuer["input"].get("derived_demonstrations", []),
            "_successor_candidate_id": candidate_id,
        }
    await workspace._external_authority(scope, {"derived_sources": save_body["_derived_sources"]})
    await _save_prepared(scope, operation, save_body)
    project = await workspace.get_project(scope, project_id)
    return {
        "project": project,
        "spec": recipe.spec,
        "spec_digest": _digest(recipe.spec),
        "candidate_id": candidate_id,
    }


async def export_candidate(scope, candidate_id):
    value = await candidate(scope, candidate_id)
    encoded = _json(value, 2 * 1024 * 1024)
    return {
        "project_id": value["project_id"],
        "candidate_id": candidate_id,
        "filename": "successor-" + candidate_id + ".json",
        "media_type": "application/json",
        "content": encoded.decode(),
        "content_digest": hashlib.sha256(encoded).hexdigest(),
    }


async def world(scope, project_id):
    from skeleton.jeeves.game_successor_runtime import SuccessorEnvironment

    project = await workspace.get_project(scope, project_id)
    encoded = next(
        (item["content"] for item in project["files"] if item["path"] == "game/successor/spec.json"), None
    )
    if encoded is None:
        raise GameLearningError(
            "successor_world_absent", "Adopt an original successor before editing its world.", 409
        )
    spec = json.loads(encoded)
    environment = SuccessorEnvironment(spec, max_steps=1)
    try:
        descriptor = environment.spec.as_dict()
    finally:
        environment.close()
    binding = await workspace._input(
        scope, await workspace._project(project_id, scope, project["version"]), require_execution=False
    )
    await workspace._authority(scope, binding)
    return {
        "project": project,
        "spec": spec,
        "spec_digest": _digest(spec),
        "environment": descriptor,
        "editable_sections": ["title", "world", "mechanics", "palette", "camera", "fidelity"],
    }


async def edit_world(scope, project_id, body):
    from core.game_console_studio import _prepare, _save_prepared
    from skeleton.jeeves.game_successor_runtime import emit_successor_project

    operation = await _prepare(scope, project_id, "successor-world", body)
    save_body = operation.get("_save_body")
    if save_body is None:
        project = await workspace._project(project_id, scope, body["expected_version"])
        current = await world(scope, project_id)
        if current["spec_digest"] != body["expected_spec_digest"]:
            raise GameLearningError("successor_world_conflict", "Successor world changed; reload it.", 409)
        changes = body["changes"]
        if set(changes) - {"title", "world", "mechanics", "palette", "camera", "fidelity"}:
            raise GameLearningError(
                "world_field_immutable", "World edits cannot change origins or runtime identity."
            )
        spec = {**current["spec"], **changes}
        # Canonical emission validates every nested bound and regenerates
        # browser/native bytes from this exact original world, never caller code.
        emitted = emit_successor_project(spec)
        files = {item["path"]: item["content"] for item in project["files"]}
        files.update(emitted)
        save_body = {
            "expected_version": body["expected_version"],
            "idempotency_key": "successor-world:" + operation["_id"],
            "files": [{"path": path, "content": text} for path, text in files.items()],
            "entrypoint": "game/successor/spec.json",
            "_successor_candidate_id": None,
        }
    await _save_prepared(scope, operation, save_body)
    return await world(scope, project_id)


async def desktop_catalog():
    from skeleton.jeeves.game_desktop_export import desktop_export_catalog

    return {"targets": await asyncio.to_thread(desktop_export_catalog)}


async def handle_desktop(scope, job, cancelled, emit_event):
    from core.game_console_build import _persist_artifacts
    from skeleton.jeeves.game_desktop_export import DesktopExportRequest, DesktopExportRunner

    candidate_id = job["request"].get("candidate_id")
    if candidate_id:
        issuer, recipe = await _candidate_job(scope, candidate_id)
        if (
            recipe.digest != job["input"]["candidate"]["recipe_digest"]
            or _digest(issuer["result"]) != job["input"]["candidate"]["result_digest"]
        ):
            raise GameLearningError("candidate_changed", "Admitted candidate changed.", 503)
        files, title = recipe.as_dict()["files"], recipe.spec["title"]
    else:
        files = {item["path"]: item["content"] for item in job["input"]["files"]}
        spec = json.loads(files["game/successor/spec.json"])
        if _digest(spec) != job["input"]["desktop_source"]["spec_digest"]:
            raise GameLearningError("desktop_world_changed", "Frozen desktop world identity changed.", 503)
        title = spec["title"]

    def build(authorize, event):
        body = job["request"]
        request = DesktopExportRequest(
            files=files,
            target_id=body["target_id"],
            title=title,
            timeout_seconds=body.get("timeout_seconds", 180),
        )
        return DesktopExportRunner().build(request, cancel=cancelled.is_set, event=event, authorize=authorize)

    result = await _execute_thread(scope, job, cancelled, emit_event, build)
    artifacts = await _persist_artifacts(scope, job, result) if result.state == "binary_ready" else []
    return {
        **result.as_dict(),
        "artifacts": artifacts,
        "candidate_id": candidate_id,
        "workspace_tree_digest": job["input"]["tree_digest"],
        "promotion_authorized": False,
    }


def register_handlers():
    workspace.register_job_handler("successor", handle_successor, input_hook=_synthesis_input)
    workspace.register_job_handler("successor_compare", handle_comparison, input_hook=_candidate_input)
    workspace.register_job_handler("desktop", handle_desktop, input_hook=_candidate_input)
