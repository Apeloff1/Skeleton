"""Offline entrypoint for the recovered B028/B030/B037 creator runtime.

The input request is the authority; a receipt cannot grant itself world,
mechanics, reward-policy, native-execution or publishing authority.
No files, providers, network, subprocesses or engine calls are made.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from typing import Any, BinaryIO, Sequence, TextIO

from skeleton.ai.game_builder.constraint_quest_synthesis import ContentPolicy, WorldModel
from skeleton.ai.game_builder.genre_template_composition import PackRegistry
from skeleton.ai.game_builder.original_quest_slice import (
    compose_verified_quest_slice, verify_original_slice,
)

REQUEST_SCHEMA = "skeleton.original_quest.request.v1"
RECEIPT_SCHEMA = "skeleton.original_quest.receipt.v1"
MAX_BYTES = 2 * 1024 * 1024
MAX_NODES = 100_000
MAX_DEPTH = 32


class QuestRequestError(ValueError):
    """Rejected before exposing the recovered runtime as an accepted result."""


def _require(condition: bool, detail: str) -> None:
    if not condition:
        raise QuestRequestError(detail)


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        _require(key not in result, "duplicate JSON property")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise QuestRequestError("nonfinite JSON number")


def _text(value: Any, cap: int = 128) -> str:
    _require(type(value) is str and 0 < len(value) <= cap
             and not any(ord(c) < 32 or 127 <= ord(c) <= 159
                         or 0xD800 <= ord(c) <= 0xDFFF for c in value),
             "invalid bounded text")
    return value


def _integer(value: Any, minimum: int, maximum: int) -> int:
    _require(type(value) is int and minimum <= value <= maximum,
             "integer outside permitted range")
    return value


def _object(value: Any, required: set[str], optional: set[str] | None = None) -> dict:
    _require(type(value) is dict and required <= value.keys()
             and value.keys() <= required | (optional or set()),
             "unexpected or missing object fields")
    return value


def _strings(value: Any, cap: int, width: int = 128, *, nonempty: bool = False) -> tuple[str, ...]:
    _require(type(value) is list and int(nonempty) <= len(value) <= cap,
             "invalid bounded string list")
    result = tuple(_text(item, width) for item in value)
    _require(len(set(result)) == len(result), "duplicate list identity")
    return result


def _bounded(value: Any) -> None:
    """Bound directly supplied Python values as well as parsed JSON."""
    stack = [(value, 0)]
    count = 0
    while stack:
        item, depth = stack.pop()
        count += 1
        _require(count <= MAX_NODES and depth <= MAX_DEPTH, "JSON structure too large")
        if type(item) is dict:
            _require(len(item) <= 10_000, "object too large")
            for key, child in item.items():
                _text(key, 512)
                stack.append((child, depth + 1))
        elif type(item) is list:
            _require(len(item) <= 10_000, "array too large")
            stack.extend((child, depth + 1) for child in item)
        elif type(item) is str:
            _require(len(item) <= 16_384 and not any(0xD800 <= ord(c) <= 0xDFFF for c in item),
                     "invalid JSON string")
        elif type(item) is int:
            _integer(item, -(2**63), 2**63 - 1)
        elif type(item) is float:
            _require(math.isfinite(item), "nonfinite JSON number")
        else:
            _require(item is None or type(item) is bool, "unsupported JSON value")


def _encode(value: Any) -> bytes:
    _bounded(value)
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    _require(len(payload) <= MAX_BYTES, "encoded value too large")
    return payload


def read_document(stream: BinaryIO) -> Any:
    raw = stream.read(MAX_BYTES + 1)
    _require(len(raw) <= MAX_BYTES, "input exceeds byte ceiling")
    try:
        value = json.loads(raw.decode("utf-8", "strict"),
                           object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise QuestRequestError("invalid or oversized JSON document") from exc
    _bounded(value)
    return value


def _models(source: Any) -> tuple[PackRegistry, tuple[str, ...], WorldModel, ContentPolicy, dict]:
    _encode(source)
    data = _object(source, {"schema", "slice_id", "packs", "pack_ids", "world", "policy", "seed"},
                   {"quest_length", "quest_title", "overrides"})
    _require(data["schema"] == REQUEST_SCHEMA, "unsupported quest request schema")
    slice_id = _text(data["slice_id"])
    pack_ids = _strings(data["pack_ids"], 64, nonempty=True)
    raw_packs = data["packs"]
    _require(type(raw_packs) is list and 1 <= len(raw_packs) <= 128, "invalid pack registry size")
    packs = []
    seen = set()
    for raw in raw_packs:
        pack = _object(raw, {"id", "provides"}, {"requires", "conflicts", "params"})
        pid = _text(pack["id"])
        _require(pid not in seen, "duplicate pack registration")
        seen.add(pid)
        for key in ("provides", "requires", "conflicts"):
            _strings(pack.get(key, []), 64, nonempty=key == "provides")
        _require(type(pack.get("params", {})) is dict and len(pack.get("params", {})) <= 64,
                 "invalid mechanic parameters")
        packs.append(pack)
    _require(set(pack_ids) <= seen, "selected mechanic not in supplied registry")
    registry = PackRegistry(packs)

    raw_world = _object(data["world"], {"start", "edges"}, {"npcs"})
    start = _text(raw_world["start"])
    raw_edges = raw_world["edges"]
    _require(type(raw_edges) is dict and 1 <= len(raw_edges) <= 4096, "invalid location graph")
    edges = {_text(key): _strings(neighbors, 256) for key, neighbors in raw_edges.items()}
    _require(start in edges and sum(map(len, edges.values())) <= 32768
             and all(n in edges for neighbors in edges.values() for n in neighbors),
             "unknown start, dangling edge or graph edge budget exceeded")
    raw_npcs = raw_world.get("npcs", {})
    _require(type(raw_npcs) is dict and len(raw_npcs) <= 4096, "invalid NPC table")
    npcs = {_text(key): _text(loc) for key, loc in raw_npcs.items()}
    _require(all(loc in edges for loc in npcs.values()), "NPC refers to unknown location")
    world = WorldModel(start=start, edges=edges, npcs=npcs)

    raw_policy = _object(data["policy"], {"max_reward_per_step", "max_total_reward", "allowed_reward_kinds"},
                         {"banned_terms"})
    policy = ContentPolicy(
        banned_terms=_strings(raw_policy.get("banned_terms", []), 128, 256),
        max_reward_per_step=_integer(raw_policy["max_reward_per_step"], 1, 100_000),
        max_total_reward=_integer(raw_policy["max_total_reward"], 0, 10_000_000),
        allowed_reward_kinds=_strings(raw_policy["allowed_reward_kinds"], 32, nonempty=True),
    )
    overrides = data.get("overrides", {})
    _require(type(overrides) is dict and len(overrides) <= 64
             and set(overrides) <= set(pack_ids)
             and all(type(v) is dict and len(v) <= 64 for v in overrides.values()),
             "invalid mechanic overrides")
    kwargs = dict(slice_id=slice_id, seed=_integer(data["seed"], -(2**63), 2**63-1),
                  quest_length=_integer(data.get("quest_length", 3), 1, 128),
                  quest_title=_text(data.get("quest_title", "An Original Adventure"), 256),
                  overrides=overrides)
    return registry, pack_ids, world, policy, kwargs


def build_receipt(request: Any) -> dict[str, Any]:
    source_digest = hashlib.sha256(_encode(request)).hexdigest()
    registry, selected, world, policy, kwargs = _models(request)
    artifact = compose_verified_quest_slice(registry, selected, world=world, policy=policy, **kwargs)
    _require(verify_original_slice(artifact, registry), "canonical objective replay refused")
    result = {"schema": RECEIPT_SCHEMA, "source_digest": source_digest,
              "artifact": artifact, "abstract_replay_verified": True,
              "native_qualified": False, "release_qualified": False}
    # A successfully built receipt must fit through the same verify envelope.
    _encode({"request": request, "receipt": result})
    return result


def verify_receipt(request: Any, receipt: Any) -> bool:
    """Regenerate using the independent request, not claims embedded in receipt."""
    try:
        submitted = _encode(receipt)
        expected = _encode(build_receipt(request))
        return submitted == expected
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False


def main(argv: Sequence[str] | None = None, *, stdin: BinaryIO | None = None,
         stdout: TextIO | None = None, stderr: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or verify an offline abstract quest receipt.")
    parser.add_argument("command", choices=("build", "verify"))
    args = parser.parse_args(argv)
    incoming = stdin if stdin is not None else sys.stdin.buffer
    outgoing = stdout if stdout is not None else sys.stdout
    errors = stderr if stderr is not None else sys.stderr
    try:
        value = read_document(incoming)
        if args.command == "build":
            result = build_receipt(value)
        else:
            bundle = _object(value, {"request", "receipt"})
            _require(verify_receipt(bundle["request"], bundle["receipt"]),
                     "receipt does not match independent request replay")
            result = {"verified": True, "abstract_replay_verified": True,
                      "native_qualified": False, "release_qualified": False}
        outgoing.write(_encode(result).decode("ascii") + "\n")
        return 0
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, OSError) as exc:
        # Do not echo submitted content, keys, paths or policy material.
        errors.write("quest request rejected: " + type(exc).__name__ + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
