"""
🔧 REPAIR & EVALUATE — runtime self-heal + judge re-evaluation for a playable.

Extracted from routes/playable.py (Session 12 monolith decomposition).
- POST /{pid}/evaluate     — (re)run the VII.1 judge eval and persist it.
- POST /{pid}/repair        — synchronous runtime self-heal (~100s).
- POST /{pid}/repair/async  — kick self-heal in the background; poll /job/{job_id}.

Shares the codegen + judge helpers and the Mongo handle with routes.playable.
All routes use deeper POST paths so they never shadow the GET /{pid} catch-all.
"""
from __future__ import annotations

from routes.playable_access import project_router, scoped_database

import uuid
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.playable_literal_patch import (
    LiteralPatchError, MAX_SOURCE_BYTES, RESPONSE_SCHEMA, apply_literal_patch,
)
from routes.playable_htmlutils import passes_playability_gate, playable_html_digest
from routes.playable_access import reauthorize_project_context

from routes.playable import (
    PlayableModelFailure,
    _db, _RUNTIME_REPAIR_POLICY, _GAME_ENSEMBLE, PLAYABILITY_THRESHOLD,
    _sanitize, _validate, _llm_in_thread, _run_job, _judge_eval,
)

router = project_router(prefix="/api/playable", tags=["playable"])


@router.post("/{pid}/evaluate")
async def evaluate_playable(pid: str):
    """★ VII.1 — (re)run the judge eval on an existing playable and persist it."""
    doc = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "html": 1, "brief": 1})
    if not doc or not doc.get("html"):
        return {"error": "not found"}
    evaluation = await _judge_eval(doc["html"], doc.get("brief", ""))
    try:
        await _db.playables.update_one({"playable_id": pid}, {"$set": {"evaluation": evaluation}})
    except Exception:
        pass
    return {"playable_id": pid, "evaluation": evaluation}


class RepairBody(BaseModel):
    error: str = ""


async def _do_repair(pid: str, error: str) -> dict:
    """Apply one bounded model-proposed patch to the exact owned source snapshot."""
    doc = await _db.playables.find_one(
        {"playable_id": pid}, {"_id": 0, "html": 1, "playability_score": 1, "repair_trail": 1,
                              "version": 1, "repair_count": 1})
    if not doc or not doc.get("html"):
        return {"error": "not found", "repaired": False}
    source = doc["html"]
    version = doc.get("version")
    if type(version) is not int or not 1 <= version < 2**53:
        return {"playable_id": pid, "repaired": False, "error_code": "repair_source_version_unavailable"}
    try:
        source_bytes = source.encode("utf-8")
    except (AttributeError, UnicodeEncodeError):
        return {"playable_id": pid, "repaired": False, "error_code": "repair_source_invalid"}
    if not source_bytes or len(source_bytes) > MAX_SOURCE_BYTES or "\x00" in source:
        return {"playable_id": pid, "repaired": False, "error_code": "repair_source_exceeds_limit"}
    source_digest = playable_html_digest(source)
    err = (error or "").strip()[:600] or "an uncaught runtime JavaScript error"
    repair_prompt = (
        f"SERVER_BOUND_SOURCE_SHA256: {source_digest}\n"
        f"REPORTED_RUNTIME_ERROR:\n{err}\n\n"
        f"CURRENT_HTML (exact immutable source; edits only):\n{source}"
    )
    try:
        routed = await asyncio.to_thread(
            _llm_in_thread, repair_prompt, _RUNTIME_REPAIR_POLICY.instructions, _GAME_ENSEMBLE,
            instruction_policy=_RUNTIME_REPAIR_POLICY, structured_output_schema=RESPONSE_SCHEMA,
            max_output_tokens=1024, max_model_turns=1,
        )
    except (PlayableModelFailure, HTTPException):
        # The shared runner owns uncertain execution and revoked authority.
        # Neither may become a completed "not applied" mutation result.
        raise
    except Exception:
        return {"playable_id": pid, "repaired": False, "error": "repair model unavailable"}
    try:
        patch = apply_literal_patch(source, routed.get("content", ""), expected_source_sha256=source_digest)
    except LiteralPatchError as exc:
        return {"playable_id": pid, "repaired": False, "error_code": exc.code}
    new_html, removed = _sanitize(patch.candidate)
    val = _validate(new_html)
    if not new_html or not passes_playability_gate(val, PLAYABILITY_THRESHOLD):
        return {"playable_id": pid, "repaired": False,
                "score": val["score"], "missing": val.get("missing", [])}
    lineage = {}
    for field in ("operation_id", "execution_id", "context_id", "context_digest"):
        value = routed.get(field)
        if not isinstance(value, str) or not value or value != value.strip() or len(value) > 192:
            return {"playable_id": pid, "repaired": False, "error_code": "repair_engine_lineage_unavailable"}
        lineage["engine_" + field] = value
    digest = lineage["engine_context_digest"]
    receipts = routed.get("provider_receipts")
    if (len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest)
        or not isinstance(receipts, (list, tuple)) or not 1 <= len(receipts) <= 64
        or any(not isinstance(ref, str) or not ref or ref != ref.strip() or len(ref) > 2048 for ref in receipts)):
        return {"playable_id": pid, "repaired": False, "error_code": "repair_engine_lineage_unavailable"}
    lineage["engine_provider_receipts"] = list(receipts)
    result_digest = playable_html_digest(new_html)
    if new_html == source:
        return {"playable_id": pid, "repaired": False, "error_code": "repair_patch_no_change"}
    old_trail = doc.get("repair_trail") if isinstance(doc.get("repair_trail"), list) else []
    count = doc.get("repair_count")
    count = count if type(count) is int and 0 <= count < 2**53 else len(old_trail)
    entry = {"attempt": count + 1, "kind": "runtime_literal_patch", "score": val["score"], "error": err,
             "model": routed.get("model"), "source_sha256": source_digest, "result_sha256": result_digest,
             "patch_fingerprint": patch.patch_fingerprint, "edit_count": patch.edit_count,
             "sanitized_count": len(removed), **lineage}
    # Scope is reauthorized after model work; exact source/version/lifecycle
    # predicates make publication an atomic compare-and-set, never a stale overwrite.
    await reauthorize_project_context(mutate=True)
    query = {"playable_id": pid, "html": source, "version": version,
             "deleted": {"$ne": True}, "revoked": {"$ne": True}, "rights_revoked": {"$ne": True},
             "state": {"$nin": ["deleted", "revoked", "archived", "withdrawn"]}}
    try:
        result = await _db.playables.update_one(query, {"$set": {
            "html": new_html, "bytes": len(new_html.encode("utf-8")), "html_digest": result_digest,
            "version": version + 1, "playability_score": val["score"], "intricacy": val.get("intricacy"),
            "repair_trail": [*old_trail[-63:], entry], "last_repair": entry, "repair_count": count + 1,
            "repaired_at": datetime.now(timezone.utc).isoformat(),
        }})
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        await reauthorize_project_context(mutate=True)  # Revocation remains an authority denial.
        return {"playable_id": pid, "repaired": False, "error_code": "repair_source_changed"}
    if getattr(result, "matched_count", 0) != 1:
        await reauthorize_project_context(mutate=True)
        return {"playable_id": pid, "repaired": False, "error_code": "repair_source_changed"}
    return {"playable_id": pid, "repaired": True, "score": val["score"],
            "raw_path": f"/api/playable/{pid}/raw", "version": version + 1,
            "bytes": len(new_html.encode("utf-8")), "html_digest": result_digest,
            "source_sha256": source_digest, "result_sha256": result_digest,
            "patch_fingerprint": patch.patch_fingerprint, "edit_count": patch.edit_count, **lineage}


@router.post("/{pid}/repair")
async def repair_playable(pid: str, body: RepairBody):
    """Synchronous runtime self-heal (can run ~100s). Prefer /repair/async + /job/{id}
    polling from clients to stay clear of public-ingress edge timeouts."""
    return await _do_repair(pid, body.error)


@router.post("/{pid}/repair/async")
async def repair_async(pid: str, body: RepairBody):
    """🔧 Kick runtime self-heal in the background; poll /job/{job_id}.
    Bulletproof against edge timeouts on long (~100s) repairs."""
    base = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "playable_id": 1, "html": 1})
    if not base or not base.get("html"):
        return {"error": "not found"}
    job_id = uuid.uuid4().hex
    await _db.playable_jobs.insert_one({
        "job_id": job_id, "job_status": "running", "kind": "repair", "parent_id": pid,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    asyncio.create_task(_run_job(job_id, _do_repair(pid, body.error)))
    return {"job_id": job_id, "job_status": "running"}
