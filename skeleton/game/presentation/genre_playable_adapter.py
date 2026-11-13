"""Source-preserving B024 genre controls → canonical offline playable input router.

Only *compatible* digital chords are admitted into a real grid campaign:
four-way keyboard/gamepad D-pad movement, explicit interaction and cancel.
Raw analog sticks, mouse deltas, touch swipes, weapon fire and racing steering
cannot honestly be routed through a boolean-event grid API. Those controls
stay available in B024's richer ActionMap for dedicated engine adapters.

The resulting profile is a canonical, revisioned InputProfile. All gameplay
commands, collision, quest, inventory, ending, save and replay checks remain
owned by the *existing* input_gameplay_bridge. No side-channel can mint wins.
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from skeleton.game.gameplay.flgb_gameplay_runtime import dig, GameplayContractError
from skeleton.game.gameplay.offline_grid_campaign import Campaign
from skeleton.game.presentation.input_actions import Binding, InputContractError
from skeleton.game.presentation.genre_action_profiles import genre_action_map
from skeleton.game.presentation.input_router import InputProfile
from skeleton.game.presentation.input_gameplay_bridge import play_inputs, verify_input_gameplay
from skeleton.game.presentation.flgb_presentation_runtime import PresentationContractError

SCHEMA = "skeleton.game.genre_playable_input_bridge.v1"
MAX_BINDINGS = 128


def _compatible(binding: Binding) -> str | None:
    device = binding.control.device
    path = binding.control.path
    action = binding.action_id
    if action == "move":
        # Legacy action-map axes are richer than the current boolean
        # presentation router. Use only unambiguous digital controls.
        if not (
            (device == "keyboard" and path.startswith("key."))
            or (device == "gamepad" and path.startswith("button.dpad_"))
        ):
            return None
        if binding.axis == "y":
            return "move-north" if binding.scale > 0 else "move-south"
        return "move-east" if binding.scale > 0 else "move-west"
    if action in {"interact", "inspect"}:
        if device in {"keyboard", "gamepad", "touch"} and (
            (device == "keyboard" and path.startswith("key."))
            or (device == "gamepad" and path.startswith("button."))
            or (device == "touch" and path in {"tap", "long_press", "double_tap"})
        ):
            return "interact"
    if action == "pause" and (
        (device == "keyboard" and path.startswith("key."))
        or (device == "gamepad" and path.startswith("button."))
    ):
        return "cancel"
    return None


def playable_input_profile(
    genre: str,
    overrides: Mapping[str, Any] | None = None,
) -> InputProfile:
    """Generate a fresh canonical profile from current versioned B024 controls.

    Changes to the caller's B024 remap are represented in the canonical
    profile digest; an old event sequence cannot be verified after a remap.
    """
    scheme = genre_action_map(genre)
    if overrides is not None:
        scheme.import_overrides(overrides)
    rows: list[dict[str, Any]] = []
    for n, binding in enumerate(scheme.bindings()):
        translated = _compatible(binding)
        if translated is None:
            continue
        path = binding.control.path
        device = "controller" if binding.control.device == "gamepad" else binding.control.device
        rows.append({
            "binding_id": "genre_" + str(n),
            "action_id": translated,
            "device_class": device,
            "control_path": path,
            "modifiers": list(binding.modifiers),
        })
        if len(rows) > MAX_BINDINGS:
            raise InputContractError("playable input binding count exceeds budget")
    if not any(row["action_id"] in {"move-north", "move-south", "move-east", "move-west"} for row in rows):
        raise InputContractError("genre has no compatible discrete playable movement")
    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", genre)
    return InputProfile.load({
        "version": 1,
        "profile_id": "galaxy-" + slug,
        "revision": 0,
        "bindings": rows,
    })


def play_genre_campaign(
    campaign: Campaign,
    genre: str,
    raw_events: Sequence[Any],
    *,
    overrides: Mapping[str, Any] | None = None,
    selected_ending: str | None = None,
) -> dict[str, Any]:
    """Actually route compatible B024 controls through current real gameplay."""
    profile = playable_input_profile(genre, overrides)
    report = play_inputs(campaign, profile, raw_events, selected_ending=selected_ending)
    body = {
        "schema": SCHEMA,
        "genre": genre,
        "overrides": scheme_overrides(genre, overrides),
        "profile": profile.manifest(),
        "gameplay": report,
    }
    return {**body, "digest": dig(body)}


def scheme_overrides(genre: str, overrides: Mapping[str, Any] | None) -> dict[str, Any]:
    """Export the exact validated, replayable B024 remap, never raw input."""
    scheme = genre_action_map(genre)
    if overrides is not None:
        scheme.import_overrides(overrides)
    return scheme.export_overrides()


def verify_genre_campaign(campaign: Campaign, value: Any) -> dict[str, Any]:
    """Replay, reject tampering and confirm exact B024->canonical source."""
    expected = {"schema", "genre", "overrides", "profile", "gameplay", "digest"}
    if type(value) is not dict or set(value) != expected or value.get("schema") != SCHEMA:
        raise GameplayContractError("unsupported genre-playable input report")
    if type(value["genre"]) is not str or type(value["overrides"]) is not dict:
        raise GameplayContractError("invalid genre-playable report source")
    body = {k: val for k, val in value.items() if k != "digest"}
    try:
        if value["digest"] != dig(body):
            raise GameplayContractError("genre-playable source checksum mismatch")
        canonical = scheme_overrides(value["genre"], value["overrides"])
        if value["overrides"] != canonical:
            raise GameplayContractError("genre-playable remap is not canonical")
    except (InputContractError, TypeError, ValueError, OverflowError) as exc:
        raise GameplayContractError("invalid genre-playable source") from exc
    try:
        profile = playable_input_profile(value["genre"], value["overrides"])
    except (InputContractError, PresentationContractError) as exc:
        raise GameplayContractError("genre-playable profile cannot be verified") from exc
    if profile.manifest() != value["profile"]:
        raise GameplayContractError("genre-playable input manifest changed")
    verified = verify_input_gameplay(campaign, profile, value["gameplay"])
    if verified != value["gameplay"]:
        raise GameplayContractError("genre-playable replay diverged")
    return value


__all__ = [
    "SCHEMA", "MAX_BINDINGS", "playable_input_profile", "play_genre_campaign",
    "verify_genre_campaign",
]
