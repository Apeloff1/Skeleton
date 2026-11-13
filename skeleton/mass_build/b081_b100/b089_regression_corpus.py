"""B089: known exploit classes and prior findings as permanent regression cases.

Cases are append-only: removing or mutating a recorded case is a gate failure.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from ._core import ContractError, digest, require, verdict


@dataclass(frozen=True)
class Case:
    case_id: str
    exploit_class: str
    payload: str
    expect_blocked: bool = True


class Corpus:
    def __init__(self) -> None:
        self._cases: dict[str, Case] = {}

    def add(self, case: Case) -> None:
        require(case.case_id not in self._cases, f"duplicate case {case.case_id}")
        self._cases[case.case_id] = case

    def manifest(self) -> dict[str, str]:
        return {cid: digest(c.__dict__) for cid, c in sorted(self._cases.items())}

    def cases(self) -> list[Case]:
        return [self._cases[k] for k in sorted(self._cases)]


def check_append_only(previous: Mapping[str, str], current: Mapping[str, str]) -> list[str]:
    out = []
    for cid, d in sorted(previous.items()):
        if cid not in current:
            out.append(f"removed:{cid}")
        elif current[cid] != d:
            out.append(f"mutated:{cid}")
    return out


def evaluate(corpus: Corpus, defenses: Mapping[str, Callable[[str], bool]], previous: Mapping[str, str] | None = None):
    findings = list(check_append_only(previous or {}, corpus.manifest()))
    for c in corpus.cases():
        fn = defenses.get(c.exploit_class)
        if fn is None:
            findings.append(f"no_defense:{c.exploit_class}")
            continue
        try:
            blocked = bool(fn(c.payload))
        except Exception as exc:  # defense crash = fail closed finding
            raise ContractError(f"defense crashed on {c.case_id}: {exc}") from exc
        if blocked != c.expect_blocked:
            findings.append(f"regressed:{c.case_id}")
    return verdict("B089", findings, cases=len(corpus.cases()))
