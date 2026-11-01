"""Deterministic disruption and fallback proof for source-bound NPC travel.

This is an authored route graph rehearsal, not native movement or travel telemetry.
Each closure scenario is recomputed from the original temporal and quest source.
Unknown or insufficient paths block playable handoff rather than being guessed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import _canonical, _digest, _lease, _open_directory, _write_all
from .studio_ecosystem_npc_transit import (
    compile_npc_transit, replay_npc_transit, compile_transit_playable,
)

SCHEMA = "skeleton.game_builder.studio_npc_transit_resilience.v1"
PROMPT = "audit source-bound npc transit disruption resilience"
FILENAME = "npc_transit_resilience.json"
MAX_VARIANTS = 12
MAX_CLOSURES = 32
MAX_BYTES = 512 * 1024
_ID = re.compile(r"[a-z][a-z0-9_-]{0,47}\Z")


def _variants(value: object, baseline: dict[str, Any]) -> list[dict[str, Any]]:
    if type(value) is not list or not 1 <= len(value) <= MAX_VARIANTS:
        raise StudioQuestError("resilience requires 1..12 typed variants")
    if len(_canonical(value)) > 32768:
        raise StudioQuestError("resilience variant request exceeds byte budget")
    edges = {(edge["from_site"], edge["to_site"]) for edge in baseline["graph"]["edges"]}
    seen_ids: set[str] = set()
    checked: list[dict[str, Any]] = []
    for item in value:
        if (type(item) is not dict or set(item) != {"id", "closed_edges"}
                or type(item["id"]) is not str or not _ID.fullmatch(item["id"])
                or item["id"] in seen_ids or type(item["closed_edges"]) is not list
                or len(item["closed_edges"]) > MAX_CLOSURES):
            raise StudioQuestError("invalid or duplicate NPC disruption scenario")
        seen_ids.add(item["id"])
        closed: set[tuple[str, str]] = set()
        for entry in item["closed_edges"]:
            if (type(entry) is not dict or set(entry) != {"from_site", "to_site"}
                    or type(entry["from_site"]) is not str
                    or type(entry["to_site"]) is not str):
                raise StudioQuestError("invalid directed route closure")
            pair = (entry["from_site"], entry["to_site"])
            if pair not in edges or pair in closed:
                raise StudioQuestError("closure must identify one unique existing directed route")
            closed.add(pair)
        checked.append({
            "id": item["id"],
            "closed_edges": [
                {"from_site": a, "to_site": b} for a, b in sorted(closed)
            ],
        })
    return checked


def _evaluate(
    documents: Mapping[str, Any], baseline: dict[str, Any],
    item: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    closed = {(e["from_site"], e["to_site"]) for e in item["closed_edges"]}
    remaining = {"edges": [
        edge for edge in baseline["graph"]["edges"]
        if (edge["from_site"], edge["to_site"]) not in closed
    ]}
    proof = compile_npc_transit(
        documents, baseline["temporal_receipt"], remaining, authorized=True)
    if (proof["source_digest"] != baseline["source_digest"]
            or proof["session_digest"] != baseline["session_digest"]
            or proof["temporal_digest"] != baseline["temporal_digest"]
            or proof["quest_source_digest"] != baseline["quest_source_digest"]
            or proof["transition_count"] != baseline["transition_count"]):
        raise StudioQuestError("disruption changed source or quest replay identity")
    transitions = []
    for prior, after in zip(baseline["transitions"], proof["transitions"], strict=True):
        if (prior["npc_id"], prior["from_scene_id"], prior["to_scene_id"]) != (
                after["npc_id"], after["from_scene_id"], after["to_scene_id"]):
            raise StudioQuestError("disruption changed NPC transition identity")
        transitions.append({
            "npc_id": after["npc_id"],
            "from_scene_id": after["from_scene_id"],
            "to_scene_id": after["to_scene_id"],
            "previous_route": prior["route_sites"],
            "fallback_route": after["route_sites"],
            "previous_slack": prior["slack_ticks"],
            "fallback_slack": after["slack_ticks"],
            "rerouted": prior["route_sites"] != after["route_sites"],
            "feasible": after["feasible"],
            "reason": after["reason"],
        })
    outcome: dict[str, Any] = {
        "id": item["id"], "closed_edges": item["closed_edges"],
        "status": "accepted" if proof["all_transitions_feasible"] else "blocked",
        "conflict_count": proof["conflict_count"],
        "rerouted_count": sum(row["rerouted"] for row in transitions),
        "fallback_transit_digest": proof["transit_digest"],
        "playable_handoff_allowed": proof["all_transitions_feasible"],
        "transitions": transitions,
        "physical_travel_verified": False,
    }
    outcome["outcome_digest"] = _digest(outcome)
    return outcome, proof


def compile_npc_transit_resilience(
    documents: Mapping[str, Any], baseline_receipt: object,
    variants: object, *, authorized: bool,
    expected_source_digest: str,
    expected_session_digest: str | None = None,
) -> dict[str, Any]:
    """Prove closure consequences without mutating the authored transit graph."""
    if authorized is not True:
        raise PermissionError("NPC disruption rehearsal requires operator authorization")
    _lease(expected_source_digest, "NPC disruption source")
    if expected_session_digest is not None:
        _lease(expected_session_digest, "NPC disruption session")
    baseline = replay_npc_transit(documents, baseline_receipt, authorized=True)
    if baseline["source_digest"] != expected_source_digest:
        raise StudioQuestError("stale NPC disruption source lease")
    if (expected_session_digest is not None
            and baseline["session_digest"] != expected_session_digest):
        raise StudioQuestError("stale NPC disruption session lease")
    checked = _variants(variants, baseline)
    outcomes = [_evaluate(documents, baseline, item)[0] for item in checked]
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": baseline["project_id"],
        "source_digest": baseline["source_digest"],
        "quest_source_digest": baseline["quest_source_digest"],
        "session_digest": baseline["session_digest"],
        "temporal_digest": baseline["temporal_digest"],
        "baseline_transit_digest": baseline["transit_digest"],
        "baseline_receipt": baseline,
        "variants": checked, "outcomes": outcomes,
        "accepted_count": sum(x["status"] == "accepted" for x in outcomes),
        "blocked_count": sum(x["status"] == "blocked" for x in outcomes),
        "tested_variant_count": len(outcomes),
        "total_directed_edges": len(baseline["graph"]["edges"]),
        "complete_disruption_coverage": (
            len(baseline["graph"]["edges"]) == len(outcomes)
            and all(len(item["closed_edges"]) == 1 for item in checked)
            and len({(item["closed_edges"][0]["from_site"],
                      item["closed_edges"][0]["to_site"]) for item in checked})
            == len(baseline["graph"]["edges"])
        ),
        "source_replay_verified": True,
        "operator_estimates_only": True,
        "physical_travel_verified": False,
        "model_inference_performed": False,
        "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_BYTES - 128:
        raise StudioQuestError("NPC disruption receipt exceeds byte budget")
    result["resilience_digest"] = _digest(result)
    return result


def propose_npc_transit_resilience(
    documents: Mapping[str, Any], baseline_receipt: object,
    prompt: str, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    """Audit up to twelve individual directed-edge outages; never invent edges."""
    if authorized is not True:
        raise PermissionError("NPC disruption proposal requires operator authorization")
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported NPC disruption prompt")
    baseline = replay_npc_transit(documents, baseline_receipt, authorized=True)
    edges = sorted(baseline["graph"]["edges"],
                   key=lambda edge: (edge["from_site"], edge["to_site"]))
    variants = [
        {"id": f"edge-outage-{index + 1}",
         "closed_edges": [{"from_site": edge["from_site"],
                           "to_site": edge["to_site"]}]}
        for index, edge in enumerate(edges[:MAX_VARIANTS])
    ] or [{"id": "no-authored-edges", "closed_edges": []}]
    return compile_npc_transit_resilience(
        documents, baseline, variants, authorized=True,
        expected_source_digest=expected_source_digest)


def replay_npc_transit_resilience(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC disruption replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid NPC disruption receipt")
    replay = compile_npc_transit_resilience(
        documents, receipt.get("baseline_receipt"), receipt.get("variants"),
        authorized=True, expected_source_digest=receipt.get("source_digest"),
        expected_session_digest=receipt.get("session_digest"))
    if replay != receipt:
        raise StudioQuestError("NPC disruption receipt failed canonical replay")
    return replay


def select_npc_transit_fallback(
    documents: Mapping[str, Any], receipt: object, variant_id: str, *,
    authorized: bool, playable: bool = False,
) -> dict[str, Any]:
    replay = replay_npc_transit_resilience(documents, receipt, authorized=authorized)
    if type(variant_id) is not str or not _ID.fullmatch(variant_id):
        raise StudioQuestError("invalid NPC disruption selection")
    if type(playable) is not bool:
        raise StudioQuestError("invalid playable request")
    matching = [item for item in replay["variants"] if item["id"] == variant_id]
    if len(matching) != 1:
        raise StudioQuestError("unknown NPC disruption variant")
    outcome, transit = _evaluate(documents, replay["baseline_receipt"], matching[0])
    if outcome["status"] != "accepted":
        raise StudioQuestError("blocked NPC disruption cannot be selected")
    result: dict[str, Any] = {
        "schema": "skeleton.game_builder.studio_npc_transit_fallback.v1",
        "resilience_digest": replay["resilience_digest"],
        "variant_id": variant_id, "outcome_digest": outcome["outcome_digest"],
        "fallback_transit_digest": transit["transit_digest"],
        "playable_handoff_allowed": True,
        "physical_travel_verified": False, "release_certified": False,
    }
    if playable:
        result["playable_manifest"] = compile_transit_playable(
            documents, transit, authorized=True)
    result["selection_digest"] = _digest(result)
    return result


def publish_npc_transit_resilience(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    replay = replay_npc_transit_resilience(documents, receipt, authorized=authorized)
    raw = _canonical(replay) + b"\n"
    if len(raw) > MAX_BYTES:
        raise StudioQuestError("NPC disruption publication exceeds byte budget")
    fd = _open_directory(directory)
    temporary = ".npc-resilience-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         os.O_NOFOLLOW, 0o600, dir_fd=fd)
        created = True
        try:
            _write_all(handle, raw)
            os.fsync(handle)
        finally:
            os.close(handle)
        os.link(temporary, FILENAME, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        os.fsync(fd)
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=fd)
        finally:
            os.close(fd)
    return {"path": str(Path(directory) / FILENAME),
            "resilience_digest": replay["resilience_digest"],
            "bytes": len(raw), "file_write_performed": True,
            "release_certified": False}


def restore_npc_transit_resilience(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC disruption restore requires authorization")
    _lease(expected_source_digest, "NPC disruption restore source")
    fd = _open_directory(directory)
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            info = os.fstat(handle)
            if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES
                    or (os.name == "posix"
                        and (info.st_uid != os.getuid() or info.st_mode & 0o077
                             or info.st_nlink != 1))):
                raise StudioQuestError("NPC disruption receipt must be private")
            raw = os.read(handle, MAX_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_BYTES:
        raise StudioQuestError("invalid NPC disruption receipt size")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise StudioQuestError("duplicate NPC disruption receipt key")
            output[key] = value
        return output
    try:
        receipt = json.loads(raw.decode("utf-8", "strict"),
                             object_pairs_hook=unique,
                             parse_constant=lambda _: (_ for _ in ()).throw(
                                 StudioQuestError("nonfinite NPC disruption receipt")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid NPC disruption receipt JSON") from exc
    if type(receipt) is not dict or receipt.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale NPC disruption source lease")
    return replay_npc_transit_resilience(documents, receipt, authorized=True)
