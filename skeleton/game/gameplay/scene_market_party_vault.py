"""Optimistic, source-bound offline cooperative save slots.

The vault never invents gameplay state: each slot stores a checkpoint verified by
the canonical party reducer. Its journal is replayed on every read, so a
forged revision, stale slot, or edited checkpoint cannot silently overwrite
an earned market result. This is offline integrity, not user authentication.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import _json
from skeleton.game.gameplay.scene_market_party import (
    export_party, import_party, normalize_party, original_party,
    resume_party, simulate_party, verify_party,
)
from skeleton.game.gameplay.scene_tile_walk import _bounded
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _object

SCHEMA = "skeleton.scene_market_party_vault.v1"
BUNDLE = "skeleton.scene_market_party_vault_bundle.v1"
MAX_SLOTS = 8
MAX_EVENTS = 24
MAX_VAULT_BYTES = 2 * 1024 * 1024


def _limit(payload: Any) -> None:
    _bounded(payload, MAX_VAULT_BYTES)


def _digest(revision: int, slots: dict[str, Any]) -> str:
    return dig({"revision": revision, "slots": slots})


def new_vault(source: Any) -> dict[str, Any]:
    spec = normalize_party(source)
    result = {"schema_version": SCHEMA, "source": spec,
              "source_digest": dig(spec), "revision": 0,
              "slots": {}, "journal": [], "state_digest": _digest(0, {})}
    _limit(result)
    return result


def _action(raw: Any) -> dict[str, Any]:
    _limit(raw)
    if type(raw) is not dict:
        raise SceneTravelError("invalid cooperative vault action")
    kind = raw.get("kind")
    fields = ({"kind", "slot", "expected_revision", "expected_slot_digest",
               "checkpoint"} if kind == "put" else
              {"kind", "slot", "expected_revision", "expected_slot_digest"})
    if kind not in ("put", "delete"):
        raise SceneTravelError("unsupported cooperative vault operation")
    obj = _object(raw, fields, "cooperative vault operation")
    slot = _id(obj["slot"], "vault slot")
    if len(slot) > 40:
        raise SceneTravelError("cooperative vault slot too long")
    revision = obj["expected_revision"]
    if type(revision) is not int or not 0 <= revision < MAX_EVENTS:
        raise SceneTravelError("invalid cooperative vault revision")
    expected = obj["expected_slot_digest"]
    if expected is not None and (type(expected) is not str
                                 or len(expected) != 64
                                 or any(c not in "0123456789abcdef" for c in expected)):
        raise SceneTravelError("invalid cooperative vault slot lease")
    cleaned = {"kind": kind, "slot": slot, "expected_revision": revision,
               "expected_slot_digest": expected}
    if kind == "put":
        cleaned["checkpoint"] = copy.deepcopy(obj["checkpoint"])
    return cleaned


def _apply(vault: dict[str, Any], raw: Any) -> dict[str, Any]:
    action = _action(raw)
    if vault["revision"] >= MAX_EVENTS:
        raise SceneTravelError("cooperative vault event budget exhausted")
    if action["expected_revision"] != vault["revision"]:
        raise SceneTravelError("stale cooperative vault revision")
    slot = action["slot"]
    previous = vault["slots"].get(slot)
    previous_digest = previous["state_digest"] if previous is not None else None
    if action["expected_slot_digest"] != previous_digest:
        raise SceneTravelError("stale cooperative vault slot")
    slots = copy.deepcopy(vault["slots"])
    if action["kind"] == "delete":
        if previous is None:
            raise SceneTravelError("cannot delete missing cooperative vault slot")
        del slots[slot]
    else:
        checkpoint = verify_party(action["checkpoint"])
        if checkpoint["source_digest"] != vault["source_digest"]:
            raise SceneTravelError("cooperative vault source mismatch")
        if previous is None and len(slots) >= MAX_SLOTS:
            raise SceneTravelError("cooperative vault slot budget exhausted")
        if previous == checkpoint:
            raise SceneTravelError("cooperative vault unchanged checkpoint")
        slots[slot] = checkpoint
    revision = vault["revision"] + 1
    after = _digest(revision, slots)
    event = {"sequence": vault["revision"], "action": action,
             "before_state_digest": vault["state_digest"],
             "after_state_digest": after}
    event["receipt"] = dig(event)
    result = {"schema_version": SCHEMA, "source": vault["source"],
              "source_digest": vault["source_digest"],
              "revision": revision, "slots": slots,
              "journal": [*vault["journal"], event], "state_digest": after}
    _limit(result)
    return result


def verify_vault(raw: Any) -> dict[str, Any]:
    _limit(raw)
    obj = _object(raw, {"schema_version", "source", "source_digest",
                        "revision", "slots", "journal", "state_digest"},
                  "cooperative vault")
    if obj["schema_version"] != SCHEMA or type(obj["journal"]) is not list:
        raise SceneTravelError("invalid cooperative vault schema or journal")
    if len(obj["journal"]) > MAX_EVENTS:
        raise SceneTravelError("cooperative vault journal budget exceeded")
    rebuilt = new_vault(obj["source"])
    for event in obj["journal"]:
        if type(event) is not dict or "action" not in event:
            raise SceneTravelError("invalid cooperative vault event")
        rebuilt = _apply(rebuilt, event["action"])
        if rebuilt["journal"][-1] != event:
            raise SceneTravelError("cooperative vault event receipt mismatch")
    if rebuilt != obj:
        raise SceneTravelError("cooperative vault lineage mismatch")
    return rebuilt


def transact_vault(vault: Any, action: Any) -> dict[str, Any]:
    return _apply(verify_vault(vault), action)


def read_slot(vault: Any, slot: str) -> dict[str, Any]:
    verified = verify_vault(vault)
    name = _id(slot, "vault slot")
    if name not in verified["slots"]:
        raise SceneTravelError("cooperative vault slot not found")
    return copy.deepcopy(verified["slots"][name])


def export_vault(vault: Any) -> dict[str, Any]:
    verified = verify_vault(vault)
    bundle = {"schema_version": BUNDLE, "vault": verified,
              "source_digest": verified["source_digest"],
              "state_digest": verified["state_digest"]}
    bundle["checksum"] = dig(bundle)
    _limit(bundle)
    return bundle


def import_vault(raw: Any) -> dict[str, Any]:
    _limit(raw)
    bundle = _object(raw, {"schema_version", "vault", "source_digest",
                           "state_digest", "checksum"}, "cooperative vault export")
    if bundle["schema_version"] != BUNDLE:
        raise SceneTravelError("unsupported cooperative vault bundle")
    if bundle["checksum"] != dig({k: v for k, v in bundle.items()
                                  if k != "checksum"}):
        raise SceneTravelError("cooperative vault export checksum mismatch")
    verified = verify_vault(bundle["vault"])
    if (verified["source_digest"] != bundle["source_digest"]
            or verified["state_digest"] != bundle["state_digest"]):
        raise SceneTravelError("cooperative vault export lineage mismatch")
    return verified


def accept_vault() -> dict[str, Any]:
    source, turns = original_party()
    cut = len(turns) // 2
    before = simulate_party(source, turns[:cut])
    final = simulate_party(source, turns)
    vault = transact_vault(new_vault(source), {
        "kind": "put", "slot": "campaign", "expected_revision": 0,
        "expected_slot_digest": None, "checkpoint": before})
    vault = import_vault(json.loads(json.dumps(export_vault(vault))))
    resumed = resume_party(read_slot(vault, "campaign"), turns[cut:])
    if resumed != final:
        raise SceneTravelError("cooperative vault restart diverged")
    vault = transact_vault(vault, {
        "kind": "put", "slot": "campaign", "expected_revision": 1,
        "expected_slot_digest": before["state_digest"], "checkpoint": resumed})
    restored = import_vault(json.loads(json.dumps(export_vault(vault))))
    if read_slot(restored, "campaign") != final:
        raise SceneTravelError("cooperative vault final checkpoint diverged")
    if import_party(export_party(final)) != final:
        raise SceneTravelError("cooperative vault party export diverged")
    result = {"schema_version": "skeleton.scene_market_party_vault_acceptance.v1",
              "source_digest": vault["source_digest"],
              "vault_state_digest": vault["state_digest"],
              "party_state_digest": final["state_digest"],
              "revision": vault["revision"], "turns": len(turns),
              "phase": final["state"]["market"]["state"]["phase"],
              "export_checksum": export_vault(vault)["checksum"],
              "qualification": "offline_replay_not_actor_authentication"}
    result["checksum"] = dig(result)
    return result


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-party-vault")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    sub.add_parser("accept")
    sub.add_parser("create").add_argument("--source-json", required=True)
    tx = sub.add_parser("transact")
    tx.add_argument("--vault-json", required=True)
    tx.add_argument("--action-json", required=True)
    slot = sub.add_parser("slot")
    slot.add_argument("--vault-json", required=True)
    slot.add_argument("--slot", required=True)
    for command in ("verify", "export"):
        sub.add_parser(command).add_argument("--vault-json", required=True)
    sub.add_parser("import").add_argument("--bundle-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, turns = original_party()
            result = transact_vault(new_vault(source), {
                "kind": "put", "slot": "demo", "expected_revision": 0,
                "expected_slot_digest": None,
                "checkpoint": simulate_party(source, turns[:2])})
        elif args.command == "accept":
            result = accept_vault()
        elif args.command == "create":
            result = new_vault(_json(args.source_json))
        elif args.command == "transact":
            result = transact_vault(_json(args.vault_json), _json(args.action_json))
        elif args.command == "slot":
            result = read_slot(_json(args.vault_json), args.slot)
        elif args.command == "verify":
            result = verify_vault(_json(args.vault_json))
        elif args.command == "export":
            result = export_vault(_json(args.vault_json))
        else:
            result = import_vault(_json(args.bundle_json))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
