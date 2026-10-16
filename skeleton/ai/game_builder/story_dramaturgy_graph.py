"""Canon-bound setup/payoff and scene-causality audit for Jeeves.

The author declares which original events constitute a dramatic promise
and its payoff. A complete reference chain is required, so two unrelated
scenes cannot be called a fulfilled arc merely by entering a high score.
These are deterministic structure checks, NOT artistic/acting judgments.
"""
from __future__ import annotations

from collections import defaultdict, deque
from hashlib import sha256
import json
import re
from typing import Any

from skeleton.ai.game_builder.story_canon_fabric import verify_story_history

SCHEMA = "skeleton.jeeves.story_threads.v1"
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,95}$")
RECORD_LIMIT = 9999
ROW_LIMIT = 400000
MAX_PATH = 4096
KINDS = ("events", "dialogue", "interactions", "beats")


class DramaturgyError(ValueError):
    pass


def _reference(value: Any, title: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise DramaturgyError("invalid " + title)
    return value


def _digest(value: object) -> str:
    blob = json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")
    return sha256(blob).hexdigest()


def _node_ref(value: Any, label: str) -> tuple[int, str]:
    if not isinstance(value, dict) or set(value) != {"scene", "anchor"}:
        raise DramaturgyError(label + " needs a canonical scene and anchor")
    scene = value["scene"]
    if type(scene) is not int or not 1 <= scene <= RECORD_LIMIT:
        raise DramaturgyError("invalid " + label + " scene")
    return scene, _reference(value["anchor"], label + " anchor")


def _causal_path(older: str, newer: str, nodes: dict[str, dict[str, Any]]) -> list[str] | None:
    """Follow cited canonical evidence backwards, never inferred prose links."""
    queue = deque([(newer, [newer])])
    visited = set()
    while queue:
        current, path = queue.popleft()
        if current == older:
            return path[::-1]
        if current in visited:
            continue
        visited.add(current)
        if len(path) > MAX_PATH:
            raise DramaturgyError("causal trail too deep for this bounded scrutiny slice")
        for prior in nodes[current]["references"]:
            if prior in nodes and prior not in visited:
                queue.append((prior, path + [prior]))
    return None


def audit_threads(bible: dict[str, Any], scenes: list[dict[str, Any]],
                  threads: Any) -> dict[str, Any]:
    """Audits *all* supplied signed scenes; refuses forged or unconnected payoffs."""
    if not isinstance(threads, list) or len(threads) > RECORD_LIMIT:
        raise DramaturgyError("dramatic thread register must be a bounded list")
    # Reuse the sole canonical scene signature, history, identity and world-state gate.
    verified = verify_story_history(bible, scenes)
    nodes: dict[str, dict[str, Any]] = {}
    scene_nodes: dict[int, list[str]] = defaultdict(list)
    if len(scenes) > RECORD_LIMIT:
        raise DramaturgyError("scene history exceeds canonical manuscript scale")
    for scene in scenes:
        sequence = scene["sequence"]
        for kind in KINDS:
            for part in scene[kind]:
                if len(nodes) >= ROW_LIMIT:
                    raise DramaturgyError("narrative node count exceeds this scrutiny slice")
                anchor = _reference(part["id"], "canonical story node")
                if anchor in nodes:
                    raise DramaturgyError("duplicate story node id across scenes")
                nodes[anchor] = {
                    "id": anchor, "scene": sequence, "kind": kind,
                    "references": list(part.get("references", [])),
                }
                scene_nodes[sequence].append(anchor)
    # No dangling or future-bound claims can become an accepted plot payoff.
    for node in nodes.values():
        for reference in node["references"]:
            if reference not in nodes:
                raise DramaturgyError("unresolved canonical story reference")
            if nodes[reference]["scene"] > node["scene"]:
                raise DramaturgyError("future event cited as previously witnessed fact")

    eligible_characters = {row["id"] for row in bible["characters"]}
    identities = set()
    results = []
    touched = set()
    for thread in threads:
        if not isinstance(thread, dict) or set(thread) != {
            "id", "character", "setup", "payoff", "state",
            "stakes", "promise", "consequence",
        }:
            raise DramaturgyError("dramatic thread missing required production fields")
        identifier = _reference(thread["id"], "dramatic thread identity")
        if identifier in identities:
            raise DramaturgyError("duplicate original dramatic thread identity")
        identities.add(identifier)
        character = _reference(thread["character"], "thread protagonist")
        if character not in eligible_characters:
            raise DramaturgyError("dramatic thread uses a character outside signed bible")
        state = thread["state"]
        if state not in ("open", "resolved", "red_herring"):
            raise DramaturgyError("unsupported closure state")
        for field in ("stakes", "promise"):
            text = thread[field]
            if not isinstance(text, str) or not 12 <= len(text.strip()) <= 2000:
                raise DramaturgyError("dramatic " + field + " needs a substantive authored rationale")
        setup_scene, setup_anchor = _node_ref(thread["setup"], "setup")
        if setup_anchor not in nodes or nodes[setup_anchor]["scene"] != setup_scene:
            raise DramaturgyError("setup must cite an existing scene-local signed source")
        if character not in scenes[setup_scene - 1]["cast"]:
            raise DramaturgyError("setup must involve the declared story character")
        touched.add(setup_anchor)
        payoff = thread["payoff"]
        consequence = thread["consequence"]
        if state == "open":
            if payoff is not None or consequence is not None:
                raise DramaturgyError("open story thread cannot claim a payoff or consequence")
            results.append({
                "id": identifier, "character": character, "state": state,
                "setup_scene": setup_scene, "setup_anchor": setup_anchor,
                "payoff_scene": None, "payoff_anchor": None,
                "causal_path": None, "scene_span": None,
                "original_audience_payoff_quality_proven": False,
            })
            continue
        payoff_scene, payoff_anchor = _node_ref(payoff, "payoff")
        if payoff_anchor not in nodes or nodes[payoff_anchor]["scene"] != payoff_scene:
            raise DramaturgyError("payoff must cite existing signed scene-local evidence")
        if payoff_scene <= setup_scene:
            raise DramaturgyError("drama payoff must follow its setup in later scene")
        if character not in scenes[payoff_scene - 1]["cast"]:
            raise DramaturgyError("payoff must involve the thread's actual character")
        if not isinstance(consequence, str) or not 12 <= len(consequence.strip()) <= 2000:
            raise DramaturgyError("resolved thread requires a meaningful authored consequence")
        route = _causal_path(setup_anchor, payoff_anchor, nodes)
        if route is None:
            raise DramaturgyError("claimed payoff has no source-verified causal path to its setup")
        touched.update(route)
        results.append({
            "id": identifier, "character": character, "state": state,
            "setup_scene": setup_scene, "setup_anchor": setup_anchor,
            "payoff_scene": payoff_scene, "payoff_anchor": payoff_anchor,
            "causal_path": route, "scene_span": payoff_scene - setup_scene,
            "original_audience_payoff_quality_proven": False,
        })
    inbound = defaultdict(int)
    cross_scene = 0
    for node in nodes.values():
        for linked in node["references"]:
            inbound[linked] += 1
            if nodes[linked]["scene"] < node["scene"]:
                cross_scene += 1
    dormant = [node["id"] for node in nodes.values()
               if node["kind"] == "beats" and not inbound[node["id"]]]
    open_ids = [row["id"] for row in results if row["state"] == "open"]
    return {
        "ok": True, "schema": SCHEMA, "action": "dramaturgy-audit",
        "bible_sha256": bible["digest"],
        "scene_history_digest": verified["digest"],
        "signed_scenes_scrutinized": len(scenes),
        "canonical_story_nodes": len(nodes),
        "referential_links": sum(len(v["references"]) for v in nodes.values()),
        "cross_scene_causal_links": cross_scene,
        "declared_thread_count": len(results),
        "declared_resolved_count": sum(r["state"] == "resolved" for r in results),
        "declared_red_herring_reveals": sum(r["state"] == "red_herring" for r in results),
        "open_thread_ids": open_ids,
        "undemonstrated_beat_callback_candidates": dormant[:100],
        "undemonstrated_beat_callback_total": len(dormant),
        "thread_evidence": results,
        "verified_causal_anchor_count": len(touched),
        "entire_history_verified": True,
        "structural_resolution_complete": bool(results) and not open_ids,
        "professional_novel_emotional_payoff_verified": False,
        "hollywood_direction_qualified": False,
        "complete_game_playthrough_verified": False,
        "source_identity_sha256": _digest({"bible": bible["digest"],
                                          "scenes": [s["digest"] for s in scenes],
                                          "threads": threads}),
    }
