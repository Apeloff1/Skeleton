"""Accessible offline JSON-line tactical arena, with bounded human input.

No graphics, audio, network or external model provider is implied. Each turn
exposes a compact text map, actor legend, legal moves and legal targets.
"""
from __future__ import annotations

import json
import sys
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, MAX_CLI_BYTES, _parse_json,
)
from skeleton.game.gameplay.tactical_arena import (
    _active, _advance, legal_moves, legal_targets, new_arena,
    normalize_arena, verify_arena,
)

MAX_INPUT_RETRIES = 3


def render_arena(source: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """Render a deterministic text grid and stable actor legend for assistive UI."""
    width, height = source["width"], source["height"]
    grid = [["." for _ in range(width)] for _ in range(height)]
    for x, y in source["walls"]:
        grid[y][x] = "#"
    legend = []
    for index, actor in enumerate(source["actors"]):
        actor_id = actor["id"]
        status = state["actors"][actor_id]
        symbol = "0123456789ABCDEF"[index]
        x, y = status["position"]
        if status["hp"] > 0:
            grid[y][x] = symbol
        legend.append({
            "symbol": symbol, "id": actor_id, "team": actor["team"],
            "hp": status["hp"], "position": list(status["position"]),
            "guard": status["guard"],
        })
    return {
        "width": width, "height": height,
        "rows": ["".join(row) for row in grid],
        "legend": legend,
        "legend_note": "# wall; . free; 0-F actors; dead actors absent from grid",
    }


def _teams(source: dict[str, Any], raw: Any) -> set[str]:
    teams = {actor["team"] for actor in source["actors"]}
    if type(raw) is not list or any(type(x) is not str for x in raw):
        raise CombatSessionError("invalid auto-team selection")
    selected = set(raw)
    if len(selected) != len(raw) or not selected.issubset(teams):
        raise CombatSessionError("unknown or duplicate auto-team")
    if selected == teams:
        raise CombatSessionError("interactive mode needs a human-controlled team")
    return selected


def _write(writer: Any, event: dict[str, Any]) -> None:
    writer.write(json.dumps(
        event, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ) + "\n")
    writer.flush()


def play_arena(source: Any, *, input_stream: Any = None,
               output_stream: Any = None, resume: Any = None,
               auto_teams: Any = None) -> dict[str, Any]:
    """Run bounded human/automated turns with replay-verifiable output.

    On malformed input, the current state is unchanged. A terminal save is
    emitted only after a real win/draw; EOF and retry exhaustion fail closed.
    """
    reader = sys.stdin if input_stream is None else input_stream
    writer = sys.stdout if output_stream is None else output_stream
    spec = normalize_arena(source)
    automated = _teams(spec, [] if auto_teams is None else auto_teams)
    session = new_arena(spec) if resume is None else verify_arena(resume)
    if session["source_digest"] != dig(spec):
        raise CombatSessionError("interactive arena source mismatch")
    while session["state"]["phase"] == "active":
        actor_id, _ = _active(spec, session["state"])
        team = next(a["team"] for a in spec["actors"] if a["id"] == actor_id)
        moves = legal_moves(spec, session["state"], actor_id)
        targets = legal_targets(spec, session["state"], actor_id)
        if team in automated:
            from skeleton.game.gameplay.arena_policy import _decide, POLICY
            before = session["state_digest"]
            action = _decide(session)
            session = _advance(session, action)
            _write(writer, {
                "event": "auto_action", "policy": POLICY, "actor_id": actor_id,
                "action": action, "before": before,
                "after": session["state_digest"],
                "receipt": session["journal"][-1]["receipt"],
            })
            continue
        _write(writer, {
            "event": "turn", "actor_id": actor_id,
            "tick": session["state"]["tick"],
            "state_digest": session["state_digest"],
            "map": render_arena(spec, session["state"]),
            "legal_moves": moves, "legal_targets": targets,
            "actions": ["move", "attack", "guard", "rest"],
        })
        for attempt in range(MAX_INPUT_RETRIES):
            line = reader.readline(MAX_CLI_BYTES + 1)
            if not line:
                raise CombatSessionError("input ended before arena terminal")
            try:
                if len(line.encode("utf-8")) > MAX_CLI_BYTES:
                    raise CombatSessionError("interactive action exceeds 128 KiB")
                action = _parse_json(line, "arena action")
                next_session = _advance(session, action)
            except (CombatSessionError, UnicodeError) as exc:
                _write(writer, {
                    "event": "rejected", "error": str(exc),
                    "remaining_retries": MAX_INPUT_RETRIES - attempt - 1,
                })
                if attempt == MAX_INPUT_RETRIES - 1:
                    raise CombatSessionError(
                        "three invalid actions in one arena turn"
                    ) from exc
            else:
                session = next_session
                break
    _write(writer, {"event": "terminal", "session": session})
    return session
