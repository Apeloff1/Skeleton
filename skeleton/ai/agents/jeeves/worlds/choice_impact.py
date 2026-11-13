"""Bounded terminal-consequence proof for original authored world choices.

This is a source-derived decision aid, not an LLM claim about narrative quality.
A choice is terminal-distinct only when its reachable terminal signatures differ
from the alternatives available in the SAME reachable player state.
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

SCHEMA = "jeeves.world.choice_impact.v1"
RECEIPT_SCHEMA = "jeeves.world.choice_impact_receipt.v1"
MAX_TRANSITIONS = 65536
MAX_OUTCOME_PAIRS = 131072
MAX_REPORT = 524288
MAX_HTML = 1572864

State = tuple[str, frozenset[str]]


def _signature(state: State) -> str:
    scene, flags = state
    return scene + ":" + ",".join(sorted(flags))


def analyze_choice_impact(world: Any) -> dict[str, Any]:
    """Enumerate legal player states, then solve terminal outcomes to a fixed point.

    A finite graph with cycles is handled by reverse propagation. Every reported
    witness is independently replayed by the canonical player interpreter.
    Unknown/inconclusive states are errors, never marked outcome-equivalent.
    """
    proof = prove(world)
    by_scene: dict[str, list[dict[str, Any]]] = {}
    for choice in world["choices"]:
        by_scene.setdefault(choice["from"], []).append(choice)
    for choices in by_scene.values():
        choices.sort(key=lambda item: item["id"])
    endings = {item["scene"] for item in world["endings"]}
    initial: State = (world["start"], frozenset())
    traces: dict[State, tuple[str, ...]] = {initial: ()}
    queue = deque([initial])
    outgoing: dict[State, list[tuple[str, State]]] = {}
    incoming: dict[State, set[State]] = {}
    transition_count = 0
    while queue:
        state = queue.popleft()
        scene, flags = state
        options: list[tuple[str, State]] = []
        if scene not in endings:
            for edge in by_scene.get(scene, ()):
                if not set(edge["requires"]) <= flags:
                    continue
                target: State = (
                    edge["to"], flags | frozenset(edge["grants"]),
                )
                options.append((edge["id"], target))
                incoming.setdefault(target, set()).add(state)
                transition_count += 1
                if transition_count > MAX_TRANSITIONS:
                    raise CanonError("choice_impact_transition_budget")
                if target not in traces:
                    if len(traces) >= MAX_STATES:
                        raise CanonError("choice_impact_state_budget")
                    traces[target] = traces[state] + (edge["id"],)
                    queue.append(target)
        outgoing[state] = options

    # Each terminal signature includes earned flags; different endings or
    # different terminal flags are distinct, but prose differences alone aren't.
    outcomes: dict[State, set[str]] = {
        state: ({_signature(state)} if state[0] in endings else set())
        for state in traces
    }
    total_pairs = sum(map(len, outcomes.values()))
    pending = deque(sorted(
        (state for state in traces if outcomes[state]),
        key=lambda state: (state[0], sorted(state[1])),
    ))
    queued = set(pending)
    while pending:
        target = pending.popleft()
        queued.remove(target)
        for parent in incoming.get(target, ()):
            delta = outcomes[target] - outcomes[parent]
            if not delta:
                continue
            total_pairs += len(delta)
            if total_pairs > MAX_OUTCOME_PAIRS:
                raise CanonError("choice_impact_outcome_budget")
            outcomes[parent].update(delta)
            if parent not in queued:
                pending.append(parent)
                queued.add(parent)
    stranded = sorted(_signature(state) for state in traces if not outcomes[state])
    if stranded:
        raise CanonError("choice_impact_no_terminal_outcome", stranded[0])

    observations: dict[str, dict[str, Any]] = {
        edge["id"]: {
            "witness": None, "reachable_contexts": 0,
            "branching_contexts": 0, "terminal_distinct_contexts": 0,
            "outcomes": set(),
        }
        for edge in world["choices"]
    }
    for state in sorted(traces, key=lambda item: (len(traces[item]), item[0], sorted(item[1]))):
        options = outgoing[state]
        for choice_id, target in options:
            row = observations[choice_id]
            row["reachable_contexts"] += 1
            row["outcomes"].update(outcomes[target])
            witness = traces[state] + (choice_id,)
            if row["witness"] is None or (len(witness), witness) < (
                len(row["witness"]), row["witness"]
            ):
                row["witness"] = witness
            alternatives = [other for other_id, other in options if other_id != choice_id]
            if alternatives:
                row["branching_contexts"] += 1
                peer_outcomes: set[str] = set()
                for other in alternatives:
                    peer_outcomes.update(outcomes[other])
                if outcomes[target] != peer_outcomes:
                    row["terminal_distinct_contexts"] += 1

    result = []
    for choice_id, row in sorted(observations.items()):
        witness = row["witness"]
        if witness is not None:
            playback = replay_choices(world, list(witness))
            if not playback["steps"] or playback["steps"][-1]["choice"] != choice_id:
                raise CanonError("choice_impact_witness_mismatch", choice_id)
        classification = (
            "unreachable" if not row["reachable_contexts"] else
            "no_peer_choice" if not row["branching_contexts"] else
            "terminal_distinct" if row["terminal_distinct_contexts"] else
            "terminal_outcome_equivalent"
        )
        result.append({
            "choice_id": choice_id, "classification": classification,
            "reachable_contexts": row["reachable_contexts"],
            "branching_contexts": row["branching_contexts"],
            "terminal_distinct_contexts": row["terminal_distinct_contexts"],
            "terminal_outcomes": sorted(row["outcomes"]),
            "witness": list(witness) if witness is not None else None,
        })
    report = {
        "schema": SCHEMA, "world_id": world["id"],
        "world_digest": proof.source_digest,
        "states_explored": len(traces), "transitions_explored": transition_count,
        "choices": result,
        "classification_note": (
            "Terminal outcome equivalence does not imply identical narrative, "
            "timing, animations, or intermediate scene experiences."
        ),
        "qualification": "bounded_canonical_replay_not_release_certified",
    }
    if len(canonical(report)) > MAX_REPORT:
        raise CanonError("choice_impact_report_budget")
    return report


class ChoiceImpactStore:
    """Private, source-leased report + real offline playable + digest receipt."""

    def __init__(self, root: str) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (
            world_id + ".choice-impact.report.json",
            world_id + ".choice-impact.playable.html",
            world_id + ".choice-impact.receipt.json",
        )

    def preview(self, world_id: str) -> dict[str, Any]:
        return analyze_choice_impact(self.worlds.read(world_id))

    @staticmethod
    def _outputs(world: Any, require_distinct: bool) -> tuple[dict[str, Any], tuple[bytes, bytes]]:
        if type(require_distinct) is not bool:
            raise CanonError("choice_impact_invalid_policy")
        report = analyze_choice_impact(world)
        if require_distinct:
            equivalent = [
                row["choice_id"] for row in report["choices"]
                if row["classification"] == "terminal_outcome_equivalent"
            ]
            if equivalent:
                raise CanonError("choice_impact_equivalent_choices", ",".join(equivalent))
        source = canonical(report)
        playable = compile_html(world).encode("utf-8")
        if len(playable) > MAX_HTML:
            raise CanonError("choice_impact_playable_budget")
        names = ChoiceImpactStore._names(world["id"])
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world),
            "report_digest": digest(report),
            "require_distinct": require_distinct,
            "artifacts": {
                names[0]: sha256(source).hexdigest(),
                names[1]: sha256(playable).hexdigest(),
            },
            "qualification": "operator_reviewed_source_proof_not_device_certified",
        }
        return receipt, (source, playable)

    def _lock(self, fd: int, world_id: str) -> None:
        try:
            handle = os.open(
                world_id + ".lock",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600, dir_fd=fd,
            )
        except FileExistsError:
            raise CanonError("lease_busy") from None
        os.close(handle)

    def _world(self, fd: int, world_id: str) -> dict[str, Any]:
        source = strict_json(self.worlds._read(fd, world_id + ".json"))
        proof = prove(source)
        if source["id"] != world_id:
            raise CanonError("choice_impact_identity_mismatch")
        if proof.source_digest != digest(source):
            raise CanonError("choice_impact_invalid_source")
        return source

    def compile(self, world_id: str, *, expected_world_digest: str,
                require_distinct: bool = False) -> dict[str, Any]:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                source = self._world(fd, world_id)
                if digest(source) != expected_world_digest:
                    raise CanonError("choice_impact_stale_source")
                receipt, outputs = self._outputs(source, require_distinct)
                names = self._names(world_id)
                for name, data in zip(names[:2], outputs):
                    self.worlds._write(fd, name, data)
                # Receipt is last: interrupted publication never verifies.
                self.worlds._write(fd, names[2], canonical(receipt))
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def verify(self, world_id: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                names = self._names(world_id)
                stored = strict_json(self.worlds._read(fd, names[2]))
                if type(stored) is not dict or type(stored.get("require_distinct")) is not bool:
                    raise CanonError("choice_impact_invalid_receipt")
                receipt, outputs = self._outputs(
                    self._world(fd, world_id), stored["require_distinct"],
                )
                if receipt != stored:
                    raise CanonError("choice_impact_receipt_mismatch")
                for name, expected in zip(names[:2], outputs):
                    if _artifact_read(fd, name) != expected:
                        raise CanonError("choice_impact_artifact_mismatch", name)
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
