"""End-to-end prompt quest -> ending witness -> canonical playable handoff.

The compiled original quest receipt is an immutable source; no model,
filesystem side effect or native game runtime is invoked during verification.
"""
from __future__ import annotations

from typing import Any

from .studio_ecosystem_quest import StudioQuestError, quest_progress, replay_quest
from .studio_ecosystem_scene_schedule import _canonical, _digest, _lease
from .studio_prompt_quest_plan import replay_prompt_quest_plan
from .studio_quest_ending_witness import (
    compile_ending_witness, replay_ending_witness,
)

SCHEMA = "skeleton.game_builder.studio_prompt_quest_playtest.v1"
MAX_BYTES = 256 * 1024


def compile_prompt_quest_playtest(
    compilation: object, *, target_ending: str, max_states: int,
    max_depth: int, authorized: bool, expected_compilation_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("prompt quest playtest requires authorization")
    _lease(expected_compilation_digest, "prompt quest compilation")
    checked = replay_prompt_quest_plan(compilation, authorized=True)
    if checked["receipt_digest"] != expected_compilation_digest:
        raise StudioQuestError("stale prompt quest compilation lease")
    if len(_canonical(checked)) > MAX_BYTES // 2:
        raise StudioQuestError("prompt quest playtest compilation exceeds budget")
    docs = checked["documents"]
    witness = compile_ending_witness(
        docs, target_ending=target_ending, initial_actions=[],
        max_states=max_states, max_depth=max_depth, authorized=True,
        expected_source_digest=checked["quest_source_digest"],
        expected_initial_session_digest=checked["initial_quest_session_digest"],
    )
    verified = replay_ending_witness(
        docs, witness, authorized=True,
        expected_source_digest=checked["quest_source_digest"],
        expected_initial_session_digest=checked["initial_quest_session_digest"])
    if verified != witness:
        raise StudioQuestError("prompt quest ending witness diverged")
    final = None
    if witness["status"] == "found":
        session = replay_quest(
            docs, witness["witness_actions"], authorized=True)
        progress = quest_progress(session, docs)
        if (session.digest != witness["witness_session_digest"]
                or target_ending not in progress["sandbox_endings_eligible"]):
            raise StudioQuestError("prompt quest playable handoff diverged")
        final = {
            "quest_session_digest": session.digest,
            "authored_actions": witness["witness_actions"],
            "sandbox_endings_eligible": progress["sandbox_endings_eligible"],
            "replay_verified": True,
            "native_runtime_verified": False,
        }
    payload: dict[str, Any] = {
        "schema": SCHEMA, "project_id": checked["project_id"],
        "compilation": checked,
        "compilation_digest": expected_compilation_digest,
        "target_ending": target_ending, "max_states": max_states,
        "max_depth": max_depth, "ending_witness": witness,
        "status": witness["status"], "playable_handoff": final,
        "typed_source_replay_verified": True,
        "sandbox_playable_handoff_verified": final is not None,
        "native_gameplay_verified": False,
        "external_evidence_verified": False,
        "file_write_performed": False, "release_certified": False,
    }
    if len(_canonical(payload)) > MAX_BYTES - 128:
        raise StudioQuestError("prompt quest playtest result exceeds budget")
    payload["receipt_digest"] = _digest(payload)
    return payload


def replay_prompt_quest_playtest(
    receipt: object, *, authorized: bool, expected_compilation_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("prompt quest playtest replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid prompt quest playtest receipt")
    checked = compile_prompt_quest_playtest(
        receipt.get("compilation"),
        target_ending=receipt.get("target_ending"),
        max_states=receipt.get("max_states"), max_depth=receipt.get("max_depth"),
        authorized=True, expected_compilation_digest=expected_compilation_digest)
    if checked != receipt:
        raise StudioQuestError("prompt quest playtest failed canonical replay")
    return checked
