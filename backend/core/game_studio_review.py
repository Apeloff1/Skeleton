"""Scoped numerical inspection, under the existing workspace job authority."""

from __future__ import annotations

import asyncio
import hashlib
import json
from functools import partial

from core.game_learning import GameLearningError, _digest, _key, workspace
from skeleton.jeeves.game_studio_review import (
    MAX_RESULT,
    compare_executed_reviews,
    review_project_sequence,
    review_triangle,
)


async def _review_input(scope, project, binding, body):
    if body.get("policy_id"):
        saved = await workspace._admitted_policy(scope, project["project_id"], body["policy_id"])
        binding["review_policy"] = {
            "policy_id": body["policy_id"],
            "snapshot_digest": saved["snapshot"]["snapshot_digest"],
        }
    if body.get("baseline_review_job_id"):
        baseline = await _load_review(scope, project["project_id"], body["baseline_review_job_id"])
        if baseline["status"] != "completed":
            raise GameLearningError(
                "review_baseline_incomplete", "Choose a completed reference review.", 409
            )
        if baseline["input"].get("review_baseline"):
            raise GameLearningError(
                "review_baseline_chained",
                "Choose an original reference review without a baseline.",
                422,
            )
        binding["review_baseline"] = {
            "job_id": baseline["job_id"],
            "review_digest": baseline["result"]["review_digest"],
            "input_digest": _digest(baseline["input"]),
        }
        if baseline["input"].get("review_policy"):
            binding["review_baseline_policy"] = dict(baseline["input"]["review_policy"])
    binding["review_output_storage"] = await workspace._admit(
        scope,
        "game-studio-review-result",
        _key(project["project_id"], "review", body["idempotency_key"]),
        MAX_RESULT,
    )
    return binding


async def _policy(scope, job):
    pinned = job["input"].get("review_policy")
    if pinned is None:
        return None
    saved = await workspace._admitted_policy(scope, job["project_id"], pinned["policy_id"])
    if saved["snapshot"]["snapshot_digest"] != pinned["snapshot_digest"]:
        raise GameLearningError(
            "review_policy_changed", "The exact reviewed policy is unavailable.", 409
        )
    return saved["snapshot"]


def _checked_result(job):
    result = job.get("result")
    if not isinstance(result, dict):
        raise GameLearningError("review_evidence_corrupt", "Review evidence is unavailable.", 503)
    payload = {key: value for key, value in result.items() if key != "review_digest"}
    actual = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    identity = result.get("source_identity", {})
    if (
        actual != result.get("review_digest")
        or identity.get("input_digest") != _digest(job["input"])
        or identity.get("job_id") != job["job_id"]
    ):
        raise GameLearningError(
            "review_evidence_corrupt", "The immutable review evidence differs.", 503
        )
    return result


async def _load_review(scope, project_id, job_id):
    job = await workspace.jobs.find_one(
        {"_id": job_id, **scope, "project_id": project_id, "kind": "review"}
    )
    if job is None:
        raise GameLearningError(
            "review_not_found", "This scoped studio review is unavailable.", 404
        )
    project = await workspace._authority(scope, job["input"])
    if job_id not in project["job_ids"]:
        raise GameLearningError(
            "review_not_found", "This review was not admitted to the project.", 404
        )
    await _policy(scope, job)
    if job["status"] == "completed":
        _checked_result(job)
    return job


async def _baseline(scope, job):
    pin = job["input"].get("review_baseline")
    if pin is None:
        return None
    baseline = await _load_review(scope, job["project_id"], pin["job_id"])
    if (
        baseline["status"] != "completed"
        or baseline["input"].get("review_baseline")
        or _digest(baseline["input"]) != pin["input_digest"]
        or baseline["result"]["review_digest"] != pin["review_digest"]
    ):
        raise GameLearningError(
            "review_baseline_changed", "The exact completed reference review is unavailable.", 409
        )
    return baseline["result"]


async def handle_studio_review(scope, job, cancelled, emit_event):
    await workspace._authority(scope, job["input"])
    request = await workspace.environment_request(scope, job["input"])
    policy = await _policy(scope, job)
    baseline = await _baseline(scope, job)
    loop = asyncio.get_running_loop()

    def event(payload):
        if cancelled.is_set():
            raise GameLearningError("job_cancelled", "Studio review was cancelled.", 409)
        future = asyncio.run_coroutine_threadsafe(emit_event(payload), loop)
        try:
            future.result(timeout=5)
        except BaseException:
            future.cancel()
            raise

    body = job["request"]
    identity = {
        "project_id": job["project_id"],
        "project_version": job["input"]["project_version"],
        "input_epoch": job["input"].get("input_epoch", 0),
        "input_digest": _digest(job["input"]),
        "tree_digest": job["input"]["tree_digest"],
        "job_id": job["job_id"],
    }
    worker = loop.run_in_executor(
        None,
        partial(
            review_project_sequence,
            request,
            actions=body.get("actions"),
            seed=body.get("seed", 0),
            capture_every=body.get("capture_every", 4),
            policy_snapshot=policy,
            cancel=cancelled.is_set,
            on_event=event,
            source_identity=identity,
        ),
    )
    try:
        result = await asyncio.shield(worker)
    except asyncio.CancelledError:
        cancelled.set()
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                cancelled.set()
            except BaseException:
                break
        if not worker.cancelled():
            worker.exception()
        raise
    if cancelled.is_set():
        raise GameLearningError("job_cancelled", "Studio review was cancelled.", 409)
    await workspace._authority(scope, job["input"])
    await _policy(scope, job)
    await _baseline(scope, job)
    if baseline is not None:
        result["comparison"] = compare_executed_reviews(baseline, result)
        result["triangle_review"] = review_triangle(result)
        result.pop("review_digest")
        result["review_digest"] = hashlib.sha256(
            json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
    return result


def register_review_handler():
    workspace.register_job_handler("review", handle_studio_review, input_hook=_review_input)


async def read_review(scope, project_id, job_id):
    public = await workspace.get_job(scope, job_id)
    job = await _load_review(scope, project_id, job_id)
    await _baseline(scope, job)
    if job["status"] == "completed":
        pin = job["input"].get("review_baseline")
        comparison = job["result"].get("comparison", {})
        if pin and (
            comparison.get("baseline_job_id") != pin["job_id"]
            or comparison.get("baseline_review_digest") != pin["review_digest"]
        ):
            raise GameLearningError(
                "review_evidence_corrupt", "The review reference binding differs.", 503
            )
    return {"job": public, "review": job.get("result") if job["status"] == "completed" else None}
