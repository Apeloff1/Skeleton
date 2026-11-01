"""Explicit, operator-gated registry for canonical Jeeves world-authoring tools.

No model-provided tool name is imported or evaluated dynamically. Every
operation is resolved from a reviewed static allowlist of existing adapters.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from skeleton.ai.agents.jeeves import studio_walk_tool as studio
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

ROUTER_SCHEMA = "skeleton.jeeves.studio_world_tool_router.v1"
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESULT_BYTES = 1024 * 1024

# Descriptor and executor symbols are static, source-reviewed Python names.
# Never derive an import path or callable name from untrusted user input.
_TOOL_SYMBOLS = (
    ("tool_schema", "execute_walk_tool"),
    ("catalog_tool_schema", "execute_catalog_audit_tool"),
    ("catalog_merge_tool_schema", "execute_catalog_merge_tool"),
    ("canon_proof_tool_schema", "execute_canon_proof_tool"),
    ("author_revision_tool_schema", "execute_author_revision_tool"),
    ("author_merge_tool_schema", "execute_author_merge_tool"),
    ("author_cherry_pick_tool_schema", "execute_author_cherry_pick_tool"),
    ("author_lineage_tool_schema", "execute_author_lineage_tool"),
    ("ending_plan_tool_schema", "execute_ending_plan_tool"),
    ("faction_reputation_tool_schema", "execute_faction_reputation_tool"),
    ("faction_plan_tool_schema", "execute_faction_plan_tool"),
    ("dialogue_staging_tool_schema", "execute_dialogue_staging_tool"),
    ("dialogue_preview_tool_schema", "execute_dialogue_preview_tool"),
    ("dialogue_commit_tool_schema", "execute_dialogue_commit_tool"),
    ("dialogue_restore_tool_schema", "execute_dialogue_restore_tool"),
    ("dialogue_transcript_tool_schema", "execute_dialogue_transcript_tool"),
    ("dialogue_compare_tool_schema", "execute_dialogue_compare_tool"),
    ("dialogue_fork_tool_schema", "execute_dialogue_fork_tool"),
    ("dialogue_checkpoint_tool_schema", "execute_dialogue_checkpoint_tool"),
    ("dialogue_route_tool_schema", "execute_dialogue_route_tool"),
    ("dialogue_itinerary_tool_schema", "execute_dialogue_itinerary_tool"),
    ("npc_codex_tool_schema", "execute_npc_codex_tool"),
    ("npc_continuity_tool_schema", "execute_npc_continuity_tool"),
    ("npc_author_tool_schema", "execute_npc_author_tool"),
    ("choice_author_tool_schema", "execute_choice_author_tool"),
    ("guided_walk_tool_schema", "execute_guided_walk_tool"),
    ("ending_atlas_tool_schema", "execute_ending_atlas_tool"),
    ("choice_impact_tool_schema", "execute_choice_impact_tool"),
    ("objective_board_tool_schema", "execute_objective_board_tool"),
    ("scene_schedule_tool_schema", "execute_scene_schedule_tool"),
    ("scene_asset_binding_tool_schema", "execute_scene_asset_binding_tool"),
    ("director_handoff_tool_schema", "execute_director_handoff_tool"),
    ("director_authoring_tool_schema", "execute_director_authoring_tool"),
    ("audio_cue_tool_schema", "execute_audio_cue_tool"),
    ("audio_prompt_tool_schema", "execute_audio_prompt_tool"),
)
_AUTHORING_SYMBOLS = frozenset({
    "author_revision_tool_schema",
    "author_merge_tool_schema",
    "author_cherry_pick_tool_schema",
    "author_lineage_tool_schema",
    "dialogue_commit_tool_schema",
    "dialogue_fork_tool_schema",
    "npc_author_tool_schema",
    "choice_author_tool_schema",
    "director_authoring_tool_schema",
})


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical Jeeves world tool payload") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def _registry() -> dict[str, tuple[dict[str, Any], Any, bool]]:
    registry: dict[str, tuple[dict[str, Any], Any, bool]] = {}
    schemas: set[str] = set()
    for descriptor_name, executor_name in _TOOL_SYMBOLS:
        descriptor = getattr(studio, descriptor_name)()
        executor = getattr(studio, executor_name)
        if (type(descriptor) is not dict or type(descriptor.get("name")) is not str
                or type(descriptor.get("parameters")) is not dict
                or type(descriptor["parameters"].get("properties")) is not dict):
            raise StudioQuestError("invalid registered Jeeves tool descriptor")
        fields = descriptor["parameters"]["properties"]
        schema = fields.get("schema")
        schema_id = schema.get("const") if type(schema) is dict else None
        if (type(schema_id) is not str or not schema_id
                or descriptor["name"] in registry or schema_id in schemas):
            raise StudioQuestError("duplicate or untyped Jeeves world tool")
        schemas.add(schema_id)
        registry[descriptor["name"]] = (
            descriptor, executor, descriptor_name in _AUTHORING_SYMBOLS)
    return registry


def world_tool_catalog() -> dict[str, object]:
    """Expose only vetted descriptors, never operator authority or credentials."""
    registry = _registry()
    tools = [
        {"name": name, "descriptor": registry[name][0],
         "explicit_authoring_permission_required": registry[name][2]}
        for name in sorted(registry)
    ]
    payload: dict[str, object] = {
        "schema": ROUTER_SCHEMA, "tool_count": len(tools), "tools": tools,
        "operator_authorization_required": True,
        "release_certified": False,
    }
    if len(_canonical(payload)) > MAX_RESULT_BYTES:
        raise StudioQuestError("Jeeves world tool catalog exceeds byte budget")
    payload["catalog_digest"] = _digest(payload)
    return payload


def route_world_tool(
    request: Mapping[str, Any], *, authorized: bool,
    allow_authoring: bool = False,
) -> dict[str, object]:
    """Dispatch one typed request with fail-closed out-of-band permissions."""
    if authorized is not True:
        raise PermissionError("Jeeves world tool routing requires operator authorization")
    if type(allow_authoring) is not bool:
        raise StudioQuestError("invalid authoring authority type")
    if (type(request) is not dict or set(request) != {"tool", "arguments"}
            or type(request.get("tool")) is not str
            or type(request.get("arguments")) is not dict):
        raise StudioQuestError("invalid Jeeves world tool envelope")
    encoded = _canonical(request)
    if len(encoded) > MAX_REQUEST_BYTES:
        raise StudioQuestError("Jeeves world tool request exceeds byte budget")
    if "authorized" in request["arguments"] or "allow_authoring" in request["arguments"]:
        raise StudioQuestError("untrusted request cannot grant tool authority")
    registry = _registry()
    if request["tool"] not in registry:
        raise StudioQuestError("unregistered Jeeves world tool")
    descriptor, executor, authoring = registry[request["tool"]]
    if authoring and not allow_authoring:
        raise PermissionError("Jeeves authoring tool requires explicit operator opt-in")
    expected = descriptor["parameters"]["properties"]["schema"]["const"]
    if request["arguments"].get("schema") != expected:
        raise StudioQuestError("Jeeves world tool schema mismatch")
    result = executor(request["arguments"], authorized=True)
    if type(result) is not dict:
        raise StudioQuestError("Jeeves world tool returned non-object result")
    if len(_canonical(result)) > MAX_RESULT_BYTES:
        raise StudioQuestError("Jeeves world tool result exceeds byte budget")
    write_evidence = result.get("file_write_performed")
    if type(write_evidence) is not bool:
        detail = result.get("detail")
        write_evidence = (detail.get("file_write_performed")
                          if type(detail) is dict
                          and type(detail.get("file_write_performed")) is bool
                          else None)
    payload: dict[str, object] = {
        "schema": ROUTER_SCHEMA, "tool": request["tool"],
        "tool_request_schema": expected,
        "request_digest": _digest(request),
        "result": result,
        "result_digest": _digest(result),
        "file_write_performed": write_evidence,
        "release_certified": False,
    }
    payload["receipt_digest"] = _digest(payload)
    return payload
