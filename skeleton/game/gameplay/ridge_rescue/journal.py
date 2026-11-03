"""CAS-protected replay journal with deterministic chain custody and historical forks."""
from __future__ import annotations
from copy import deepcopy
from typing import Any
from .schema import World, parse_world, world_dict
from .engine import apply, initial_state, RescueError
from .custody import canonical, digest, export_run, verify_run

MAX_JOURNAL_BYTES = 256_000
class JournalError(ValueError):
    pass

def _genesis(source_sha256: str) -> str:
    return digest({"schema": "ridge.rescue.genesis.v1", "source_sha256": source_sha256, "sequence": 0})

def _entry_hash(previous: str, sequence: int, action: dict) -> str:
    return digest({"schema": "ridge.rescue.entry.v1", "previous": previous, "sequence": sequence, "action": action})

def open_journal(world: World) -> dict:
    source = world_dict(world)
    source_hash = digest(source)
    return {
        "schema": "ridge.rescue.journal.v1",
        "world": source,
        "source_sha256": source_hash,
        "entries": [],
        "head": _genesis(source_hash),
        "state": initial_state(world),
    }

def verify_journal(journal: dict | bytes | str) -> dict:
    if isinstance(journal, bytes):
        if len(journal) > MAX_JOURNAL_BYTES:
            raise JournalError("journal exceeds byte budget")
        try:
            journal = journal.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise JournalError("journal not UTF-8") from exc
    if isinstance(journal, str):
        if len(journal.encode("utf-8")) > MAX_JOURNAL_BYTES:
            raise JournalError("journal exceeds byte budget")
        import json
        try:
            journal = json.loads(journal)
        except ValueError as exc:
            raise JournalError("invalid journal JSON") from exc
    if not isinstance(journal, dict) or set(journal) != {"schema", "world", "source_sha256", "entries", "head", "state"}:
        raise JournalError("invalid journal envelope")
    if journal["schema"] != "ridge.rescue.journal.v1":
        raise JournalError("unsupported journal schema")
    if len(canonical(journal)) > MAX_JOURNAL_BYTES:
        raise JournalError("journal exceeds byte budget")
    try:
        world = parse_world(journal["world"])
    except (ValueError, TypeError) as exc:
        raise JournalError("invalid journal world") from exc
    if digest(world_dict(world)) != journal["source_sha256"]:
        raise JournalError("source digest mismatch")
    entries = journal["entries"]
    if not isinstance(entries, list) or len(entries) > world.max_turns:
        raise JournalError("invalid journal length")
    head = _genesis(journal["source_sha256"])
    state = initial_state(world)
    actions: list[dict] = []
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict) or set(entry) != {"sequence", "previous", "action", "sha256"}:
            raise JournalError("malformed entry")
        if type(entry["sequence"]) is not int or entry["sequence"] != index or entry["previous"] != head:
            raise JournalError("journal sequence or parent mismatch")
        if not isinstance(entry["action"], dict):
            raise JournalError("invalid action")
        expected = _entry_hash(head, index, entry["action"])
        if entry["sha256"] != expected:
            raise JournalError("journal entry digest mismatch")
        try:
            state = apply(world, state, entry["action"])
        except (RescueError, ValueError, KeyError, TypeError) as exc:
            raise JournalError(f"unreplayable action at {index}") from exc
        head = expected
        actions.append(entry["action"])
    if head != journal["head"] or canonical(state) != canonical(journal["state"]):
        raise JournalError("journal head or final state mismatch")
    return {"world": world, "state": state, "head": head, "actions": deepcopy(actions)}

def append_journal(journal: dict, action: dict, *, expected_head: str) -> dict:
    verified = verify_journal(journal)
    if not isinstance(expected_head, str) or verified["head"] != expected_head:
        raise JournalError("stale journal revision")
    if not isinstance(action, dict):
        raise JournalError("invalid action")
    world = verified["world"]
    if len(journal["entries"]) >= world.max_turns:
        raise JournalError("journal turn budget exhausted")
    try:
        next_state = apply(world, verified["state"], action)
    except (RescueError, ValueError, KeyError, TypeError) as exc:
        raise JournalError("invalid gameplay transition") from exc
    result = deepcopy(journal)
    sequence = len(result["entries"]) + 1
    new_head = _entry_hash(expected_head, sequence, action)
    result["entries"].append({"sequence": sequence, "previous": expected_head, "action": deepcopy(action), "sha256": new_head})
    result["head"] = new_head
    result["state"] = next_state
    if len(canonical(result)) > MAX_JOURNAL_BYTES:
        raise JournalError("journal byte budget exhausted")
    return result

def fork_journal(journal: dict, *, expected_head: str, sequence: int) -> dict:
    verified = verify_journal(journal)
    if verified["head"] != expected_head:
        raise JournalError("stale journal revision")
    if type(sequence) is not int or not 0 <= sequence <= len(journal["entries"]):
        raise JournalError("invalid fork sequence")
    result = open_journal(verified["world"])
    for entry in journal["entries"][:sequence]:
        result = append_journal(result, entry["action"], expected_head=result["head"])
    return result

def export_journal(journal: dict) -> dict:
    verified = verify_journal(journal)
    bundle = export_run(verified["world"], verified["actions"])
    if canonical(bundle["payload"]["state"]) != canonical(verified["state"]):
        raise JournalError("journal and export diverged")
    return bundle

def import_run(bundle: dict | bytes | str) -> dict:
    verified = verify_run(bundle)
    result = open_journal(verified["world"])
    for action in verified["actions"]:
        result = append_journal(result, action, expected_head=result["head"])
    if canonical(result["state"]) != canonical(verified["state"]):
        raise JournalError("import diverged")
    return result
