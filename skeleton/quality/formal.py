"""Finite-state proof helpers for scoped P2 formal targets."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, AbstractSet, Hashable


class FormalModelError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FormalModelResult:
    state_count: int
    edge_count: int
    terminal_count: int


def check_finite_state_model(
    *,
    states: AbstractSet[Hashable],
    transitions: Mapping[Hashable, AbstractSet[Hashable]],
    terminals: AbstractSet[Hashable],
    initial: Hashable,
) -> FormalModelResult:
    state_set = set(states)
    terminal_set = set(terminals)
    if not state_set:
        raise FormalModelError("formal model has no states")
    if initial not in state_set:
        raise FormalModelError("initial state is not declared")
    if not terminal_set or not terminal_set <= state_set:
        raise FormalModelError("terminal states must be non-empty declared states")
    if set(transitions) != state_set:
        missing = sorted(str(x) for x in state_set - set(transitions))
        extra = sorted(str(x) for x in set(transitions) - state_set)
        raise FormalModelError(
            f"transition domain must equal state set; missing={missing} extra={extra}"
        )

    edge_count = 0
    for source, targets_raw in transitions.items():
        targets = set(targets_raw)
        unknown = targets - state_set
        if unknown:
            raise FormalModelError(
                f"{source!s} transitions to undeclared states: "
                f"{sorted(str(x) for x in unknown)}"
            )
        if source in terminal_set and targets:
            raise FormalModelError(f"terminal state {source!s} has outgoing transitions")
        if source not in terminal_set and not targets:
            raise FormalModelError(f"non-terminal state {source!s} is a dead end")
        edge_count += len(targets)

    reachable = {initial}
    frontier = [initial]
    while frontier:
        source = frontier.pop()
        for target in transitions[source]:
            if target not in reachable:
                reachable.add(target)
                frontier.append(target)
    unreachable = state_set - reachable
    if unreachable:
        raise FormalModelError(
            "states unreachable from initial: "
            + ", ".join(sorted(str(x) for x in unreachable))
        )

    reverse: dict[Hashable, set[Hashable]] = {state: set() for state in state_set}
    for source, targets in transitions.items():
        for target in targets:
            reverse[target].add(source)
    can_reach_terminal = set(terminal_set)
    frontier = list(terminal_set)
    while frontier:
        target = frontier.pop()
        for source in reverse[target]:
            if source not in can_reach_terminal:
                can_reach_terminal.add(source)
                frontier.append(source)
    no_terminal_path = state_set - can_reach_terminal
    if no_terminal_path:
        raise FormalModelError(
            "states cannot reach a terminal: "
            + ", ".join(sorted(str(x) for x in no_terminal_path))
        )

    return FormalModelResult(
        state_count=len(state_set),
        edge_count=edge_count,
        terminal_count=len(terminal_set),
    )


__all__ = ["FormalModelError", "FormalModelResult", "check_finite_state_model"]
