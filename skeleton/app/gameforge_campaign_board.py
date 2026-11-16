"""Read-only campaign board, branch comparison and offline HTML report.

The canonical campaign replay remains the only action authority. This module
does not execute JavaScript or rely on a browser for verification.
"""
from __future__ import annotations

from collections import defaultdict
from html import escape
from typing import Any

from skeleton.app.gameforge_campaign import _admit, append_actions, digest, detached, verify_session
from skeleton.app.gameforge_campaign_assist import plan_completion
from skeleton.app.gameforge_quest_bridge import _steps
from skeleton.app.original_quest_cli import _encode, _integer, _object, _require
from skeleton.gameforge.errors import GameForgeError

BOARD_SCHEMA = "skeleton.gameforge.campaign.board.v1"
COMPARISON_SCHEMA = "skeleton.gameforge.campaign.comparison.v1"
MAX_HTML_BYTES = 2 * 1024 * 1024


def _totals(rewards: list) -> dict:
    totals: dict[str, int] = defaultdict(int)
    for reward in rewards:
        totals[reward["kind"]] += reward["amount"]
    return dict(sorted(totals.items()))


def board(source: Any, checkpoint: Any) -> dict:
    _require(verify_session(source, checkpoint), "checkpoint does not replay")
    base, conversations, gates = _admit(source)
    state = checkpoint["state"]
    position = state["location"]
    quest = state["quest"]["state"]["quest_snapshot"]
    objectives = []
    for step in _steps(base["quest_receipt"]["artifact"]):
        row = {"id": step["id"], "description": step["text"],
               "location": step["location"], "npc": step["npc"],
               "state": quest["states"][step["id"]],
               "requires": step["requires"]}
        if step["id"] in gates:
            npc, grant = gates[step["id"]]
            dialogue = state["dialogues"][npc]["state"]
            row["dialogue_gate"] = {
                "npc": npc, "grant": grant,
                "satisfied": dialogue["phase"] == "ended" and grant in dialogue["quests"],
            }
        objectives.append(row)
    nearby = []
    for npc, location in sorted(base["world"]["npcs"].items()):
        if location != position:
            continue
        row = {"npc": npc, "location": location}
        if npc in conversations:
            saved = state["dialogues"][npc]["state"]
            node = next(n for n in conversations[npc]["source"]["nodes"]
                        if n["id"] == saved["node_id"])
            row.update({"node": saved["node_id"], "text": node["text"],
                        "phase": saved["phase"], "reputation": saved["reputation"],
                        "earned_grants": saved["quests"],
                        "choices": [a["choice"] for a in state["legal_actions"]
                                    if a["type"] == "dialogue" and a["npc"] == npc]})
        nearby.append(row)
    body = {"schema": BOARD_SCHEMA, "source_digest": digest(source),
            "checkpoint_digest": checkpoint["session_digest"],
            "title": base["conductor_manifest"]["metadata"]["title"],
            "status": state["status"], "location": position,
            "neighbors": base["world"]["edges"][position],
            "regions": sorted(base["world"]["edges"]),
            "nearby_npcs": nearby, "objectives": objectives,
            "earned_totals": _totals(state["earned_rewards"]),
            "legal_actions": state["legal_actions"], "action_count": len(checkpoint["actions"]),
            "native_qualified": False, "release_qualified": False}
    result = {**body, "board_digest": digest(body)}
    _encode(result)
    return result


def compare_branches(source: Any, left: Any, right: Any, *, max_expansions: int = 256) -> dict:
    _require(verify_session(source, left) and verify_session(source, right),
             "both branches require independent source replay")
    a, b = left["actions"], right["actions"]
    common = 0
    for first, second in zip(a, b):
        if first != second:
            break
        common += 1
    ls, rs = left["state"], right["state"]
    left_totals, right_totals = _totals(ls["earned_rewards"]), _totals(rs["earned_rewards"])
    reward_delta = {kind: right_totals.get(kind, 0) - left_totals.get(kind, 0)
                    for kind in sorted(left_totals.keys() | right_totals.keys())}
    objective_left = ls["quest"]["state"]["quest_snapshot"]["states"]
    objective_right = rs["quest"]["state"]["quest_snapshot"]["states"]
    outcomes = {npc: {
        "left_phase": ls["dialogues"][npc]["state"]["phase"],
        "right_phase": rs["dialogues"][npc]["state"]["phase"],
        "reputation_delta": rs["dialogues"][npc]["state"]["reputation"]
                            - ls["dialogues"][npc]["state"]["reputation"],
        "left_grants": ls["dialogues"][npc]["state"]["quests"],
        "right_grants": rs["dialogues"][npc]["state"]["quests"],
    } for npc in sorted(ls["dialogues"])}
    left_plan = plan_completion(source, left, max_expansions=max_expansions)
    right_plan = plan_completion(source, right, max_expansions=max_expansions)
    body = {"schema": COMPARISON_SCHEMA, "source_digest": digest(source),
            "left_digest": left["session_digest"], "right_digest": right["session_digest"],
            "common_prefix": common,
            "left_action_count": len(a), "right_action_count": len(b),
            "left_first_divergence": a[common] if common < len(a) else None,
            "right_first_divergence": b[common] if common < len(b) else None,
            "left_status": ls["status"], "right_status": rs["status"],
            "left_location": ls["location"], "right_location": rs["location"],
            "reward_delta_right_minus_left": reward_delta,
            "dialogue_outcomes": outcomes,
            "objective_changes": {oid: {"left": objective_left[oid], "right": objective_right[oid]}
                                  for oid in sorted(objective_left)
                                  if objective_left[oid] != objective_right[oid]},
            "left_completion": {"status": left_plan["status"], "blocker": left_plan["blocker"]},
            "right_completion": {"status": right_plan["status"], "blocker": right_plan["blocker"]},
            "search_budget_per_branch": max_expansions,
            "native_qualified": False, "release_qualified": False}
    result = {**body, "comparison_digest": digest(body)}
    _encode(result)
    return result


def render_html(source: Any, checkpoint: Any) -> str:
    """Portable no-script, no-network player board; use CLI to apply actions."""
    data = board(source, checkpoint)
    def e(value: Any) -> str:
        return escape(str(value), quote=True)
    sections = []
    for objective in data["objectives"]:
        gate = objective.get("dialogue_gate")
        extra = ""
        if gate:
            extra = ("; dialogue grant satisfied" if gate["satisfied"] else
                     "; requires " + e(gate["grant"]) + " from " + e(gate["npc"]))
        sections.append("<li><strong>" + e(objective["description"]) + "</strong> — "
                        + e(objective["state"]) + " (" + e(objective["location"]) + ")" + extra + "</li>")
    npcs = []
    for npc in data["nearby_npcs"]:
        npcs.append("<article><h3>" + e(npc["npc"]) + "</h3><p>"
                    + e(npc.get("text", "No authored dialogue attached.")) + "</p><p>"
                    + e(npc.get("phase", "present")) + "</p></article>")
    actions = ["<li><code>" + e(_encode(action).decode("ascii")) + "</code></li>"
               for action in data["legal_actions"]]
    totals = ["<li>" + e(kind) + ": " + e(amount) + "</li>"
              for kind, amount in data["earned_totals"].items()]
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
        '<title>' + e(data["title"]) + '</title><style>'
        'body{font:1rem system-ui,sans-serif;background:#151923;color:#eef1f5;margin:0}'
        'main{max-width:58rem;margin:auto;padding:1.5rem}section{border:1px solid #637083;'
        'border-radius:.5rem;padding:1rem;margin:1rem 0}li{margin:.6rem 0}'
        'code{overflow-wrap:anywhere}h1,h2{color:#c9e4ff}small{overflow-wrap:anywhere}'
        '</style></head><body><main><h1>' + e(data["title"]) + '</h1>'
        '<p>Verified abstract checkpoint · ' + e(data["status"]) + ' · ' + e(data["location"]) + '</p>'
        '<section><h2>World</h2><p>Adjacent regions: ' + e(", ".join(data["neighbors"])) + '</p>'
        '<h2>Nearby characters</h2>' + ("".join(npcs) or "<p>None</p>") + '</section>'
        '<section><h2>Objectives</h2><ul>' + "".join(sections) + '</ul></section>'
        '<section><h2>Earned rewards</h2><ul>' + ("".join(totals) or "<li>None yet</li>") + '</ul></section>'
        '<section><h2>Legal player actions</h2><p>Submit one action through the campaign CLI. '
        'This offline report cannot change saves.</p><ul>' + ("".join(actions) or "<li>None</li>") + '</ul></section>'
        '<small>Checkpoint ' + e(data["checkpoint_digest"]) + '<br>Native and release qualification: false.</small>'
        '</main></body></html>'
    )
    _require(len(html.encode("utf-8")) <= MAX_HTML_BYTES, "HTML board too large")
    return html


def verify_board(source: Any, checkpoint: Any, submitted: Any) -> bool:
    try:
        return _encode(submitted) == _encode(board(source, checkpoint))
    except (GameForgeError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False


def verify_comparison(source: Any, left: Any, right: Any, submitted: Any) -> bool:
    try:
        return _encode(submitted) == _encode(compare_branches(
            source, left, right, max_expansions=submitted["search_budget_per_branch"]))
    except (GameForgeError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False


HANDOFF_SCHEMA = "skeleton.gameforge.campaign.portable_checkpoint.v1"


def choose_board_action(source: Any, checkpoint: Any, board_digest: str, index: int) -> dict:
    """Select by zero-based index under an exact board digest, never a stale index."""
    current = board(source, checkpoint)
    _require(type(board_digest) is str and board_digest == current["board_digest"],
             "player board changed")
    legal = current["legal_actions"]
    _require(bool(legal), "no legal player actions")
    selected = _integer(index, 0, len(legal) - 1)
    following = append_actions(source, checkpoint, [legal[selected]])
    result = {"previous_board_digest": board_digest, "selected_index": selected,
              "action": legal[selected], "receipt": following,
              "board": board(source, following), "native_qualified": False,
              "release_qualified": False}
    _encode(result)
    return result


def export_checkpoint(source: Any, checkpoint: Any) -> dict:
    """Portable source-and-receipt envelope, with derived report identities."""
    current = board(source, checkpoint)
    body = {"schema": HANDOFF_SCHEMA, "source": source, "receipt": checkpoint,
            "board_digest": current["board_digest"],
            "native_qualified": False, "release_qualified": False}
    result = {**body, "handoff_digest": digest(body)}
    # Must fit the receiving command with an independent source, too.
    _encode({"request": source, "handoff": result})
    return detached(result)


def import_checkpoint(source: Any, handoff: Any) -> dict:
    """The imported source is descriptive; independent input remains authoritative."""
    _encode({"request": source, "handoff": handoff})
    data = _object(handoff, {"schema", "source", "receipt", "board_digest",
                             "native_qualified", "release_qualified", "handoff_digest"})
    _require(_encode(source) == _encode(data["source"]), "handoff source mismatch")
    _require(_encode(data) == _encode(export_checkpoint(source, data["receipt"])),
             "handoff differs from independent canonical replay")
    return detached(data["receipt"])
