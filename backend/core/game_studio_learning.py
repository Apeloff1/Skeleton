"""Durable, bounded studio campaigns using the existing governed job authority."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event
from uuid import uuid4

from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

from core.game_learning import GameLearningError, _digest, _json, _key, _now, _public, workspace
from core.game_successor import _execute_thread

campaigns = workspace.database["game_learning_campaigns"]
round_records = workspace.database["game_learning_rounds"]
lesson_records = workspace.database["game_learning_lessons"]
log = logging.getLogger(__name__)
_indexes_ready = False
_index_lock = asyncio.Lock()


async def ensure_campaign_indexes():
    global _indexes_ready
    if _indexes_ready:
        return
    async with _index_lock:
        if _indexes_ready:
            return
        await campaigns.create_index(
            [("auto_continue", 1), ("desired_status", 1), ("source_fenced", 1), ("updated_at", 1)],
            name="studio_recovery",
        )
        await campaigns.create_index(
            [("tenant_id", 1), ("owner_id", 1), ("project_id", 1), ("created_at", -1)],
            name="studio_project_campaigns",
        )
        await round_records.create_index(
            [("tenant_id", 1), ("owner_id", 1), ("campaign_id", 1), ("kind", 1), ("round_index", 1)],
            name="studio_round_pages",
        )
        await round_records.create_index(
            [("tenant_id", 1), ("owner_id", 1), ("campaign_id", 1), ("kind", 1), ("worker_epoch", 1)],
            name="studio_attempt_pages",
        )
        await lesson_records.create_index(
            [("tenant_id", 1), ("owner_id", 1), ("project_id", 1), ("created_at", -1), ("_id", -1)],
            name="studio_lesson_pages",
        )
        await lesson_records.create_index(
            [("tenant_id", 1), ("owner_id", 1), ("project_id", 1), ("search_terms", 1), ("created_at", -1)],
            name="studio_lesson_terms",
        )
        await lesson_records.create_index(
            [
                ("tenant_id", 1),
                ("owner_id", 1),
                ("project_id", 1),
                ("context_digest", 1),
                ("round_index", -1),
            ],
            name="studio_lesson_context",
        )
        await lesson_records.create_index(
            [
                ("tenant_id", 1),
                ("owner_id", 1),
                ("context.target_id", 1),
                ("context.genre", 1),
                ("context.engine", 1),
                ("context.code_digest", 1),
                ("created_at", -1),
            ],
            name="studio_lesson_transfer",
        )
        await lesson_records.create_index(
            [
                ("tenant_id", 1),
                ("owner_id", 1),
                ("context.target_id", 1),
                ("context.genre", 1),
                ("context.engine", 1),
                ("context.code_digest", 1),
                ("lesson.role", 1),
                ("context.source_digest", 1),
                ("created_at", -1),
                ("_id", -1),
            ],
            name="studio_decision_transfer",
        )
        _indexes_ready = True


def _lesson_terms(lesson):
    text = " ".join(str(lesson.get(name, "")) for name in ("role", "outcome", "recommendation"))
    text += " " + str(lesson.get("facts", {}).get("mechanic", ""))
    return sorted(set(re.findall(r"[\w.:-]{1,64}", text.casefold())))[:64]


def _code_digest():
    root = Path(__file__).resolve().parents[2] / "skeleton" / "jeeves"
    game_builder = root.parent / "ai" / "game_builder"
    dependencies = sorted(game_builder.glob("advanced_*_runtime.py")) + [
        game_builder / "advanced_level_scenes.py",
        game_builder / "system_editors.py",
    ]
    if len(dependencies) > 64:
        raise GameLearningError("campaign_code_inventory", "Studio runtime inventory exceeds64.", 503)
    return _digest(
        {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in (
                "game_studio_learning.py",
                "game_studio_environment.py",
                "game_studio_frame.py",
                "game_studio_rule_curriculum.py",
                "game_studio_scenario_lab.py",
                "game_learning.py",
                "game_learning_parallel.py",
                "game_learning_demonstrations.py",
                "game_learning_runtime.py",
                "game_console_editor.py",
                "game_console_graph.py",
                "game_console_simulation.py",
                "game_console_assets.py",
                "game_successor_runtime.py",
                "game_successor.py",
                "game_successor_world.py",
                "game_successor_assets.py",
                "game_emulator_host.py",
                "game_emulator_worker.py",
                "game_emulator_catalog.py",
                "game_style_analysis.py",
                "game_studio_review.py",
            )
        }
        | {
            "game_builder/" + path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in dependencies
        }
    )


def _projection(row):
    result = _public(row)
    for key in (
        "binding",
        "config",
        "context",
        "lineage",
        "environment_request",
        "policy_snapshot",
        "snapshot",
        "pending_reports",
        "request",
        "proposal_priors",
    ):
        result.pop(key, None)
    snapshot = row.get("snapshot") or {}
    champion = snapshot.get("champion")
    if isinstance(champion, dict):
        result["champion"] = {
            key: value
            for key, value in champion.items()
            if key
            in {"round_index", "policy_digest", "request_digest", "metrics", "score", "environment_digest"}
        }
    result["configuration"] = row["config"]
    result["stop_requested"] = (
        row.get("desired_status") in {"paused", "cancelled"} and row["status"] == "running"
    )
    result["champion"] = {
        key: snapshot[key]
        for key in (
            "champion_request_digest",
            "champion_policy_digest",
            "history_digest",
            "cumulative_steps",
            "lesson_count",
        )
        if key in snapshot
    }
    return result


async def _read(
    scope, identifier, *, historical=False, dragon_guarded=False, allowed_editor_operation_id=None
):
    row = await campaigns.find_one({"_id": identifier, **scope})
    if row is None:
        raise GameLearningError("campaign_not_found", "Owned learning campaign not found.", 404)
    # Normalize only declared runtime JSON envelopes. Mongo's signed Int64
    # wrapper is a JSON integer, but strict pure validators correctly require
    # plain Python ints; retain exact values/digests rather than coercing schema.
    for name in (
        "binding",
        "config",
        "context",
        "lineage",
        "environment_request",
        "policy_snapshot",
        "snapshot",
        "pending_reports",
        "proposal_priors",
    ):
        if name in row:
            row[name] = workspace._stored_evidence(row[name])
    if historical:
        dependencies = [{**ref, "project_id": row["project_id"]} for ref in row["binding"]["sources"]]
        dependencies += row["binding"].get("external_sources", []) + row["binding"].get("derived_sources", [])
        await workspace._external_authority(
            scope,
            {"derived_sources": dependencies},
            dragon_guarded=dragon_guarded,
            **(
                {"allowed_editor_operation_id": allowed_editor_operation_id}
                if allowed_editor_operation_id
                else {}
            ),
        )
        await workspace._derived_demonstration_authority(
            scope,
            row["binding"],
            dragon_guarded=dragon_guarded,
            **(
                {"allowed_editor_operation_id": allowed_editor_operation_id}
                if allowed_editor_operation_id
                else {}
            ),
        )
        if row["binding"].get("demonstrations") or row["binding"].get("inherited_demonstrations"):
            await workspace._demonstration_authority(
                scope,
                row["binding"],
                dragon_guarded=dragon_guarded,
                **(
                    {"allowed_editor_operation_id": allowed_editor_operation_id}
                    if allowed_editor_operation_id
                    else {}
                ),
            )
        for role in ("parent_policy", "generation_policy", "review_policy", "review_baseline_policy"):
            pin = row["binding"].get(role)
            if pin:
                policy = await workspace._admitted_policy(
                    scope,
                    pin.get("project_id", row["project_id"]),
                    pin["policy_id"],
                    dragon_guarded=dragon_guarded,
                    allow_environment_changed=True,
                    **(
                        {"allowed_editor_operation_id": allowed_editor_operation_id}
                        if allowed_editor_operation_id
                        else {}
                    ),
                )
                if policy["snapshot"]["snapshot_digest"] != pin["snapshot_digest"]:
                    raise GameLearningError(
                        "parent_policy_changed", "Historical policy source identity differs.", 403
                    )
    else:
        if row.get("source_fenced"):
            raise GameLearningError(
                "campaign_source_withdrawn", "Campaign source authority was withdrawn.", 403
            )
        await workspace._authority(scope, row["binding"], dragon_guarded=dragon_guarded)
        if _code_digest() != row["code_digest"]:
            raise GameLearningError(
                "campaign_code_changed", "Campaign runtime code changed; start a fresh campaign.", 409
            )
    return row


def _checked_report(row, report):
    from skeleton.jeeves.game_studio_learning import digest as runtime_digest

    report = workspace._stored_evidence(report)
    _json(report, 262144)
    if (
        report.get("round_digest") != runtime_digest({k: v for k, v in report.items() if k != "round_digest"})
        or report.get("context_digest") != runtime_digest(row["context"])
        or report.get("campaign_id") != (row.get("snapshot") or {}).get("campaign_id")
        or type(report.get("round_index")) is not int
        or not 1 <= report["round_index"] <= row["cursor"]
    ):
        raise GameLearningError("round_evidence_corrupt", "Committed round evidence differs.", 503)
    return report


def _checked_round_record(row, record):
    report = _checked_report(row, record["report"])
    if (
        record.get("campaign_id") != row["campaign_id"]
        or record.get("round_index") != report["round_index"]
        or record.get("round_digest") != report["round_digest"]
        or record.get("context") != row["context"]
    ):
        raise GameLearningError("round_projection_conflict", "Committed round identity differs.", 503)
    return report


def _checked_lesson(row, record):
    from skeleton.jeeves.game_studio_learning import digest as runtime_digest, validate_lesson

    lesson = workspace._stored_evidence(record["lesson"])
    _json(lesson, 262144)
    if (
        record["lesson_digest"] != _digest(lesson)
        or record["context"] != row["context"]
        or record.get("campaign_id") != row["campaign_id"]
        or record.get("project_id") != row["project_id"]
    ):
        raise GameLearningError("lesson_evidence_corrupt", "Committed lesson evidence differs.", 503)
    try:
        checked = validate_lesson(lesson, context_digest=runtime_digest(row["context"]))
    except (ValueError, RuntimeError) as exc:
        raise GameLearningError("lesson_evidence_corrupt", "Committed lesson schema differs.", 503) from exc
    if checked["round_index"] != record["round_index"] or checked["round_index"] > row["cursor"]:
        raise GameLearningError("lesson_evidence_corrupt", "Lesson cursor differs.", 503)
    return checked


async def _admitted_lesson(scope, issuer, record, *, round_cache=None):
    """A projected lesson is usable only with its exact issued round."""
    lesson = _checked_lesson(issuer, record)
    identifier = issuer["campaign_id"] + ":" + str(lesson["round_index"])
    proof = None if round_cache is None else round_cache.get(identifier)
    if proof is None:
        issued = await round_records.find_one({"_id": identifier, **scope, "kind": "round"})
        if issued is None:
            raise GameLearningError("lesson_issuer_missing", "Lesson lacks a committed round.", 503)
        report = _checked_round_record(issuer, issued)
        if not isinstance(report.get("lessons"), list) or len(report["lessons"]) != 4:
            raise GameLearningError("lesson_issuer_missing", "Round lesson count differs.", 503)
        proof = {
            "round_digest": report["round_digest"],
            "lesson_digests": {_digest(value) for value in report["lessons"]},
        }
        if round_cache is not None:
            round_cache[identifier] = proof
    if record.get("round_digest") != proof["round_digest"] or _digest(lesson) not in proof["lesson_digests"]:
        raise GameLearningError("lesson_issuer_missing", "Lesson differs from its issued round.", 503)
    return lesson


async def _repair(scope, row):
    for report in row.get("pending_reports", []):
        _checked_report(row, report)
        ordinal = report["round_index"]
        identifier = row["campaign_id"] + ":" + str(ordinal)
        doc = {
            "_id": identifier,
            **scope,
            "kind": "round",
            "project_id": row["project_id"],
            "campaign_id": row["campaign_id"],
            "round_index": ordinal,
            "report": report,
            "round_digest": report["round_digest"],
            "context": row["context"],
            "created_at": _now(),
        }
        await round_records.update_one({"_id": identifier}, {"$setOnInsert": doc}, upsert=True)
        issued = await round_records.find_one({"_id": identifier, **scope})
        if (
            issued is None
            or issued["round_digest"] != report["round_digest"]
            or _digest(_checked_round_record(row, issued)) != _digest(report)
        ):
            raise GameLearningError("round_projection_conflict", "Committed round projection differs.", 503)
        for index, lesson in enumerate(report.get("lessons", [])):
            lesson_digest = _digest(lesson)
            lesson_id = identifier + ":lesson:" + str(index)
            record = {
                "_id": lesson_id,
                **scope,
                "project_id": row["project_id"],
                "campaign_id": row["campaign_id"],
                "round_index": ordinal,
                "round_digest": report["round_digest"],
                "lesson_digest": lesson_digest,
                "lesson": lesson,
                "search_terms": _lesson_terms(lesson),
                "context_digest": _digest(row["context"]),
                "context": row["context"],
                "created_at": _now(),
            }
            await lesson_records.update_one({"_id": lesson_id}, {"$setOnInsert": record}, upsert=True)
            existing = await lesson_records.find_one({"_id": lesson_id, **scope})
            if (
                existing is None
                or existing["lesson_digest"] != lesson_digest
                or _digest(_checked_lesson(row, existing)) != _digest(lesson)
            ):
                raise GameLearningError(
                    "lesson_projection_conflict", "Committed lesson projection differs.", 503
                )
        # The complete report+lesson payload stays in the authoritative row
        # until all exact projections exist. A partial projection grants no new cursor.
        await campaigns.update_one(
            {"_id": row["campaign_id"], **scope, "cursor": {"$gte": ordinal}},
            {"$pull": {"pending_reports": {"round_index": ordinal, "round_digest": report["round_digest"]}}},
        )


async def _proposal_inputs(scope, context, binding):
    from skeleton.jeeves.game_studio_learning import make_proposal_prior

    predicate = {
        **scope,
        **{"context." + k: context[k] for k in ("target_id", "genre", "engine", "code_digest")},
        "lesson.role": "decision",
    }
    records = []
    # Fix both pools before issuance. A popular same-build campaign cannot
    # consume the other-build page, and later worker restarts do not refresh
    # either pool or inherit newly appearing unbound source obligations.
    for source_filter in (context["source_digest"], {"$ne": context["source_digest"]}):
        records.extend(
            await lesson_records.find({**predicate, "context.source_digest": source_filter})
            .sort([("created_at", -1), ("_id", -1)])
            .limit(64)
            .max_time_ms(2000)
            .to_list(length=64)
        )
    # Give distinct actual design arms a slot before filling the remaining
    # bounded prior set with repeated trials of a popular arm.
    first, repeated, mechanics = [], [], set()
    for record in records:
        mechanic = record.get("lesson", {}).get("facts", {}).get("mechanic")
        if not isinstance(mechanic, str) or not 1 <= len(mechanic) <= 128:
            raise GameLearningError("lesson_evidence_corrupt", "Decision mechanic identity differs.", 503)
        if mechanic in mechanics:
            repeated.append(record)
        else:
            first.append(record)
            mechanics.add(mechanic)
    records = first + repeated
    priors, source_refs, teacher_refs, seen = (
        [],
        list(binding.get("derived_sources", [])),
        list(binding.get("derived_demonstrations", [])),
        set(),
    )
    issuers, round_cache = {}, {}
    for record in records:
        try:
            if record["campaign_id"] not in issuers:
                issuers[record["campaign_id"]] = await _read(scope, record["campaign_id"], historical=True)
            origin = issuers[record["campaign_id"]]
        except GameLearningError as exc:
            if exc.status in {403, 404, 409}:
                continue
            raise
        lesson = await _admitted_lesson(scope, origin, record, round_cache=round_cache)
        if lesson["lesson_digest"] in seen:
            continue
        prior = make_proposal_prior(lesson, origin_context=origin["context"], destination_context=context)
        original = origin["binding"]
        policy_sources, policy_teachers = await _policy_dependencies(scope, origin)
        refs = (
            [{**v, "project_id": origin["project_id"]} for v in original["sources"]]
            + original.get("external_sources", [])
            + original.get("derived_sources", [])
        )
        merged_sources = {_digest(v): v for v in source_refs + policy_sources + refs}
        teachers = list(original.get("derived_demonstrations", []))
        teachers += [
            {**v, "project_id": origin["project_id"], "tree_digest": original["tree_digest"]}
            for v in original.get("demonstrations", []) + original.get("inherited_demonstrations", [])
        ]
        merged_teachers = {_digest(v): v for v in teacher_refs + policy_teachers + teachers}
        if len(merged_sources) > 64 or len(merged_teachers) > 64 or len(_json(priors + [prior])) > 262144:
            continue
        priors.append(prior)
        source_refs, teacher_refs = list(merged_sources.values()), list(merged_teachers.values())
        seen.add(lesson["lesson_digest"])
        if len(priors) >= 32:
            break
    binding["derived_sources"], binding["derived_demonstrations"] = source_refs, teacher_refs
    return list(reversed(priors))


async def create(scope, project_id, body):
    from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest
    from skeleton.jeeves.game_studio_learning import CampaignConfig

    await ensure_campaign_indexes()

    identifier = _key(project_id, "studio-campaign", body["idempotency_key"])
    digest = _digest(body)
    prior = await campaigns.find_one({"_id": identifier, **scope})
    if prior:
        if prior["request_digest"] != digest:
            raise GameLearningError("idempotency_conflict", "Campaign key binds different input.", 409)
        value = await inspect(scope, identifier)
        if prior.get("auto_continue") and value["status"] == "ready" and prior["cursor"] == 0:
            started = await pulse(
                scope,
                identifier,
                {"expected_campaign_version": value["version"], "idempotency_key": "auto:start"},
            )
            return started["campaign"]
        return value
    project = await workspace._project(project_id, scope, body["expected_version"])
    config = CampaignConfig(
        round_limit=body["round_limit"],
        slice_rounds=body["slice_rounds"],
        episodes_per_round=body["episodes"],
        episode_steps=(
            min(128, body["max_steps"]) if project["console_id"].startswith("studio:") else body["max_steps"]
        ),
        seed=body["seed"],
        evaluation_seeds=body.get("evaluation_seeds", 3),
        curriculum=body.get("curriculum", "mixed"),
        objective_weights=body.get(
            "objective_weights",
            {"return": 1.0, "completion": 0.5, "survival": 0.5, "coverage": 0.2, "diversity": 0.1},
        ),
        max_mean_step_ms=body.get("max_mean_step_ms"),
        max_death_regression=body.get("max_death_regression", 0.0),
        max_worst_seed_regression=body.get("max_worst_seed_regression", 0.0),
        proposal_width=body.get("proposal_width", 2),
        exploration_strategy=body.get("exploration_strategy", "least_visited"),
        n_step=body.get("n_step", 4),
    )
    binding = await workspace._input(
        scope, project, source_id=body.get("source_id"), episode_steps=body["max_steps"]
    )
    request = GameEnvironmentRequest.from_dict(
        workspace._stored_evidence(await workspace.environment_request(scope, binding))
    )
    mirror_steps = 20 * min(6, config.episode_steps) if request.kind == "studio" else 0
    planned = min(config.slice_rounds, config.round_limit) * (
        (config.episodes_per_round + 4 * config.evaluation_seeds) * config.episode_steps + mirror_steps
    )
    if planned > config.max_slice_steps:
        raise GameLearningError(
            "campaign_step_budget", "Configured slice exceeds its bounded actual-step admission.", 422
        )
    policy = None
    if body.get("policy_id"):
        admitted = await workspace._admitted_policy(scope, project_id, body["policy_id"])
        policy = admitted["snapshot"]
        binding["inherited_demonstrations"] = admitted["input"].get("demonstrations", []) + admitted[
            "input"
        ].get("inherited_demonstrations", [])
        binding["derived_demonstrations"] = admitted["input"].get("derived_demonstrations", [])
        if len(binding["inherited_demonstrations"]) + len(binding["derived_demonstrations"]) > 64:
            raise GameLearningError("teacher_lineage_limit", "Campaign teacher lineage exceeds 64.", 413)
        binding["generation_policy"] = {
            "policy_id": body["policy_id"],
            "snapshot_digest": policy["snapshot_digest"],
        }
    binding.pop("files")
    binding["files_omitted"] = True
    context = {
        "project_id": project_id,
        "target_id": request.target_id,
        "genre": (
            "authored_successor"
            if request.kind == "successor"
            else (
                "console_scene"
                if request.kind == "console_editor"
                else (
                    "authored_studio"
                    if request.kind == "studio"
                    else "native_observation" if request.kind == "libretro" else "reference"
                )
            )
        ),
        "engine": request.kind,
        "engine_era": project["engine_era"],
        "source_digest": _digest(
            {
                "tree_digest": binding["tree_digest"],
                "sources": binding["sources"],
                "source_id": binding.get("source_id"),
                "compiled_artifact": binding.get("compiled_artifact"),
                "emulator_binding": binding.get("emulator_binding"),
            }
        ),
        "tree_digest": binding["tree_digest"],
        "code_digest": _code_digest(),
    }
    proposal_priors = await _proposal_inputs(scope, context, binding)
    row = {
        "_id": identifier,
        **scope,
        "campaign_id": identifier,
        "project_id": project_id,
        "version": 1,
        "status": "ready",
        "cursor": 0,
        "round_limit": body["round_limit"],
        "slice_rounds": body["slice_rounds"],
        "config": config.as_dict(),
        "context": context,
        "lineage": {
            "input_digest": _digest(binding),
            "sources": binding["sources"],
            "context_digest": _digest(context),
        },
        "binding": binding,
        "environment_request": request.as_dict(),
        "request_digest": digest,
        "policy_snapshot": policy,
        "proposal_priors": proposal_priors,
        "snapshot": None,
        "pending_reports": [],
        "code_digest": _code_digest(),
        "active_job_id": None,
        "desired_status": "ready",
        "created_at": _now(),
        "updated_at": _now(),
    }
    row.update(
        auto_continue=body.get("auto_continue", False),
        authorization_expires_at=_now() + timedelta(seconds=body.get("authorization_seconds", 3600)),
        source_fenced=False,
    )
    _json(
        {
            key: value
            for key, value in row.items()
            if key not in {"created_at", "updated_at", "authorization_expires_at"}
        }
    )
    await workspace._admit(
        scope,
        "game-studio-campaign",
        identifier,
        len(_json(body))
        + len(_json(binding))
        + len(_json(request.as_dict()))
        + (len(_json(policy)) if policy else 0)
        + len(_json(proposal_priors)),
    )
    reserved = await workspace.projects.update_one(
        {
            "_id": project_id,
            **scope,
            "version": body["expected_version"],
            "_campaign_ids": {"$ne": identifier},
            "$or": [{"_campaign_ids.63": {"$exists": False}}],
        },
        {"$addToSet": {"_campaign_ids": identifier}},
    )
    if not reserved.modified_count:
        head = await workspace.projects.find_one({"_id": project_id, **scope})
        if head is None or identifier not in head.get("_campaign_ids", []):
            raise GameLearningError("campaign_limit", "Project changed or has reached 64 campaigns.", 409)
    await campaigns.update_one({"_id": identifier}, {"$setOnInsert": row}, upsert=True)
    issued = await campaigns.find_one({"_id": identifier, **scope})
    if issued is None or issued["request_digest"] != digest:
        raise GameLearningError("idempotency_conflict", "Campaign identity conflicts.", 409)
    if row["auto_continue"]:
        started = await pulse(
            scope, identifier, {"expected_campaign_version": 1, "idempotency_key": "auto:start"}
        )
        return started["campaign"]
    return await inspect(scope, identifier)


async def inspect(scope, identifier):
    row = await _read(scope, identifier, historical=True)
    await _repair(scope, row)
    if row["status"] == "running" and row.get("active_job_id"):
        try:
            job = await workspace.get_job(scope, row["active_job_id"])
        except GameLearningError as exc:
            if exc.status != 404:
                raise
            job = {"status": "interrupted"}
        if (
            job["status"] in {"completed", "failed", "cancelled", "interrupted"}
            and row["active_job_id"] not in workspace._tasks
        ):
            if job.get("worker_epoch"):
                await _archive_attempt(scope, row, job)
            status = (
                "completed"
                if row["cursor"] >= row["round_limit"]
                else (
                    row["desired_status"]
                    if row["desired_status"] in {"paused", "cancelled"}
                    else "ready" if job["status"] == "completed" else "interrupted"
                )
            )
            await campaigns.update_one(
                {"_id": identifier, **scope, "version": row["version"], "status": "running"},
                {
                    "$set": {
                        "status": status,
                        "updated_at": _now(),
                        "active_job_id": None,
                        "active_slice_id": None,
                    },
                    "$unset": {"_worker_token": "", "_worker_epoch": "", "_worker_lease_until": ""},
                    "$inc": {"version": 1},
                },
            )
    return _projection(await campaigns.find_one({"_id": identifier, **scope}))


async def _admit_slice(scope, project, binding, body):
    row = await _read(scope, body["campaign_id"])
    if row["project_id"] != project["project_id"]:
        raise GameLearningError("campaign_scope_mismatch", "Campaign belongs to another project.", 403)
    binding = dict(row["binding"])
    binding["studio_campaign"] = row["campaign_id"]
    return binding


async def pulse(scope, identifier, body, *, recovery_token=None):
    from core.game_learning import _time

    await inspect(scope, identifier)
    row = await _read(scope, identifier)
    receipt_id = _key(identifier, "campaign-pulse", body["idempotency_key"])
    body_digest = _digest(body)
    receipt = await round_records.find_one({"_id": receipt_id, **scope})
    if receipt and receipt["request_digest"] != body_digest:
        raise GameLearningError("idempotency_conflict", "Pulse key binds different input.", 409)
    job_body = {
        "expected_version": row["binding"]["project_version"],
        "idempotency_key": "studio-campaign-worker:" + identifier,
        "campaign_id": identifier,
    }
    job_id = _key(row["project_id"], "studio_learning", job_body["idempotency_key"])
    old = await workspace.jobs.find_one({"_id": job_id, **scope})
    if receipt and old and old["worker_epoch"] >= receipt["expected_worker_epoch"]:
        return {"campaign": await inspect(scope, identifier), "job": await workspace.get_job(scope, job_id)}
    same_intent = row.get("_pulse_intent", {}).get("receipt_id") == receipt_id
    recovery_replay = bool(
        recovery_token
        and receipt
        and receipt.get("start_cursor") == row["cursor"]
        and receipt.get("expected_worker_epoch", 0) > (old.get("worker_epoch", 0) if old else 0)
    )
    if (
        not same_intent and not recovery_replay and row["version"] != body["expected_campaign_version"]
    ) or row["status"] not in {
        "ready",
        "interrupted",
        "running",
    }:
        raise GameLearningError(
            "campaign_conflict", "Reload a ready or interrupted campaign before pulsing.", 409
        )
    if row["status"] == "running" and not same_intent:
        raise GameLearningError("campaign_worker_busy", "Another slice is already admitted.", 409)
    if row.get("_champion_handoff_receipt") and not row.get("_champion_handoff_completed"):
        raise GameLearningError(
            "champion_handoff_pending",
            "Finish the prepared champion source handoff before running more rounds.",
            409,
        )
    if row["desired_status"] != "ready" or row["cursor"] >= row["round_limit"]:
        raise GameLearningError("campaign_complete", "Campaign is paused, cancelled or complete.", 409)
    if _time(row["authorization_expires_at"]) <= _now():
        raise GameLearningError(
            "campaign_authorization_expired", "Campaign execution authorization expired.", 403
        )
    if old and job_id in workspace._tasks:
        raise GameLearningError("campaign_worker_draining", "The previous worker is still quiescing.", 409)
    await _repair(scope, row)
    if old and old["status"] in {"completed", "failed", "cancelled", "interrupted"}:
        await _archive_attempt(scope, row, old)
    await workspace._admit(scope, "game-studio-pulse", receipt_id, 1024)
    if receipt is None:
        receipt = {
            "_id": receipt_id,
            **scope,
            "kind": "command",
            "project_id": row["project_id"],
            "campaign_id": identifier,
            "request_digest": body_digest,
            "request": dict(body),
            "job_id": job_id,
            "slice_id": _key(identifier, "slice", str(row["cursor"])),
            "start_cursor": row["cursor"],
            "expected_worker_epoch": (old["worker_epoch"] if old else 0) + 1,
        }
        await round_records.update_one({"_id": receipt_id}, {"$setOnInsert": receipt}, upsert=True)
        issued = await round_records.find_one({"_id": receipt_id, **scope})
        if issued["request_digest"] != body_digest:
            raise GameLearningError("idempotency_conflict", "Pulse receipt differs.", 409)
        receipt = issued
    if receipt["start_cursor"] != row["cursor"]:
        raise GameLearningError("campaign_slice_stale", "This slice cursor has already advanced.", 409)
    claimed = await campaigns.find_one_and_update(
        {
            "_id": identifier,
            **scope,
            "version": row["version"],
            "status": row["status"],
            "source_fenced": False,
            "desired_status": "ready",
            **(
                {"_recovery_token": recovery_token, "_recovery_until": {"$gt": _now()}}
                if recovery_token
                else {}
            ),
        },
        {
            "$set": {
                "status": "running",
                "active_job_id": job_id,
                "active_slice_id": receipt["slice_id"],
                "slice_start": row["cursor"],
                "_pulse_intent": {"receipt_id": receipt_id, "digest": body_digest},
                "updated_at": _now(),
            },
            "$inc": {"version": 1},
        },
        return_document=ReturnDocument.AFTER,
    )
    if claimed is None:
        raise GameLearningError("campaign_conflict", "Campaign changed before slice admission.", 409)
    if old and old["status"] in {"completed", "failed", "cancelled", "interrupted"}:
        changed = await workspace.jobs.update_one(
            {"_id": job_id, **scope, "status": old["status"], "worker_epoch": old["worker_epoch"]},
            {
                "$set": {
                    "status": "queued",
                    "cancel_requested": False,
                    "input_changed": False,
                    "updated_at": _now(),
                },
                "$unset": {"error": "", "result": "", "worker_token": "", "lease_until": ""},
            },
        )
        if not changed.modified_count:
            raise GameLearningError("campaign_worker_busy", "Worker changed before safe requeue.", 409)
    job = await workspace.start_job(scope, row["project_id"], "studio_learning", job_body)
    return {"campaign": _projection(claimed), "job": job}


async def control(scope, identifier, action, body):
    from core.game_learning import _time

    if action not in {"pause", "resume", "cancel"}:
        raise GameLearningError("campaign_operation_unknown", "Campaign control is undeclared.")
    row = await campaigns.find_one({"_id": identifier, **scope})
    if row is None:
        raise GameLearningError("campaign_not_found", "Owned learning campaign not found.", 404)
    receipt_id = _key(identifier, "campaign-" + action, body["idempotency_key"])
    request_digest = _digest(body)
    old = await round_records.find_one({"_id": receipt_id, **scope})
    if old and old["request_digest"] != request_digest:
        raise GameLearningError("idempotency_conflict", "Control key binds different input.", 409)
    applied = bool(old and old.get("applied")) or row.get("_last_control_receipt") == receipt_id
    if not applied:
        if row["version"] != body["expected_campaign_version"]:
            raise GameLearningError("campaign_conflict", "Campaign changed; reload its current version.", 409)
        if action == "resume":
            if row.get("_champion_handoff_receipt") and not row.get("_champion_handoff_completed"):
                raise GameLearningError(
                    "champion_handoff_pending",
                    "Finish the prepared champion source handoff before resuming.",
                    409,
                )
            await _read(scope, identifier)
            if _time(row["authorization_expires_at"]) <= _now():
                raise GameLearningError(
                    "campaign_authorization_expired", "Renew execution authorization before resuming.", 403
                )
            if row["status"] not in {"paused", "interrupted"}:
                raise GameLearningError(
                    "campaign_not_resumable", "Only a quiesced paused/interrupted campaign can resume.", 409
                )
            desired, status = "ready", "ready"
        else:
            desired = "paused" if action == "pause" else "cancelled"
            status = "running" if row["status"] == "running" else desired
        if row.get("_last_control_receipt"):
            await round_records.update_one(
                {"_id": row["_last_control_receipt"], **scope, "kind": "command"}, {"$set": {"applied": True}}
            )
        await workspace._admit(scope, "game-studio-control", receipt_id, len(_json(body, 8192)))
        await round_records.update_one(
            {"_id": receipt_id},
            {
                "$setOnInsert": {
                    "_id": receipt_id,
                    **scope,
                    "kind": "command",
                    "campaign_id": identifier,
                    "project_id": row["project_id"],
                    "request_digest": request_digest,
                    "request": dict(body),
                    "action": action,
                    "created_at": _now(),
                }
            },
            upsert=True,
        )
        issued = await round_records.find_one({"_id": receipt_id, **scope})
        if issued is None or issued["request_digest"] != request_digest:
            raise GameLearningError("idempotency_conflict", "Control receipt differs.", 409)
        changed = await campaigns.update_one(
            {"_id": identifier, **scope, "version": row["version"]},
            {
                "$set": {
                    "status": status,
                    "desired_status": desired,
                    "_last_control_receipt": receipt_id,
                    **(
                        {
                            "_recovery_failures": 0,
                            "_recovery_failure_epoch": row.get("_recovery_failure_epoch"),
                            "_recovery_due_at": _now(),
                        }
                        if action == "resume"
                        else {}
                    ),
                    "updated_at": _now(),
                },
                "$inc": {"version": 1},
            },
        )
        if not changed.modified_count:
            current = await campaigns.find_one({"_id": identifier, **scope})
            if current.get("_last_control_receipt") != receipt_id:
                raise GameLearningError("campaign_conflict", "Campaign control lost its version fence.", 409)
    # Stop remains available even after source withdrawal; retry completes actual
    # cancellation side effects after a committed intent and interrupted process.
    row = await campaigns.find_one({"_id": identifier, **scope})
    if row.get("active_job_id") and action != "resume" and row["desired_status"] != "ready":
        # Capture the old worker's event before any await; a reusable slot may
        # later own a different worker/event after an explicit resume.
        event = workspace._cancel.get(row["active_job_id"])
        active = await workspace.jobs.find_one({"_id": row["active_job_id"], **scope})
        if active and active["status"] in {"queued", "running", "interrupted"}:
            await workspace.jobs.update_one(
                {
                    "_id": row["active_job_id"],
                    **scope,
                    "status": active["status"],
                    "worker_epoch": active["worker_epoch"],
                },
                {"$set": {"cancel_requested": True}},
            )
            await workspace.jobs.update_one(
                {
                    "_id": row["active_job_id"],
                    **scope,
                    "status": "queued",
                    "worker_epoch": active["worker_epoch"],
                    "cancel_requested": True,
                },
                {"$set": {"status": "cancelled"}},
            )
        if event:
            event.set()
    await round_records.update_one(
        {"_id": receipt_id, **scope, "request_digest": request_digest}, {"$set": {"applied": True}}
    )
    value = await inspect(scope, identifier) if action == "resume" else _projection(row)
    if action == "resume" and row.get("auto_continue") and value["status"] == "ready":
        await _recover_one(scope, identifier)
        return await inspect(scope, identifier)
    return value


async def _commit(scope, job, snapshot, report):
    identifier = job["request"]["campaign_id"]
    row = await _read(scope, identifier)
    live_job = await workspace.jobs.find_one(
        {
            "_id": job["job_id"],
            **scope,
            "status": "running",
            "worker_token": job["worker_token"],
            "cancel_requested": False,
            "input_changed": False,
            "lease_until": {"$gt": _now()},
        }
    )
    if (
        live_job is None
        or row["status"] != "running"
        or row["desired_status"] != "ready"
        or row["active_job_id"] != job["job_id"]
    ):
        raise GameLearningError(
            "campaign_worker_fenced", "Learning worker lost current campaign authority.", 409
        )
    from skeleton.jeeves.game_studio_learning import digest as runtime_digest

    if report.get("round_digest") != runtime_digest(
        {key: value for key, value in report.items() if key != "round_digest"}
    ) or snapshot.get("snapshot_digest") != runtime_digest(
        {key: value for key, value in snapshot.items() if key != "snapshot_digest"}
    ):
        raise GameLearningError(
            "campaign_evidence_corrupt", "Native round or full snapshot digest differs.", 503
        )
    if (
        type(snapshot.get("cursor")) is not int
        or snapshot["cursor"] != row["cursor"] + 1
        or report.get("round_index") != snapshot["cursor"]
        or snapshot["cursor"] > row["round_limit"]
    ):
        raise GameLearningError(
            "campaign_cursor_invalid", "Actual completed round cursor is inconsistent.", 503
        )
    if len(row.get("pending_reports", [])) >= 8:
        raise GameLearningError(
            "campaign_projection_pending", "Repair committed lesson projections before continuing.", 503
        )
    _json(report, 262144)
    _json(
        {
            "binding": row["binding"],
            "request": row["environment_request"],
            "policy": row["policy_snapshot"],
            "snapshot": snapshot,
            "pending_reports": row.get("pending_reports", []) + [report],
            "context": row["context"],
            "config": row["config"],
            "lineage": row["lineage"],
            "proposal_priors": row.get("proposal_priors", []),
        }
    )
    payload = {"snapshot": snapshot, "report": report}
    _json(payload, 4 * 1024 * 1024)
    admission = await workspace._admit(
        scope, "game-studio-round", identifier + ":" + str(snapshot["cursor"]), len(_json(payload))
    )
    await _read(scope, identifier)

    async def publish():
        return await campaigns.update_one(
            {
                "_id": identifier,
                **scope,
                "version": row["version"],
                "cursor": row["cursor"],
                "status": "running",
                "desired_status": "ready",
                "active_job_id": job["job_id"],
                "_worker_token": job["worker_token"],
                "_worker_epoch": job["worker_epoch"],
                "_worker_lease_until": {"$gt": _now()},
                "source_fenced": False,
                "authorization_expires_at": {"$gt": _now()},
            },
            {
                "$set": {
                    "snapshot": snapshot,
                    "cursor": snapshot["cursor"],
                    "updated_at": _now(),
                    "round_storage_receipt": admission,
                },
                "$push": {"pending_reports": report},
                "$inc": {"version": 1},
            },
        )

    changed = await workspace._guarded_write(scope, row["binding"], publish)
    if not changed.modified_count:
        raise GameLearningError(
            "campaign_round_conflict", "Completed round lost its atomic cursor/lesson fence.", 409
        )
    # The callback returns only after the authoritative round+lesson payload is
    # durable. Projection failure leaves repairable evidence, never rolls it back.
    try:
        await _repair(scope, await campaigns.find_one({"_id": identifier, **scope}))
    except Exception as exc:
        log.warning("Committed campaign lesson projection awaits repair: %s", type(exc).__name__)


async def handle_slice(scope, job, cancelled, emit_event):
    from core.game_learning import _time
    from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest
    from skeleton.jeeves.game_studio_learning import CampaignConfig, StudioLearningCampaign

    row = await _read(scope, job["request"]["campaign_id"])
    expires_at = _time(row["authorization_expires_at"])
    if expires_at <= _now():
        raise GameLearningError(
            "campaign_authorization_expired", "Campaign execution authorization expired before work.", 403
        )
    if row["active_job_id"] != job["job_id"] or row["desired_status"] != "ready":
        raise GameLearningError(
            "campaign_slice_fenced", "This campaign is no longer accepting the slice.", 409
        )
    current_worker = await workspace.jobs.find_one(
        {
            "_id": job["job_id"],
            **scope,
            "worker_token": job["worker_token"],
            "worker_epoch": job["worker_epoch"],
            "status": "running",
            "lease_until": {"$gt": _now()},
            "cancel_requested": False,
            "input_changed": False,
        }
    )
    if current_worker is None:
        raise GameLearningError("campaign_worker_fenced", "Canonical job worker is no longer live.", 409)
    claim = await campaigns.update_one(
        {
            "_id": row["campaign_id"],
            **scope,
            "status": "running",
            "desired_status": "ready",
            "active_job_id": job["job_id"],
            "source_fenced": False,
            "$or": [
                {"_worker_epoch": {"$exists": False}},
                {"_worker_epoch": {"$lt": job["worker_epoch"]}},
                {"_worker_epoch": job["worker_epoch"], "_worker_token": job["worker_token"]},
            ],
        },
        {
            "$set": {
                "_worker_token": job["worker_token"],
                "_worker_epoch": job["worker_epoch"],
                "_worker_lease_until": job["lease_until"],
            }
        },
    )
    if not claim.matched_count:
        raise GameLearningError("campaign_worker_fenced", "Campaign is no longer accepting a worker.", 409)
    await _record_attempt_claim(scope, row, job)
    request = GameEnvironmentRequest.from_dict(
        workspace._stored_evidence(await workspace.environment_request(scope, row["binding"]))
    )
    expected = GameEnvironmentRequest.from_dict(workspace._stored_evidence(row["environment_request"]))
    if request.digest != expected.digest:
        raise GameLearningError("campaign_environment_changed", "Campaign executable request changed.", 409)
    await _repair(scope, row)
    loop = asyncio.get_running_loop()

    def run(authorize, event):
        def campaign_authorize():
            if _now() >= expires_at:
                cancelled.set()
                raise GameLearningError(
                    "campaign_authorization_expired", "The admitted slice authorization expired.", 403
                )
            authorize()

        campaign_authorize()
        campaign = StudioLearningCampaign(
            request,
            CampaignConfig(**workspace._stored_evidence(row["config"])),
            workspace._stored_evidence(row["context"]),
            workspace._stored_evidence(row["lineage"]),
            policy_snapshot=workspace._stored_evidence(row["policy_snapshot"]),
            snapshot=workspace._stored_evidence(row["snapshot"]),
            proposal_priors=workspace._stored_evidence(row.get("proposal_priors", [])),
        )

        def checkpoint(snapshot, report):
            publication = asyncio.run_coroutine_threadsafe(_commit(scope, job, snapshot, report), loop)
            try:
                publication.result(timeout=30)
            except TimeoutError:
                cancelled.set()
                # Preserve capacity and the exact commit outcome; cancelling a
                # concurrent future cannot prove a Mongo write did not land.
                publication.result()
            try:
                event(
                    {
                        "type": "log",
                        "phase": "round_committed",
                        "campaign_id": row["campaign_id"],
                        "round_index": report["round_index"],
                        "round_digest": report["round_digest"],
                    }
                )
            except GameLearningError as exc:
                cancelled.set()
                log.warning("Committed campaign event unavailable: %s", exc.code)

        campaign.run_slice(
            rounds=min(row["slice_rounds"], row["round_limit"] - row["cursor"]),
            on_checkpoint=checkpoint,
            authorize=campaign_authorize,
            cancel=cancelled.is_set,
        )
        return {
            "campaign_id": row["campaign_id"],
            "slice_id": row["active_slice_id"],
            "production_promotion_authorized": False,
        }

    result = await _execute_thread(scope, job, cancelled, emit_event, run)
    current = await campaigns.find_one({"_id": row["campaign_id"], **scope})
    return {
        **result,
        "cursor": current["cursor"],
        "start_cursor": row["cursor"],
        "actual_committed_rounds": current["cursor"] - row["cursor"],
        "committed_snapshot_digest": (current.get("snapshot") or {}).get("snapshot_digest"),
        "remaining_rounds": current["round_limit"] - current["cursor"],
    }


async def rounds(scope, identifier, after=0, limit=32):
    if type(after) is not int or not 0 <= after <= 100000 or type(limit) is not int or not 1 <= limit <= 32:
        raise GameLearningError("round_query_invalid", "Round page bounds differ.")
    await ensure_campaign_indexes()
    row = await _read(scope, identifier, historical=True)
    await _repair(scope, row)
    rows = (
        await round_records.find(
            {
                **scope,
                "campaign_id": identifier,
                "kind": "round",
                "round_index": {"$gt": after, "$lte": row["cursor"]},
            }
        )
        .sort("round_index", 1)
        .limit(limit)
        .to_list(length=limit)
    )
    return {
        "campaign_id": identifier,
        "rounds": [_checked_round_record(row, record) for record in rows],
        "next_cursor": rows[-1]["round_index"] if rows and rows[-1]["round_index"] < row["cursor"] else None,
    }


async def export_evidence(scope, identifier, *, after=0, limit=16):
    """Export a bounded exact committed window, not a configured run count."""
    if type(limit) is not int or not 1 <= limit <= 16:
        raise GameLearningError("campaign_export_limit", "Export at most16 completed rounds.")
    row = await _read(scope, identifier, historical=True)
    page = await rounds(scope, identifier, after, limit)
    snapshot = row.get("snapshot") or {}
    reports = [report for report in page["rounds"] if report["round_index"] <= row["cursor"]]
    payload = {
        "schema_version": "skeleton.game.studio_evidence_export.v1",
        "campaign_id": identifier,
        "project_id": row["project_id"],
        "campaign_version": row["version"],
        "captured_head_cursor": row["cursor"],
        "head_snapshot_digest": snapshot.get("snapshot_digest"),
        "history_digest": snapshot.get("history_digest"),
        "context": row["context"],
        "configuration": row["config"],
        "after_round": after,
        "rounds": [],
        "next_after": None,
        "production_promotion_authorized": False,
        "scope": "committed role/comparison/acceptance/lesson evidence; no unexecuted rounds or import authority",
    }
    # Honor the byte bound without silently dropping report fields. A smaller
    # complete prefix is explicit through its continuation cursor.
    for report in reports:
        candidate = {**payload, "rounds": [*payload["rounds"], report]}
        try:
            _json(candidate, 4 * 1024 * 1024 - 1024)
        except GameLearningError as exc:
            if exc.code != "payload_limit" or not payload["rounds"]:
                raise
            break
        payload["rounds"].append(report)
    last = payload["rounds"][-1]["round_index"] if payload["rounds"] else after
    payload["next_after"] = last if last < row["cursor"] else None
    encoded = _json(payload, 4 * 1024 * 1024)
    current = await _read(scope, identifier, historical=True)
    if current["context"] != row["context"] or current["code_digest"] != row["code_digest"]:
        raise GameLearningError("campaign_export_changed", "Campaign authority changed during export.", 409)
    return {
        "campaign_id": identifier,
        "project_id": row["project_id"],
        "campaign_version": row["version"],
        "captured_head_cursor": row["cursor"],
        "round_count": len(payload["rounds"]),
        "next_after": payload["next_after"],
        "filename": "studio-evidence-" + identifier + "-after-" + str(after) + ".json",
        "media_type": "application/json",
        "content": encoded.decode(),
        "content_digest": hashlib.sha256(encoded).hexdigest(),
    }


async def lessons(scope, project_id, query="", limit=32, cursor=None):
    if type(limit) is not int or not 1 <= limit <= 32 or not isinstance(query, str) or len(query) > 256:
        raise GameLearningError("lesson_query_invalid", "Lesson query bounds differ.")
    await ensure_campaign_indexes()
    project = await workspace._project(project_id, scope)
    await _index_legacy_lessons(scope, project_id)
    terms = sorted(set(re.findall(r"[\w.:-]{1,64}", query.casefold())))
    if query.strip() and not terms:
        raise GameLearningError("lesson_query_invalid", "Enter a literal word or identifier.")
    if len(terms) > 16:
        raise GameLearningError("lesson_query_invalid", "Use at most16 literal search terms.")
    predicate = {**scope, "project_id": project_id}
    if terms:
        predicate["search_terms"] = {"$all": terms}
    if cursor:
        anchor = await lesson_records.find_one({"_id": cursor, **scope, "project_id": project_id})
        if anchor is None:
            raise GameLearningError("lesson_cursor_invalid", "Owned lesson cursor not found.", 409)
        predicate["$or"] = [
            {"created_at": {"$lt": anchor["created_at"]}},
            {"created_at": anchor["created_at"], "_id": {"$lt": cursor}},
        ]
    records = (
        await lesson_records.find(predicate)
        .sort([("created_at", -1), ("_id", -1)])
        .limit(limit + 1)
        .max_time_ms(2000)
        .to_list(length=limit + 1)
    )
    output, issuers, round_cache = [], {}, {}
    for record in records[:limit]:
        if record["campaign_id"] not in issuers:
            issuers[record["campaign_id"]] = await _read(scope, record["campaign_id"], historical=True)
        checked = await _admitted_lesson(
            scope, issuers[record["campaign_id"]], record, round_cache=round_cache
        )
        if record.get("search_terms") is not None and record["search_terms"] != _lesson_terms(checked):
            raise GameLearningError("lesson_index_corrupt", "Derived lesson search index differs.", 503)
        output.append(
            {
                "lesson_id": record["_id"],
                "campaign_id": record["campaign_id"],
                "round_index": record["round_index"],
                "lesson_digest": record["lesson_digest"],
                "lesson": checked,
                "context": record["context"],
                "applicable_to_current_tree": record["context"]["tree_digest"] == _digest(project["files"])
                and record["context"]["code_digest"] == _code_digest(),
            }
        )
    return {
        "lessons": output,
        "next_cursor": records[limit - 1]["_id"] if len(records) > limit else None,
        "search_mode": "bounded_literal_terms",
        "legacy_indexing_pending": await lesson_records.count_documents(
            {**scope, "project_id": project_id, "search_terms": {"$exists": False}}, limit=1
        ),
    }


async def execute_command(scope, command):
    from routes.game_studio_learning import CampaignCreate, CampaignControl

    payload = dict(command.payload)
    if command.operation == "campaign.create":
        return {
            "campaign": await create(
                scope, command.project_id, CampaignCreate.model_validate(payload).model_dump()
            )
        }
    if command.operation == "lessons.search":
        if set(payload) - {"q", "limit", "cursor"}:
            raise GameLearningError("campaign_payload_invalid", "Lesson search accepts q and limit only.")
        return await lessons(
            scope,
            command.project_id,
            payload.get("q", ""),
            payload.get("limit", 32),
            payload.get("cursor"),
        )
    identifier = payload.pop("campaign_id", None)
    row = (
        await campaigns.find_one({"_id": identifier, **scope})
        if command.operation in {"campaign.pause", "campaign.cancel"}
        else await _read(scope, identifier, historical=True)
    )
    if row is None or row["project_id"] != command.project_id:
        raise GameLearningError("campaign_scope_mismatch", "Campaign belongs to another project.", 403)
    if command.operation == "campaign.inspect":
        if payload:
            raise GameLearningError("campaign_payload_invalid", "Inspect accepts campaign_id only.")
        return {"campaign": await inspect(scope, identifier)}
    if command.operation == "campaign.rounds":
        if set(payload) - {"after", "limit"}:
            raise GameLearningError("campaign_payload_invalid", "Round page fields differ.")
        return await rounds(scope, identifier, payload.get("after", 0), payload.get("limit", 32))
    body = CampaignControl.model_validate(payload).model_dump()
    if command.operation == "campaign.pulse":
        return await pulse(scope, identifier, body)
    if command.operation not in {"campaign.pause", "campaign.resume", "campaign.cancel"}:
        raise GameLearningError("campaign_operation_unknown", "This learning command is undeclared.")
    return {"campaign": await control(scope, identifier, command.operation.split(".")[-1], body)}


def register_handler():
    workspace.register_job_handler("studio_learning", handle_slice, input_hook=_admit_slice)


async def after_job(scope, job_id, *, expected_worker_epoch):
    job = await workspace.jobs.find_one(
        {
            "_id": job_id,
            **scope,
            "kind": "studio_learning",
            "status": "completed",
            "worker_epoch": expected_worker_epoch,
            "cancel_requested": False,
            "input_changed": False,
        }
    )
    if job is None or job_id in workspace._tasks:
        return
    return await _recover_one(
        scope, job["request"]["campaign_id"], expected_worker_epoch=expected_worker_epoch
    )


async def _record_attempt_claim(scope, row, job):
    identifier = _key(row["campaign_id"], "attempt-claim", str(job["worker_epoch"]))
    evidence = {
        "campaign_id": row["campaign_id"],
        "project_id": row["project_id"],
        "job_id": job["job_id"],
        "worker_epoch": job["worker_epoch"],
        "slice_id": row["active_slice_id"],
        "start_cursor": row["cursor"],
        "start_steps": (row.get("snapshot") or {}).get("cumulative_steps", 0),
        "source_digest": row["context"]["source_digest"],
        "code_digest": row["code_digest"],
        "input_digest": _digest(job["input"]),
    }
    encoded = _json(evidence, 8192)
    await workspace._admit(scope, "game-studio-attempt-claim", identifier, len(encoded))
    await round_records.update_one(
        {"_id": identifier},
        {
            "$setOnInsert": {
                "_id": identifier,
                **scope,
                "kind": "attempt_claim",
                **evidence,
                "evidence_digest": _digest(evidence),
                "created_at": job.get("started_at", job["updated_at"]),
            }
        },
        upsert=True,
    )
    issued = await round_records.find_one({"_id": identifier, **scope})
    if issued is None or issued["evidence_digest"] != _digest(evidence):
        raise GameLearningError(
            "attempt_claim_conflict", "Worker attempt binds different source or cursor.", 503
        )


async def _archive_attempt(scope, row, job):
    if job["status"] not in {"completed", "failed", "cancelled", "interrupted"} or not job.get(
        "worker_epoch"
    ):
        return
    identifier = _key(row["campaign_id"], "attempt", str(job["worker_epoch"]))
    prior = await round_records.find_one({"_id": identifier, **scope, "kind": "attempt"})
    if prior is not None:
        _checked_attempt(row, prior)
        return
    claim = await round_records.find_one(
        {
            "_id": _key(row["campaign_id"], "attempt-claim", str(job["worker_epoch"])),
            **scope,
            "kind": "attempt_claim",
        }
    )
    snapshot = row.get("snapshot") or {}
    if claim is not None:
        evidence = {
            key: value
            for key, value in claim.items()
            if key not in {"_id", "tenant_id", "owner_id", "kind", "evidence_digest", "created_at"}
        }
        if (
            claim["evidence_digest"] != _digest(evidence)
            or claim["campaign_id"] != row["campaign_id"]
            or claim["job_id"] != job["job_id"]
            or claim["worker_epoch"] != job["worker_epoch"]
            or claim["input_digest"] != _digest(job["input"])
            or type(claim.get("start_steps")) is not int
            or not 0 <= claim["start_steps"] <= snapshot.get("cumulative_steps", 0)
        ):
            raise GameLearningError(
                "attempt_claim_corrupt", "Worker claim identity or exact committed start differs.", 503
            )
    start = claim["start_cursor"] if claim else row.get("slice_start")
    if type(start) is not int or not 0 <= start <= row["cursor"]:
        start = None
    evidence = {
        "schema_version": "skeleton.game.studio_attempt.v1",
        "campaign_id": row["campaign_id"],
        "project_id": row["project_id"],
        "job_id": job["job_id"],
        "worker_epoch": job["worker_epoch"],
        "state": job["status"],
        "slice_id": claim["slice_id"] if claim else row.get("active_slice_id"),
        "start_cursor": start,
        "end_cursor": row["cursor"],
        "committed_rounds": None if start is None else row["cursor"] - start,
        "committed_steps": (
            None if claim is None else snapshot.get("cumulative_steps", 0) - claim["start_steps"]
        ),
        "snapshot_digest": snapshot.get("snapshot_digest"),
        "last_round_digest": snapshot.get("last_round_digest"),
        "claim_digest": None if claim is None else claim["evidence_digest"],
        "error_code": (job.get("error") or {}).get("code"),
        "uncommitted_work_measured": False,
    }
    await workspace._admit(scope, "game-studio-attempt", identifier, len(_json(evidence, 8192)))
    record = {
        "_id": identifier,
        **scope,
        "kind": "attempt",
        **evidence,
        "evidence_digest": _digest(evidence),
        "created_at": job["updated_at"],
    }
    await round_records.update_one({"_id": identifier}, {"$setOnInsert": record}, upsert=True)
    issued = await round_records.find_one({"_id": identifier, **scope})
    if issued is None or issued["evidence_digest"] != record["evidence_digest"]:
        raise GameLearningError("attempt_history_conflict", "Terminal worker history differs.", 503)


def _checked_attempt(row, record):
    excluded = {"_id", "tenant_id", "owner_id", "kind", "evidence_digest", "created_at"}
    evidence = {key: value for key, value in record.items() if key not in excluded}
    _json(evidence, 8192)
    if (
        evidence.get("campaign_id") != row["campaign_id"]
        or evidence.get("project_id") != row["project_id"]
        or record.get("evidence_digest") != _digest(evidence)
    ):
        raise GameLearningError("attempt_history_corrupt", "Stored worker attempt evidence differs.", 503)
    if (
        evidence.get("schema_version") != "skeleton.game.studio_attempt.v1"
        or type(evidence.get("worker_epoch")) is not int
        or evidence["worker_epoch"] < 1
        or evidence.get("state") not in {"completed", "failed", "cancelled", "interrupted"}
        or evidence.get("uncommitted_work_measured") is not False
    ):
        raise GameLearningError("attempt_history_corrupt", "Stored worker attempt schema differs.", 503)
    start, end, count, steps = (
        evidence.get(name) for name in ("start_cursor", "end_cursor", "committed_rounds", "committed_steps")
    )
    if (
        type(end) is not int
        or not 0 <= end <= row["cursor"]
        or (start is None and count is not None)
        or (
            start is not None
            and (
                type(start) is not int
                or not 0 <= start <= end
                or type(count) is not int
                or count != end - start
            )
        )
        or (steps is not None and (type(steps) is not int or steps < 0))
    ):
        raise GameLearningError(
            "attempt_history_corrupt", "Stored attempt counts differ from committed cursor evidence.", 503
        )
    return evidence


async def attempts(scope, identifier, after_epoch=0, limit=32):
    if (
        type(after_epoch) is not int
        or not 0 <= after_epoch <= 2**63 - 1
        or type(limit) is not int
        or not 1 <= limit <= 32
    ):
        raise GameLearningError("attempt_query_invalid", "Worker history page bounds differ.")
    row = await _read(scope, identifier, historical=True)
    await ensure_campaign_indexes()
    await inspect(scope, identifier)
    records = (
        await round_records.find(
            {**scope, "campaign_id": identifier, "kind": "attempt", "worker_epoch": {"$gt": after_epoch}}
        )
        .sort("worker_epoch", 1)
        .limit(limit + 1)
        .max_time_ms(2000)
        .to_list(length=limit + 1)
    )
    page = records[:limit]
    return {
        "campaign_id": identifier,
        "attempts": [_checked_attempt(row, record) for record in page],
        "next_epoch": page[-1]["worker_epoch"] if len(records) > limit else None,
    }


async def _recover_one(scope, identifier, *, expected_worker_epoch=None):
    from core.game_learning import _time

    token, now = str(uuid4()), _now()
    retry_delay = 0
    row = await campaigns.find_one_and_update(
        {
            "_id": identifier,
            **scope,
            "auto_continue": True,
            "desired_status": "ready",
            "source_fenced": False,
            "status": {"$in": ["ready", "running", "interrupted"]},
            "authorization_expires_at": {"$gt": now},
            "$or": [{"_recovery_until": {"$exists": False}}, {"_recovery_until": {"$lte": now}}],
            "$and": [
                {"$or": [{"_recovery_due_at": {"$exists": False}}, {"_recovery_due_at": {"$lte": now}}]}
            ],
        },
        {"$set": {"_recovery_token": token, "_recovery_until": now + timedelta(seconds=30)}},
        return_document=ReturnDocument.AFTER,
    )
    if row is None:
        return "waiting"
    try:
        await _read(scope, identifier)
        await inspect(scope, identifier)
        row = await _read(scope, identifier)
        if row["desired_status"] != "ready" or _time(row["authorization_expires_at"]) <= _now():
            return "blocked"
        job_id = _key(row["project_id"], "studio_learning", "studio-campaign-worker:" + identifier)
        job = await workspace.jobs.find_one({"_id": job_id, **scope})
        if expected_worker_epoch is not None and (
            job is None or job.get("worker_epoch") != expected_worker_epoch
        ):
            return "waiting"
        if job_id in workspace._tasks:
            return "waiting"
        if job is not None and job["status"] in {"queued", "running"}:
            await workspace._schedule(job_id, scope)
            return "waiting"
        if row["cursor"] >= row["round_limit"]:
            if job and job["status"] in {"completed", "failed", "cancelled", "interrupted"}:
                await _archive_attempt(scope, row, job)
            if row["status"] != "completed":
                await campaigns.update_one(
                    {
                        "_id": identifier,
                        **scope,
                        "_recovery_token": token,
                        "version": row["version"],
                        "cursor": row["cursor"],
                    },
                    {
                        "$set": {
                            "status": "completed",
                            "active_job_id": None,
                            "active_slice_id": None,
                            "updated_at": _now(),
                        },
                        "$unset": {"_worker_token": "", "_worker_epoch": "", "_worker_lease_until": ""},
                        "$inc": {"version": 1},
                    },
                )
            return "complete"
        if row["status"] not in {"ready", "interrupted"}:
            return "waiting"
        if job is not None and job.get("input_changed"):
            return "blocked"
        epoch = 0 if job is None else job.get("worker_epoch", 0)
        if job and (
            job["status"] in {"failed", "interrupted"}
            or job["status"] == "cancelled"
            and not job.get("cancel_requested")
        ):
            terminal = await round_records.find_one(
                {"_id": _key(identifier, "attempt", str(epoch)), **scope, "kind": "attempt"}
            )
            progress = (
                0 if terminal is None else (_checked_attempt(row, terminal).get("committed_rounds") or 0)
            )
            failures = 0 if progress else row.get("_recovery_failures", 0)
            if not progress and row.get("_recovery_failure_epoch") != epoch:
                failures += 1
                retry_delay = min(300, 5 * 2 ** min(failures, 6))
                await campaigns.update_one(
                    {"_id": identifier, **scope, "_recovery_token": token},
                    {
                        "$set": {
                            "_recovery_failures": failures,
                            "_recovery_failure_epoch": epoch,
                            "_recovery_due_at": _now() + timedelta(seconds=retry_delay),
                        }
                    },
                )
                if failures < 5:
                    return "waiting"
            if failures >= 5:
                await campaigns.update_one(
                    {"_id": identifier, **scope, "_recovery_token": token},
                    {
                        "$set": {
                            "status": "paused",
                            "desired_status": "paused",
                            "recovery_error": {
                                "code": "campaign_repeated_failure",
                                "message": "Five distinct attempts made no durable round progress; inspect and explicitly resume.",
                            },
                            "updated_at": _now(),
                        },
                        "$inc": {"version": 1},
                    },
                )
                return "blocked"
            if progress:
                await campaigns.update_one(
                    {"_id": identifier, **scope, "_recovery_token": token},
                    {"$set": {"_recovery_failures": 0}},
                )
        pending = await round_records.find_one(
            {"_id": row.get("_pulse_intent", {}).get("receipt_id"), **scope, "kind": "command"}
        )
        if (
            pending
            and pending.get("start_cursor") == row["cursor"]
            and pending.get("expected_worker_epoch", 0) > epoch
        ):
            request = pending.get("request")
            if not isinstance(request, dict) or _digest(request) != pending["request_digest"]:
                raise GameLearningError(
                    "campaign_evidence_corrupt", "Unadmitted pulse has no exact frozen request.", 503
                )
        else:
            request = {
                "expected_campaign_version": row["version"],
                "idempotency_key": "recovery:" + str(row["cursor"]) + ":" + str(epoch),
            }
            existing = await round_records.find_one(
                {"_id": _key(identifier, "campaign-pulse", request["idempotency_key"]), **scope}
            )
            if existing is not None:
                request = existing.get("request")
                if not isinstance(request, dict) or _digest(request) != existing["request_digest"]:
                    raise GameLearningError(
                        "campaign_evidence_corrupt", "Recovery pulse identity differs.", 503
                    )
        await pulse(scope, identifier, request, recovery_token=token)
        return "recovered"
    except GameLearningError as exc:
        if exc.status in {403, 404} or exc.code in {
            "campaign_code_changed",
            "campaign_evidence_corrupt",
            "campaign_round_conflict",
        }:
            current = await campaigns.find_one({"_id": identifier, **scope})
            event = workspace._cancel.get((current or {}).get("active_job_id"))
            await campaigns.update_one(
                {"_id": identifier, **scope, "_recovery_token": token},
                {
                    "$set": {
                        "status": "running" if current and current["status"] == "running" else "paused",
                        "desired_status": "paused",
                        "recovery_error": {"code": exc.code},
                        "updated_at": _now(),
                    },
                    "$inc": {"version": 1},
                },
            )
            if current and current.get("active_job_id"):
                await workspace.jobs.update_one(
                    {
                        "_id": current["active_job_id"],
                        **scope,
                        "status": {"$in": ["queued", "running", "interrupted"]},
                    },
                    {"$set": {"cancel_requested": True}},
                )
                await workspace.jobs.update_one(
                    {"_id": current["active_job_id"], **scope, "status": "queued", "cancel_requested": True},
                    {"$set": {"status": "cancelled"}},
                )
            if event:
                event.set()
            return "blocked"
        if exc.status == 409:
            return "waiting"
        raise
    finally:
        await campaigns.update_one(
            {"_id": identifier, **scope, "_recovery_token": token},
            {
                "$set": {
                    "_recovery_due_at": _now() + timedelta(seconds=retry_delay),
                    "_recovery_until": _now(),
                },
                "$unset": {"_recovery_token": ""},
            },
        )


async def recover_studio_campaigns(*, limit=32):
    if type(limit) is not int or not 1 <= limit <= 32:
        raise ValueError("Campaign recovery sweep is bounded to32 records")
    await ensure_campaign_indexes()
    now = _now()
    rows = (
        await campaigns.find(
            {
                "auto_continue": True,
                "desired_status": "ready",
                "source_fenced": False,
                "status": {"$in": ["ready", "running", "interrupted"]},
                "authorization_expires_at": {"$gt": now},
                "$or": [{"_recovery_due_at": {"$exists": False}}, {"_recovery_due_at": {"$lte": now}}],
            }
        )
        .sort("updated_at", 1)
        .limit(limit)
        .max_time_ms(2000)
        .to_list(length=limit)
    )
    result = {"scanned": len(rows), "recovered": 0, "waiting": 0, "blocked": 0, "failures": 0}
    for row in rows:
        scope = workspace._scope(row["tenant_id"], row["owner_id"])
        try:
            state = await _recover_one(scope, row["campaign_id"])
            result[state if state in result else "waiting"] += 1
        except Exception as exc:
            result["failures"] += 1
            log.warning("Studio recovery %s stopped with %s", row["campaign_id"], type(exc).__name__)
    return result


async def authorize_campaign(scope, identifier, body):
    row = await _read(scope, identifier)
    receipt_id = _key(identifier, "campaign-authorization", body["idempotency_key"])
    request_digest = _digest(body)
    receipt = await round_records.find_one({"_id": receipt_id, **scope})
    if receipt and receipt["request_digest"] != request_digest:
        raise GameLearningError("idempotency_conflict", "Authorization key binds different input.", 409)
    applied = bool(receipt and receipt.get("applied")) or row.get("_last_authorization_receipt") == receipt_id
    if not applied:
        if row["version"] != body["expected_campaign_version"]:
            raise GameLearningError(
                "campaign_conflict", "Reload campaign before changing execution authorization.", 409
            )
        if row.get("_last_authorization_receipt"):
            await round_records.update_one(
                {"_id": row["_last_authorization_receipt"], **scope, "kind": "command"},
                {"$set": {"applied": True}},
            )
        if receipt is None:
            await workspace._admit(scope, "game-studio-authorization", receipt_id, len(_json(body, 8192)))
            await round_records.update_one(
                {"_id": receipt_id},
                {
                    "$setOnInsert": {
                        "_id": receipt_id,
                        **scope,
                        "kind": "command",
                        "campaign_id": identifier,
                        "project_id": row["project_id"],
                        "request_digest": request_digest,
                        "request": dict(body),
                        "expires_at": _now() + timedelta(seconds=body["authorization_seconds"]),
                        "created_at": _now(),
                    }
                },
                upsert=True,
            )
            receipt = await round_records.find_one({"_id": receipt_id, **scope})
        if receipt is None or receipt["request_digest"] != request_digest:
            raise GameLearningError("idempotency_conflict", "Authorization receipt differs.", 409)
        changed = await campaigns.update_one(
            {"_id": identifier, **scope, "version": row["version"], "source_fenced": False},
            {
                "$set": {
                    "auto_continue": body["auto_continue"],
                    "authorization_expires_at": receipt["expires_at"],
                    "_last_authorization_receipt": receipt_id,
                    "_recovery_due_at": _now(),
                    "updated_at": _now(),
                },
                "$inc": {"version": 1},
            },
        )
        if not changed.modified_count:
            current = await campaigns.find_one({"_id": identifier, **scope})
            if current.get("_last_authorization_receipt") != receipt_id:
                raise GameLearningError("campaign_conflict", "Authorization lost its version fence.", 409)
    await round_records.update_one(
        {"_id": receipt_id, **scope, "request_digest": request_digest}, {"$set": {"applied": True}}
    )
    if body["auto_continue"]:
        await _recover_one(scope, identifier)
    return await inspect(scope, identifier)


async def _champion_handoff(scope, row):
    from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest
    from skeleton.jeeves.game_studio_learning import digest as runtime_digest

    await _repair(scope, row)
    snapshot = row.get("snapshot") or {}
    if (
        not snapshot
        or snapshot.get("snapshot_digest")
        != runtime_digest({k: v for k, v in snapshot.items() if k != "snapshot_digest"})
        or snapshot.get("cursor") != row["cursor"]
    ):
        raise GameLearningError(
            "champion_snapshot_unavailable", "A complete current champion snapshot is required.", 409
        )
    request = GameEnvironmentRequest.from_dict(workspace._stored_evidence(snapshot["champion_request"]))
    if request.digest != snapshot["champion_request_digest"]:
        raise GameLearningError("champion_snapshot_corrupt", "Champion request identity differs.", 503)
    result = {
        "round_index": None,
        "round_digest": None,
        "request_digest": request.digest,
        "policy_digest": snapshot["champion_policy_digest"],
        "tree_digest": None,
        "files": [],
        "eligible_for_adoption": False,
        "reason": "No accepted current champion round.",
        "target_id": request.target_id,
        "kind": request.kind,
        "source_changed_from_admission": dict(request.tree or {})
        != dict(row["environment_request"].get("tree") or {}),
    }
    record = await round_records.find_one(
        {
            **scope,
            "campaign_id": row["campaign_id"],
            "kind": "round",
            "round_index": {"$lte": row["cursor"]},
            "report.champion_promoted": True,
            "report.candidate_digest": request.digest,
        },
        sort=[("round_index", -1)],
    )
    if record is None:
        return result
    report = _checked_round_record(row, record)
    if report.get("roles", {}).get("jeeves", {}).get("policy_digest") != snapshot["champion_policy_digest"]:
        raise GameLearningError(
            "champion_policy_corrupt", "Current champion policy differs from its exact issued promotion.", 503
        )
    result.update(round_index=report["round_index"], round_digest=report["round_digest"])
    if request.kind not in {"successor", "console_editor", "studio"} or not request.tree:
        result["reason"] = "This runtime champion has no editable typed source handoff."
        return result
    project = await workspace._project(row["project_id"], scope, row["binding"]["project_version"])
    tree = {item["path"]: item["content"] for item in project["files"]}
    tree.update(
        {
            path: content
            for path, content in request.tree.items()
            if path != "game/editor/source_manifest.json"
        }
    )
    if request.kind == "successor":
        import json
        from skeleton.jeeves.game_successor_runtime import emit_successor_project

        tree.update(emit_successor_project(json.loads(tree["game/successor/spec.json"])))
    files = [{"path": path, "content": content} for path, content in sorted(tree.items())]
    from core.game_learning import _files

    _files(files)
    _json({"files": files}, 1048576)
    changed = result["source_changed_from_admission"]
    result.update(
        files=files,
        tree_digest=_digest(tree),
        eligible_for_adoption=changed,
        reason=None if changed else "Policy-only gains do not change the admitted source tree.",
    )
    return result


async def champion(scope, identifier):
    row = await _read(scope, identifier)
    handoff = await _champion_handoff(scope, row)
    return {
        "campaign_id": identifier,
        "campaign_version": row["version"],
        "cursor": row["cursor"],
        "champion": handoff,
        "scope": "measured_champion_source_only",
        "production_promotion_authorized": False,
    }


async def adopt_champion(scope, identifier, body):
    receipt_id = _key(identifier, "champion-handoff", body["idempotency_key"])
    request_digest = _digest(body)
    receipt = await round_records.find_one({"_id": receipt_id, **scope, "kind": "champion_handoff"})
    row = await _read(
        scope,
        identifier,
        historical=receipt is not None,
        allowed_editor_operation_id=(
            None
            if receipt is None
            else _key(receipt["project_id"], "editor", receipt["evidence"]["editor"]["idempotency_key"])
        ),
    )
    if receipt is None:
        if row["version"] != body["expected_campaign_version"]:
            raise GameLearningError(
                "campaign_conflict", "Reload the current champion before adopting source.", 409
            )
        if row["status"] == "running" or (row.get("active_job_id") in workspace._tasks):
            raise GameLearningError(
                "campaign_worker_busy", "Pause and drain the campaign before adopting source.", 409
            )
        handoff = await _champion_handoff(scope, row)
        if not handoff["eligible_for_adoption"] or handoff["round_digest"] != body["champion_round_digest"]:
            raise GameLearningError(
                "champion_handoff_stale", "An exact accepted current editable champion is required.", 409
            )
        project = await workspace._project(row["project_id"], scope, body["expected_version"])
        entrypoint = {
            "successor": "game/successor/spec.json",
            "console_editor": "game/editor/console.json",
            "studio": "game/studio/session.json",
        }[handoff["kind"]]
        editor = {
            "expected_version": body["expected_version"],
            "idempotency_key": "studio-champion:" + receipt_id,
            "files": handoff["files"],
            "entrypoint": entrypoint,
            "_derived_sources": [
                {**ref, "project_id": row["project_id"]} for ref in row["binding"]["sources"]
            ]
            + row["binding"].get("external_sources", [])
            + row["binding"].get("derived_sources", []),
            "_derived_demonstrations": row["binding"].get("derived_demonstrations", [])
            + [
                {**ref, "project_id": row["project_id"], "tree_digest": row["binding"]["tree_digest"]}
                for ref in row["binding"].get("demonstrations", [])
                + row["binding"].get("inherited_demonstrations", [])
            ],
        }
        policy_sources, policy_teachers = await _policy_dependencies(scope, row)
        editor["_derived_sources"] += policy_sources
        editor["_derived_demonstrations"] += policy_teachers
        for name in ("_derived_sources", "_derived_demonstrations"):
            editor[name] = list({_digest(ref): ref for ref in editor[name]}.values())
            if len(editor[name]) > 64:
                raise GameLearningError(
                    "champion_lineage_limit", "Champion handoff source/teacher references exceed64.", 413
                )
        await workspace._derived_demonstration_authority(
            scope, {"derived_demonstrations": editor["_derived_demonstrations"]}
        )
        evidence = {
            "schema_version": "skeleton.game.studio_champion_handoff.v1",
            "campaign_id": identifier,
            "project_id": project["project_id"],
            "campaign_version": row["version"],
            "cursor": row["cursor"],
            "snapshot_digest": row["snapshot"]["snapshot_digest"],
            "source_digest": row["context"]["source_digest"],
            "code_digest": row["code_digest"],
            "handoff": handoff,
            "editor": editor,
        }
        await workspace._admit(scope, "game-studio-champion", receipt_id, len(_json(evidence, 2097152)))
        await round_records.update_one(
            {"_id": receipt_id},
            {
                "$setOnInsert": {
                    "_id": receipt_id,
                    **scope,
                    "kind": "champion_handoff",
                    "campaign_id": identifier,
                    "project_id": row["project_id"],
                    "request_digest": request_digest,
                    "evidence": evidence,
                    "evidence_digest": _digest(evidence),
                    "created_at": _now(),
                }
            },
            upsert=True,
        )
        receipt = await round_records.find_one({"_id": receipt_id, **scope})
    if receipt is None or receipt["request_digest"] != request_digest:
        raise GameLearningError("idempotency_conflict", "Champion handoff key binds different input.", 409)
    evidence = receipt["evidence"]
    _json(evidence, 2097152)
    if (
        _digest(evidence) != receipt["evidence_digest"]
        or evidence["campaign_id"] != identifier
        or evidence["project_id"] != row["project_id"]
        or evidence["handoff"]["round_digest"] != body["champion_round_digest"]
    ):
        raise GameLearningError("champion_handoff_corrupt", "Stored source handoff differs.", 503)

    async def publish():
        current = await _read(
            scope,
            identifier,
            historical=True,
            dragon_guarded=True,
            allowed_editor_operation_id=_key(
                row["project_id"], "editor", evidence["editor"]["idempotency_key"]
            ),
        )
        if current.get("_champion_handoff_receipt") != receipt_id:
            changed = await campaigns.update_one(
                {
                    "_id": identifier,
                    **scope,
                    "version": evidence["campaign_version"],
                    "cursor": evidence["cursor"],
                    "status": {"$ne": "running"},
                    "source_fenced": False,
                    "$or": [
                        {"_champion_handoff_receipt": {"$exists": False}},
                        {"_champion_handoff_receipt": receipt_id},
                    ],
                },
                {
                    "$set": {
                        "status": "paused",
                        "desired_status": "paused",
                        "_champion_handoff_receipt": receipt_id,
                        "updated_at": _now(),
                    },
                    "$inc": {"version": 1},
                },
            )
            if not changed.modified_count:
                raise GameLearningError(
                    "champion_handoff_stale", "Champion changed before source handoff was reserved.", 409
                )
        await _read(
            scope,
            identifier,
            historical=True,
            dragon_guarded=True,
            allowed_editor_operation_id=_key(
                row["project_id"], "editor", evidence["editor"]["idempotency_key"]
            ),
        )
        await workspace._derived_demonstration_authority(
            scope,
            {"derived_demonstrations": evidence["editor"]["_derived_demonstrations"]},
            dragon_guarded=True,
            allowed_editor_operation_id=_key(
                row["project_id"], "editor", evidence["editor"]["idempotency_key"]
            ),
        )
        return await workspace.save_editor(scope, row["project_id"], evidence["editor"])

    guard_binding = {**row["binding"], "derived_sources": evidence["editor"]["_derived_sources"]}
    project = await workspace._guarded_write(scope, guard_binding, publish)
    await campaigns.update_one(
        {"_id": identifier, **scope, "_champion_handoff_receipt": receipt_id},
        {"$set": {"_champion_handoff_completed": True}},
    )
    return {
        "campaign": await inspect(scope, identifier),
        "project": project,
        "handoff": {k: v for k, v in evidence.items() if k != "editor"},
        "source_only": True,
        "policy_promoted": False,
    }


async def export_champion(scope, identifier):
    data = await champion(scope, identifier)
    if not data["champion"]["files"] or not data["champion"]["round_digest"]:
        raise GameLearningError(
            "champion_export_unavailable", "No accepted editable champion source is available.", 409
        )
    content = _json(data, 2097152).decode("utf-8")
    return {
        "schema_version": "skeleton.game.studio_champion_export.v1",
        "filename": "champion-" + identifier + ".json",
        "media_type": "application/json",
        "content": content,
        "content_digest": hashlib.sha256(content.encode()).hexdigest(),
        "scope": "measured_champion_source_only",
        "attachments_embedded": False,
    }


async def _index_legacy_lessons(scope, project_id):
    records = (
        await lesson_records.find(
            {
                **scope,
                "project_id": project_id,
                "$or": [{"search_terms": {"$exists": False}}, {"context_digest": {"$exists": False}}],
            }
        )
        .sort("created_at", 1)
        .limit(64)
        .max_time_ms(2000)
        .to_list(length=64)
    )
    issuers = {}
    for record in records:
        try:
            if record["campaign_id"] not in issuers:
                issuers[record["campaign_id"]] = await _read(scope, record["campaign_id"], historical=True)
            lesson = _checked_lesson(issuers[record["campaign_id"]], record)
        except GameLearningError as exc:
            if exc.status in {403, 404}:
                continue
            raise
        derived = {"search_terms": _lesson_terms(lesson), "context_digest": _digest(record["context"])}
        await workspace._admit(
            scope,
            "game-studio-lesson-index",
            _key(record["_id"], "search-index", _digest(derived)),
            len(_json(derived, 8192)),
        )
        await lesson_records.update_one(
            {"_id": record["_id"], **scope, "lesson_digest": record["lesson_digest"]}, {"$set": derived}
        )


async def _policy_dependencies(scope, row, *, allowed_editor_operation_id=None, dragon_guarded=False):
    sources, teachers, seen = [], [], {}
    pending = [
        (pin.get("project_id", row["project_id"]), pin)
        for role in ("parent_policy", "generation_policy", "review_policy")
        if (pin := row["binding"].get(role))
    ]
    while pending:
        project_id, pin = pending.pop()
        key = (project_id, pin["policy_id"])
        if key in seen:
            if seen[key] != pin["snapshot_digest"]:
                raise GameLearningError(
                    "parent_policy_changed", "One ancestor binds conflicting policy identities.", 403
                )
            continue
        if len(seen) >= 64:
            raise GameLearningError("policy_lineage_limit", "Historical policy ancestry exceeds64.", 413)
        policy = await workspace._admitted_policy(
            scope,
            project_id,
            pin["policy_id"],
            allow_environment_changed=True,
            dragon_guarded=dragon_guarded,
            **(
                {"allowed_editor_operation_id": allowed_editor_operation_id}
                if allowed_editor_operation_id
                else {}
            ),
        )
        if policy["snapshot"]["snapshot_digest"] != pin["snapshot_digest"]:
            raise GameLearningError("parent_policy_changed", "Original policy identity differs.", 403)
        seen[key] = pin["snapshot_digest"]
        binding = policy["input"]
        sources += (
            [{**ref, "project_id": project_id} for ref in binding["sources"]]
            + binding.get("derived_sources", [])
            + binding.get("external_sources", [])
        )
        teachers += binding.get("derived_demonstrations", []) + [
            {**ref, "project_id": project_id, "tree_digest": binding["tree_digest"]}
            for ref in binding.get("demonstrations", []) + binding.get("inherited_demonstrations", [])
        ]
        pending.extend(
            (parent.get("project_id", project_id), parent)
            for role in ("parent_policy", "generation_policy", "review_policy")
            if (parent := binding.get(role))
        )
    return list({_digest(ref): ref for ref in sources}.values()), list(
        {_digest(ref): ref for ref in teachers}.values()
    )


# Read-only spectator simulations are never a write path to training state.
# This limits backend fan-out even when several users watch the same campaign.
async def _drain_studio_compute(future, cancel=None):
    """Do not cancel the underlying physical work on repeated caller cancellation."""
    cancelled = False
    while not future.done():
        try:
            await asyncio.shield(future)
        except asyncio.CancelledError:
            if future.cancelled():
                break
            cancelled = True
            if cancel is not None:
                cancel.set()
            continue
        except BaseException:
            break
    # Retrieve failures even when the caller was cancelled, without replacing
    # that caller's original exception during cleanup.
    if future.done() and not future.cancelled():
        future.exception()
    return cancelled


async def _run_studio_compute(scope, local_slots, operation):
    """Borrow one existing physical CPU credit for a bounded read-only probe."""
    from core.game_play import resource_profiles

    if local_slots.locked():
        raise GameLearningError(
            "studio_compute_busy", "This diagnostic is already running; retry later.", 409
        )
    # Semaphore.acquire does not yield when a permit is immediately available.
    # This local fan-out guard is separate from the shared physical admission.
    await local_slots.acquire()
    token, credit_ids, credit_id = str(uuid4()), [], None
    stopped, heartbeat_stopped, authority_lost = Event(), Event(), Event()
    worker = heartbeat = None
    try:
        profile = next(
            (item for item in resource_profiles()["profiles"] if item["profile_id"] == "cpu"), None
        )
        credit_ids = list(profile.get("training_credit_ids", ())) if profile else []
        if (
            profile is None
            or not profile["available"]
            or not credit_ids
            or len(credit_ids) > 8
            or len(set(credit_ids)) != len(credit_ids)
            or any(
                not isinstance(value, str) or not value.startswith("game-learning-actor:")
                for value in credit_ids
            )
        ):
            raise GameLearningError(
                "studio_compute_unavailable",
                "The existing CPU resource profile has no diagnostic capacity.",
                409,
            )
        for identity in credit_ids:
            await workspace.workers.update_one(
                {"_id": identity},
                {"$setOnInsert": {"lease_until": datetime(1970, 1, 1, tzinfo=timezone.utc)}},
                upsert=True,
            )
            claimed = await workspace.workers.find_one_and_update(
                {"_id": identity, "lease_until": {"$lt": _now()}},
                {
                    "$set": {
                        "worker_token": token,
                        "resource_class": "studio_probe",
                        "tenant_id": scope["tenant_id"],
                        "owner_id": scope["owner_id"],
                        "lease_until": _now() + timedelta(seconds=30),
                    },
                    "$unset": {"job_id": "", "play_id": "", "credit_kind": ""},
                },
                return_document=ReturnDocument.AFTER,
            )
            if claimed is not None:
                credit_id = identity
                break
        if credit_id is None:
            raise GameLearningError(
                "studio_compute_busy",
                "Existing CPU credits are occupied by play, training or diagnostics; retry later.",
                409,
            )

        async def renew_credit():
            while not heartbeat_stopped.is_set():
                try:
                    await asyncio.sleep(1)
                    renewed = await workspace.workers.update_one(
                        {
                            "_id": credit_id,
                            "worker_token": token,
                            "resource_class": "studio_probe",
                            "lease_until": {"$gt": _now()},
                        },
                        {"$set": {"lease_until": _now() + timedelta(seconds=30)}},
                    )
                    if renewed.matched_count != 1:
                        authority_lost.set()
                        stopped.set()
                        return
                except asyncio.CancelledError:
                    stopped.set()
                    # Even shutdown cancellation must not end the heartbeat
                    # before the guarded executor has physically quiesced.
                    if heartbeat_stopped.is_set():
                        return
                except Exception:
                    authority_lost.set()
                    stopped.set()
                    return

        heartbeat = asyncio.create_task(renew_credit())
        worker = asyncio.get_running_loop().run_in_executor(None, lambda: operation(stopped))
        try:
            result = await asyncio.shield(worker)
        except asyncio.CancelledError:
            stopped.set()
            raise
        if authority_lost.is_set():
            raise GameLearningError(
                "studio_compute_fenced",
                "Diagnostic capacity authority was lost; no result is published.",
                409,
            )
        live = await workspace.workers.find_one(
            {
                "_id": credit_id,
                "worker_token": token,
                "resource_class": "studio_probe",
                "tenant_id": scope["tenant_id"],
                "owner_id": scope["owner_id"],
                "lease_until": {"$gt": _now()},
            },
            {"_id": 1},
        )
        if live is None:
            raise GameLearningError(
                "studio_compute_fenced", "Diagnostic capacity authority expired; no result is published.", 409
            )
        return result
    except PyMongoError as exc:
        raise GameLearningError(
            "studio_compute_storage_unavailable",
            "Diagnostic capacity could not be confirmed; retry later.",
            503,
        ) from exc
    finally:
        # Drain before cancelling the heartbeat or releasing shared capacity.
        # Most pure helpers have no cancellation hook and finish finite work.
        cancelled_while_draining = False
        if worker is not None and not worker.done():
            cancelled_while_draining = await _drain_studio_compute(worker, stopped)
        stopped.set()
        heartbeat_stopped.set()
        if heartbeat is not None:
            heartbeat.cancel()
            cancelled_while_draining |= await _drain_studio_compute(heartbeat)

        async def release_credit():
            if credit_ids:
                try:
                    # Also covers a cancelled/lost acknowledgement of claim.
                    await workspace.workers.update_many(
                        {"_id": {"$in": credit_ids}, "worker_token": token, "resource_class": "studio_probe"},
                        {
                            "$set": {"lease_until": _now()},
                            "$unset": {
                                "worker_token": "",
                                "resource_class": "",
                                "tenant_id": "",
                                "owner_id": "",
                            },
                        },
                    )
                except PyMongoError:
                    log.warning("Studio diagnostic credit release awaits lease expiry")

        cleanup = asyncio.create_task(release_credit())
        try:
            cancelled_while_draining |= await _drain_studio_compute(cleanup)
        finally:
            local_slots.release()
        if cancelled_while_draining:
            raise asyncio.CancelledError


_scenario_spectator_slots = asyncio.Semaphore(2)


async def scenario_mirror_views(scope, identifier, *, lanes=10, steps=12, sample=0):
    """Owner-authorized, bounded parallel replay telemetry while campaigns train."""
    from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest
    from skeleton.jeeves.game_studio_environment import parse_studio_source
    from skeleton.jeeves.game_studio_scenario_lab import ANGLES, mirrored_simulations

    if (
        type(lanes) is not int
        or not 1 <= lanes <= 10
        or type(steps) is not int
        or not 1 <= steps <= 24
        or type(sample) is not int
        or not 0 <= sample <= 255
    ):
        raise GameLearningError("spectator_bounds", "Bounded spectator controls required.", 422)
    row = await _read(scope, identifier)
    latest = (row.get("snapshot") or {}).get("champion_request")
    executable = GameEnvironmentRequest.from_dict(latest or row["environment_request"])
    if executable.kind != "studio" or executable.target_id != row["environment_request"]["target_id"]:
        raise GameLearningError(
            "spectator_engine",
            "Only original-engine studio campaigns have mirrored reference telemetry.",
            409,
        )
    source = parse_studio_source(__import__("json").loads(executable.tree["game/studio/session.json"]))
    # Sampling advances spectator seeds only, not campaign/training RNG or rows.
    seed = (row["config"]["seed"] + row["cursor"] * 257 + sample * 7) % (2**31 - 16)
    result = await _run_studio_compute(
        scope,
        _scenario_spectator_slots,
        lambda _cancel: mirrored_simulations(
            source,
            seed=seed,
            steps=steps,
            angles=ANGLES[:lanes],
            workers=1,
        ),
    )
    await _read(scope, identifier)
    return {
        **result,
        "campaign_id": identifier,
        "campaign_cursor": row["cursor"],
        "ten_pass_audits_verified": result["scrutiny_checked_runs"] == len(result["lanes"]),
        "spectral_hardware_available": False,
        "campaign_status": row["status"],
        "sample": sample,
        "spectator_only": True,
        "frames_show_training_episodes": False,
        "native_gameplay_rendering_claimed": False,
    }


async def scenario_drafts(scope, identifier, *, limit=4):
    """Draft original possible scenarios from actual committed campaign signals."""
    from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest
    from skeleton.jeeves.game_studio_environment import parse_studio_source
    from skeleton.jeeves.game_studio_scenario_lab import propose_scenarios

    if type(limit) is not int or not 1 <= limit <= 5:
        raise GameLearningError("scenario_bounds", "Scenario draft limit outside bounds.", 422)
    row = await _read(scope, identifier)
    req = GameEnvironmentRequest.from_dict(
        (row.get("snapshot") or {}).get("champion_request") or row["environment_request"]
    )
    if req.kind != "studio":
        raise GameLearningError(
            "scenario_engine", "This campaign does not run an original studio engine.", 409
        )
    source = parse_studio_source(__import__("json").loads(req.tree["game/studio/session.json"]))
    records = (
        await round_records.find(
            {
                **scope,
                "campaign_id": identifier,
                "kind": "round",
                "round_index": {"$lte": row["cursor"]},
            }
        )
        .sort("round_index", -1)
        .limit(16)
        .to_list(length=16)
    )
    measured = []
    already_explored = set()
    for item in records:
        checked = _checked_round_record(row, item)
        mutation = checked.get("mutation") or {}
        for edit in mutation.get("changes", []):
            if type(edit) is not dict:
                continue
            value = edit.get("source_after_digest")
            if type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value):
                already_explored.add(value)
        # Only recorded measurements, never user-supplied invented labels.
        vector = checked.get("objective_vector") or {}
        candidate_metrics = vector.get("candidate") or {}
        role = (checked.get("roles") or {}).get("jeeves") or {}
        play = role.get("play") or {}
        value = candidate_metrics.get("return", play.get("return", 0))
        if type(value) not in (int, float) or not __import__("math").isfinite(value):
            value = 0
        survival = candidate_metrics.get("survival")
        if type(survival) not in (int, float) or not 0 <= survival <= 1:
            failure = 1.0 if play.get("dead") is True else 0.0
        else:
            failure = 1.0 - float(survival)
        episodes = role.get("actual_training_episodes", 1)
        if type(episodes) is not int or not 1 <= episodes <= 4:
            episodes = 1
        measured.append(
            {
                "mean_return": max(-1e9, min(1e9, float(value))),
                "failure_rate": failure,
                "episodes": episodes,
            }
        )
    result = propose_scenarios(
        source,
        observations=measured,
        limit=limit,
        excluded_source_digests=sorted(already_explored),
    )
    return {
        **result,
        "campaign_id": identifier,
        "measured_committed_rounds": len(measured),
        "already_explored_rule_variants": len(already_explored),
        "current_champion_source": True,
        "drafts_only": True,
        "no_automatic_gameplay_promotion": True,
    }


async def scenario_engine_test_manifest(scope, editor):
    """Authenticated inspect-only test matrix; pass status is never fabricated."""
    from skeleton.jeeves.game_studio_scenario_lab import test_manifest
    from skeleton.jeeves.game_learning import GameLearningError as LearnerError

    try:
        return test_manifest(editor)
    except (ValueError, LearnerError) as exc:
        raise GameLearningError("test_manifest_engine", "Unknown studio engine.", 404) from exc


_engine_probe_slots = asyncio.Semaphore(1)


async def engine_probe_page(scope, editor, *, offset=0, limit=8):
    """Read-only, owner-authenticated executable controls, never synthetic pass."""
    if type(offset) is not int or not 0 <= offset <= 100000 or type(limit) is not int or not 1 <= limit <= 16:
        raise GameLearningError("engine_test_bounds", "Engine diagnostics page exceeds safe limits.", 422)
    from skeleton.jeeves.game_studio_engine_diagnostics import (
        run_engine_contract_diagnostics,
        engine_action_diagnostics,
    )
    from skeleton.jeeves.game_studio_scenario_lab import ScenarioLabError
    from skeleton.jeeves.game_studio_engine_diagnostics import EngineDiagnosticsError

    try:
        contract, actions = await _run_studio_compute(
            scope,
            _engine_probe_slots,
            lambda _cancel: (
                run_engine_contract_diagnostics(editor),
                engine_action_diagnostics(editor, offset=offset, limit=limit),
            ),
        )
    except (ScenarioLabError, EngineDiagnosticsError, ValueError) as exc:
        raise GameLearningError(
            "engine_test_failed",
            "Actual engine diagnostic failed; no verified pass is claimed.",
            409,
        ) from exc
    return {
        "engine": editor,
        "contract": contract,
        "actions": actions,
        "release_certified": False,
        "full_engine_state_exhausted": False,
    }


_shadow_audit_slots = asyncio.Semaphore(1)


async def scenario_shadow_audit(
    scope,
    identifier,
    *,
    angle="explore",
    steps=2,
    max_cycles=12,
    replay_budget=600,
):
    """Owner-scoped, read-only, bounded one-sim shadow convergence probe."""
    from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest
    from skeleton.jeeves.game_studio_environment import parse_studio_source
    from skeleton.jeeves.game_studio_scenario_lab import ANGLES
    from skeleton.jeeves.game_studio_shadow_saturation import (
        run_shadow_saturation,
        verify_shadow_receipts,
    )

    if (
        type(angle) is not str
        or angle not in ANGLES
        or type(steps) is not int
        or not 1 <= steps <= 4
        or type(max_cycles) is not int
        or not 10 <= max_cycles <= 16
        or type(replay_budget) is not int
        or not 100 <= replay_budget <= 1000
    ):
        raise GameLearningError("shadow_limits", "Source-bound shadow audit budget exceeded.", 422)
    row = await _read(scope, identifier)
    candidate = (row.get("snapshot") or {}).get("champion_request")
    request = GameEnvironmentRequest.from_dict(candidate or row["environment_request"])
    if request.kind != "studio" or request.target_id != row["environment_request"]["target_id"]:
        raise GameLearningError(
            "shadow_source", "Only owner-registered original studios admit shadow reviews.", 409
        )
    source = parse_studio_source(__import__("json").loads(request.tree["game/studio/session.json"]))
    seed = (row["config"]["seed"] + row["cursor"] * 101) % (2**31 - 12000)
    result = await _run_studio_compute(
        scope,
        _shadow_audit_slots,
        lambda cancel: run_shadow_saturation(
            source,
            seed=seed,
            steps=steps,
            angles=(angle,),
            workers=1,
            max_cycles_per_sim=max_cycles,
            max_replay_work_per_sim=replay_budget,
            train_policy=False,
            cancel=cancel.is_set,
        ),
    )
    await _read(scope, identifier)
    if not verify_shadow_receipts(result):
        raise GameLearningError("shadow_evidence", "Shadow receipt chain verification failed.", 409)
    return {
        **result,
        "campaign_id": identifier,
        "campaign_cursor": row["cursor"],
        "spectator_only": True,
        "training_weight_changes": False,
        "complete_run_proof_scope": "ten_consecutive_zero_gain_cycles_only_if_reached",
        "native_spectral_camera_claim": False,
    }


_multifactor_probe_slots = asyncio.Semaphore(1)


async def _multifactor_original_source(scope, identifier):
    from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest
    from skeleton.jeeves.game_studio_environment import parse_studio_source

    row = await _read(scope, identifier)
    pinned = (row.get("snapshot") or {}).get("champion_request")
    req = GameEnvironmentRequest.from_dict(pinned or row["environment_request"])
    if req.kind != "studio" or req.target_id != row["environment_request"]["target_id"]:
        raise GameLearningError(
            "multifactor_source",
            "Multi-factor training requires an authorized original-game studio source.",
            409,
        )
    source = parse_studio_source(__import__("json").loads(req.tree["game/studio/session.json"]))
    return row, source


async def multifactor_control_catalog(scope, identifier):
    from skeleton.jeeves.game_studio_multifactor import multifactor_capabilities

    row, source = await _multifactor_original_source(scope, identifier)
    return {
        **multifactor_capabilities(source),
        "campaign_id": identifier,
        "campaign_cursor": row["cursor"],
        "automatic_neural_training": False,
        "native_multimedia_simulation_assumed": False,
    }


async def multifactor_plan_preview(scope, identifier, *, axis_offset=0, count=6, order=3):
    from skeleton.jeeves.game_studio_multifactor import (
        plan_multifactor_scenarios,
        MultiFactorError,
    )

    if (
        type(axis_offset) is not int
        or not 0 <= axis_offset <= 63
        or type(count) is not int
        or not 2 <= count <= 8
        or type(order) is not int
        or order not in (2, 3)
    ):
        raise GameLearningError("multifactor_limits", "Factor design bounds differ.", 422)
    row, source = await _multifactor_original_source(scope, identifier)
    try:
        design = await _run_studio_compute(
            scope,
            _multifactor_probe_slots,
            lambda _cancel: plan_multifactor_scenarios(
                source,
                interaction_order=order,
                axis_offset=axis_offset,
                max_scenarios=count,
            ),
        )
        await _read(scope, identifier)
    except MultiFactorError as exc:
        raise GameLearningError(
            "multifactor_plan",
            "No source-legal combination is available in the selected control bank.",
            409,
        ) from exc
    return {
        **design,
        "campaign_id": identifier,
        "campaign_cursor": row["cursor"],
        "training_performed": False,
        "production_neural_weights_changed": False,
    }


async def multifactor_verified_experiments(
    scope,
    identifier,
    *,
    axis_offset=0,
    count=2,
    steps=2,
):
    """Authorized campaign owner requests audited source-control experiments only.

    Separate CLI needs explicit operator rights to update local Q candidates.
    Network reader never promotes weights, adopts worlds, or trains models.
    """
    from skeleton.jeeves.game_studio_multifactor import (
        execute_multifactor_scenarios,
        MultiFactorError,
    )

    if (
        type(axis_offset) is not int
        or not 0 <= axis_offset <= 63
        or type(count) is not int
        or not 2 <= count <= 3
        or type(steps) is not int
        or not 1 <= steps <= 4
    ):
        raise GameLearningError("multifactor_limits", "Factor experiment budgets exceeded.", 422)
    row, source = await _multifactor_original_source(scope, identifier)
    seed = (row["config"]["seed"] + row["cursor"] * 163) % (2**31 - 22000)
    try:
        result = await _run_studio_compute(
            scope,
            _multifactor_probe_slots,
            lambda _cancel: execute_multifactor_scenarios(
                source,
                interaction_order=3,
                axis_offset=axis_offset,
                max_scenarios=count,
                steps=steps,
                seed=seed,
                train=False,
            ),
        )
        await _read(scope, identifier)
    except MultiFactorError as exc:
        raise GameLearningError(
            "multifactor_execution",
            "A source-verified multi-factor experiment could not be completed.",
            409,
        ) from exc
    return {
        **result,
        "campaign_id": identifier,
        "campaign_cursor": row["cursor"],
        "spectator_only": True,
        "actual_production_weights_changed": False,
    }
