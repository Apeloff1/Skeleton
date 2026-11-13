"""Bounded deterministic choice-coverage proof and exact-source playable handoff.

Unlike ending reachability, this proves which authored individual decisions
can actually be exercised by a player with earned flags. Unreachable choices
are reported explicitly; exhausted search never masquerades as full coverage.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256
import os
from typing import Any

from .bundle import _artifact_read
from .session import replay_choices
from .world_canon import (
    CanonError, MAX_STATES, WorldStore, _id, canonical, compile_html,
    digest, prove, strict_json,
)

SCHEMA = "jeeves.world.playtest_coverage.v1"
RECEIPT_SCHEMA = "jeeves.world.playtest_receipt.v1"
MAX_ARTIFACT = 1572864


def prove_choice_coverage(world: Any) -> dict[str, Any]:
    proof = prove(world)
    by_scene: dict[str, list[dict[str, Any]]] = {}
    for choice in world["choices"]:
        by_scene.setdefault(choice["from"], []).append(choice)
    for edges in by_scene.values():
        edges.sort(key=lambda item: item["id"])
    endings = {item["scene"] for item in world["endings"]}
    start = (world["start"], frozenset())
    queue = deque([(start, ())])
    visited = {start}
    witnesses: dict[str, tuple[str, ...]] = {}
    while queue:
        (scene, flags), path = queue.popleft()
        if scene in endings:
            continue
        for edge in by_scene.get(scene, []):
            if not set(edge["requires"]) <= flags:
                continue
            trace = path + (edge["id"],)
            witnesses.setdefault(edge["id"], trace)
            next_state = (edge["to"], flags | frozenset(edge["grants"]))
            if next_state in visited:
                continue
            if len(visited) >= MAX_STATES:
                raise CanonError("playtest_state_budget_exhausted")
            visited.add(next_state)
            queue.append((next_state, trace))
    # Recheck all emitted witnesses with the canonical player interpreter.
    for choice_id, trace in witnesses.items():
        replay = replay_choices(world, list(trace))
        if replay["steps"][-1]["choice"] != choice_id:
            raise CanonError("playtest_invalid_witness", choice_id)
    all_ids = {item["id"] for item in world["choices"]}
    uncovered = sorted(all_ids - set(witnesses))
    report = {
        "schema": SCHEMA,
        "world_id": world["id"],
        "world_digest": proof.source_digest,
        "states_explored": len(visited),
        "total_choices": len(all_ids),
        "covered_choices": len(witnesses),
        "uncovered_choices": uncovered,
        "choice_witnesses": {key: list(value) for key, value in
                             sorted(witnesses.items())},
        "ending_witnesses": {key: list(value) for key, value in
                             sorted(proof.ending_witnesses.items())},
        "complete": not uncovered,
        "qualification": "bounded_source_replay_not_device_certified",
    }
    if len(canonical(report)) > 524288:
        raise CanonError("playtest_report_too_large")
    return report


class PlaytestStore:
    """Source-leased offline QA report and playable HTML with final receipt."""
    def __init__(self, root: str) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (world_id + ".playtest.report.json",
                world_id + ".playtest.playable.html",
                world_id + ".playtest.receipt.json")

    def preview(self, world_id: str) -> dict[str, Any]:
        return prove_choice_coverage(self.worlds.read(world_id))

    @staticmethod
    def _outputs(world: Any, require_full_coverage: bool):
        if type(require_full_coverage) is not bool:
            raise CanonError("playtest_invalid_coverage_policy")
        report = prove_choice_coverage(world)
        if require_full_coverage and not report["complete"]:
            raise CanonError("playtest_uncovered_choices",
                             ",".join(report["uncovered_choices"]))
        source = canonical(report)
        playable = compile_html(world).encode("utf-8")
        if len(playable) > MAX_ARTIFACT:
            raise CanonError("playtest_playable_too_large")
        names = PlaytestStore._names(world["id"])
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world),
            "coverage_digest": digest(report),
            "require_full_coverage": require_full_coverage,
            "artifacts": {
                names[0]: sha256(source).hexdigest(),
                names[1]: sha256(playable).hexdigest(),
            },
            "qualification": "source_proven_not_release_certified",
        }
        return receipt, (source, playable)

    def compile(self, world_id: str, *, expected_world_digest: str,
                require_full_coverage: bool = True) -> dict[str, Any]:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            lock = world_id + ".lock"
            try:
                handle = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                 os.O_NOFOLLOW, 0o600, dir_fd=fd)
            except FileExistsError:
                raise CanonError("lease_busy") from None
            try:
                os.close(handle)
                world = strict_json(self.worlds._read(fd, world_id + ".json"))
                proof = prove(world)
                if world["id"] != world_id or proof.source_digest != expected_world_digest:
                    raise CanonError("playtest_stale_source")
                receipt, outputs = self._outputs(world, require_full_coverage)
                names = self._names(world_id)
                for name, data in zip(names[:2], outputs):
                    self.worlds._write(fd, name, data)
                # A missing or stale receipt never certifies partially written
                # artifacts; verification always recomputes exact source bytes.
                self.worlds._write(fd, names[2], canonical(receipt))
                return receipt
            finally:
                os.unlink(lock, dir_fd=fd)
        finally:
            os.close(fd)

    def verify(self, world_id: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            lock = world_id + ".lock"
            try:
                handle = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                 os.O_NOFOLLOW, 0o600, dir_fd=fd)
            except FileExistsError:
                raise CanonError("lease_busy") from None
            try:
                os.close(handle)
                names = self._names(world_id)
                stored = strict_json(self.worlds._read(fd, names[2]))
                if type(stored) is not dict or type(stored.get("require_full_coverage")) is not bool:
                    raise CanonError("playtest_invalid_receipt")
                world = strict_json(self.worlds._read(fd, world_id + ".json"))
                prove(world)
                if world["id"] != world_id:
                    raise CanonError("playtest_identity_mismatch")
                receipt, outputs = self._outputs(
                    world, stored["require_full_coverage"])
                if receipt != stored:
                    raise CanonError("playtest_receipt_mismatch")
                for name, expected in zip(names[:2], outputs):
                    if _artifact_read(fd, name) != expected:
                        raise CanonError("playtest_artifact_mismatch", name)
                return receipt
            finally:
                os.unlink(lock, dir_fd=fd)
        finally:
            os.close(fd)
