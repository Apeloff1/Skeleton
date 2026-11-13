"""Replay-bound keyboard/controller/touch input to real offline game actions.

The presentation router is authoritative for chords; the canonical grid game
is authoritative for movement, collisions, pickups, quests and saves.
Ambiguous interactions are rejected rather than silently choosing an NPC or
ending. Neither subsystem can grant state through an unverified receipt.
"""
from __future__ import annotations

from typing import Any, Sequence

from skeleton.game.gameplay.flgb_gameplay_runtime import (
    GameplayContractError, dig,
)
from skeleton.game.gameplay.offline_grid_campaign import (
    Campaign, Command, Session,
)
from skeleton.game.presentation.flgb_presentation_runtime import (
    PresentationContractError,
)
from skeleton.game.presentation.input_router import (
    InputEvent, InputProfile, InputSession, MAX_EVENTS,
)

SCHEMA = "skeleton.input_gameplay_bridge.v1"


def _interaction(session: Session) -> tuple[str, str]:
    candidates = []
    for obj in session.campaign.spec["objects"]:
        if (obj["x"], obj["y"]) != (session.x, session.y):
            continue
        if obj["kind"] == "item" and obj["id"] not in session.inventory:
            candidates.append(("collect", obj["id"]))
        elif obj["kind"] == "npc" and obj["id"] not in session.spoken:
            candidates.append(("talk", obj["id"]))
    if len(candidates) != 1:
        raise GameplayContractError("input interaction absent or ambiguous")
    return candidates[0]


def _finish(session: Session, selected_ending: str | None) -> tuple[str, str]:
    source = session.campaign.spec
    if source["rows"][session.y][session.x] != "G":
        raise GameplayContractError("input confirm requires goal tile")
    available = [
        ending["id"] for ending in source["endings"]
        if set(ending["requires_quests"]) <= set(session.quests)
    ]
    if selected_ending is None:
        if len(available) != 1:
            raise GameplayContractError("input ending absent or ambiguous")
        return "finish", available[0]
    if type(selected_ending) is not str or selected_ending not in available:
        raise GameplayContractError("selected ending unavailable")
    return "finish", selected_ending


def _game_action(
    session: Session, command: dict[str, str],
    selected_ending: str | None,
) -> tuple[str, str] | None:
    kind = command["kind"]
    if kind == "move":
        return kind, command["target"]
    if kind == "interact":
        return _interaction(session)
    if kind == "confirm":
        return _finish(session, selected_ending)
    if kind in ("inventory", "cancel"):
        # Read-only UI controls cannot mutate the canonical game save.
        return None
    raise GameplayContractError("unsupported routed gameplay command")


def play_inputs(
    campaign: Campaign, profile: InputProfile, raw_events: Sequence[Any],
    *, selected_ending: str | None = None,
) -> dict[str, Any]:
    """Route and apply an atomic, ordered input batch through both engines."""
    if not isinstance(campaign, Campaign) or not isinstance(profile, InputProfile):
        raise GameplayContractError("invalid input gameplay source")
    if type(raw_events) not in (list, tuple) or len(raw_events) > MAX_EVENTS:
        raise GameplayContractError("invalid gameplay input batch")
    if selected_ending is not None and (
        type(selected_ending) is not str
        or selected_ending not in {e["id"] for e in campaign.spec["endings"]}
    ):
        raise GameplayContractError("unknown selected game ending")
    inputs = InputSession(profile)
    game = Session.new(campaign)
    transitions = []
    for raw in raw_events:
        event = raw if isinstance(raw, InputEvent) else InputEvent.load(raw)
        inputs = inputs.step(event)
        receipt = inputs.events[-1]
        before = game.state_digest
        command = receipt["command"]
        game_action = (
            _game_action(game, command, selected_ending)
            if command is not None else None
        )
        executed = None
        if game_action is not None:
            kind, target = game_action
            executed = {
                "command_id": f"input-{event.sequence}",
                "kind": kind, "target": target,
            }
            game = game.step(Command(**executed))
        transition = {
            "input_sequence": event.sequence,
            "input_receipt_digest": receipt["digest"],
            "routed_command": command,
            "game_command": executed,
            "before_digest": before,
            "after_digest": game.state_digest,
        }
        transition["receipt"] = dig(transition)
        transitions.append(transition)
    # Every returned game save must be canonical and replayable.
    restored = Session.restore(campaign, game.snapshot())
    if restored.state_digest != game.state_digest:
        raise GameplayContractError("input gameplay save replay mismatch")
    if InputSession.restore(profile, inputs.snapshot()).snapshot() != inputs.snapshot():
        raise GameplayContractError("input profile replay mismatch")
    report = {
        "schema_version": SCHEMA,
        "game_source_digest": campaign.source_digest,
        "profile_digest": profile.digest,
        "selected_ending": selected_ending,
        "input_snapshot": inputs.snapshot(),
        "game_snapshot": game.snapshot(),
        "game_state_digest": game.state_digest,
        "game_ending": game.ending,
        "transitions": transitions,
    }
    report["checksum"] = dig(report)
    return report


def verify_input_gameplay(
    campaign: Campaign, profile: InputProfile, payload: Any,
) -> dict[str, Any]:
    """Reconstruct every input and game event; reject forged cross-plane state."""
    keys = {
        "schema_version", "game_source_digest", "profile_digest",
        "selected_ending", "input_snapshot", "game_snapshot",
        "game_state_digest", "game_ending", "transitions", "checksum",
    }
    if type(payload) is not dict or set(payload) != keys:
        raise GameplayContractError("invalid input gameplay report fields")
    if payload["schema_version"] != SCHEMA:
        raise GameplayContractError("unsupported input gameplay schema")
    if (payload["game_source_digest"] != campaign.source_digest
            or payload["profile_digest"] != profile.digest):
        raise GameplayContractError("input gameplay source mismatch")
    snapshot = payload["input_snapshot"]
    InputSession.restore(profile, snapshot)
    events = [receipt["event"] for receipt in snapshot["events"]]
    expected = play_inputs(
        campaign, profile, events,
        selected_ending=payload["selected_ending"],
    )
    if expected != payload:
        raise GameplayContractError("input gameplay replay or checksum mismatch")
    return expected
