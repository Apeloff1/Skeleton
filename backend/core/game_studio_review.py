"""Scoped numerical inspection, under the existing workspace job authority."""

from __future__ import annotations

import asyncio
import hashlib
import json

from core.game_learning import GameLearningError, _digest, _key, workspace
from skeleton.jeeves.game_studio_review import MAX_RESULT, review_project_sequence


async def _review_input(scope, project, binding, body):
    if body.get("policy_id"):
        saved = await workspace._admitted_policy(scope, project["project_id"], body["policy_id"])
        binding["review_policy"] = {
            "policy_id": body["policy_id"],
            "snapshot_digest": saved["snapshot"]["snapshot_digest"],
        }
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
        raise GameLearningError("review_policy_changed", "The exact reviewed policy is unavailable.", 409)
    return saved["snapshot"]


async def handle_studio_review(scope, job, cancelled, emit_event):
    await workspace._authority(scope, job["input"])
    request = await workspace.environment_request(scope, job["input"])
    policy = await _policy(scope, job)
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
    worker = asyncio.create_task(
        asyncio.to_thread(
            review_project_sequence,
            request,
            actions=body.get("actions"),
            seed=body.get("seed", 0),
            capture_every=body.get("capture_every", 4),
            policy_snapshot=policy,
            cancel=cancelled.is_set,
            on_event=event,
            source_identity=identity,
        )
    )
    try:
        result = await asyncio.shield(worker)
    except asyncio.CancelledError:
        cancelled.set()
        await asyncio.gather(asyncio.shield(worker), return_exceptions=True)
        raise
    if cancelled.is_set():
        raise GameLearningError("job_cancelled", "Studio review was cancelled.", 409)
    await workspace._authority(scope, job["input"])
    await _policy(scope, job)
    return result


def register_review_handler():
    workspace.register_job_handler("review", handle_studio_review, input_hook=_review_input)


async def read_review(scope, project_id, job_id):
    public = await workspace.get_job(scope, job_id)
    job = await workspace.jobs.find_one({"_id": job_id, **scope, "project_id": project_id, "kind": "review"})
    if job is None:
        raise GameLearningError("review_not_found", "This scoped studio review is unavailable.", 404)
    await workspace._authority(scope, job["input"])
    await _policy(scope, job)
    if job["status"] == "completed":
        result = job["result"]
        payload = {key: value for key, value in result.items() if key != "review_digest"}
        actual = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
        identity = result.get("source_identity", {})
        if (
            actual != result.get("review_digest")
            or identity.get("input_digest") != _digest(job["input"])
            or identity.get("job_id") != job_id
        ):
            raise GameLearningError("review_evidence_corrupt", "The immutable review evidence differs.", 503)
    return {"job": public, "review": job.get("result") if job["status"] == "completed" else None}
