"""B076 — Property/fuzz testing for gameplay.

Success criterion: "State machines, parsers and generated mechanics survive
broad invalid/random input domains."

Dependency-free property testing seeded through B071's
:class:`DeterministicRng`:

* :class:`Gen` — composable generators (ints, text incl. hostile bytes,
  choices, lists).
* :func:`check_property` — run a predicate over N generated cases; on failure
  shrink list inputs and report the seed so the case is reproducible.
* :func:`fuzz_state_machine` — random action sequences (valid *and* invalid)
  against a state machine, asserting an invariant after each step and that
  invalid actions are rejected with a declared exception, never a crash.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Sequence, Tuple, Type

from skeleton.gameforge.batch_b071 import DeterministicRng

HOSTILE = ["", "\x00", "\uffff", "-1", "1e309", "NaN", "{" * 50, "' OR 1=1", "../../etc", "\u202e"]


class Gen:
    def __init__(self, fn: Callable[[DeterministicRng], Any]) -> None:
        self.fn = fn

    def __call__(self, rng: DeterministicRng) -> Any:
        return self.fn(rng)

    @staticmethod
    def ints(lo: int = -2**31, hi: int = 2**31) -> "Gen":
        edges = [lo, hi, 0, -1, 1]
        return Gen(lambda r: r.choice([e for e in edges if lo <= e <= hi]) if r.random() < 0.2 else r.randint(lo, hi))

    @staticmethod
    def text(max_len: int = 20) -> "Gen":
        if type(max_len) is not int or not 0 <= max_len <= 1024:
            raise ValueError("fuzz text length exceeds bound")
        alphabet = "abcXYZ019 _-{}[]:,\"\\\n"
        def g(r):
            if r.random() < 0.3:
                return r.choice(HOSTILE)
            return "".join(r.choice(alphabet) for _ in range(r.randint(0, max_len)))
        return Gen(g)

    @staticmethod
    def one_of(options: Sequence[Any]) -> "Gen":
        return Gen(lambda r: r.choice(list(options)))

    def lists(self, max_len: int = 10) -> "Gen":
        if type(max_len) is not int or not 0 <= max_len <= 1024:
            raise ValueError("fuzz list length exceeds bound")
        return Gen(lambda r: [self(r) for _ in range(r.randint(0, max_len))])


@dataclass(frozen=True)
class FuzzFailure:
    seed: int
    case_index: int
    value: Any
    error: str


@dataclass(frozen=True)
class FuzzResult:
    cases: int
    failure: Optional[FuzzFailure]

    @property
    def ok(self) -> bool:
        return self.failure is None


def shrink_list(value: list, fails: Callable[[list], bool]) -> list:
    """Greedy delta shrink: drop halves, then single items, while still failing."""
    if len(value) > 10_000:
        raise ValueError("fuzz shrink input exceeds bound")
    cur = list(value)
    n = 2
    while len(cur) >= 1:
        chunk = max(1, len(cur) // n)
        reduced = False
        for i in range(0, len(cur), chunk):
            cand = cur[:i] + cur[i + chunk:]
            if fails(cand):
                cur, reduced = cand, True
                break
        if not reduced:
            if chunk == 1:
                break
            n *= 2
    return cur


def _fails(prop, v) -> Optional[str]:
    try:
        return None if prop(v) else "property returned False"
    except Exception as exc:  # noqa: BLE001 - any exception is a property failure
        return f"{type(exc).__name__}: {exc}"


def check_property(gen: Gen, prop: Callable[[Any], bool], seed: int = 0, cases: int = 200) -> FuzzResult:
    if type(cases) is not int or not 1 <= cases <= 10_000:
        raise ValueError("property case count exceeds bound")
    rng = DeterministicRng(seed)
    for i in range(cases):
        v = gen(rng)
        err = _fails(prop, v)
        if err:
            if isinstance(v, list):
                v = shrink_list(v, lambda c: _fails(prop, c) is not None)
                err = _fails(prop, v) or err
            return FuzzResult(i + 1, FuzzFailure(seed, i, v, err))
    return FuzzResult(cases, None)


def fuzz_state_machine(factory: Callable[[], Any], actions: Sequence[Tuple[str, Gen]],
                       invariant: Callable[[Any], bool], rejects: Tuple[Type[BaseException], ...],
                       seed: int = 0, runs: int = 50, steps: int = 30) -> FuzzResult:
    """Apply random ``(method_name, arg)`` sequences; declared rejections are fine, others fail."""
    if (type(runs) is not int or type(steps) is not int
            or not 1 <= runs <= 10_000 or not 1 <= steps <= 10_000
            or runs * steps > 100_000 or not 1 <= len(actions) <= 64):
        raise ValueError("state-machine fuzz workload exceeds bound")
    rng = DeterministicRng(seed)
    for run in range(runs):
        sm = factory()
        trace: List[Tuple[str, Any]] = []
        for _ in range(steps):
            name, gen = rng.choice(list(actions))
            arg = gen(rng)
            trace.append((name, arg))
            try:
                getattr(sm, name)(arg)
            except rejects:
                pass
            except Exception as exc:  # noqa: BLE001
                return FuzzResult(run + 1, FuzzFailure(seed, run, trace, f"crash {type(exc).__name__}: {exc}"))
            if not invariant(sm):
                return FuzzResult(run + 1, FuzzFailure(seed, run, trace, "invariant violated"))
    return FuzzResult(runs, None)
