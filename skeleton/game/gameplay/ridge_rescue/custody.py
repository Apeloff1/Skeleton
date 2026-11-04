"""Source-bound portable replay bundle with canonical digests (integrity, not signatures)."""
from __future__ import annotations
import hashlib
import json
from typing import Any
from .schema import parse_world, world_dict, World
from .engine import replay, RescueError

MAX_BUNDLE = 256_000

def _strict_json(text: str) -> Any:
    def unique_members(pairs: list[tuple[str, Any]]) -> dict:
        result: dict = {}
        for key, value in pairs:
            if key in result:
                raise CustodyError("duplicate bundle JSON member")
            result[key] = value
        return result

    def reject_nonfinite(value: str) -> None:
        raise CustodyError("nonfinite bundle JSON number")

    return json.loads(text, object_pairs_hook=unique_members,
                      parse_constant=reject_nonfinite)

class CustodyError(ValueError):
    pass

def canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    except (ValueError, TypeError, OverflowError) as exc:
        raise CustodyError("noncanonical JSON value") from exc

def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()

def export_run(world: World, actions: list[dict]) -> dict:
    final = replay(world, actions)
    payload = {"schema": "ridge.rescue.run.v1", "world": world_dict(world), "actions": actions, "state": final}
    if len(canonical(payload)) > MAX_BUNDLE:
        raise CustodyError("bundle exceeds byte budget")
    return {"payload": payload, "sha256": digest(payload)}

def verify_run(bundle: dict | bytes | str) -> dict:
    if isinstance(bundle, bytes):
        if len(bundle) > MAX_BUNDLE:
            raise CustodyError("bundle exceeds byte budget")
        try:
            bundle = bundle.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CustodyError("invalid bundle encoding") from exc
    if isinstance(bundle, str):
        if len(bundle.encode("utf-8")) > MAX_BUNDLE:
            raise CustodyError("bundle exceeds byte budget")
        try:
            bundle = _strict_json(bundle)
        except ValueError as exc:
            raise CustodyError("invalid bundle JSON") from exc
    if not isinstance(bundle, dict) or set(bundle) != {"payload", "sha256"}:
        raise CustodyError("invalid envelope")
    payload = bundle["payload"]
    if not isinstance(payload, dict) or set(payload) != {"schema", "world", "actions", "state"}:
        raise CustodyError("invalid payload")
    if payload["schema"] != "ridge.rescue.run.v1":
        raise CustodyError("unsupported bundle version")
    if not isinstance(bundle["sha256"], str) or bundle["sha256"] != digest(payload):
        raise CustodyError("payload digest mismatch")
    try:
        world = parse_world(payload["world"])
        state = replay(world, payload["actions"])
    except (RescueError, ValueError, TypeError, KeyError) as exc:
        raise CustodyError("invalid or unreplayable action chain") from exc
    if canonical(state) != canonical(payload["state"]):
        raise CustodyError("final state does not match replay")
    return {"world": world, "state": state, "actions": payload["actions"]}
