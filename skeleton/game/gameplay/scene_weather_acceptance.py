"""Playable weather delivery acceptance: source -> CLI -> replay -> export.

No external filesystem, shell or network side effects. Checksums are integrity
receipts, not signatures; untrusted sources remain untrusted after verification.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_tile_walk import _bounded, _json
from skeleton.game.gameplay.scene_travel import SceneTravelError
from skeleton.game.gameplay.scene_weather import (
    export_weather, import_weather, new_weather, original_weather,
    resume_weather, simulate_weather, verify_weather,
)
from skeleton.game.gameplay.scene_weather_author import preview_weather
from skeleton.game.gameplay.scene_weather_interactive import play_weather

SCHEMA = "skeleton.scene_weather_acceptance.v1"
MAX_ACCEPT_ACTIONS = 32
MAX_ACCEPT_SOURCE_BYTES = 64 * 1024
MAX_TRANSCRIPT_BYTES = 512 * 1024


class _CappedTranscript:
    """Bounded write-only stream compatible with the interactive CLI."""
    def __init__(self) -> None:
        self._parts: list[str] = []
        self._bytes = 0

    def write(self, data: str) -> int:
        if type(data) is not str:
            raise SceneTravelError("non-text weather transcript")
        size = len(data.encode("utf-8"))
        if self._bytes + size > MAX_TRANSCRIPT_BYTES:
            raise SceneTravelError("weather transcript size budget exceeded")
        self._parts.append(data)
        self._bytes += size
        return len(data)

    def flush(self) -> None:
        pass

    def events(self) -> list[dict[str, Any]]:
        result = []
        for line in "".join(self._parts).splitlines():
            obj = _json(line)
            if type(obj) is not dict or type(obj.get("event")) is not str:
                raise SceneTravelError("malformed weather interactive event")
            result.append(obj)
        return result


def accept_weather(source: Any, actions: Any) -> dict[str, Any]:
    """Require one actual winning journey through every production surface."""
    _bounded(source, MAX_ACCEPT_SOURCE_BYTES)
    if type(actions) is not list or not 1 <= len(actions) <= MAX_ACCEPT_ACTIONS:
        raise SceneTravelError("invalid weather acceptance action budget")
    _bounded(actions, 32 * 1024)
    initial = new_weather(source)
    final = simulate_weather(source, actions)
    if final["state"]["phase"] != "won":
        raise SceneTravelError("weather acceptance requires a playable victory")
    if verify_weather(final) != final:
        raise SceneTravelError("weather acceptance replay mismatch")
    mid = len(actions) // 2
    restored = resume_weather(simulate_weather(source, actions[:mid]),
                              actions[mid:])
    if restored != final:
        raise SceneTravelError("weather acceptance restart mismatch")
    bundle = export_weather(final)
    if import_weather(bundle) != final:
        raise SceneTravelError("weather acceptance portable mismatch")
    preview = preview_weather(source, actions)
    if preview["state_digest"] != final["state_digest"]:
        raise SceneTravelError("weather editor preview diverged from runtime")
    lines = []
    for action in actions:
        line = json.dumps(action, sort_keys=True, separators=(",", ":"))
        if len(line.encode("utf-8")) > 8192:
            raise SceneTravelError("weather action exceeds interactive line budget")
        lines.append(line)
    stream = _CappedTranscript()
    played = play_weather(source=source, expected_source_digest=initial["source_digest"],
                          checkpoint_every=8,
                          input_stream=io.StringIO("\n".join(lines) + "\n"),
                          output_stream=stream)
    events = stream.events()
    accepted = [event for event in events if event["event"] == "accepted"]
    checkpoints = [event for event in events if event["event"] == "checkpoint"]
    if (played != final or len(accepted) != len(actions)
            or any(event["tick"] != i + 1 for i, event in enumerate(accepted))
            or not checkpoints or checkpoints[-1]["reason"] != "terminal"
            or verify_weather(checkpoints[-1]["session"]) != final):
        raise SceneTravelError("weather interactive delivery diverged from replay")
    result = {
        "schema_version": SCHEMA,
        "status": "playable_verified",
        "source_digest": final["source_digest"],
        "initial_state_digest": initial["state_digest"],
        "final_state_digest": final["state_digest"],
        "action_count": len(actions),
        "actions": actions,
        "journal_digest": dig(final["journal"]),
        "checkpoint_count": len(checkpoints),
        "interactive_event_digest": dig(events),
        "portable_checksum": bundle["checksum"],
        "proof_kind": "canonical_playable_acceptance_not_signature",
    }
    result["checksum"] = dig(result)
    _bounded(result)
    return result


def verify_weather_acceptance(receipt: Any, source: Any) -> dict[str, Any]:
    """Re-run full gameplay acceptance; reject forged or stale source receipts."""
    _bounded(receipt)
    if type(receipt) is not dict or set(receipt) != {
        "schema_version", "status", "source_digest", "initial_state_digest",
        "final_state_digest", "action_count", "actions", "journal_digest",
        "checkpoint_count", "interactive_event_digest", "portable_checksum",
        "proof_kind", "checksum",
    } or receipt["schema_version"] != SCHEMA or receipt["status"] != "playable_verified":
        raise SceneTravelError("invalid weather acceptance receipt")
    if receipt["checksum"] != dig({k: v for k, v in receipt.items()
                                  if k != "checksum"}):
        raise SceneTravelError("weather acceptance checksum mismatch")
    rebuilt = accept_weather(source, receipt["actions"])
    if rebuilt != receipt:
        raise SceneTravelError("weather acceptance source or replay mismatch")
    return rebuilt


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-weather-accept")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    p = sub.add_parser("accept")
    p.add_argument("--source-json", required=True)
    p.add_argument("--actions-json", required=True)
    p = sub.add_parser("verify")
    p.add_argument("--source-json", required=True)
    p.add_argument("--receipt-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, actions = original_weather()
            result = accept_weather(source, actions)
        elif args.command == "accept":
            result = accept_weather(_json(args.source_json), _json(args.actions_json))
        else:
            result = verify_weather_acceptance(_json(args.receipt_json),
                                               _json(args.source_json))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
