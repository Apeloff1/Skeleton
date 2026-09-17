"""Provider-neutral deterministic replay for skeleton.game.

Issue #936 / #807 B071-B072. Rendering, network, and worldgen stay out.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from skeleton.game.clock import MAX_TICKS
from skeleton.game.engine import DeterministicEngine
from skeleton.game.mechanics import (
    CombatStyle,
    CombatSystemSpec,
    EconomySystemSpec,
    GameMechanicsError,
    ProgressionStyle,
    ProgressionSystemSpec,
)


REPLAY_SCHEMA_VERSION = 1
REPLAY_KIND = "skeleton.game.replay"


class ReplayError(GameMechanicsError):
    code = "GAME.REPLAY"


def canonical_dumps(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest_payload(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_dumps(payload).encode("utf-8")).hexdigest()


def _combat_spec(raw: Mapping[str, Any] | None) -> CombatSystemSpec:
    data = dict(raw or {})
    style = data.get("style", data.get("combat_style", CombatStyle.TURN_BASED))
    return CombatSystemSpec(
        style=style,
        include_magic=bool(data.get("include_magic", True)),
        include_status_effects=bool(data.get("include_status_effects", True)),
        party_based=bool(data.get("party_based", False)),
        enemy_ai_complexity=str(data.get("enemy_ai_complexity", "moderate")),
    )


def _economy_spec(raw: Mapping[str, Any] | None) -> EconomySystemSpec:
    data = dict(raw or {})
    currencies = data.get("currencies", ("gold",))
    return EconomySystemSpec(
        currencies=tuple(currencies),
        include_trading=bool(data.get("include_trading", True)),
        include_crafting=bool(data.get("include_crafting", False)),
        inflation_model=bool(data.get("inflation_model", False)),
    )


def _progression_spec(raw: Mapping[str, Any] | None) -> ProgressionSystemSpec:
    data = dict(raw or {})
    style = data.get("style", data.get("progression_style", ProgressionStyle.LINEAR))
    return ProgressionSystemSpec(
        style=style,
        max_level=int(data.get("max_level", 100)),
        include_prestige=bool(data.get("include_prestige", False)),
        skill_tree_branches=int(data.get("skill_tree_branches", 3)),
    )


@dataclass(frozen=True, slots=True)
class ReplayTrace:
    schema_version: int
    kind: str
    seed: int | str
    hz: int
    spec: dict[str, Any]
    inputs: list[dict[str, Any]]
    frames: list[dict[str, Any]]
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "seed": self.seed,
            "hz": self.hz,
            "spec": dict(self.spec),
            "inputs": list(self.inputs),
            "frames": list(self.frames),
            "digest": self.digest,
        }


def _engine_from_spec(seed: int | str, spec: Mapping[str, Any], hz: int) -> DeterministicEngine:
    return DeterministicEngine(
        seed=seed,
        combat=_combat_spec(spec.get("combat") if isinstance(spec.get("combat"), Mapping) else spec),
        economy=_economy_spec(spec.get("economy") if isinstance(spec.get("economy"), Mapping) else spec),
        progression=_progression_spec(
            spec.get("progression") if isinstance(spec.get("progression"), Mapping) else spec
        ),
        hz=hz,
    )


def record(
    *,
    seed: int | str,
    inputs: list[Mapping[str, Any]] | None = None,
    spec: Mapping[str, Any] | None = None,
    hz: int = 60,
) -> ReplayTrace:
    events = [dict(item) for item in (inputs or [])]
    engine = _engine_from_spec(seed, spec or {}, hz)
    frames = engine.run(events)
    body = {
        "schema_version": REPLAY_SCHEMA_VERSION,
        "kind": REPLAY_KIND,
        "seed": engine.seed,
        "hz": hz,
        "spec": engine.spec_card(),
        "inputs": events,
        "frames": frames,
    }
    return ReplayTrace(digest=digest_payload(body), **body)  # type: ignore[arg-type]


def load_trace(raw: Mapping[str, Any] | str) -> ReplayTrace:
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            raise ReplayError("empty trace")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ReplayError(f"malformed trace json: {exc.msg}") from exc
    else:
        payload = raw
    if not isinstance(payload, Mapping):
        raise ReplayError("trace must be an object")
    version = payload.get("schema_version")
    if version != REPLAY_SCHEMA_VERSION:
        raise ReplayError(
            "incompatible replay schema",
            context={"got": version, "expected": REPLAY_SCHEMA_VERSION},
        )
    if payload.get("kind") != REPLAY_KIND:
        raise ReplayError("unknown replay kind", context={"kind": payload.get("kind")})
    for key in ("seed", "hz", "spec", "inputs", "frames", "digest"):
        if key not in payload:
            raise ReplayError(f"trace missing {key}")
    if not isinstance(payload["inputs"], list) or not isinstance(payload["frames"], list):
        raise ReplayError("inputs and frames must be lists")
    if len(payload["frames"]) > MAX_TICKS + 1:
        raise ReplayError("trace exceeds tick ceiling")
    if not isinstance(payload["digest"], str) or len(payload["digest"]) != 64:
        raise ReplayError("digest must be sha256 hex")
    return ReplayTrace(
        schema_version=int(payload["schema_version"]),
        kind=str(payload["kind"]),
        seed=payload["seed"],
        hz=int(payload["hz"]),
        spec=dict(payload["spec"]),
        inputs=[dict(item) for item in payload["inputs"]],
        frames=[dict(item) for item in payload["frames"]],
        digest=str(payload["digest"]),
    )


def replay(trace: ReplayTrace | Mapping[str, Any] | str) -> ReplayTrace:
    sealed = trace if isinstance(trace, ReplayTrace) else load_trace(trace)
    return record(seed=sealed.seed, inputs=sealed.inputs, spec=sealed.spec, hz=sealed.hz)


def compare(left: ReplayTrace, right: ReplayTrace) -> dict[str, Any]:
    match = left.digest == right.digest
    first = None
    limit = min(len(left.frames), len(right.frames))
    for index in range(limit):
        if left.frames[index] != right.frames[index]:
            first = index
            break
    if first is None and len(left.frames) != len(right.frames):
        first = limit
    return {
        "match": match,
        "left_digest": left.digest,
        "right_digest": right.digest,
        "first_divergent_frame": first,
        "left_frames": len(left.frames),
        "right_frames": len(right.frames),
    }


def verify(raw: Mapping[str, Any] | str) -> dict[str, Any]:
    sealed = load_trace(raw)
    unsigned = {
        "schema_version": sealed.schema_version,
        "kind": sealed.kind,
        "seed": sealed.seed,
        "hz": sealed.hz,
        "spec": sealed.spec,
        "inputs": sealed.inputs,
        "frames": sealed.frames,
    }
    expected = digest_payload(unsigned)
    if expected != sealed.digest:
        raise ReplayError("sealed digest does not match payload")
    live = replay(sealed)
    report = compare(sealed, live)
    if not report["match"]:
        raise ReplayError("replay diverged from sealed digest", context=report)
    return {"ok": True, "digest": live.digest, "frames": len(live.frames)}
