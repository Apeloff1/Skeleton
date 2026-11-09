"""Deterministic state machine for one autonomous feature build session.

The model never selects or advances phases. Host code records every admitted
transition and fails closed on impossible ordering. The resulting trace is
content-addressed and can be embedded in PR evidence without storing source
content, credentials, or executable instructions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Mapping

from .supervisor_runtime import canonical_json


SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PHASES = frozenset(
    {
        "initialized",
        "architecture",
        "build-graph",
        "implementation",
        "validation",
        "review",
        "repair",
        "completed",
        "failed",
    }
)
TERMINAL_PHASES = frozenset({"completed", "failed"})

_ALLOWED_TRANSITIONS = {
    "initialized": frozenset({"architecture", "failed"}),
    "architecture": frozenset({"build-graph", "failed"}),
    "build-graph": frozenset({"implementation", "failed"}),
    "implementation": frozenset(
        {
            "implementation",
            "validation",
            "failed",
        }
    ),
    "validation": frozenset({"review", "failed"}),
    "review": frozenset(
        {
            "repair",
            "completed",
            "failed",
        }
    ),
    "repair": frozenset({"validation", "failed"}),
    "completed": frozenset(),
    "failed": frozenset(),
}

MAX_EVENTS = 64
MAX_METRICS = 24
MAX_METRIC_KEY = 64
MAX_METRIC_TEXT_BYTES = 1_000


class BuildSessionError(ValueError):
    """Build session identity or transition violated the host state machine."""


def _sha256(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or SHA256_RE.fullmatch(value) is None
    ):
        raise BuildSessionError(f"invalid {label}")
    return value


def _sha40(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or SHA40_RE.fullmatch(value) is None
    ):
        raise BuildSessionError(f"invalid {label}")
    return value


def _metric_value(value: object) -> object:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        if len(value.encode("utf-8")) > MAX_METRIC_TEXT_BYTES:
            raise BuildSessionError(
                "session metric text exceeds byte budget"
            )
        return value
    if isinstance(value, tuple):
        if len(value) > 32:
            raise BuildSessionError(
                "session metric tuple exceeds item budget"
            )
        return tuple(
            _metric_value(item)
            for item in value
        )
    raise BuildSessionError(
        "session metric must use bounded primitive data"
    )


def _metrics(
    value: Mapping[str, object] | None,
) -> tuple[tuple[str, object], ...]:
    if value is None:
        return ()
    if not isinstance(value, Mapping):
        raise BuildSessionError(
            "session metrics must be a mapping"
        )
    if len(value) > MAX_METRICS:
        raise BuildSessionError(
            "session metrics exceed field budget"
        )

    result: list[tuple[str, object]] = []
    for key in sorted(value):
        if (
            not isinstance(key, str)
            or not key
            or len(key) > MAX_METRIC_KEY
        ):
            raise BuildSessionError(
                "invalid session metric key"
            )
        result.append(
            (
                key,
                _metric_value(value[key]),
            )
        )
    return tuple(result)


@dataclass(frozen=True, slots=True)
class BuildSessionEvent:
    sequence: int
    phase: str
    artifact_fingerprint: str
    metrics: tuple[tuple[str, object], ...] = ()

    def __post_init__(self) -> None:
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 1
        ):
            raise BuildSessionError(
                "invalid build session event sequence"
            )
        if self.phase not in PHASES - {"initialized"}:
            raise BuildSessionError(
                "invalid build session event phase"
            )
        _sha256(
            self.artifact_fingerprint,
            label="session artifact fingerprint",
        )
        if len(self.metrics) > MAX_METRICS:
            raise BuildSessionError(
                "session event metrics exceed field budget"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "phase": self.phase,
            "artifact_fingerprint": self.artifact_fingerprint,
            "metrics": {
                key: value
                for key, value in self.metrics
            },
        }


@dataclass(slots=True)
class BuildSession:
    task_digest: str
    base_sha: str
    budget_fingerprint: str
    state: str = "initialized"
    events: list[BuildSessionEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.task_digest = _sha256(
            self.task_digest,
            label="session task digest",
        )
        self.base_sha = _sha40(
            self.base_sha,
            label="session base SHA",
        )
        self.budget_fingerprint = _sha256(
            self.budget_fingerprint,
            label="session budget fingerprint",
        )
        if self.state != "initialized":
            raise BuildSessionError(
                "new build session must begin initialized"
            )
        if self.events:
            raise BuildSessionError(
                "new build session cannot contain prior events"
            )

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL_PHASES

    @property
    def sequence(self) -> int:
        return len(self.events)

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(
            canonical_json(self.as_dict())
        ).hexdigest()

    def as_dict(self) -> dict[str, object]:
        return {
            "task_digest": self.task_digest,
            "base_sha": self.base_sha,
            "budget_fingerprint": self.budget_fingerprint,
            "state": self.state,
            "events": [
                item.as_dict()
                for item in self.events
            ],
        }

    def to_json(self) -> str:
        return json.dumps(
            {
                **self.as_dict(),
                "fingerprint": self.fingerprint,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    def advance(
        self,
        phase: str,
        artifact_fingerprint: str,
        *,
        metrics: Mapping[str, object] | None = None,
    ) -> BuildSessionEvent:
        if phase not in PHASES:
            raise BuildSessionError(
                "unknown build session phase"
            )
        if phase == "initialized":
            raise BuildSessionError(
                "cannot transition back to initialized"
            )
        if self.terminal:
            raise BuildSessionError(
                "cannot transition a terminal build session"
            )
        allowed = _ALLOWED_TRANSITIONS[self.state]
        if phase not in allowed:
            raise BuildSessionError(
                f"illegal build transition: {self.state} -> {phase}"
            )
        if len(self.events) >= MAX_EVENTS:
            raise BuildSessionError(
                "build session exceeds event budget"
            )

        event = BuildSessionEvent(
            sequence=len(self.events) + 1,
            phase=phase,
            artifact_fingerprint=_sha256(
                artifact_fingerprint,
                label="session artifact fingerprint",
            ),
            metrics=_metrics(metrics),
        )
        self.events.append(event)
        self.state = phase
        return event

    def fail(
        self,
        artifact_fingerprint: str,
        *,
        reason: str,
    ) -> BuildSessionEvent:
        if not isinstance(reason, str) or not reason.strip():
            raise BuildSessionError(
                "failed session requires a reason"
            )
        clean = reason.strip()
        if len(clean.encode("utf-8")) > MAX_METRIC_TEXT_BYTES:
            clean = clean.encode("utf-8")[
                :MAX_METRIC_TEXT_BYTES
            ].decode("utf-8", errors="ignore")
        return self.advance(
            "failed",
            artifact_fingerprint,
            metrics={"reason": clean},
        )

    def complete(
        self,
        artifact_fingerprint: str,
        *,
        files: int,
        model_calls: int,
        rounds: int,
    ) -> BuildSessionEvent:
        if self.state != "review":
            raise BuildSessionError(
                "build session may complete only after review"
            )
        for label, value in (
            ("files", files),
            ("model_calls", model_calls),
            ("rounds", rounds),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise BuildSessionError(
                    f"invalid completion metric: {label}"
                )
        return self.advance(
            "completed",
            artifact_fingerprint,
            metrics={
                "files": files,
                "model_calls": model_calls,
                "rounds": rounds,
            },
        )
