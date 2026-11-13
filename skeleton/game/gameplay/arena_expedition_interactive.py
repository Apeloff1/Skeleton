"""Bounded human expedition CLI over the canonical source-bound runtime.

The JSON-line protocol makes offline expedition choices accessible without
claiming native graphics, voice, networking or a signed save format.
"""
from __future__ import annotations

import json
import re
import sys
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, MAX_CLI_BYTES, _parse_json,
)
from skeleton.game.gameplay.arena_expedition import (
    _advance, new_expedition, normalize_expedition, verify_expedition,
)

MAX_RETRIES = 3
MAX_OUTPUT_BYTES = 2 * 1024 * 1024


def _write(writer: Any, value: dict[str, Any]) -> None:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    )
    if len(encoded.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise CombatSessionError("interactive expedition output budget exceeded")
    writer.write(encoded + "\n")
    writer.flush()


def _checkpoint(writer: Any, session: dict[str, Any], reason: str) -> None:
    verified = verify_expedition(session)
    _write(writer, {
        "event": "checkpoint", "reason": reason,
        "source_digest": verified["source_digest"],
        "state_digest": verified["state_digest"], "session": verified,
    })


def play_expedition(
    source: Any, *, input_stream: Any = None,
    output_stream: Any = None, resume: Any = None,
    expected_source_digest: str | None = None,
    checkpoint_every: int = 8,
) -> dict[str, Any]:
    reader = sys.stdin if input_stream is None else input_stream
    writer = sys.stdout if output_stream is None else output_stream
    if type(checkpoint_every) is not int or not 1 <= checkpoint_every <= 32:
        raise CombatSessionError("invalid expedition checkpoint interval")
    spec = normalize_expedition(source)
    session = new_expedition(spec) if resume is None else verify_expedition(resume)
    if session["source_digest"] != dig(spec):
        raise CombatSessionError("interactive expedition source mismatch")
    if expected_source_digest is not None and (
        type(expected_source_digest) is not str
        or re.fullmatch(r"[0-9a-f]{64}", expected_source_digest) is None
        or expected_source_digest != session["source_digest"]
    ):
        raise CombatSessionError("expedition trusted source digest mismatch")
    while session["state"]["phase"] == "active":
        state = session["state"]
        index = state["next_index"]
        _write(writer, {
            "event": "turn",
            "expedition_id": spec["expedition_id"],
            "tick": state["tick"],
            "state_digest": session["state_digest"],
            "next_arena": (
                spec["arenas"][index]["arena"]["arena_id"]
                if index < len(spec["arenas"]) else None
            ),
            "hero_hp": state["hero_hp"],
            "currency": state["currency"],
            "inventory": state["inventory"],
            "shop": spec["shop"],
            "actions": ["fight", "fight_tactical", "buy", "use"],
            "tactical_note": (
                "fight_tactical takes ordered hero_actions; opponents use "
                "deterministic offline policy; incomplete scripts are rejected"
            ),
        })
        for attempt in range(MAX_RETRIES):
            line = reader.readline(MAX_CLI_BYTES + 1)
            if not line:
                _checkpoint(writer, session, "input_eof")
                raise CombatSessionError(
                    "input ended before expedition terminal; checkpoint emitted"
                )
            try:
                if len(line.encode("utf-8")) > MAX_CLI_BYTES:
                    raise CombatSessionError("interactive expedition action exceeds 128 KiB")
                action = _parse_json(line, "expedition action")
                updated = _advance(session, action)
            except (CombatSessionError, UnicodeError) as exc:
                _write(writer, {
                    "event": "rejected", "error": str(exc),
                    "remaining_retries": MAX_RETRIES - attempt - 1,
                    "state_digest": session["state_digest"],
                })
                if attempt == MAX_RETRIES - 1:
                    _checkpoint(writer, session, "invalid_actions")
                    raise CombatSessionError(
                        "three invalid actions in one expedition turn; checkpoint emitted"
                    ) from exc
            else:
                session = updated
                _write(writer, {
                    "event": "accepted",
                    "state_digest": session["state_digest"],
                    "receipt": session["journal"][-1]["receipt"],
                })
                if session["state"]["tick"] % checkpoint_every == 0:
                    _checkpoint(writer, session, "periodic")
                break
    verified = verify_expedition(session)
    _write(writer, {"event": "terminal", "session": verified})
    return verified
