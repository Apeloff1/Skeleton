"""Execution preconditions for repository/workspace state observed at review time."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from types import MappingProxyType
from typing import Callable, Mapping


DigestProvider = Callable[[str], str]


@dataclass(frozen=True)
class ResourcePrecondition:
    resource_id: str
    expected_digest: str
    required: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        if not self.resource_id or len(self.resource_id) > 1024:
            raise ValueError("invalid precondition resource_id")
        if len(self.expected_digest) != 64:
            raise ValueError("expected_digest must be SHA-256 hex")
        if len(self.description) > 1024:
            raise ValueError("precondition description too long")

    def to_dict(self) -> dict[str, object]:
        return {
            "resource_id": self.resource_id,
            "expected_digest": self.expected_digest,
            "required": self.required,
            "description": self.description,
        }


@dataclass(frozen=True)
class Preconditions:
    resources: tuple[ResourcePrecondition, ...]
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        resources = tuple(self.resources)
        ids = [item.resource_id for item in resources]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate precondition resource_id")
        metadata = dict(self.metadata)
        if len(metadata) > 64:
            raise ValueError("too many precondition metadata fields")
        object.__setattr__(self, "resources", resources)
        object.__setattr__(self, "metadata", MappingProxyType(metadata))

    @property
    def digest(self) -> str:
        raw = json.dumps(
            {
                "resources": [item.to_dict() for item in self.resources],
                "metadata": dict(self.metadata),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class PreconditionResult:
    resource_id: str
    required: bool
    matched: bool
    expected_digest: str
    observed_digest: str
    error: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "resource_id": self.resource_id,
            "required": self.required,
            "matched": self.matched,
            "expected_digest": self.expected_digest,
            "observed_digest": self.observed_digest,
            "error": self.error,
        }


@dataclass(frozen=True)
class PreconditionReport:
    results: tuple[PreconditionResult, ...]

    @property
    def ok(self) -> bool:
        return all(item.matched for item in self.results if item.required)

    @property
    def drifted(self) -> tuple[str, ...]:
        return tuple(
            item.resource_id
            for item in self.results
            if not item.matched
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "drifted": list(self.drifted),
            "results": [item.to_dict() for item in self.results],
        }


class PreconditionChecker:
    def __init__(self, digest_provider: DigestProvider) -> None:
        self.digest_provider = digest_provider

    def inspect(self, preconditions: Preconditions) -> PreconditionReport:
        results = []
        for item in preconditions.resources:
            try:
                observed = self.digest_provider(item.resource_id)
                if len(observed) != 64:
                    raise ValueError("digest provider returned invalid digest")
                matched = observed == item.expected_digest
                error = ""
            except BaseException as exc:
                observed = ""
                matched = False
                error = type(exc).__name__
            results.append(
                PreconditionResult(
                    item.resource_id,
                    item.required,
                    matched,
                    item.expected_digest,
                    observed,
                    error,
                )
            )
        return PreconditionReport(tuple(results))

    def require(self, preconditions: Preconditions) -> PreconditionReport:
        report = self.inspect(preconditions)
        if not report.ok:
            raise RuntimeError(
                "AI execution precondition drift: " + ", ".join(report.drifted)
            )
        return report
