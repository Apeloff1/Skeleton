"""Deterministic validation policy independent of model suggestions."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable

@dataclass(frozen=True)
class ValidationPlan:
    commands: tuple[tuple[str,...], ...]
    reason: str

def plan_validation(paths: Iterable[str], related_tests: Iterable[str]=()) -> ValidationPlan:
    paths=tuple(dict.fromkeys(paths)); tests=tuple(sorted(set(related_tests)))
    commands:list[tuple[str,...]]=[]
    direct=tuple(p for p in paths if p.endswith(".py") and ("/test" in p or PurePosixPath(p).name.startswith("test_")))
    if direct: commands.append(("python","-m","pytest","-q",*direct[:8]))
    elif tests: commands.append(("python","-m","pytest","-q",*tests[:8]))
    py=tuple(p for p in paths if p.endswith(".py"))
    if py: commands.append(("python","-m","compileall","-q",*py[:8]))
    return ValidationPlan(tuple(commands[:3]), "deterministic-path-derived")
