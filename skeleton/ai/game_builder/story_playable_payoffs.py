"""Cross-evidence proof that an original dramatic payoff is actually played.

Only join receipts from canonical StoryCanon and the existing Director quest
runtime. A signed prose payoff alone, or an unrelated solved quest, must never
masquerade as game-ready narrative closure. Source structures are revalidated
by their owning auditors before this read-only join is called.
"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import json
from typing import Any

SCHEMA = "skeleton.jeeves.playable_payoff_review.v1"


class PlayablePayoffError(ValueError):
    """Incompatible original story and game replay evidence."""


def _fingerprint(value: object) -> str:
    return sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")).hexdigest()


def audit_playable_payoffs(dramaturgy: dict[str, Any],
                          gameplay: dict[str, Any], *,
                          demand_alternative_outcomes: bool = False) -> dict[str, Any]:
    """Cross-check EVERY thread against actual source-bound Director results.

    Status remains unqualified unless all resolved story threads have one
    canonical signed payoff with executed gameplay evidence. Alternative
    consequences require distinct outcomes for the SAME quest/stage and
    the SAME source-authored dramatic payoff.
    """
    if not isinstance(dramaturgy, dict) or dramaturgy.get("schema") != (
        "skeleton.jeeves.story_threads.v1"
    ):
        raise PlayablePayoffError("verified canonical dramaturgy evidence required")
    if not isinstance(gameplay, dict) or gameplay.get("schema") != (
        "skeleton.jeeves.story_gameplay_binding.v1"
    ):
        raise PlayablePayoffError("verified canonical gameplay replay evidence required")
    if dramaturgy["scene_history_digest"] != gameplay["canonical_story_digest"]:
        raise PlayablePayoffError("literary payoff and playable quest evidence refer to different signed story histories")
    if type(demand_alternative_outcomes) is not bool:
        raise PlayablePayoffError("alternative outcome requirement must be explicit boolean")
    threads = dramaturgy["thread_evidence"]
    rows = gameplay["binding_evidence"]
    if not isinstance(threads, list) or not isinstance(rows, list):
        raise PlayablePayoffError("missing complete source-linked gameplay receipt collections")
    by_source: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, dict) or row.get("executed_in_canonical_director") is not True:
            raise PlayablePayoffError("unexecuted game result in playable payoff receipt")
        by_source[(row["scene_sequence"], row["source_anchor"])].append(row)

    statuses = []
    pending = []
    for thread in threads:
        if not isinstance(thread, dict) or thread.get("state") not in (
            "open", "resolved", "red_herring"
        ):
            raise PlayablePayoffError("malformed signed original story arc receipt")
        identifier = thread["id"]
        if thread["state"] == "open":
            pending.append({"thread_id": identifier, "issue": "no_canonical_payoff"})
            statuses.append({
                "thread_id": identifier, "state": "open", "executed_playable_payoff": False,
                "qualifying_branch_pairs": 0, "source_anchor": None,
                "executed_proofs": [], "professional_emotional_impact_verified": False,
            })
            continue
        if not thread.get("causal_path") or thread["causal_path"][0] != thread["setup_anchor"]:
            raise PlayablePayoffError("source-level payoff lacks its original causal setup proof")
        matching = by_source.get((thread["payoff_scene"], thread["payoff_anchor"]), [])
        pairs_by_stage: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
        receipts = []
        for row in matching:
            quest_stage = (row["quest"], row["stage"])
            pairs_by_stage[quest_stage].add((row["approach"], row["consequence"]))
            receipts.append({
                "quest": row["quest"], "stage": row["stage"],
                "replay": row["replay"],
                "replay_digest": row["director_replay_sha256"],
                "approach": row["approach"], "consequence": row["consequence"],
            })
        branched = any(len(pairs) >= 2 for pairs in pairs_by_stage.values())
        qualified = bool(receipts) and (
            not demand_alternative_outcomes or branched
        )
        if not receipts:
            pending.append({"thread_id": identifier, "issue": "unplayed_canonical_payoff"})
        elif demand_alternative_outcomes and not branched:
            pending.append({"thread_id": identifier, "issue": "no_distinct_playable_consequence"})
        statuses.append({
            "thread_id": identifier, "state": thread["state"],
            "source_anchor": {
                "scene": thread["payoff_scene"], "anchor": thread["payoff_anchor"]
            },
            "executed_playable_payoff": qualified,
            "qualifying_branch_pairs": max((len(v) for v in pairs_by_stage.values()), default=0),
            "executed_proofs": receipts,
            "professional_emotional_impact_verified": False,
        })
    complete = bool(statuses) and not pending
    return {
        "ok": True, "action": "playable-payoff-audit", "schema": SCHEMA,
        "canonical_story_digest": dramaturgy["scene_history_digest"],
        "director_world_digest": gameplay["director_world_digest"],
        "declared_dramatic_threads": len(statuses),
        "dramatic_threads_with_played_payoff": sum(x["executed_playable_payoff"] for x in statuses),
        "unresolved_or_unplayed_threads": pending,
        "payoffs": statuses,
        "requires_alternative_outcomes": demand_alternative_outcomes,
        "all_declared_story_payoffs_executed": complete,
        "source_replay_join_sha256": _fingerprint({
            "dramaturgy": dramaturgy["source_identity_sha256"],
            "gameplay": gameplay["replay_evidence_sha256"],
            "payoffs": statuses,
        }),
        "artistic_story_quality_verified": False,
        "independent_player_review_verified": False,
        "full_game_runtime_or_platform_certified": False,
        "human_approval_verified_by_this_lens": False,
    }
