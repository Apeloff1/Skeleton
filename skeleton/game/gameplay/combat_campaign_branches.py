"""Replay-verified alternative player choices for source-bound combat campaigns.

Preview is non-mutating. Every accepted branch uses the canonical combat
reducer and is independently replayed before a portable save is returned.
Blocked actions cannot mint rewards or masquerade as accepted victories.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.combat_campaign import original_campaign
from skeleton.game.gameplay.combat_campaign_player import (
    _advance, _bounded, demo_player_campaign, export_player_campaign,
    import_player_campaign, new_player_campaign, verify_player_campaign,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _action, _id, _object, _parse_json,
)

SCHEMA = "skeleton.combat_campaign_branches.v1"
BUNDLE = "skeleton.combat_campaign_branches_bundle.v1"
MAX_CANDIDATES = 8
MAX_ACTIONS = 32
MAX_TOTAL_ACTIONS = 96


def normalize_branches(raw: Any) -> list[dict[str, Any]]:
    """Canonicalize bounded, strictly typed candidate commands."""
    _bounded(raw)
    if type(raw) is not list or not 1 <= len(raw) <= MAX_CANDIDATES:
        raise CombatSessionError("invalid campaign branch candidate count")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    total = 0
    for candidate in raw:
        item = _object(candidate, {"candidate_id", "actions"}, "branch candidate")
        name = _id(item["candidate_id"], "candidate id")
        if name in seen:
            raise CombatSessionError("duplicate campaign branch candidate id")
        seen.add(name)
        actions = item["actions"]
        if type(actions) is not list or not 1 <= len(actions) <= MAX_ACTIONS:
            raise CombatSessionError("invalid campaign branch action count")
        total += len(actions)
        if total > MAX_TOTAL_ACTIONS:
            raise CombatSessionError("campaign branch total action budget exceeded")
        result.append({
            "candidate_id": name,
            "actions": [_action(action) for action in actions],
        })
    return sorted(result, key=lambda entry: entry["candidate_id"])


def _outcomes(checkpoint: dict[str, Any],
              candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    outcomes = []
    for candidate in candidates:
        current = checkpoint
        blocked_step: int | None = None
        blocked_reason: str | None = None
        for index, action in enumerate(candidate["actions"]):
            try:
                current = _advance(current, action)
            except CombatSessionError as exc:
                blocked_step, blocked_reason = index, str(exc)
                break
        if blocked_step is not None:
            outcomes.append({
                "candidate_id": candidate["candidate_id"],
                "status": "blocked",
                "blocked_step": blocked_step,
                "blocked_reason": blocked_reason,
                "state_digest": None, "phase": None,
                "hero_hp": None, "currency": None,
                "player_turns": None, "completed_encounters": None,
                "portable_checksum": None,
            })
            continue
        verified = verify_player_campaign(current)
        portable = export_player_campaign(verified)
        if import_player_campaign(portable) != verified:
            raise CombatSessionError("campaign branch portable replay diverged")
        state = verified["state"]
        outcomes.append({
            "candidate_id": candidate["candidate_id"],
            "status": "accepted", "blocked_step": None,
            "blocked_reason": None,
            "state_digest": verified["state_digest"],
            "phase": state["phase"], "hero_hp": state["hero_hp"],
            "currency": state["currency"],
            "player_turns": state["player_turns"],
            "completed_encounters": [
                item["encounter_id"] for item in state["completed"]
            ],
            "portable_checksum": portable["checksum"],
        })
    return outcomes


def _rank(outcomes: list[dict[str, Any]]) -> str | None:
    accepted = [item for item in outcomes if item["status"] == "accepted"]
    if not accepted:
        return None
    priority = {"won": 3, "active": 2, "draw": 1, "lost": 0}
    return min(accepted, key=lambda item: (
        -priority.get(item["phase"], 0),
        -item["currency"], -item["hero_hp"],
        item["player_turns"], item["candidate_id"],
    ))["candidate_id"]


def evaluate_branches(checkpoint: Any, candidates: Any) -> dict[str, Any]:
    """Compare legal player futures without mutating the source checkpoint."""
    canonical = verify_player_campaign(checkpoint)
    if canonical["state"]["phase"] != "active":
        raise CombatSessionError("cannot branch a terminal campaign")
    plans = normalize_branches(candidates)
    outcomes = _outcomes(canonical, plans)
    report = {
        "schema_version": SCHEMA,
        "checkpoint": canonical,
        "source_digest": canonical["source_digest"],
        "checkpoint_state_digest": canonical["state_digest"],
        "candidates": plans,
        "outcomes": outcomes,
        "heuristic_candidate": _rank(outcomes),
        "qualification": "offline_replay_heuristic_not_optimality_or_release",
    }
    report["checksum"] = dig(report)
    _bounded(report)
    return report


def verify_branches(raw: Any) -> dict[str, Any]:
    """Reject forged outcomes even when a caller recomputes the checksum."""
    _bounded(raw)
    report = _object(raw, {
        "schema_version", "checkpoint", "source_digest",
        "checkpoint_state_digest", "candidates", "outcomes",
        "heuristic_candidate", "qualification", "checksum",
    }, "campaign branch report")
    if report["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported campaign branch schema")
    if report["qualification"] != "offline_replay_heuristic_not_optimality_or_release":
        raise CombatSessionError("campaign branch qualification mismatch")
    expected = evaluate_branches(report["checkpoint"], report["candidates"])
    if expected != report:
        raise CombatSessionError("campaign branch witness or replay mismatch")
    return expected


def choose_branch(raw: Any, candidate_id: str) -> dict[str, Any]:
    """Commit one accepted alternative as an ordinary verified campaign save."""
    report = verify_branches(raw)
    name = _id(candidate_id, "branch candidate id")
    outcome = next((item for item in report["outcomes"]
                    if item["candidate_id"] == name), None)
    if outcome is None:
        raise CombatSessionError("unknown campaign branch candidate")
    if outcome["status"] != "accepted":
        raise CombatSessionError("blocked campaign branch cannot be committed")
    actions = next(item["actions"] for item in report["candidates"]
                   if item["candidate_id"] == name)
    current = report["checkpoint"]
    for action in actions:
        current = _advance(current, action)
    current = verify_player_campaign(current)
    portable = export_player_campaign(current)
    if (current["state_digest"] != outcome["state_digest"]
            or portable["checksum"] != outcome["portable_checksum"]
            or import_player_campaign(copy.deepcopy(portable)) != current):
        raise CombatSessionError("selected campaign branch replay diverged")
    return current


def export_branches(raw: Any) -> dict[str, Any]:
    report = verify_branches(raw)
    bundle = {
        "schema_version": BUNDLE,
        "source_digest": report["source_digest"],
        "checkpoint_state_digest": report["checkpoint_state_digest"],
        "report": report,
    }
    bundle["checksum"] = dig(bundle)
    _bounded(bundle)
    return bundle


def import_branches(raw: Any) -> dict[str, Any]:
    _bounded(raw)
    bundle = _object(raw, {
        "schema_version", "source_digest",
        "checkpoint_state_digest", "report", "checksum",
    }, "campaign branch bundle")
    if bundle["schema_version"] != BUNDLE:
        raise CombatSessionError("unsupported campaign branch bundle")
    if bundle["checksum"] != dig({k: v for k, v in bundle.items()
                                 if k != "checksum"}):
        raise CombatSessionError("campaign branch bundle checksum mismatch")
    report = verify_branches(bundle["report"])
    if (bundle["source_digest"] != report["source_digest"]
            or bundle["checkpoint_state_digest"] != report["checkpoint_state_digest"]):
        raise CombatSessionError("campaign branch bundle lineage mismatch")
    return report


def demo_branches() -> dict[str, Any]:
    """One earned victory and one distinct legal defensive choice."""
    completed = demo_player_campaign()
    actions = [event["action"] for event in completed["journal"]]
    if len(actions) < 2 or len(actions) > MAX_ACTIONS + 1:
        raise CombatSessionError("original campaign branch demo exceeds budget")
    checkpoint = _advance(new_player_campaign(original_campaign()), actions[0])
    hero = checkpoint["source"]["hero_id"]
    return evaluate_branches(checkpoint, [
        {"candidate_id": "finish_patrol", "actions": actions[1:]},
        {"candidate_id": "guard_then_reconsider",
         "actions": [{"kind": "guard", "actor_id": hero}]},
    ])


def accept_branches() -> dict[str, Any]:
    """End-to-end original combat, alternatives, save, replay and export."""
    report = demo_branches()
    verified = verify_branches(json.loads(json.dumps(report)))
    if verified != report or report["heuristic_candidate"] != "finish_patrol":
        raise CombatSessionError("campaign branch acceptance ranking diverged")
    selected = choose_branch(report, "finish_patrol")
    expected = demo_player_campaign()
    if selected != expected or selected["state"]["phase"] != "won":
        raise CombatSessionError("campaign branch acceptance victory diverged")
    bundle = export_branches(report)
    if import_branches(json.loads(json.dumps(bundle))) != report:
        raise CombatSessionError("campaign branch acceptance bundle diverged")
    receipt = {
        "schema_version": "skeleton.combat_campaign_branches_acceptance.v1",
        "source_digest": selected["source_digest"],
        "checkpoint_state_digest": report["checkpoint_state_digest"],
        "final_state_digest": selected["state_digest"],
        "earned_currency": selected["state"]["currency"],
        "hero_hp": selected["state"]["hero_hp"],
        "phase": selected["state"]["phase"],
        "candidate_count": len(report["candidates"]),
        "portable_checksum": export_player_campaign(selected)["checksum"],
        "branch_bundle_checksum": bundle["checksum"],
        "qualification": "offline_source_to_playable_replay_export_only",
    }
    receipt["checksum"] = dig(receipt)
    _bounded(receipt)
    return receipt


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton.game.gameplay.combat_campaign_branches")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    sub.add_parser("accept")
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--session-json", required=True)
    evaluate.add_argument("--candidates-json", required=True)
    for name in ("verify", "export", "choose"):
        p = sub.add_parser(name)
        p.add_argument("--report-json", required=True)
        if name == "choose":
            p.add_argument("--candidate-id", required=True)
    sub.add_parser("import").add_argument("--bundle-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = demo_branches()
        elif args.command == "accept":
            result = accept_branches()
        elif args.command == "evaluate":
            result = evaluate_branches(
                _parse_json(args.session_json, "campaign checkpoint"),
                _parse_json(args.candidates_json, "branch candidates"))
        elif args.command == "import":
            result = import_branches(_parse_json(args.bundle_json, "branch bundle"))
        else:
            report = _parse_json(args.report_json, "branch report")
            if args.command == "verify":
                result = verify_branches(report)
            elif args.command == "export":
                result = export_branches(report)
            else:
                result = choose_branch(report, args.candidate_id)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (CombatSessionError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
