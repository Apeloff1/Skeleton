"""Strict offline keyboard remapping for canonical game play sessions.

Profiles affect terminal input only; saves retain semantic controls and
source-bound replay is independent of the operator's keyboard layout.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .game_play_session import GamePlaySessionError

SCHEMA = "skeleton.game.terminal_input_profile.v1"
_ACTIONS = frozenset(("left", "right", "jump", "wait", "quit"))
_MOVEMENT = frozenset(("left", "right", "jump"))
_DEFAULT = {"left": "a", "right": "d", "jump": "w", "wait": ".", "quit": "q"}


def validate_terminal_input_profile(profile: Any = None) -> dict[str, str]:
    """Reject conflicting bindings, unsupported versions and unsafe keys."""
    if profile is None:
        return dict(_DEFAULT)
    if type(profile) is not dict or set(profile) != {"schema_version", "bindings"}:
        raise GamePlaySessionError("terminal input profile schema mismatch")
    if profile["schema_version"] != SCHEMA:
        raise GamePlaySessionError("unsupported terminal input profile version")
    bindings = profile["bindings"]
    if type(bindings) is not dict or set(bindings) != _ACTIONS:
        raise GamePlaySessionError("terminal input profile requires five actions")
    for action, key in bindings.items():
        if type(key) is not str or len(key) != 1 or key not in "abcdefghijklmnopqrstuvwxyz0123456789.":
            raise GamePlaySessionError("terminal bindings require lowercase ASCII single keys")
        if action in _MOVEMENT and key == ".":
            raise GamePlaySessionError("movement cannot bind the reserved idle key")
    if bindings["wait"] != "." or bindings["quit"] == ".":
        raise GamePlaySessionError("terminal idle must remain '.' and quit must be explicit")
    if len(set(bindings.values())) != len(_ACTIONS):
        raise GamePlaySessionError("terminal input profile contains conflicting keys")
    return {action: bindings[action] for action in sorted(_ACTIONS)}


def terminal_profile_receipt(profile: Any = None) -> dict[str, Any]:
    """Stable layout identity, not a signature or authorization token."""
    bindings = validate_terminal_input_profile(profile)
    canonical = json.dumps(
        {"schema_version": SCHEMA, "bindings": bindings},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("ascii")
    return {
        "schema_version": "skeleton.game.terminal_input_profile.receipt.v1",
        "profile_sha256": hashlib.sha256(canonical).hexdigest(),
        "bindings": bindings,
        "offline_input": True,
    }


__all__ = ["SCHEMA", "validate_terminal_input_profile", "terminal_profile_receipt"]
