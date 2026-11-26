"""Source-replayed original NPC knowledge lineage for operator authoring and QA.

The lineage describes authored facts and sandbox consequences. It never
generates testimony or grants NPC speech, hardware, or release authority.
"""
from __future__ import annotations

from html import escape
from typing import Any, Mapping, cast

from .studio_ecosystem_npc_knowledge import (
    _canonical, _digest, _lease, compile_npc_knowledge, source_knowledge_facts,
)
from .studio_ecosystem_quest import StudioQuestError

SCHEMA = "skeleton.game_builder.studio_npc_knowledge_lineage.v1"
MAX_BYTES = 256 * 1024


def compile_npc_lineage(
    documents: Mapping[str, Any], actions: list[list[str]],
    authoring: object, *, authorized: bool, expected_source_digest: str,
    expected_session_digest: str | None = None,
) -> dict[str, object]:
    """Rebuild exact source facts, causal handoffs, and replay-gated outcomes."""
    if authorized is not True:
        raise PermissionError("NPC lineage requires operator authorization")
    _lease(expected_source_digest, "lineage source")
    if expected_session_digest is not None:
        _lease(expected_session_digest, "lineage session")
    compiled = cast(dict[str, Any], compile_npc_knowledge(
        documents, actions, authoring, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=expected_session_digest))
    facts = cast(dict[str, Any], source_knowledge_facts(
        documents, actions, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=compiled["session_digest"]))
    if (facts["project_id"] != compiled["project_id"] or
            facts["source_digest"] != compiled["source_digest"] or
            facts["session_digest"] != compiled["session_digest"]):
        raise StudioQuestError("NPC lineage source or session drift")
    sources: dict[str, dict[str, Any]] = {}
    for fact in facts["facts"]:
        if fact["fact_id"] in sources:
            raise StudioQuestError("duplicate source NPC fact identity")
        sources[fact["fact_id"]] = fact
    nodes: list[dict[str, Any]] = []
    positions: dict[str, int] = {}
    for i, scene in enumerate(compiled["scenes"]):
        scene_id = scene["scene_id"]
        if scene_id in positions:
            raise StudioQuestError("duplicate NPC lineage scene")
        positions[scene_id] = i
        nodes.append({
            "scene_id": scene_id, "npc_id": scene["npc_id"],
            "quest_stage": scene["quest_stage"], "status": scene["status"],
            "incoming": 0, "outgoing": 0, "earned_incoming": 0,
        })
    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for reveal in compiled["reveals"]:
        source, target = reveal["source_scene_id"], reveal["recipient_scene_id"]
        fact = sources.get(reveal["fact_id"])
        identity = (reveal["fact_id"], target)
        if (fact is None or identity in seen or
                source not in positions or target not in positions or
                positions[source] >= positions[target] or
                fact["scene_id"] != source or
                fact["source_ref"] != reveal["source_ref"] or
                fact["source_text_digest"] != reveal["source_text_digest"]):
            raise StudioQuestError("NPC lineage edge lacks authored causal proof")
        seen.add(identity)
        if reveal["status"] not in ("pending", "earned_in_sandbox_replay"):
            raise StudioQuestError("unknown NPC lineage status")
        earned = reveal["status"] == "earned_in_sandbox_replay"
        edge: dict[str, Any] = {
            "fact_id": reveal["fact_id"], "source_scene_id": source,
            "recipient_scene_id": target,
            "source_ref": fact["source_ref"],
            "source_text_digest": fact["source_text_digest"],
            "required_alternative": reveal["required_alternative"],
            "status": reveal["status"], "sandbox_earned": earned,
            "native_dialogue_spoken_verified": False,
        }
        edge["edge_digest"] = _digest(edge)
        edges.append(edge)
        nodes[positions[source]]["outgoing"] += 1
        nodes[positions[target]]["incoming"] += 1
        if earned:
            nodes[positions[target]]["earned_incoming"] += 1
    if (sum(edge["sandbox_earned"] for edge in edges) != compiled["earned_count"]
            or len(edges) - compiled["earned_count"] != compiled["pending_count"]):
        raise StudioQuestError("NPC lineage replay count drift")
    for node in nodes:
        node["node_digest"] = _digest(node)
    result: dict[str, object] = {
        "schema": SCHEMA, "project_id": compiled["project_id"],
        "source_digest": compiled["source_digest"],
        "session_digest": compiled["session_digest"],
        "knowledge_digest": compiled["knowledge_digest"],
        "authoring_digest": compiled["authoring_digest"],
        "facts_digest": facts["facts_digest"],
        "nodes": nodes, "edges": edges,
        "scene_count": len(nodes), "reveal_count": len(edges),
        "earned_count": compiled["earned_count"],
        "pending_count": compiled["pending_count"],
        "source_replay_verified": True, "authored_facts_only": True,
        "model_inference_performed": False, "file_write_performed": False,
        "npc_speech_verified": False, "release_certified": False,
    }
    if len(_canonical(result)) > MAX_BYTES:
        raise StudioQuestError("NPC lineage exceeds bounded size")
    result["lineage_digest"] = _digest(result)
    return result


def render_npc_lineage_html(lineage: Mapping[str, Any]) -> bytes:
    """Script-free accessible operator graph, not a playable NPC conversation."""
    if type(lineage) is not dict or lineage.get("schema") != SCHEMA:
        raise StudioQuestError("invalid NPC lineage display")
    digest = _lease(lineage.get("lineage_digest"), "lineage display")
    if _digest({k: v for k, v in lineage.items()
                if k != "lineage_digest"}) != digest:
        raise StudioQuestError("tampered NPC lineage display")
    if (type(lineage.get("nodes")) is not list or
            type(lineage.get("edges")) is not list or
            len(lineage["nodes"]) > 64 or len(lineage["edges"]) > 128 or
            len(lineage["nodes"]) != lineage.get("scene_count") or
            len(lineage["edges"]) != lineage.get("reveal_count")):
        raise StudioQuestError("unbounded NPC lineage display")
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; ",
        "base-uri 'none'; form-action 'none'\">",
        "<title>Original NPC lineage</title></head><body><main>",
        "<h1>Original NPC lineage</h1><p>Operator-only authored QA. No NPC speech verified.</p>",
        "<h2>Scenes</h2><ol>",
    ]
    for node in lineage["nodes"]:
        if type(node) is not dict:
            raise StudioQuestError("invalid lineage node")
        parts.append("<li>" + escape(node["scene_id"], quote=True) +
                     " — " + escape(node["npc_id"], quote=True) +
                     " (" + escape(node["status"], quote=True) + ")</li>")
    parts.append("</ol><h2>Knowledge handoffs</h2><ol>")
    for edge in lineage["edges"]:
        if type(edge) is not dict:
            raise StudioQuestError("invalid lineage edge")
        parts.append("<li>" + escape(edge["source_scene_id"], quote=True) +
                     " → " + escape(edge["recipient_scene_id"], quote=True) +
                     ": " + escape(edge["source_ref"], quote=True) +
                     " [" + escape(edge["status"], quote=True) + "]</li>")
    parts.append("</ol></main></body></html>")
    html = "".join(parts).encode("utf-8", "strict")
    if len(html) > MAX_BYTES:
        raise StudioQuestError("NPC lineage HTML exceeds bounded size")
    return html
