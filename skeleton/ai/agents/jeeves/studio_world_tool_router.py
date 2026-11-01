"""Explicit, operator-gated registry for canonical Jeeves world-authoring tools.

No model-provided tool name is imported or evaluated dynamically. Every
operation is resolved from a reviewed static allowlist of existing adapters.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from skeleton.ai.agents.jeeves import studio_walk_tool as studio
from skeleton.ai.agents.jeeves import studio_npc_knowledge_tool as knowledge
from skeleton.ai.agents.jeeves import studio_scene_rehearsal_tool as rehearsal
from skeleton.ai.agents.jeeves import studio_clue_visibility_tool as clue
from skeleton.ai.agents.jeeves import studio_temporal_windows_tool as temporal
from skeleton.ai.agents.jeeves import studio_temporal_scenarios_tool as scenarios
from skeleton.ai.agents.jeeves import studio_npc_transit_tool as transit
from skeleton.ai.agents.jeeves import studio_npc_transit_resilience_tool as resilience
from skeleton.ai.agents.jeeves import studio_npc_rendezvous_tool as rendezvous
from skeleton.ai.agents.jeeves import studio_npc_knowledge_exchange_tool as exchange
from skeleton.ai.agents.jeeves import studio_npc_continuity_tool as continuity
from skeleton.ai.agents.jeeves import studio_npc_continuity_merge_tool as continuity_merge
from skeleton.ai.agents.jeeves import studio_world_batch_tool as batch
from skeleton.ai.agents.jeeves import studio_world_batch_merge_tool as batch_merge
from skeleton.ai.agents.jeeves import studio_world_dependency_tool as dependency
from skeleton.ai.agents.jeeves import studio_world_dependency_impact_tool as dependency_impact
from skeleton.ai.agents.jeeves import studio_waypoint_route_tool as waypoint
from skeleton.ai.agents.jeeves import studio_waypoint_risk_tool as waypoint_risk
from skeleton.ai.agents.jeeves import studio_waypoint_handoff_tool as waypoint_handoff
from skeleton.ai.agents.jeeves import studio_npc_contact_handoff_tool as npc_contact_handoff
from skeleton.ai.agents.jeeves import studio_quest_hint_tool as hints
from skeleton.ai.agents.jeeves import studio_original_asset_briefs_tool as asset_briefs
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
    ("npc_continuity_merge_tool_schema", "execute_npc_continuity_merge_tool"),
    ("world_batch_tool_schema", "execute_world_batch_tool"),
    ("world_batch_merge_tool_schema", "execute_world_batch_merge_tool"),
    ("world_dependency_tool_schema", "execute_world_dependency_tool"),
    ("world_dependency_impact_tool_schema", "execute_world_dependency_impact_tool"),
    ("waypoint_route_tool_schema", "execute_waypoint_route_tool"),
    ("waypoint_risk_tool_schema", "execute_waypoint_risk_tool"),
    ("waypoint_handoff_tool_schema", "execute_waypoint_handoff_tool"),
    ("npc_contact_handoff_tool_schema", "execute_npc_contact_handoff_tool"),
    ("quest_hint_tool_schema", "execute_quest_hint_tool"),
    ("original_asset_briefs_tool_schema", "execute_original_asset_briefs_tool"),
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
    ("npc_knowledge_tool_schema", "execute_npc_knowledge_tool"),
    ("scene_rehearsal_tool_schema", "execute_scene_rehearsal_tool"),
    ("clue_visibility_tool_schema", "execute_clue_visibility_tool"),
    ("temporal_windows_tool_schema", "execute_temporal_windows_tool"),
    ("temporal_scenarios_tool_schema", "execute_temporal_scenarios_tool"),
    ("npc_transit_tool_schema", "execute_npc_transit_tool"),
    ("npc_transit_resilience_tool_schema", "execute_npc_transit_resilience_tool"),
    ("npc_rendezvous_tool_schema", "execute_npc_rendezvous_tool"),
    ("npc_knowledge_exchange_tool_schema", "execute_npc_knowledge_exchange_tool"),
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
        adapter = (knowledge if descriptor_name == "npc_knowledge_tool_schema" else
                   rehearsal if descriptor_name == "scene_rehearsal_tool_schema" else
                   clue if descriptor_name == "clue_visibility_tool_schema" else
                   temporal if descriptor_name == "temporal_windows_tool_schema" else
                   scenarios if descriptor_name == "temporal_scenarios_tool_schema" else
                   transit if descriptor_name == "npc_transit_tool_schema" else
                   resilience if descriptor_name == "npc_transit_resilience_tool_schema" else
                   rendezvous if descriptor_name == "npc_rendezvous_tool_schema" else
                   exchange if descriptor_name == "npc_knowledge_exchange_tool_schema" else
                   continuity if descriptor_name == "npc_continuity_tool_schema" else
                   continuity_merge if descriptor_name == "npc_continuity_merge_tool_schema" else
                   batch if descriptor_name == "world_batch_tool_schema" else
                   batch_merge if descriptor_name == "world_batch_merge_tool_schema" else
                   dependency if descriptor_name == "world_dependency_tool_schema" else
                   dependency_impact if descriptor_name == "world_dependency_impact_tool_schema" else
                   waypoint if descriptor_name == "waypoint_route_tool_schema" else
                   waypoint_risk if descriptor_name == "waypoint_risk_tool_schema" else
                   waypoint_handoff if descriptor_name == "waypoint_handoff_tool_schema" else
                   npc_contact_handoff if descriptor_name == "npc_contact_handoff_tool_schema" else
                   hints if descriptor_name == "quest_hint_tool_schema" else
                   asset_briefs if descriptor_name == "original_asset_briefs_tool_schema" else studio)
        descriptor = getattr(adapter, descriptor_name)()
        executor = getattr(adapter, executor_name)
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
