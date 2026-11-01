"""Atomic source-leased structural authoring for original quest stages/endings.

The author supplies explicit typed edits. No LLM-generated structure is silently
trusted; the canonical quest compiler revalidates the *entire* resulting graph.
A rejected edit never writes or changes the baseline compilation.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import _canonical, _digest, _lease
from .studio_prompt_quest_plan import (
    PLAN_SCHEMA, compile_prompt_quest_plan, replay_prompt_quest_plan,
)

SCHEMA = "skeleton.game_builder.studio_quest_structural_edit.v1"
MAX_EDITS = 32
MAX_BYTES = 256 * 1024
OPS = frozenset({
    "add_stage", "replace_stage", "remove_stage", "reorder_stages",
    "add_ending", "replace_ending", "remove_ending", "replace_prompt",
})


def _record(records: list[dict[str, Any]], identity: str, label: str) -> int:
    matches = [index for index, row in enumerate(records) if row["id"] == identity]
    if len(matches) != 1:
        raise StudioQuestError("unknown or ambiguous " + label + " edit target")
    return matches[0]


def _edit(plan: dict[str, Any], instruction: dict[str, Any]) -> None:
    if type(instruction) is not dict or set(instruction) != {"op", "id", "value"}:
        raise StudioQuestError("invalid structural edit envelope")
    op, identity, value = (
        instruction["op"], instruction["id"], instruction["value"])
    if (type(op) is not str or op not in OPS
            or type(identity) is not str or not 1 <= len(identity) <= 256
            or identity.strip() != identity
            or any(ord(char) < 32 for char in identity)):
        raise StudioQuestError("invalid structural edit operation or target")
    if op == "replace_prompt":
        if identity != "prompt" or type(value) is not str:
            raise StudioQuestError("invalid structural prompt replacement")
        plan["prompt"] = value
        return
    if op == "reorder_stages":
        stages = plan["stages"]
        names = [stage["id"] for stage in stages]
        if (identity != "stages" or type(value) is not list
                or len(value) != len(names)
                or any(type(item) is not str for item in value)
                or len(set(value)) != len(value) or set(value) != set(names)):
            raise StudioQuestError("stage reorder must be an exact permutation")
        by_id = {stage["id"]: stage for stage in stages}
        plan["stages"] = [by_id[item] for item in value]
        return
    collection = "stages" if op.endswith("_stage") else "endings"
    rows = plan[collection]
    if op.startswith("add_"):
        if (type(value) is not dict or value.get("id") != identity
                or any(row["id"] == identity for row in rows)):
            raise StudioQuestError("duplicate or malformed structural addition")
        rows.append(deepcopy(value))
    elif op.startswith("replace_"):
        if type(value) is not dict or value.get("id") != identity:
            raise StudioQuestError("invalid structural replacement")
        rows[_record(rows, identity, collection)] = deepcopy(value)
    elif op.startswith("remove_"):
        if value is not None:
            raise StudioQuestError("structural removal value must be null")
        del rows[_record(rows, identity, collection)]
    else:
        raise StudioQuestError("unrecognized structural edit")


def compile_quest_structural_edit(
    baseline: object, edits: object, *, authorized: bool,
    expected_baseline_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("structural quest authoring requires authorization")
    _lease(expected_baseline_digest, "structural quest baseline")
    original = replay_prompt_quest_plan(baseline, authorized=True)
    if original["receipt_digest"] != expected_baseline_digest:
        raise StudioQuestError("stale structural quest baseline lease")
    if (type(edits) is not list or not 1 <= len(edits) <= MAX_EDITS
            or len(_canonical(edits)) > 64 * 1024):
        raise StudioQuestError("invalid bounded structural quest edit batch")
    plan = deepcopy(original["plan"])
    if plan["schema"] != PLAN_SCHEMA:
        raise StudioQuestError("invalid original quest plan schema")
    for instruction in edits:
        _edit(plan, instruction)
    if len(_canonical(plan)) > 64 * 1024:
        raise StudioQuestError("structural quest candidate exceeds budget")
    candidate = compile_prompt_quest_plan(
        plan, authorized=True, expected_plan_digest=_digest(plan))
    if candidate["project_id"] != original["project_id"]:
        raise StudioQuestError("structural edit cannot change project custody")
    payload: dict[str, Any] = {
        "schema": SCHEMA, "project_id": original["project_id"],
        "baseline_compilation": original,
        "baseline_digest": expected_baseline_digest,
        "edits": deepcopy(edits), "edits_digest": _digest(edits),
        "candidate_compilation": candidate,
        "candidate_digest": candidate["receipt_digest"],
        "source_changed": (
            original["quest_source_digest"] != candidate["quest_source_digest"]),
        "typed_edit_compiled": True,
        "sandbox_quest_handoff_verified": True,
        "native_gameplay_verified": False,
        "file_write_performed": False, "release_certified": False,
    }
    if len(_canonical(payload)) > MAX_BYTES - 128:
        raise StudioQuestError("structural quest edit proof exceeds budget")
    payload["receipt_digest"] = _digest(payload)
    return payload


def replay_quest_structural_edit(
    receipt: object, *, authorized: bool, expected_baseline_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("structural quest replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid structural quest edit proof")
    checked = compile_quest_structural_edit(
        receipt.get("baseline_compilation"), receipt.get("edits"),
        authorized=True, expected_baseline_digest=expected_baseline_digest)
    if checked != receipt:
        raise StudioQuestError("structural quest edit failed canonical replay")
    return checked
