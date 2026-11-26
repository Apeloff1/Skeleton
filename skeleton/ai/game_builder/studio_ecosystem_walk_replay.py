"""Authoritative, deterministic, source-bound walkable game state engine.

Movement is physical grid collision, and decisions require arrival at an
authored scene marker. All receipts are replayable locally; movement does
not represent real-world observation or proof of completed genre mechanics.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from .studio_ecosystem_walkable import playable_world_source
from .studio_ecosystem_quest import StudioQuestError

DIRECTIONS = {"up": (0, -1), "down": (0, 1),
              "left": (-1, 0), "right": (1, 0)}

# Bound untrusted browser transcripts before world generation, replay, or
# digesting. These are game-event proof limits, not local model/context limits.
MAX_WALK_EVENTS = 4096
MAX_WALK_EVENT_BYTES = 4096
MAX_WALK_HISTORY_BYTES = 1024 * 1024
# Allow JSON framing, but never deserialize an unbounded saved session.
MAX_WALK_RECEIPT_BYTES = MAX_WALK_HISTORY_BYTES + MAX_WALK_EVENTS * 64 + 8192


def _admit_events(events: Sequence[tuple[str, str]]) -> None:
    if not isinstance(events, (list, tuple)):
        raise StudioQuestError("walk events must be an ordered sequence")
    if len(events) > MAX_WALK_EVENTS:
        raise StudioQuestError("walk replay exceeds event budget")
    total = 0
    for event in events:
        if (not isinstance(event, (tuple, list)) or len(event) != 2
                or any(not isinstance(value, str) for value in event)):
            raise StudioQuestError("invalid walk event")
        for value in event:
            if len(value) > MAX_WALK_EVENT_BYTES:
                raise StudioQuestError("walk event exceeds byte budget")
            try:
                size = len(value.encode("utf-8", "strict"))
            except UnicodeError as exc:
                raise StudioQuestError("noncanonical walk event text") from exc
            if size > MAX_WALK_EVENT_BYTES:
                raise StudioQuestError("walk event exceeds byte budget")
            total += size
            if total > MAX_WALK_HISTORY_BYTES:
                raise StudioQuestError("walk replay exceeds history byte budget")


def validate_walk_events(events: Sequence[tuple[str, str]]) -> None:
    """Preflight untrusted event history without loading authored world source."""
    _admit_events(events)


def _sha(payload: object) -> str:
    try:
        raw = json.dumps(payload, ensure_ascii=True, sort_keys=True,
                         allow_nan=False, separators=(",", ":")).encode("ascii")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise StudioQuestError("noncanonical walk replay") from exc
    return sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class WalkSession:
    project_id: str
    source_digest: str
    events: tuple[tuple[str, str], ...]
    scene_index: int
    position: tuple[int, int]
    chosen: tuple[tuple[str, str], ...]
    accepted_moves: int
    digest: str

    def receipt(self) -> dict[str, object]:
        return {"schema": "skeleton.game_builder.studio_walk_replay.v1",
                "project_id": self.project_id, "source_digest": self.source_digest,
                "events": [list(e) for e in self.events],
                "scene_index": self.scene_index, "position": list(self.position),
                "choices": [list(e) for e in self.chosen],
                "accepted_moves": self.accepted_moves,
                "session_digest": self.digest,
                "external_evidence_verified": False,
                "native_genre_runtime_verified": False,
                "release_certified": False}


def _compute(documents: Mapping[str, Any],
             events: Sequence[tuple[str, str]]) -> WalkSession:
    _admit_events(events)
    world = playable_world_source(documents)
    stages = world["stages"]
    maps = world["maps"]
    x, y = world["spawn"]
    target_x, target_y = world["target"]
    scene = 0
    moved = 0
    history: list[tuple[str, str]] = []
    choices: list[tuple[str, str]] = []
    chosen_ids: set[str] = set()
    for event in events:
        kind, value = event
        if scene >= len(stages):
            raise StudioQuestError("walk event after authored game completion")
        stage = stages[scene]
        if kind == "move":
            delta = DIRECTIONS.get(value)
            if delta is None:
                raise StudioQuestError("unknown walk direction")
            nx, ny = x + delta[0], y + delta[1]
            if (not 0 <= nx < world["width"] or not 0 <= ny < world["height"]
                    or maps[scene][ny][nx] == "#"):
                raise StudioQuestError("blocked or off-grid movement")
            x, y = nx, ny
            moved += 1
        elif kind == "choose":
            if (value not in stage["alternatives"]
                    or abs(x - target_x) + abs(y - target_y) > 1
                    or not set(stage["prerequisites"]).issubset(chosen_ids)):
                raise StudioQuestError("unauthorized or distant scene interaction")
            choices.append((stage["id"], value))
            chosen_ids.add(stage["id"])
            scene += 1
            x, y = world["spawn"]
        else:
            raise StudioQuestError("unregistered walk action")
        history.append((kind, value))
    state = {"project_id": world["project_id"],
             "source_digest": world["source_digest"],
             "events": history, "scene_index": scene,
             "position": [x, y], "choices": choices,
             "accepted_moves": moved}
    return WalkSession(world["project_id"], world["source_digest"],
                       tuple(history), scene, (x, y), tuple(choices),
                       moved, _sha(state))


def replay_walk(documents: Mapping[str, Any],
                events: Sequence[tuple[str, str]], *, authorized: bool) -> WalkSession:
    if not authorized:
        raise PermissionError("walk game replay requires operator authorization")
    return _compute(documents, events)


def start_walk(documents: Mapping[str, Any], *, authorized: bool) -> WalkSession:
    return replay_walk(documents, (), authorized=authorized)


def verify_walk(session: WalkSession, documents: Mapping[str, Any]) -> None:
    if not isinstance(session, WalkSession):
        raise StudioQuestError("invalid walk session")
    if session != _compute(documents, session.events):
        raise StudioQuestError("walk state does not match authoritative replay")


def walk_action(session: WalkSession, documents: Mapping[str, Any], *,
                action: str, value: str, authorized: bool) -> WalkSession:
    if not authorized:
        raise PermissionError("walk movement requires operator authorization")
    if not isinstance(session, WalkSession):
        raise StudioQuestError("invalid walk session")
    # Avoid replaying the old history twice when the proposed action cannot
    # possibly be admitted; verification still precedes every accepted action.
    if len(session.events) >= MAX_WALK_EVENTS:
        raise StudioQuestError("walk replay exceeds event budget")
    _admit_events(((action, value),))
    verify_walk(session, documents)
    return _compute(documents, session.events + ((action, value),))


def export_walk_receipt(session: WalkSession, documents: Mapping[str, Any], *,
                        authorized: bool) -> bytes:
    """Serialize a verified source-bound walk save without trusting cached state."""
    if not authorized:
        raise PermissionError("walk session export requires operator authorization")
    verify_walk(session, documents)
    raw = json.dumps(session.receipt(), sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True, allow_nan=False).encode("ascii")
    if len(raw) > MAX_WALK_RECEIPT_BYTES:
        raise StudioQuestError("walk receipt exceeds export byte budget")
    return raw


_RECEIPT_FIELDS = frozenset({
    "schema", "project_id", "source_digest", "events", "scene_index",
    "position", "choices", "accepted_moves", "session_digest",
    "external_evidence_verified", "native_genre_runtime_verified",
    "release_certified",
})


def restore_walk_receipt(documents: Mapping[str, Any], raw: bytes, *,
                         authorized: bool) -> WalkSession:
    """Restore an untrusted saved session by replaying against canonical source.

    A browser/exported receipt is not authority: no cached position, choice,
    digest, or certification claim is accepted without deterministic replay.
    """
    if not authorized:
        raise PermissionError("walk session restore requires operator authorization")
    if (not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_WALK_RECEIPT_BYTES):
        raise StudioQuestError("invalid or oversized walk receipt")

    def unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
        record: dict[str, object] = {}
        for key, value in pairs:
            if key in record:
                raise StudioQuestError("duplicate walk receipt field")
            record[key] = value
        return record

    try:
        payload = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique_fields,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite walk receipt")),
        )
    except StudioQuestError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StudioQuestError("invalid walk receipt JSON") from exc
    if (not isinstance(payload, dict) or set(payload) != _RECEIPT_FIELDS
            or payload["schema"] != "skeleton.game_builder.studio_walk_replay.v1"
            or any(payload[key] is not False for key in (
                "external_evidence_verified", "native_genre_runtime_verified",
                "release_certified"))
            or type(payload["scene_index"]) is not int
            or type(payload["accepted_moves"]) is not int
            or not isinstance(payload["position"], list)
            or len(payload["position"]) != 2
            or any(type(n) is not int for n in payload["position"])
            or not isinstance(payload["events"], list)
            or not isinstance(payload["choices"], list)):
        raise StudioQuestError("invalid walk receipt contract")
    # This call enforces event count/byte limits before constructing the world.
    session = replay_walk(documents, payload["events"], authorized=True)
    if payload != session.receipt():
        raise StudioQuestError("walk receipt differs from authoritative source replay")
    return session


# The route explorer is a source-bound hint, not evidence of native gameplay.
MAX_ROUTE_CELLS = 4096
_ROUTE_ORDER = ("up", "right", "down", "left")


def walk_route_hint(session: WalkSession, documents: Mapping[str, Any], *,
                    authorized: bool) -> dict[str, object]:
    """Find a deterministic shortest walk to an authored interaction marker.

    Validate the entire existing replay before using its position. Locked,
    completed, or physically unreachable scenes never receive fabricated paths.
    """
    if not authorized:
        raise PermissionError("walk route requires operator authorization")
    verify_walk(session, documents)
    world = playable_world_source(documents)
    scene = session.scene_index
    stage = world["stages"][scene] if scene < len(world["stages"]) else None
    status = "completed"
    moves: list[str] = []
    if stage is not None:
        chosen_ids = {key for key, _ in session.chosen}
        if not set(stage["prerequisites"]).issubset(chosen_ids):
            status = "locked"
        else:
            width, height = world["width"], world["height"]
            if (type(width) is not int or type(height) is not int
                    or width < 1 or height < 1
                    or width * height > MAX_ROUTE_CELLS):
                raise StudioQuestError("walk route exceeds grid budget")
            rows = world["maps"][scene]
            if (len(rows) != height or any(not isinstance(row, str)
                                           or len(row) != width for row in rows)):
                raise StudioQuestError("invalid authored walk route map")
            start = session.position
            target = tuple(world["target"])
            if (len(target) != 2 or any(type(n) is not int for n in target)
                    or not (0 <= start[0] < width and 0 <= start[1] < height)
                    or rows[start[1]][start[0]] == "#"):
                raise StudioQuestError("invalid walk route coordinates")
            parents: dict[tuple[int, int], tuple[tuple[int, int], str] | None] = {start: None}
            queue = deque([start])
            destination = None
            while queue:
                cell = queue.popleft()
                if abs(cell[0] - target[0]) + abs(cell[1] - target[1]) <= 1:
                    destination = cell
                    break
                for direction in _ROUTE_ORDER:
                    dx, dy = DIRECTIONS[direction]
                    neighbor = (cell[0] + dx, cell[1] + dy)
                    nx, ny = neighbor
                    if (0 <= nx < width and 0 <= ny < height
                            and rows[ny][nx] != "#" and neighbor not in parents):
                        parents[neighbor] = (cell, direction)
                        queue.append(neighbor)
            if destination is None:
                status = "unreachable"
            else:
                while destination != start:
                    parent, direction = parents[destination]
                    moves.append(direction)
                    destination = parent
                moves.reverse()
                status = "ready" if moves else "already_near"
    payload = {"schema": "skeleton.game_builder.studio_walk_route_hint.v1",
               "project_id": session.project_id,
               "source_digest": session.source_digest,
               "session_digest": session.digest,
               "scene_id": stage["id"] if stage is not None else None,
               "status": status, "moves": moves,
               "distance": len(moves) if status in ("ready", "already_near") else None,
               "external_evidence_verified": False,
               "native_genre_runtime_verified": False,
               "release_certified": False}
    payload["route_digest"] = _sha(payload)
    return payload


def follow_walk_route(session: WalkSession, documents: Mapping[str, Any], *,
                      authorized: bool) -> tuple[WalkSession, dict[str, object]]:
    """Atomically replay a verified route to the next authored interaction.

    Only cardinal movement is performed: a route never chooses an authored
    alternative, unlocks a prerequisite, or confers game completion. Replaying
    the entire proposed history means a failed operation returns no new state.
    """
    if not authorized:
        raise PermissionError("walk route execution requires operator authorization")
    hint = walk_route_hint(session, documents, authorized=True)
    if hint["status"] not in ("ready", "already_near"):
        raise StudioQuestError("walk route cannot execute: " + str(hint["status"]))
    moves = hint["moves"]
    if not isinstance(moves, list) or any(move not in DIRECTIONS for move in moves):
        raise StudioQuestError("invalid computed walk route")
    if len(session.events) + len(moves) > MAX_WALK_EVENTS:
        raise StudioQuestError("walk route exceeds event budget")
    proposed = session.events + tuple(("move", move) for move in moves)
    _admit_events(proposed)
    after = replay_walk(documents, proposed, authorized=True)
    # A changed source or an inconsistent route must never produce a save.
    if (after.source_digest != session.source_digest
            or after.project_id != session.project_id
            or after.scene_index != session.scene_index
            or after.chosen != session.chosen):
        raise StudioQuestError("walk route changed source or authored state")
    final_hint = walk_route_hint(after, documents, authorized=True)
    if (final_hint["status"] != "already_near"
            or final_hint["scene_id"] != hint["scene_id"]):
        raise StudioQuestError("walk route failed authoritative destination check")
    proof: dict[str, object] = {
        "schema": "skeleton.game_builder.studio_walk_route_execution.v1",
        "project_id": session.project_id,
        "source_digest": session.source_digest,
        "scene_id": hint["scene_id"],
        "before_session_digest": session.digest,
        "after_session_digest": after.digest,
        "route_digest": hint["route_digest"],
        "moves": moves,
        "steps": len(moves),
        "interaction_ready": True,
        "choice_executed": False,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    proof["execution_digest"] = _sha(proof)
    return after, proof


MAX_WALK_CHOICE_PREVIEWS = 8


def walk_choice_previews(session: WalkSession, documents: Mapping[str, Any], *,
                         authorized: bool) -> dict[str, object]:
    """Preview exactly one authored choice per branch, without mutating a save.

    A preview is an authoritative sandbox replay, not an ending prediction or
    an external proof. Unreachable/locked scenes disclose no executable branch.
    All returned successor digests are derived from replay, not caller claims.
    """
    if not authorized:
        raise PermissionError("walk choice preview requires operator authorization")
    verify_walk(session, documents)
    world = playable_world_source(documents)
    if (world["source_digest"] != session.source_digest
            or world["project_id"] != session.project_id):
        raise StudioQuestError("walk preview changed authoritative source")
    scene = session.scene_index
    stages = world["stages"]
    if scene > len(stages):
        raise StudioQuestError("invalid walk preview scene index")
    stage = stages[scene] if scene < len(stages) else None
    status = "completed"
    previews: list[dict[str, object]] = []
    if stage is not None:
        chosen_ids = {key for key, _ in session.chosen}
        if not set(stage["prerequisites"]).issubset(chosen_ids):
            status = "locked"
        else:
            x, y = session.position
            target_x, target_y = world["target"]
            if abs(x - target_x) + abs(y - target_y) > 1:
                status = "distant"
            elif len(session.events) >= MAX_WALK_EVENTS:
                status = "budget_exhausted"
            else:
                alternatives = stage["alternatives"]
                if (not isinstance(alternatives, (tuple, list))
                        or not 1 <= len(alternatives) <= MAX_WALK_CHOICE_PREVIEWS
                        or any(not isinstance(a, str) or not 1 <= len(a) <= 256
                               for a in alternatives)
                        or len(set(alternatives)) != len(alternatives)):
                    raise StudioQuestError("invalid authored choice preview alternatives")
                status = "ready"
                for alternative in alternatives:
                    successor = replay_walk(
                        documents, session.events + (("choose", alternative),),
                        authorized=True,
                    )
                    if (successor.source_digest != session.source_digest
                            or successor.project_id != session.project_id
                            or successor.scene_index != scene + 1
                            or successor.chosen != session.chosen + ((stage["id"], alternative),)
                            or successor.accepted_moves != session.accepted_moves):
                        raise StudioQuestError("walk preview changed authoritative source")
                    next_stage = (stages[scene + 1] if scene + 1 < len(stages)
                                  else None)
                    previews.append({
                        "alternative": alternative,
                        "result_session_digest": successor.digest,
                        "next_scene_id": next_stage["id"] if next_stage else None,
                        "next_scene_index": successor.scene_index,
                        "sandbox_stages_complete": next_stage is None,
                    })
    payload: dict[str, object] = {
        "schema": "skeleton.game_builder.studio_walk_choice_previews.v1",
        "project_id": session.project_id,
        "source_digest": session.source_digest,
        "session_digest": session.digest,
        "scene_id": stage["id"] if stage is not None else None,
        "status": status,
        "alternatives": previews,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["preview_digest"] = _sha(payload)
    return payload


MAX_WALK_FORECAST_DEPTH = 3
MAX_WALK_FORECAST_NODES = 24


def walk_branch_forecast(session: WalkSession, documents: Mapping[str, Any], *,
                         depth: int = 2, authorized: bool) -> dict[str, object]:
    """Explore bounded physically reachable authored choices without saving.

    Every hypothetical step first walks the actual collision-checked route,
    then replays one authored alternative. A bounded breadth-first search
    produces deterministic leaf receipts and explicitly discloses truncation.
    These are sandbox predictions, not completed gameplay or ending proofs.
    """
    if not authorized:
        raise PermissionError("walk branch forecast requires operator authorization")
    if type(depth) is not int or not 1 <= depth <= MAX_WALK_FORECAST_DEPTH:
        raise StudioQuestError("walk forecast depth must be 1..3")
    verify_walk(session, documents)
    world = playable_world_source(documents)
    if (world["source_digest"] != session.source_digest
            or world["project_id"] != session.project_id):
        raise StudioQuestError("walk forecast changed authoritative source")
    stages = world["stages"]
    pending = deque([(session, (), 0)])
    admitted_nodes = 1
    examined_nodes = 0
    truncated = False
    leaves: list[dict[str, object]] = []

    def leaf(current: WalkSession, path: tuple[dict[str, object], ...],
             status: str) -> None:
        leaves.append({"status": status, "scene_index": current.scene_index,
                       "scene_id": (stages[current.scene_index]["id"]
                                    if current.scene_index < len(stages) else None),
                       "session_digest": current.digest, "steps": list(path)})

    while pending:
        current, path, distance = pending.popleft()
        examined_nodes += 1
        if (current.source_digest != session.source_digest
                or current.project_id != session.project_id):
            raise StudioQuestError("walk forecast changed authoritative source")
        if current.scene_index >= len(stages):
            leaf(current, path, "sandbox_complete")
            continue
        if distance >= depth:
            leaf(current, path, "depth_limit")
            continue
        hint = walk_route_hint(current, documents, authorized=True)
        if (hint["source_digest"] != session.source_digest
                or hint["session_digest"] != current.digest):
            raise StudioQuestError("walk forecast changed authoritative source")
        if hint["status"] not in ("ready", "already_near"):
            leaf(current, path, str(hint["status"]))
            continue
        moves = hint["moves"]
        if len(current.events) + len(moves) + 1 > MAX_WALK_EVENTS:
            leaf(current, path, "budget_exhausted")
            continue
        # Route execution is hypothetical: no caller session or save is mutated.
        approached, execution = follow_walk_route(current, documents, authorized=True)
        if (approached.source_digest != session.source_digest
                or approached.project_id != session.project_id
                or execution["before_session_digest"] != current.digest
                or execution["after_session_digest"] != approached.digest):
            raise StudioQuestError("walk forecast changed authoritative source")
        preview = walk_choice_previews(approached, documents, authorized=True)
        if (preview["source_digest"] != session.source_digest
                or preview["session_digest"] != approached.digest):
            raise StudioQuestError("walk forecast changed authoritative source")
        if preview["status"] != "ready":
            leaf(current, path, str(preview["status"]))
            continue
        for option in preview["alternatives"]:
            if admitted_nodes >= MAX_WALK_FORECAST_NODES:
                truncated = True
                continue
            choice = option["alternative"]
            next_session = replay_walk(
                documents, approached.events + (("choose", choice),),
                authorized=True,
            )
            if (next_session.digest != option["result_session_digest"]
                    or next_session.source_digest != session.source_digest
                    or next_session.scene_index != current.scene_index + 1
                    or next_session.chosen != current.chosen +
                    ((stages[current.scene_index]["id"], choice),)):
                raise StudioQuestError("walk forecast changed authoritative source")
            step: dict[str, object] = {
                "scene_id": stages[current.scene_index]["id"],
                "alternative": choice, "route_moves": list(moves),
                "route_digest": hint["route_digest"],
                "before_session_digest": current.digest,
                "after_session_digest": next_session.digest,
            }
            pending.append((next_session, path + (step,), distance + 1))
            admitted_nodes += 1

    payload: dict[str, object] = {
        "schema": "skeleton.game_builder.studio_walk_branch_forecast.v1",
        "project_id": session.project_id, "source_digest": session.source_digest,
        "session_digest": session.digest, "depth": depth,
        "node_budget": MAX_WALK_FORECAST_NODES,
        "nodes_examined": examined_nodes,
        "complete_enumeration": not truncated,
        "branches": leaves,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["forecast_digest"] = _sha(payload)
    return payload


def commit_walk_forecast_branch(
    session: WalkSession, documents: Mapping[str, Any], *,
    branch_index: int, depth: int = 2, authorized: bool,
) -> tuple[WalkSession, dict[str, object]]:
    """Commit one forecasted branch by authoritative replay, never by trusting a preview.

    The branch index refers to the canonical deterministic forecast for the
    *current* verified session. Callers cannot supply steps, route cells, choice
    text or digests as authority. The original immutable session is untouched
    if a route, prerequisite, source or event budget check fails mid-branch.
    """
    if not authorized:
        raise PermissionError("walk forecast commitment requires operator authorization")
    if type(branch_index) is not int or branch_index < 0:
        raise StudioQuestError("walk forecast branch index must be nonnegative integer")
    # Recompute from source and verify the supplied session before selecting
    # the index. The forecast itself is bounded to three scenes / 24 nodes.
    forecast = walk_branch_forecast(session, documents, depth=depth, authorized=True)
    branches = forecast["branches"]
    if branch_index >= len(branches):
        raise StudioQuestError("walk forecast branch index out of range")
    selected = branches[branch_index]
    if not selected["steps"]:
        raise StudioQuestError("walk forecast branch has no executable authored choices")
    current = session
    for step in selected["steps"]:
        if current.digest != step["before_session_digest"]:
            raise StudioQuestError("walk forecast branch stale before replay")
        hint = walk_route_hint(current, documents, authorized=True)
        if (hint["status"] not in ("ready", "already_near")
                or hint["scene_id"] != step["scene_id"]
                or hint["route_digest"] != step["route_digest"]
                or hint["moves"] != step["route_moves"]):
            raise StudioQuestError("walk forecast branch route changed")
        approached, execution = follow_walk_route(current, documents, authorized=True)
        if (execution["before_session_digest"] != current.digest
                or execution["after_session_digest"] != approached.digest):
            raise StudioQuestError("walk forecast branch movement proof changed")
        next_session = replay_walk(
            documents, approached.events + (("choose", step["alternative"]),),
            authorized=True,
        )
        if (next_session.digest != step["after_session_digest"]
                or next_session.source_digest != session.source_digest
                or next_session.project_id != session.project_id
                or next_session.scene_index != current.scene_index + 1):
            raise StudioQuestError("walk forecast branch choice proof changed")
        current = next_session
    if (current.digest != selected["session_digest"]
            or current.scene_index != selected["scene_index"]
            or current.events[:len(session.events)] != session.events):
        raise StudioQuestError("walk forecast branch final receipt mismatch")
    # A complete save is exported only after the entire branch passes; this
    # also enforces the receipt-size bound for clients that persist the result.
    export_walk_receipt(current, documents, authorized=True)
    proof: dict[str, object] = {
        "schema": "skeleton.game_builder.studio_walk_forecast_commit.v1",
        "project_id": session.project_id,
        "source_digest": session.source_digest,
        "before_session_digest": session.digest,
        "after_session_digest": current.digest,
        "forecast_digest": forecast["forecast_digest"],
        "forecast_depth": depth,
        "branch_index": branch_index,
        "branch_status": selected["status"],
        "committed_scenes": len(selected["steps"]),
        "committed_events": len(current.events) - len(session.events),
        "complete_enumeration": forecast["complete_enumeration"],
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    proof["commit_digest"] = _sha(proof)
    return current, proof


def walk_narrative_continuity(
    session: WalkSession, documents: Mapping[str, Any], *, authorized: bool,
) -> dict[str, object]:
    """Audit the *played* narrative against canonical quest/scene/ending source.

    Stage completion and earned rewards are sandbox facts, not external proof.
    The output is read-only, deterministic and bound to the verified session.
    Cross-section drift fails closed instead of silently projecting an ending.
    """
    if not authorized:
        raise PermissionError("walk continuity requires operator authorization")
    verify_walk(session, documents)
    from .studio_ecosystem_quest import compile_quest_program

    program = compile_quest_program(documents)
    world = playable_world_source(documents)
    stages = world["stages"]
    if (program.project_id != session.project_id
            or program.source_digest != session.source_digest
            or world["project_id"] != session.project_id
            or world["source_digest"] != session.source_digest
            or len(stages) != len(program.stages)
            or session.scene_index != len(session.chosen)):
        raise StudioQuestError("walk continuity source or scene count mismatch")
    for index, (stage, authored) in enumerate(zip(stages, program.stages, strict=True)):
        if (not isinstance(stage, dict)
                or stage.get("id") != authored.key
                or stage.get("alternatives") != list(authored.alternatives)
                or stage.get("prerequisites") != list(authored.prerequisites)
                or stage.get("reward") != authored.reward
                or not isinstance(stage.get("scene_id"), str)
                or not stage["scene_id"]):
            raise StudioQuestError("walk continuity quest/scene contract mismatch")
        if index < session.scene_index and session.chosen[index][0] != authored.key:
            raise StudioQuestError("walk continuity choice order mismatch")
    facts: set[str] = set()
    completed_ids: set[str] = set()
    trail: list[dict[str, object]] = []
    for index, (stage_id, choice) in enumerate(session.chosen):
        stage = program.stages[index]
        if (stage_id != stage.key or choice not in stage.alternatives
                or not set(stage.prerequisites).issubset(completed_ids)):
            raise StudioQuestError("walk continuity causal history mismatch")
        completed_ids.add(stage_id)
        facts.add(stage_id)
        facts.add(stage.reward)
        trail.append({"stage_id": stage_id,
                      "scene_id": stages[index]["scene_id"],
                      "alternative": choice, "sandbox_reward": stage.reward})
    endings = []
    for ending_id, requirements in program.endings:
        missing = sorted(set(requirements) - facts)
        endings.append({"ending_id": ending_id,
                        "sandbox_eligible": not missing,
                        "unmet_predicates": missing})
    next_stage = (stages[session.scene_index]
                  if session.scene_index < len(stages) else None)
    route = walk_route_hint(session, documents, authorized=True)
    if route["scene_id"] != (next_stage["id"] if next_stage else None):
        raise StudioQuestError("walk continuity route/source mismatch")
    payload: dict[str, object] = {
        "schema": "skeleton.game_builder.studio_walk_narrative_continuity.v1",
        "project_id": session.project_id,
        "source_digest": session.source_digest,
        "session_digest": session.digest,
        "completed_stages": len(trail),
        "authored_stage_count": len(stages),
        "sandbox_story_complete": next_stage is None,
        "played_trail": trail,
        "next_stage_id": next_stage["id"] if next_stage else None,
        "next_scene_id": next_stage["scene_id"] if next_stage else None,
        "next_route_status": route["status"],
        "sandbox_endings": endings,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["continuity_digest"] = _sha(payload)
    return payload



def compare_walk_sessions(
    current: WalkSession, alternative: WalkSession,
    documents: Mapping[str, Any], *, authorized: bool,
) -> dict[str, object]:
    """Compare two *verified* authored playthroughs without mutating either.

    The first differing event is causal replay evidence, not proof that an
    authored narrative branch has different consequences. Movement forks may
    converge to identical quest choices; those distinctions are explicit.
    """
    if not authorized:
        raise PermissionError("walk comparison requires operator authorization")
    verify_walk(current, documents)
    verify_walk(alternative, documents)
    if (current.project_id != alternative.project_id
            or current.source_digest != alternative.source_digest):
        raise StudioQuestError("walk comparison source mismatch")

    left, right = current.events, alternative.events
    shared = 0
    while shared < min(len(left), len(right)) and left[shared] == right[shared]:
        shared += 1
    if shared == len(left) == len(right):
        relation = "identical"
    elif shared == len(left):
        relation = "current_prefix"
    elif shared == len(right):
        relation = "alternative_prefix"
    else:
        relation = "fork"

    common_choices = 0
    while (common_choices < min(len(current.chosen), len(alternative.chosen))
           and current.chosen[common_choices] == alternative.chosen[common_choices]):
        common_choices += 1
    differing_choices = (common_choices < min(len(current.chosen), len(alternative.chosen)))
    payload: dict[str, object] = {
        "schema": "skeleton.game_builder.studio_walk_comparison.v1",
        "project_id": current.project_id,
        "source_digest": current.source_digest,
        "current_session_digest": current.digest,
        "alternative_session_digest": alternative.digest,
        "relation": relation,
        "shared_event_count": shared,
        "first_difference_index": None if relation == "identical" else shared,
        "current_next_event": list(left[shared]) if shared < len(left) else None,
        "alternative_next_event": list(right[shared]) if shared < len(right) else None,
        "current_event_count": len(left),
        "alternative_event_count": len(right),
        "shared_choice_count": common_choices,
        "same_authored_choices": current.chosen == alternative.chosen,
        "choice_fork": differing_choices,
        "current_completed_stages": current.scene_index,
        "alternative_completed_stages": alternative.scene_index,
        "current_position": list(current.position),
        "alternative_position": list(alternative.position),
        "current_accepted_moves": current.accepted_moves,
        "alternative_accepted_moves": alternative.accepted_moves,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["comparison_digest"] = _sha(payload)
    return payload


def rewind_walk_choices(
    session: WalkSession, documents: Mapping[str, Any], *,
    count: int, authorized: bool,
) -> tuple[WalkSession, dict[str, object]]:
    """Branch from immediately before an authored choice, never mutate a save.

    Movement preceding the selected choice remains authoritative, so the
    player may select a different authored alternative at the same marker.
    Subsequent scenes, rewards and movement are discarded by full replay.
    """
    if not authorized:
        raise PermissionError("walk rewind requires operator authorization")
    if type(count) is not int or not 1 <= count <= 32:
        raise StudioQuestError("walk rewind count must be 1..32")
    verify_walk(session, documents)
    positions = [i for i, event in enumerate(session.events) if event[0] == "choose"]
    if count > len(positions):
        raise StudioQuestError("walk rewind exceeds authored choice history")
    cutoff = positions[-count]
    retained = session.events[:cutoff]
    restored = replay_walk(documents, retained, authorized=True)
    # Guard against source changes between the original verification and
    # branch construction, even when a test/provider swaps world sources.
    verify_walk(session, documents)
    verify_walk(restored, documents)
    if (restored.source_digest != session.source_digest
            or restored.project_id != session.project_id
            or restored.scene_index != session.scene_index - count
            or restored.chosen != session.chosen[:-count]
            or restored.events != retained):
        raise StudioQuestError("walk rewind source or history drift")
    removed = session.events[cutoff:]
    payload: dict[str, object] = {
        "schema": "skeleton.game_builder.studio_walk_choice_rewind.v1",
        "project_id": session.project_id,
        "source_digest": session.source_digest,
        "before_session_digest": session.digest,
        "after_session_digest": restored.digest,
        "rewound_choice_count": count,
        "removed_event_count": len(removed),
        "retained_event_count": len(retained),
        "restored_scene_index": restored.scene_index,
        "restored_position": list(restored.position),
        "reopened_stage_id": session.chosen[-count][0],
        "removed_choices": [list(choice) for choice in session.chosen[-count:]],
        "original_save_unchanged": True,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["rewind_digest"] = _sha(payload)
    return restored, payload


# A timeline is intentionally a small replay index, not a second saved-state
# authority. Each checkpoint is reconstructed from the canonical event prefix.
MAX_WALK_CHECKPOINTS = 32
MAX_WALK_TIMELINE_REPLAY_EVENTS = 16384


def _checkpoint_cutoffs(session: WalkSession) -> list[tuple[int, int]]:
    """Return (absolute choice index, event prefix length), including genesis."""
    return [(0, 0)] + [
        (index, position + 1)
        for index, (position, event) in enumerate(
            ((pos, action) for pos, action in enumerate(session.events)
             if action[0] == "choose"), start=1,
        )
    ]


def walk_checkpoint_timeline(
    session: WalkSession, documents: Mapping[str, Any], *, authorized: bool,
) -> dict[str, object]:
    """Inspect bounded authored scene checkpoints without mutating the save.

    The latest checkpoints are selected under an aggregate replay-work budget.
    Checkpoint numbers are absolute choice counts, not positions in the page.
    Every displayed checkpoint is independently reconstructed from source.
    """
    if not authorized:
        raise PermissionError("walk timeline requires operator authorization")
    verify_walk(session, documents)
    cutoffs = _checkpoint_cutoffs(session)
    if len(cutoffs) != session.scene_index + 1:
        raise StudioQuestError("walk timeline choice history mismatch")
    selected = [cutoffs[0]]
    replay_cost = 0
    latest: list[tuple[int, int]] = []
    for index, cutoff in reversed(cutoffs[1:]):
        if (len(latest) >= MAX_WALK_CHECKPOINTS
                or replay_cost + cutoff > MAX_WALK_TIMELINE_REPLAY_EVENTS):
            break
        latest.append((index, cutoff))
        replay_cost += cutoff
    selected.extend(reversed(latest))
    checkpoints: list[dict[str, object]] = []
    for index, cutoff in selected:
        checkpoint = replay_walk(documents, session.events[:cutoff], authorized=True)
        if (checkpoint.project_id != session.project_id
                or checkpoint.source_digest != session.source_digest
                or checkpoint.scene_index != index
                or checkpoint.chosen != session.chosen[:index]
                or checkpoint.events != session.events[:cutoff]):
            raise StudioQuestError("walk timeline source or history drift")
        checkpoint_record: dict[str, object] = {
            "checkpoint_index": index,
            "event_count": cutoff,
            "scene_index": checkpoint.scene_index,
            "completed_stage_id": session.chosen[index - 1][0] if index else None,
            "selected_choice": session.chosen[index - 1][1] if index else None,
            "position": list(checkpoint.position),
            "session_digest": checkpoint.digest,
        }
        checkpoint_record["checkpoint_digest"] = _sha({
            "project_id": session.project_id,
            "source_digest": session.source_digest,
            **checkpoint_record,
        })
        checkpoints.append(checkpoint_record)
    verify_walk(session, documents)
    payload: dict[str, object] = {
        "schema": "skeleton.game_builder.studio_walk_timeline.v1",
        "project_id": session.project_id,
        "source_digest": session.source_digest,
        "session_digest": session.digest,
        "total_choice_count": session.scene_index,
        "checkpoint_count": len(checkpoints),
        "omitted_checkpoint_count": len(cutoffs) - len(checkpoints),
        "replay_work_events": replay_cost,
        "checkpoints": checkpoints,
        "original_save_unchanged": True,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["timeline_digest"] = _sha(payload)
    return payload


def restore_walk_checkpoint(
    session: WalkSession, documents: Mapping[str, Any], *,
    checkpoint_index: int, authorized: bool,
) -> tuple[WalkSession, dict[str, object]]:
    """Restore a displayed authored checkpoint by replay, never cached state."""
    if not authorized:
        raise PermissionError("walk checkpoint restore requires operator authorization")
    if type(checkpoint_index) is not int or checkpoint_index < 0:
        raise StudioQuestError("invalid walk checkpoint index")
    timeline = walk_checkpoint_timeline(session, documents, authorized=True)
    available = {point["checkpoint_index"]: point
                 for point in timeline["checkpoints"]}
    if checkpoint_index not in available:
        raise StudioQuestError("walk checkpoint outside bounded timeline")
    point = available[checkpoint_index]
    restored = replay_walk(
        documents, session.events[:point["event_count"]], authorized=True,
    )
    verify_walk(session, documents)
    verify_walk(restored, documents)
    if (restored.digest != point["session_digest"]
            or restored.source_digest != session.source_digest
            or restored.chosen != session.chosen[:checkpoint_index]
            or restored.scene_index != checkpoint_index):
        raise StudioQuestError("walk checkpoint source or history drift")
    payload: dict[str, object] = {
        "schema": "skeleton.game_builder.studio_walk_checkpoint_restore.v1",
        "project_id": session.project_id,
        "source_digest": session.source_digest,
        "before_session_digest": session.digest,
        "after_session_digest": restored.digest,
        "checkpoint_index": checkpoint_index,
        "checkpoint_digest": point["checkpoint_digest"],
        "retained_event_count": len(restored.events),
        "discarded_event_count": len(session.events) - len(restored.events),
        "original_save_unchanged": True,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["restore_digest"] = _sha(payload)
    return restored, payload
