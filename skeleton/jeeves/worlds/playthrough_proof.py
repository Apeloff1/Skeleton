"""Source-bound, deterministic acceptance of a complete original-world playthrough.

This verifies a real sequence of player choices against canonical world rules.
It does not claim browser, device, native engine or human playtest evidence.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from typing import Any

from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, canonical, compile_html, prove, strict_json,
)

MAX_TRACE = 2048



def replay_checkpoint(world: dict[str, Any], choices: list[str], *,
                      expected_source_sha: str,
                      previous_checkpoint: dict[str, Any] | None = None) -> dict[str, Any]:
    """Reconstruct a saveable checkpoint from source-bound player actions.

    A caller may supply a prior checkpoint to detect tampering or divergence
    before continuing. The trace is always replayed from the canonical start.
    This is a portable record, not a claim of durable disk publication.
    """
    proof = prove(world)
    if type(expected_source_sha) is not str or proof.source_digest != expected_source_sha:
        raise CanonError("stale_source")
    if type(choices) is not list or len(choices) > MAX_TRACE or any(
            type(choice) is not str for choice in choices):
        raise CanonError("invalid_trace")
    if previous_checkpoint is not None:
        if type(previous_checkpoint) is not dict or set(previous_checkpoint) != {
                "schema", "world_id", "source_digest", "scene", "flags",
                "trace", "trace_digest", "finished"}:
            raise CanonError("invalid_checkpoint")
        prior_trace = previous_checkpoint["trace"]
        if type(prior_trace) is not list or len(prior_trace) > len(choices):
            raise CanonError("checkpoint_divergence")
        if choices[:len(prior_trace)] != prior_trace:
            raise CanonError("checkpoint_divergence")
        expected_prior = replay_checkpoint(world, prior_trace,
                                           expected_source_sha=expected_source_sha)
        if expected_prior != previous_checkpoint:
            raise CanonError("checkpoint_tampered")
    edges = {choice["id"]: choice for choice in world["choices"]}
    endings = {ending["scene"] for ending in world["endings"]}
    scene = world["start"]
    flags: set[str] = set()
    for index, choice_id in enumerate(choices):
        if scene in endings:
            raise CanonError("action_after_ending", str(index))
        edge = edges.get(choice_id)
        if edge is None or edge["from"] != scene:
            raise CanonError("invalid_player_choice", str(index))
        if not set(edge["requires"]).issubset(flags):
            raise CanonError("missing_quest_requirement", str(index))
        flags.update(edge["grants"])
        scene = edge["to"]
    return {
        "schema": "jeeves.world.checkpoint.v1",
        "world_id": world["id"],
        "source_digest": proof.source_digest,
        "scene": scene,
        "flags": sorted(flags),
        "trace": list(choices),
        "trace_digest": sha256(canonical(choices)).hexdigest(),
        "finished": scene in endings,
    }


def verify_playthrough(world: dict[str, Any], choices: list[str],
                       *, expected_source_sha: str,
                       expected_html_sha: str | None = None) -> dict[str, Any]:
    proof = prove(world)
    if proof.source_digest != expected_source_sha:
        raise CanonError("stale_source")
    if type(choices) is not list or len(choices) > MAX_TRACE:
        raise CanonError("invalid_trace")
    if any(type(choice) is not str for choice in choices):
        raise CanonError("invalid_trace")
    if expected_html_sha is not None:
        if type(expected_html_sha) is not str or len(expected_html_sha) != 64:
            raise CanonError("invalid_export_digest")
        actual = sha256(compile_html(world).encode("utf-8")).hexdigest()
        if actual != expected_html_sha:
            raise CanonError("export_mismatch")
    edges = {choice["id"]: choice for choice in world["choices"]}
    endings = {ending["scene"]: ending["label"] for ending in world["endings"]}
    scene = world["start"]
    flags: set[str] = set()
    for index, choice_id in enumerate(choices):
        if scene in endings:
            raise CanonError("action_after_ending", str(index))
        edge = edges.get(choice_id)
        if edge is None or edge["from"] != scene:
            raise CanonError("invalid_player_choice", str(index))
        if not set(edge["requires"]).issubset(flags):
            raise CanonError("missing_quest_requirement", str(index))
        flags.update(edge["grants"])
        scene = edge["to"]
    if scene not in endings:
        raise CanonError("unfinished_playthrough")
    return {
        "schema": "jeeves.world.playthrough-proof.v1",
        "world_id": world["id"],
        "source_digest": proof.source_digest,
        "ending_scene": scene,
        "ending_label": endings[scene],
        "choice_count": len(choices),
        "trace_digest": sha256(canonical(choices)).hexdigest(),
        "export_digest": expected_html_sha,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace")
    parser.add_argument("world_id")
    parser.add_argument("source_sha")
    parser.add_argument("trace_json", help="JSON array of actual choice IDs")
    parser.add_argument("--html-sha")
    args = parser.parse_args()
    try:
        trace = strict_json(args.trace_json.encode("utf-8"))
        result = verify_playthrough(
            WorldStore(args.workspace).read(args.world_id), trace,
            expected_source_sha=args.source_sha, expected_html_sha=args.html_sha)
    except (CanonError, OSError, UnicodeError) as exc:
        parser.exit(2, f"playthrough_rejected: {exc}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
