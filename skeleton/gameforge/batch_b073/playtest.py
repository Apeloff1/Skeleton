"""B073 — Autonomous playtest agents.

Success criterion: "Agents can navigate, act, pursue goals and report
softlocks/exploits with replay evidence."

:class:`PlaytestAgent` drives any world implementing the small ``World``
protocol (``reset``, ``actions``, ``step``, ``observe``, ``is_goal``). It does
seeded BFS-guided exploration toward the goal, and reports:

* ``softlock`` — a reachable state with no actions and not the goal, or a goal
  that is unreachable from the visited frontier;
* ``exploit`` — a step that violates a caller-supplied invariant (e.g. score
  jumps beyond a cap, walking through walls).

Every finding carries the action path from reset, which is replay evidence.
"""
from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Dict, Hashable, List, Optional, Protocol, Tuple


class World(Protocol):
    def reset(self) -> Hashable: ...
    def actions(self, state: Hashable) -> List[str]: ...
    def step(self, state: Hashable, action: str) -> Hashable: ...
    def is_goal(self, state: Hashable) -> bool: ...


Invariant = Callable[[Hashable, str, Hashable], Optional[str]]


@dataclass(frozen=True)
class Finding:
    kind: str  # "softlock" | "exploit" | "unreachable_goal"
    detail: str
    path: Tuple[str, ...]


@dataclass
class PlaytestReport:
    seed: int
    reached_goal: bool
    goal_path: Tuple[str, ...]
    states_visited: int
    findings: List[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.reached_goal and not self.findings


class PlaytestAgent:
    def __init__(self, world: World, seed: int = 0, max_states: int = 10_000,
                 invariants: Tuple[Invariant, ...] = ()) -> None:
        self.world, self.seed, self.max_states = world, seed, max_states
        self.invariants = invariants

    def run(self) -> PlaytestReport:
        rng = random.Random(self.seed)
        start = self.world.reset()
        paths: Dict[Hashable, Tuple[str, ...]] = {start: ()}
        q = deque([start])
        findings: List[Finding] = []
        goal_path: Optional[Tuple[str, ...]] = None
        while q and len(paths) < self.max_states:
            s = q.popleft()
            if self.world.is_goal(s):
                goal_path = goal_path or paths[s]
                continue
            acts = list(self.world.actions(s))
            if not acts:
                findings.append(Finding("softlock", f"no actions at {s!r}", paths[s]))
                continue
            rng.shuffle(acts)
            for a in acts:
                n = self.world.step(s, a)
                for inv in self.invariants:
                    msg = inv(s, a, n)
                    if msg:
                        findings.append(Finding("exploit", msg, paths[s] + (a,)))
                if n not in paths:
                    paths[n] = paths[s] + (a,)
                    q.append(n)
        if goal_path is None:
            findings.append(Finding("unreachable_goal", f"explored {len(paths)} states", ()))
        return PlaytestReport(self.seed, goal_path is not None, goal_path or (), len(paths), findings)

    def replay(self, path: Tuple[str, ...]) -> Hashable:
        s = self.world.reset()
        for a in path:
            if a not in self.world.actions(s):
                raise ValueError(f"illegal action {a!r} at {s!r}")
            s = self.world.step(s, a)
        return s


class GridWorld:
    """Reference world: ``#`` wall, ``S`` start, ``G`` goal, ``X`` trap (no exits)."""

    MOVES = {"N": (-1, 0), "S": (1, 0), "W": (0, -1), "E": (0, 1)}

    def __init__(self, rows: List[str]) -> None:
        self.rows = rows
        self.start = self.goal = None
        for r, line in enumerate(rows):
            for c, ch in enumerate(line):
                if ch == "S":
                    self.start = (r, c)
                elif ch == "G":
                    self.goal = (r, c)
        if self.start is None:
            raise ValueError("grid needs a start")

    def _cell(self, p):
        r, c = p
        if 0 <= r < len(self.rows) and 0 <= c < len(self.rows[r]):
            return self.rows[r][c]
        return "#"

    def reset(self):
        return self.start

    def actions(self, s):
        if self._cell(s) == "X":
            return []
        return [m for m, (dr, dc) in sorted(self.MOVES.items())
                if self._cell((s[0] + dr, s[1] + dc)) != "#"]

    def step(self, s, a):
        dr, dc = self.MOVES[a]
        return (s[0] + dr, s[1] + dc)

    def is_goal(self, s):
        return s == self.goal
