"""Observed tool-call topology reconstruction from digested execution traces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class ToolCallObservation:
    observation_id: str
    trace_id: str
    step: int
    caller: str
    tool_name: str
    input_digest: str
    output_digest: str
    success: bool

    def __post_init__(self) -> None:
        if not self.observation_id or not self.trace_id or not self.caller or not self.tool_name:
            raise ReverseEngineeringError("tool-call observation identity fields are required")
        if self.step < 0:
            raise ReverseEngineeringError("tool-call step must be non-negative")
        if not is_sha256_digest(self.input_digest) or not is_sha256_digest(self.output_digest):
            raise ReverseEngineeringError("tool-call digests must be sha256 hex digests")


@dataclass(frozen=True)
class ToolTopologyReport:
    observation_count: int
    trace_count: int
    callers: tuple[str, ...]
    tools: tuple[str, ...]
    caller_tool_edges: tuple[tuple[str, str, int], ...]
    tool_transition_edges: tuple[tuple[str, str, int], ...]
    tool_success_rates: tuple[tuple[str, float], ...]
    cycle_candidate_count: int
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "observation_count": self.observation_count,
            "trace_count": self.trace_count,
            "callers": list(self.callers),
            "tools": list(self.tools),
            "caller_tool_edges": [list(item) for item in self.caller_tool_edges],
            "tool_transition_edges": [list(item) for item in self.tool_transition_edges],
            "tool_success_rates": [list(item) for item in self.tool_success_rates],
            "cycle_candidate_count": self.cycle_candidate_count,
            "digest": self.digest,
        }


def analyze_tool_topology(
    observations: Sequence[ToolCallObservation],
) -> ToolTopologyReport:
    if not observations:
        raise ReverseEngineeringError("tool topology requires observations")
    ids = [item.observation_id for item in observations]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("observation_id values must be unique")

    caller_edges: dict[tuple[str, str], int] = {}
    success: dict[str, list[bool]] = {}
    traces: dict[str, list[ToolCallObservation]] = {}
    for item in observations:
        caller_edges[(item.caller, item.tool_name)] = caller_edges.get((item.caller, item.tool_name), 0) + 1
        success.setdefault(item.tool_name, []).append(item.success)
        traces.setdefault(item.trace_id, []).append(item)

    transition_edges: dict[tuple[str, str], int] = {}
    for trace_id, items in sorted(traces.items()):
        ordered = sorted(items, key=lambda item: (item.step, item.observation_id))
        steps = [item.step for item in ordered]
        if len(steps) != len(set(steps)):
            raise ReverseEngineeringError(f"trace {trace_id!r} contains duplicate step values")
        for left, right in zip(ordered, ordered[1:]):
            key = (left.tool_name, right.tool_name)
            transition_edges[key] = transition_edges.get(key, 0) + 1

    cycle_candidates = 0
    for (left, right), count in transition_edges.items():
        if left == right:
            cycle_candidates += count
        elif (right, left) in transition_edges and left < right:
            cycle_candidates += min(count, transition_edges[(right, left)])

    payload = {
        "observations": [
            {
                "observation_id": item.observation_id,
                "trace_id": item.trace_id,
                "step": item.step,
                "caller": item.caller,
                "tool_name": item.tool_name,
                "input_digest": item.input_digest,
                "output_digest": item.output_digest,
                "success": item.success,
            }
            for item in sorted(observations, key=lambda value: value.observation_id)
        ]
    }
    return ToolTopologyReport(
        observation_count=len(observations),
        trace_count=len(traces),
        callers=tuple(sorted({item.caller for item in observations})),
        tools=tuple(sorted(success)),
        caller_tool_edges=tuple(
            (caller, tool, count)
            for (caller, tool), count in sorted(caller_edges.items())
        ),
        tool_transition_edges=tuple(
            (left, right, count)
            for (left, right), count in sorted(transition_edges.items())
        ),
        tool_success_rates=tuple(
            (tool, sum(values) / len(values))
            for tool, values in sorted(success.items())
        ),
        cycle_candidate_count=cycle_candidates,
        digest=stable_digest(payload),
    )
