"""Independent original campaign acceptance over executed canonical story/game events."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256

from .production_quality import QualityGateError, _digest
from .production_deep_gates import _sha

def accept_original_campaign(
    world, player, storybook, questbook, snapshots: Sequence[Mapping], *,
    controller_evidence: Sequence[Mapping] = (),
    native_report: Mapping | None = None,
    require_all_endings: bool = True,
) -> dict:
    """Re-execute complete source-bound gameplay and validate branch coverage.

    A winning simulation is never represented as a real native run. The native
    lane needs the existing Godot runtime verifier's exact source-bound report.
    """
    from skeleton.jeeves.game_frontier_expedition import ExpeditionWorld, Traveler
    from skeleton.jeeves.game_frontier_expedition_narrative import StoryBook
    from skeleton.jeeves.game_frontier_expedition_quests import QuestBook
    from skeleton.jeeves.game_frontier_expedition_session import ProductionSession
    if (not isinstance(world, ExpeditionWorld) or
            not isinstance(player, Traveler) or
            not isinstance(storybook, StoryBook) or
            not isinstance(questbook, QuestBook)):
        raise QualityGateError("authoritative game/story/quest sources required")
    if (not isinstance(snapshots, (tuple, list)) or
            len(snapshots) > 64 or
            not isinstance(controller_evidence, (tuple, list)) or
            len(controller_evidence) > 64):
        raise QualityGateError("bounded campaign replays and controller observations required")
    authored_endings = {e.ending_id for e in questbook.endings}
    won_endings: set[str] = set()
    receipts = []
    failures = []
    for n, snapshot in enumerate(snapshots):
        try:
            session = ProductionSession.restore(world, player, storybook, questbook, snapshot)
            if not session.game.won:
                failures.append({"run": n, "code": "non_winning_session"})
                continue
            ending = session.ending()
            eid = ending["ending_id"]
            if eid not in authored_endings or ending.get("victory") is not True:
                failures.append({"run": n, "code": "forged_ending"})
                continue
            won_endings.add(eid)
            receipts.append({
                "run": n, "ending_id": eid, "session_head": session.head,
                "event_count": len(session.events),
                "original_game_played": True,
                "snapshot_sha256": _digest(snapshot),
            })
        except (ValueError, KeyError, TypeError) as exc:
            failures.append({"run": n, "code": "invalid_replay"})
    inspected_devices = set()
    for proof in controller_evidence:
        if not isinstance(proof, Mapping):
            raise QualityGateError("controller evidence must be structured")
        if (proof.get("world_digest") != world.digest or
                proof.get("verified") is not True or
                proof.get("kind") not in ("keyboard", "gamepad") or
                not isinstance(proof.get("receipt_sha256"), str)):
            raise QualityGateError("controller parity evidence has foreign or missing source")
        _sha(proof["receipt_sha256"], "controller evidence")
        inspected_devices.add(proof["kind"])
    if not {"keyboard", "gamepad"} <= inspected_devices:
        failures.append({"code": "controller_parity_incomplete"})
    native_valid = False
    if native_report is not None:
        if (not isinstance(native_report, Mapping) or
                native_report.get("schema") != "skeleton.game.expedition_native_complete_replay.v1" or
                native_report.get("world_digest") != world.digest or
                native_report.get("source_digest") != world.source_digest or
                native_report.get("native_process_executed") is not True or
                native_report.get("native_gameplay_consistent") is not True or
                native_report.get("completed") is not True or
                native_report.get("receipt_digest") != _digest({
                    k: v for k, v in native_report.items() if k != "receipt_digest"
                })):
            raise QualityGateError("native replay report cannot be independently traced")
        native_valid = True
    if not native_valid:
        failures.append({"code": "real_native_run_missing"})
    if require_all_endings and won_endings != authored_endings:
        failures.append({"code": "uncovered_endings",
                         "ids": sorted(authored_endings - won_endings)})
    if not receipts:
        failures.append({"code": "no_winning_canon_replays"})
    report = {
        "schema": "game.original_campaign_acceptance.v1",
        "world_digest": world.digest,
        "source_sha256": world.source_digest,
        "story_digest": storybook.digest,
        "quest_digest": questbook.digest,
        "authored_endings": sorted(authored_endings),
        "earned_endings": sorted(won_endings),
        "controller_profiles_observed": sorted(inspected_devices),
        "verified_sessions": receipts,
        "real_native_run_observed": native_valid,
        "candidate_passed": not failures,
        "production_release_certified": False,
        "failures": failures,
    }
    return {**report, "receipt_digest": _digest(report)}
