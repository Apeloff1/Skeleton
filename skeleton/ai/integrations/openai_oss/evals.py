"""Evaluation interchange inspired by the MIT-licensed OpenAI Evals core."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
import json
from typing import Callable, Iterable, Mapping

from .optional import dependency_status
from .registry import source


@dataclass(frozen=True, slots=True)
class EvalCase:
    sample_id: str
    input: object
    ideal: object | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.sample_id, str) or not self.sample_id.strip():
            raise ValueError("sample_id must be non-empty")
        object.__setattr__(self, "metadata", dict(self.metadata))

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "sample_id": self.sample_id,
            "input": self.input,
            "metadata": dict(self.metadata),
        }
        if self.ideal is not None:
            payload["ideal"] = self.ideal
        return payload


@dataclass(frozen=True, slots=True)
class EvalResult:
    sample_id: str
    metrics: Mapping[str, float]
    passed: bool | None = None

    def __post_init__(self) -> None:
        metrics: dict[str, float] = {}
        for key, value in self.metrics.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError("eval metrics must be numeric")
            metrics[str(key)] = float(value)
        object.__setattr__(self, "metrics", metrics)


def export_jsonl(cases: Iterable[EvalCase]) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, EvalCase):
            raise TypeError("cases must contain EvalCase")
        if case.sample_id in seen:
            raise ValueError(f"duplicate eval sample_id: {case.sample_id}")
        seen.add(case.sample_id)
        lines.append(
            json.dumps(
                case.as_dict(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        )
    return "\n".join(lines) + ("\n" if lines else "")


def upstream_evals_status(
    *, importer: Callable[[str], object] = import_module
):
    return dependency_status(source("evals"), "evals", importer=importer)


__all__ = [
    "EvalCase",
    "EvalResult",
    "export_jsonl",
    "upstream_evals_status",
]
