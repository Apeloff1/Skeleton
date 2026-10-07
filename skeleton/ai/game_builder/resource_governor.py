"""Bounded-resource accounting for no-wall-clock-deadline forge modes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .contracts import canonical_digest


class ResourceLimitError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ResourceEnvelope:
    max_tokens: int
    max_tool_calls: int
    max_artifact_bytes: int
    max_retries: int
    max_active_branches: int
    max_concurrency: int
    checkpoint_interval_rounds: int

    def __post_init__(self) -> None:
        for name in (
            "max_tokens",
            "max_tool_calls",
            "max_artifact_bytes",
            "max_retries",
            "max_active_branches",
            "max_concurrency",
            "checkpoint_interval_rounds",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class ResourceDelta:
    tokens: int = 0
    tool_calls: int = 0
    artifact_bytes: int = 0
    retries: int = 0
    active_branches: int | None = None
    concurrency: int | None = None

    def __post_init__(self) -> None:
        for name in ("tokens", "tool_calls", "artifact_bytes", "retries"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        for name in ("active_branches", "concurrency"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(f"{name} must be a non-negative integer or None")


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    tokens: int
    tool_calls: int
    artifact_bytes: int
    retries: int
    active_branches: int
    concurrency: int
    digest: str

    def to_payload(self) -> dict[str, int | str]:
        return {
            "active_branches": self.active_branches,
            "artifact_bytes": self.artifact_bytes,
            "concurrency": self.concurrency,
            "digest": self.digest,
            "retries": self.retries,
            "tokens": self.tokens,
            "tool_calls": self.tool_calls,
        }


class ResourceGovernor:
    """Atomic accounting for bounded resources.

    Wall-clock duration is intentionally absent.  The forge may run as long as
    needed, but every charged resource remains inside an explicit envelope.
    """

    SCHEMA = "skeleton.ai_game_builder.resource_governor.v1"

    def __init__(
        self,
        envelope: ResourceEnvelope,
        *,
        tokens: int = 0,
        tool_calls: int = 0,
        artifact_bytes: int = 0,
        retries: int = 0,
        active_branches: int = 0,
        concurrency: int = 0,
    ) -> None:
        self.envelope = envelope
        self.tokens = tokens
        self.tool_calls = tool_calls
        self.artifact_bytes = artifact_bytes
        self.retries = retries
        self.active_branches = active_branches
        self.concurrency = concurrency
        self._assert_within_bounds()

    def _assert_within_bounds(self) -> None:
        checks = (
            ("tokens", self.tokens, self.envelope.max_tokens),
            ("tool_calls", self.tool_calls, self.envelope.max_tool_calls),
            ("artifact_bytes", self.artifact_bytes, self.envelope.max_artifact_bytes),
            ("retries", self.retries, self.envelope.max_retries),
            ("active_branches", self.active_branches, self.envelope.max_active_branches),
            ("concurrency", self.concurrency, self.envelope.max_concurrency),
        )
        for name, value, limit in checks:
            if value < 0 or value > limit:
                raise ResourceLimitError(
                    f"{name} resource bound exceeded: {value} > {limit}"
                )

    def charge(self, delta: ResourceDelta) -> ResourceSnapshot:
        proposal = {
            "tokens": self.tokens + delta.tokens,
            "tool_calls": self.tool_calls + delta.tool_calls,
            "artifact_bytes": self.artifact_bytes + delta.artifact_bytes,
            "retries": self.retries + delta.retries,
            "active_branches": (
                self.active_branches
                if delta.active_branches is None
                else delta.active_branches
            ),
            "concurrency": (
                self.concurrency if delta.concurrency is None else delta.concurrency
            ),
        }
        checks = (
            ("tokens", proposal["tokens"], self.envelope.max_tokens),
            ("tool_calls", proposal["tool_calls"], self.envelope.max_tool_calls),
            ("artifact_bytes", proposal["artifact_bytes"], self.envelope.max_artifact_bytes),
            ("retries", proposal["retries"], self.envelope.max_retries),
            ("active_branches", proposal["active_branches"], self.envelope.max_active_branches),
            ("concurrency", proposal["concurrency"], self.envelope.max_concurrency),
        )
        for name, value, limit in checks:
            if value > limit:
                raise ResourceLimitError(
                    f"{name} resource bound exceeded: {value} > {limit}"
                )
        self.tokens = proposal["tokens"]
        self.tool_calls = proposal["tool_calls"]
        self.artifact_bytes = proposal["artifact_bytes"]
        self.retries = proposal["retries"]
        self.active_branches = proposal["active_branches"]
        self.concurrency = proposal["concurrency"]
        return self.snapshot

    @property
    def snapshot(self) -> ResourceSnapshot:
        core = {
            "active_branches": self.active_branches,
            "artifact_bytes": self.artifact_bytes,
            "concurrency": self.concurrency,
            "retries": self.retries,
            "tokens": self.tokens,
            "tool_calls": self.tool_calls,
        }
        return ResourceSnapshot(**core, digest=canonical_digest(core))

    def checkpoint_due(self, completed_rounds: int) -> bool:
        if isinstance(completed_rounds, bool) or not isinstance(completed_rounds, int):
            raise ValueError("completed_rounds must be an integer")
        if completed_rounds <= 0:
            return False
        return completed_rounds % self.envelope.checkpoint_interval_rounds == 0

    def to_checkpoint(self) -> dict[str, object]:
        core: dict[str, object] = {
            "envelope": {
                "checkpoint_interval_rounds": self.envelope.checkpoint_interval_rounds,
                "max_active_branches": self.envelope.max_active_branches,
                "max_artifact_bytes": self.envelope.max_artifact_bytes,
                "max_concurrency": self.envelope.max_concurrency,
                "max_retries": self.envelope.max_retries,
                "max_tokens": self.envelope.max_tokens,
                "max_tool_calls": self.envelope.max_tool_calls,
            },
            "schema": self.SCHEMA,
            "usage": {
                "active_branches": self.active_branches,
                "artifact_bytes": self.artifact_bytes,
                "concurrency": self.concurrency,
                "retries": self.retries,
                "tokens": self.tokens,
                "tool_calls": self.tool_calls,
            },
        }
        return {**core, "checkpoint_digest": canonical_digest(core)}

    @classmethod
    def restore(cls, payload: Mapping[str, object]) -> "ResourceGovernor":
        supplied = payload.get("checkpoint_digest")
        core = {k: v for k, v in payload.items() if k != "checkpoint_digest"}
        if supplied != canonical_digest(core):
            raise ResourceLimitError("resource checkpoint digest mismatch")
        if payload.get("schema") != cls.SCHEMA:
            raise ResourceLimitError("unsupported resource checkpoint schema")
        envelope = payload.get("envelope")
        usage = payload.get("usage")
        if not isinstance(envelope, Mapping) or not isinstance(usage, Mapping):
            raise ResourceLimitError("resource checkpoint payload malformed")
        return cls(
            ResourceEnvelope(
                max_tokens=int(envelope["max_tokens"]),
                max_tool_calls=int(envelope["max_tool_calls"]),
                max_artifact_bytes=int(envelope["max_artifact_bytes"]),
                max_retries=int(envelope["max_retries"]),
                max_active_branches=int(envelope["max_active_branches"]),
                max_concurrency=int(envelope["max_concurrency"]),
                checkpoint_interval_rounds=int(envelope["checkpoint_interval_rounds"]),
            ),
            tokens=int(usage["tokens"]),
            tool_calls=int(usage["tool_calls"]),
            artifact_bytes=int(usage["artifact_bytes"]),
            retries=int(usage["retries"]),
            active_branches=int(usage["active_branches"]),
            concurrency=int(usage["concurrency"]),
        )
