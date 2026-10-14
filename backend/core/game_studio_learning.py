"""Durable, bounded studio campaigns using the existing governed job authority."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import timedelta
from pathlib import Path

from pymongo import ReturnDocument

from core.game_learning import GameLearningError, _digest, _json, _key, _now, _public, workspace
from core.game_successor import _execute_thread

campaigns = workspace.database["game_learning_campaigns"]
round_records = workspace.database["game_learning_rounds"]
lesson_records = workspace.database["game_learning_lessons"]
log = logging.getLogger(__name__)


def _code_digest():
    root = Path(__file__).resolve().parents[2] / "skeleton" / "jeeves"
    return _digest(
        {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in (
                "game_studio_learning.py",
                "game_learning.py",
                "game_learning_parallel.py",
                "game_learning_demonstrations.py",
                "game_learning_runtime.py",
                "game_console_editor.py",
                "game_console_simulation.py",
                "game_console_assets.py",
                "game_successor_runtime.py",
                "game_successor_world.py",
                "game_successor_assets.py",
                "game_emulator_host.py",
                "game_emulator_worker.py",
                "game_emulator_catalog.py",
                "game_style_analysis.py",
            )
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


async def _read(scope, identifier, *, historical=False):
    row = await campaigns.find_one({"_id": identifier, **scope})
    if row is None:
        raise GameLearningError("campaign_not_found", "Owned learning campaign not found.", 404)
    if historical:
        dependencies = [{**ref, "project_id": row["project_id"]} for ref in row["binding"]["sources"]]
        dependencies += row["binding"].get("derived_sources", [])
        await workspace._external_authority(scope, {"derived_sources": dependencies})
        await workspace._derived_demonstration_authority(scope, row["binding"])
        if row["binding"].get("demonstrations") or row["binding"].get("inherited_demonstrations"):
            await workspace._demonstration_authority(scope, row["binding"])
    else:
        if row.get("source_fenced"):
            raise GameLearningError(
                "campaign_source_withdrawn", "Campaign source authority was withdrawn.", 403
            )
        await workspace._authority(scope, row["binding"])
        if _code_digest() != row["code_digest"]:
            raise GameLearningError(
                "campaign_code_changed", "Campaign runtime code changed; start a fresh campaign.", 409
            )
    return row


def _checked_report(row, report):
    from skeleton.jeeves.game_studio_learning import digest as runtime_digest

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

    lesson = record["lesson"]
    _json(lesson, 262144)
    if record["lesson_digest"] != _digest(lesson) or record["context"] != row["context"]:
        raise GameLearningError("lesson_evidence_corrupt", "Committed lesson evidence differs.", 503)
    try:
        checked = validate_lesson(lesson, context_digest=runtime_digest(row["context"]))
    except (ValueError, RuntimeError) as exc:
        raise GameLearningError("lesson_evidence_corrupt", "Committed lesson schema differs.", 503) from exc
    if checked["round_index"] != record["round_index"] or checked["round_index"] > row["cursor"]:
        raise GameLearningError("lesson_evidence_corrupt", "Lesson cursor differs.", 503)
    return checked


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

    records = (
        await lesson_records.find(
            {**scope, **{"context." + k: context[k] for k in ("target_id", "genre", "engine", "code_digest")}}
        )
        .sort("created_at", -1)
        .limit(128)
        .to_list(length=128)
    )
    priors, source_refs, teacher_refs, seen = (
        [],
        list(binding.get("derived_sources", [])),
        list(binding.get("derived_demonstrations", [])),
        set(),
    )
    for record in records:
        if record["context"].get("source_digest") == context["source_digest"]:
            continue
        try:
            origin = await _read(scope, record["campaign_id"], historical=True)
        except GameLearningError as exc:
            if exc.status in {403, 404, 409}:
                continue
            raise
        lesson = _checked_lesson(origin, record)
        if lesson["lesson_digest"] in seen:
            continue
        round_row = await round_records.find_one(
            {"_id": origin["campaign_id"] + ":" + str(record["round_index"]), **scope, "kind": "round"}
        )
        if round_row is None or _digest(lesson) not in {
            _digest(v) for v in _checked_round_record(origin, round_row)["lessons"]
        }:
            raise GameLearningError(
                "lesson_issuer_missing", "Proposal lesson lacks exact committed round evidence.", 503
            )
        prior = make_proposal_prior(lesson, origin_context=origin["context"], destination_context=context)
        original = origin["binding"]
        refs = [{**v, "project_id": origin["project_id"]} for v in original["sources"]] + original.get(
            "derived_sources", []
        )
        merged_sources = {(v["project_id"], v["source_id"]): v for v in source_refs + refs}
        teachers = list(original.get("derived_demonstrations", []))
        teachers += [
            {**v, "project_id": origin["project_id"], "tree_digest": original["tree_digest"]}
            for v in original.get("demonstrations", []) + original.get("inherited_demonstrations", [])
        ]
        merged_teachers = {v["recording_id"]: v for v in teacher_refs + teachers}
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
        episode_steps=body["max_steps"],
        seed=body["seed"],
    )
    binding = await workspace._input(scope, project, episode_steps=body["max_steps"])
    request = GameEnvironmentRequest.from_dict(await workspace.environment_request(scope, binding))
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
                else "native_observation" if request.kind == "libretro" else "reference"
            )
        ),
        "engine": request.kind,
        "engine_era": project["engine_era"],
        "source_digest": binding["tree_digest"],
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


async def pulse(scope, identifier, body):
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
    if (not same_intent and row["version"] != body["expected_campaign_version"]) or row["status"] not in {
        "ready",
        "interrupted",
        "running",
    }:
        raise GameLearningError(
            "campaign_conflict", "Reload a ready or interrupted campaign before pulsing.", 409
        )
    if row["status"] == "running" and not same_intent:
        raise GameLearningError("campaign_worker_busy", "Another slice is already admitted.", 409)
    if row["desired_status"] != "ready" or row["cursor"] >= row["round_limit"]:
        raise GameLearningError("campaign_complete", "Campaign is paused, cancelled or complete.", 409)
    if _time(row["authorization_expires_at"]) <= _now():
        raise GameLearningError(
            "campaign_authorization_expired", "Campaign execution authorization expired.", 403
        )
    if old and job_id in workspace._tasks:
        raise GameLearningError("campaign_worker_draining", "The previous worker is still quiescing.", 409)
    await _repair(scope, row)
    await workspace._admit(scope, "game-studio-pulse", receipt_id, 1024)
    if receipt is None:
        receipt = {
            "_id": receipt_id,
            **scope,
            "kind": "command",
            "project_id": row["project_id"],
            "campaign_id": identifier,
            "request_digest": body_digest,
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
    row = await campaigns.find_one({"_id": identifier, **scope})
    if row is None:
        raise GameLearningError("campaign_not_found", "Owned learning campaign not found.", 404)
    receipt_id = _key(identifier, "campaign-" + action, body["idempotency_key"])
    old = await round_records.find_one({"_id": receipt_id, **scope})
    if old:
        if old["request_digest"] != _digest(body):
            raise GameLearningError("idempotency_conflict", "Control key binds different input.", 409)
        return (
            _projection(await campaigns.find_one({"_id": identifier, **scope}))
            if action != "resume"
            else await inspect(scope, identifier)
        )
    if row["version"] != body["expected_campaign_version"]:
        raise GameLearningError("campaign_conflict", "Campaign changed; reload its current version.", 409)
    if action == "resume":
        await _read(scope, identifier)
        if row["status"] not in {"paused", "interrupted"}:
            raise GameLearningError(
                "campaign_not_resumable", "Only a quiesced paused/interrupted campaign can resume.", 409
            )
        desired, status = "ready", "ready"
    else:
        desired = "paused" if action == "pause" else "cancelled"
        status = "running" if row["status"] == "running" else desired
    changed = await campaigns.update_one(
        {"_id": identifier, **scope, "version": row["version"]},
        {"$set": {"status": status, "desired_status": desired, "updated_at": _now()}, "$inc": {"version": 1}},
    )
    if not changed.modified_count:
        raise GameLearningError("campaign_conflict", "Campaign control lost its version fence.", 409)
    if row.get("active_job_id") and action != "resume":
        await workspace.jobs.update_one(
            {"_id": row["active_job_id"], **scope, "status": {"$in": ["queued", "running", "interrupted"]}},
            {"$set": {"cancel_requested": True}},
        )
        await workspace.jobs.update_one(
            {"_id": row["active_job_id"], **scope, "status": "queued", "cancel_requested": True},
            {"$set": {"status": "cancelled"}},
        )
        event = workspace._cancel.get(row["active_job_id"])
        if event:
            event.set()
    await round_records.update_one(
        {"_id": receipt_id},
        {
            "$setOnInsert": {
                "_id": receipt_id,
                **scope,
                "kind": "command",
                "campaign_id": identifier,
                "request_digest": _digest(body),
            }
        },
        upsert=True,
    )
    value = (
        await inspect(scope, identifier)
        if action == "resume"
        else _projection(await campaigns.find_one({"_id": identifier, **scope}))
    )
    if action == "resume" and row.get("auto_continue") and value["status"] == "ready":
        started = await pulse(
            scope,
            identifier,
            {
                "expected_campaign_version": value["version"],
                "idempotency_key": "auto:resume:" + _digest(body["idempotency_key"]),
            },
        )
        return started["campaign"]
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
    from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest
    from skeleton.jeeves.game_studio_learning import CampaignConfig, StudioLearningCampaign

    row = await _read(scope, job["request"]["campaign_id"])
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
    request = GameEnvironmentRequest.from_dict(await workspace.environment_request(scope, row["binding"]))
    expected = GameEnvironmentRequest.from_dict(row["environment_request"])
    if request.digest != expected.digest:
        raise GameLearningError("campaign_environment_changed", "Campaign executable request changed.", 409)
    await _repair(scope, row)
    admitted_lessons = []
    records = (
        await lesson_records.find({**scope, "project_id": row["project_id"], "context": row["context"]})
        .sort("round_index", -1)
        .limit(32)
        .to_list(length=32)
    )
    seen_lessons = set()
    for record in records:
        issuer = await _read(scope, record["campaign_id"], historical=True)
        checked = _checked_lesson(issuer, record)
        if checked["lesson_digest"] not in seen_lessons:
            admitted_lessons.append(checked)
            seen_lessons.add(checked["lesson_digest"])
    loop = asyncio.get_running_loop()

    def run(authorize, event):
        campaign = StudioLearningCampaign(
            request,
            CampaignConfig(**row["config"]),
            row["context"],
            row["lineage"],
            policy_snapshot=row["policy_snapshot"],
            snapshot=row["snapshot"],
            lessons=list(reversed(admitted_lessons)),
            proposal_priors=row.get("proposal_priors", []),
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
            authorize=authorize,
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
        "remaining_rounds": current["round_limit"] - current["cursor"],
    }


async def rounds(scope, identifier, after=0, limit=32):
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


async def lessons(scope, project_id, query="", limit=32):
    project = await workspace._project(project_id, scope)
    rows = (
        await lesson_records.find({**scope, "project_id": project_id})
        .sort("round_index", -1)
        .limit(128)
        .to_list(length=128)
    )
    output = []
    for record in rows:
        issuer = await _read(scope, record["campaign_id"], historical=True)
        _checked_lesson(issuer, record)
        if query.casefold() not in _json(record["lesson"]).decode().casefold():
            continue
        output.append(
            {
                "lesson_id": record["_id"],
                "campaign_id": record["campaign_id"],
                "round_index": record["round_index"],
                "lesson_digest": record["lesson_digest"],
                "lesson": record["lesson"],
                "context": record["context"],
                "applicable_to_current_tree": record["context"]["tree_digest"] == _digest(project["files"])
                and record["context"]["code_digest"] == _code_digest(),
            }
        )
        if len(output) >= limit:
            break
    return {"lessons": output}


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
        if set(payload) - {"q", "limit"}:
            raise GameLearningError("campaign_payload_invalid", "Lesson search accepts q and limit only.")
        return await lessons(
            scope,
            command.project_id,
            str(payload.get("q", ""))[:256],
            min(32, max(1, int(payload.get("limit", 32)))),
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
        return await rounds(
            scope, identifier, int(payload.get("after", 0)), min(32, max(1, int(payload.get("limit", 32))))
        )
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
    identifier = job["request"]["campaign_id"]
    value = await inspect(scope, identifier)
    row = await _read(scope, identifier)
    from core.game_learning import _time

    if (
        not row.get("auto_continue")
        or row["status"] != "ready"
        or row["desired_status"] != "ready"
        or row["cursor"] >= row["round_limit"]
        or _time(row["authorization_expires_at"]) <= _now()
    ):
        return
    await pulse(
        scope,
        identifier,
        {
            "expected_campaign_version": value["version"],
            "idempotency_key": "auto:" + str(row["cursor"]) + ":" + str(job["worker_epoch"]),
        },
    )
