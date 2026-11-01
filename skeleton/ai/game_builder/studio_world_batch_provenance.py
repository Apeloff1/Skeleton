"""Source-leased multi-world custody for read-only Jeeves batch execution.

Each step is bound to the exact authored blueprint that was inspected before
execution. Independent worlds remain separate: a source change in any world
invalidates the whole plan rather than silently mixing different canon epochs.
No authority is derived from tool arguments or from receipt digest strings.
"""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _digest, _lease

SCHEMA = "skeleton.jeeves.studio_world_batch_provenance.v1"
MAX_PROJECTS = 8
MAX_PROJECT_ID_BYTES = 128


def _source(project_id: object) -> dict[str, str]:
    if (type(project_id) is not str or not project_id
            or len(project_id.encode("utf-8", "strict")) > MAX_PROJECT_ID_BYTES
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in project_id)):
        raise StudioQuestError("world batch requires a bounded authored project")
    proof = audit_canon_source(read_blueprint(project_id), authorized=True)
    _lease(proof.get("source_digest"), "world batch source")
    _lease(proof.get("proof_digest"), "world batch canon proof")
    if proof.get("project_id") != project_id or proof.get("release_certified") is not False:
        raise StudioQuestError("world batch source identity or release claim invalid")
    return {
        "project_id": project_id,
        "source_digest": proof["source_digest"],
        "canon_proof_digest": proof["proof_digest"],
    }


def compile_world_batch_provenance(
    requests: list[dict[str, Any]], *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("world batch source custody requires authorization")
    if type(requests) is not list or not 1 <= len(requests) <= MAX_PROJECTS:
        raise StudioQuestError("world batch source custody exceeds step budget")
    projects: dict[str, dict[str, str]] = {}
    bindings: list[dict[str, Any]] = []
    for ordinal, request in enumerate(requests):
        if (type(request) is not dict or set(request) != {"tool", "arguments"}
                or type(request.get("arguments")) is not dict):
            raise StudioQuestError("invalid world batch source binding")
        args = request["arguments"]
        project_id = args.get("project_id")
        if type(project_id) is not str:
            raise StudioQuestError("world batch tool lacks explicit project identity")
        if project_id not in projects:
            if len(projects) >= MAX_PROJECTS:
                raise StudioQuestError("world batch project budget exhausted")
            projects[project_id] = _source(project_id)
        source = projects[project_id]
        expected = args.get("expected_source_digest")
        if expected is not None:
            _lease(expected, "world batch expected source")
            if expected != source["source_digest"]:
                raise StudioQuestError("world batch step has stale source lease")
        bindings.append({
            "ordinal": ordinal,
            "tool": request["tool"],
            "project_id": project_id,
            "source_digest": source["source_digest"],
            "canon_proof_digest": source["canon_proof_digest"],
            "request_digest": _digest(request),
        })
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "projects": [projects[key] for key in sorted(projects)],
        "step_bindings": bindings,
        "project_count": len(projects),
        "step_count": len(bindings),
        "source_replay_required": True,
        "file_write_performed": False,
        "release_certified": False,
    }
    result["manifest_digest"] = _digest(result)
    return result


def replay_world_batch_provenance(
    manifest: object, requests: list[dict[str, Any]], *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("world batch source replay requires authorization")
    if type(manifest) is not dict or manifest.get("schema") != SCHEMA:
        raise StudioQuestError("invalid world batch provenance manifest")
    verified = compile_world_batch_provenance(requests, authorized=True)
    if verified != manifest:
        raise StudioQuestError("world batch provenance failed canonical source replay")
    return verified


def verify_world_batch_step(
    request: dict[str, Any], router_receipt: Mapping[str, Any],
    binding: Mapping[str, Any], *, authorized: bool,
) -> None:
    """Check result identity, digest chain and source again after execution."""
    if authorized is not True:
        raise PermissionError("world batch result verification requires authorization")
    if (type(request) is not dict or type(router_receipt) is not dict
            or type(binding) is not dict):
        raise StudioQuestError("invalid world batch provenance evidence")
    if (binding.get("request_digest") != _digest(request)
            or binding.get("tool") != request.get("tool")
            or binding.get("project_id") != request.get("arguments", {}).get("project_id")):
        raise StudioQuestError("world batch step source binding mismatch")
    result = router_receipt.get("result")
    if (type(result) is not dict
            or router_receipt.get("tool") != request["tool"]
            or router_receipt.get("request_digest") != _digest(request)
            or router_receipt.get("file_write_performed") is not False
            or router_receipt.get("release_certified") is not False
            or router_receipt.get("result_digest") != _digest(result)
            or router_receipt.get("receipt_digest") != _digest({
                key: value for key, value in router_receipt.items()
                if key != "receipt_digest"
            })):
        raise StudioQuestError("world batch router custody chain invalid")
    if (result.get("project_id") != binding["project_id"]
            or result.get("request_digest") != binding["request_digest"]
            or result.get("file_write_performed") is not False
            or result.get("release_certified") is not False
            or result.get("result_digest") != _digest({
                key: value for key, value in result.items()
                if key != "result_digest"
            })
            or ("source_replay_verified" in result
                and result["source_replay_verified"] is not True)):
        raise StudioQuestError("world batch tool source or result proof invalid")
    current = _source(binding["project_id"])
    if current["source_digest"] != binding["source_digest"]:
        raise StudioQuestError("world batch source changed during execution")
    if current["canon_proof_digest"] != binding.get("canon_proof_digest"):
        raise StudioQuestError("world batch canon proof changed during execution")
