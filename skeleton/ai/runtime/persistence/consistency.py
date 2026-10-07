"""Explicit consistency contracts for canonical and projected state.

VOL-132 runtime contract.  A caller must name the state domain and the
freshness class of a read.  Stale or unknown state can never masquerade as a
fresh authoritative read; projections may be served stale only through an
explicit opt-in decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, Mapping


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,191}$")


class ConsistencyError(ValueError):
    """Consistency metadata or a read decision is unsafe."""


class ReadGuarantee(str, Enum):
    AUTHORITATIVE_COMMITTED = "authoritative_committed"
    EVENTUAL_PROJECTION = "eventual_projection"
    BEST_EFFORT_SCRATCH = "best_effort_scratch"
    RECOVERY_AID_ONLY = "recovery_aid_only"


class WriteGuarantee(str, Enum):
    DURABLE_COMMIT_ACK = "durable_commit_ack"
    SOURCE_FIRST_THEN_PROJECT = "source_first_then_project"
    NON_AUTHORITATIVE_RECOMPUTABLE = "non_authoritative_recomputable"
    RECOVERY_AID_NO_AUTHORITY = "recovery_aid_no_authority"


class FreshnessState(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


class ReadDisposition(str, Enum):
    SERVE_FRESH = "serve_fresh"
    SERVE_EXPLICIT_STALE = "serve_explicit_stale"
    BLOCK_STALE = "block_stale"
    BLOCK_UNKNOWN = "block_unknown"
    BLOCK_RECOVERY_AID = "block_recovery_aid"


def _id(value: object, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ConsistencyError(f"{field} must be a canonical identifier")
    return value


def _nonnegative(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConsistencyError(f"{field} must be a non-negative integer")
    return value


def _digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ConsistencyError("consistency identity must be canonical JSON") from exc
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class ConsistencyProfile:
    domain_id: str
    physical_store: str
    authority: str
    source_of_truth: bool
    read_guarantee: ReadGuarantee
    write_guarantee: WriteGuarantee
    stale_policy: str
    unknown_policy: str
    source_refs: tuple[str, ...] = ()
    max_staleness_ms: int | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "domain_id", _id(self.domain_id, "domain_id"))
        object.__setattr__(
            self,
            "physical_store",
            _id(self.physical_store, "physical_store"),
        )
        object.__setattr__(self, "authority", _id(self.authority, "authority"))
        if not isinstance(self.source_of_truth, bool):
            raise ConsistencyError("source_of_truth must be boolean")
        try:
            object.__setattr__(
                self,
                "read_guarantee",
                ReadGuarantee(self.read_guarantee),
            )
            object.__setattr__(
                self,
                "write_guarantee",
                WriteGuarantee(self.write_guarantee),
            )
        except ValueError as exc:
            raise ConsistencyError("unsupported consistency guarantee") from exc
        if self.stale_policy not in {"reject", "explicit_only"}:
            raise ConsistencyError("unsupported stale_policy")
        if self.unknown_policy != "reject":
            raise ConsistencyError("unknown_policy must fail closed")
        sources: list[str] = []
        for item in self.source_refs:
            if not isinstance(item, str) or not item.strip() or len(item) > 512:
                raise ConsistencyError("source_ref must be a bounded non-empty string")
            if item != item.strip():
                raise ConsistencyError("source_ref must be normalized")
            sources.append(item)
        object.__setattr__(self, "source_refs", tuple(sorted(set(sources))))
        if self.max_staleness_ms is not None:
            object.__setattr__(
                self,
                "max_staleness_ms",
                _nonnegative(self.max_staleness_ms, "max_staleness_ms"),
            )
        if self.schema_version != 1:
            raise ConsistencyError("unsupported consistency profile schema")

        authoritative = self.authority in {
            "authoritative",
            "conditional-authoritative",
        }
        if authoritative:
            if not self.source_of_truth:
                raise ConsistencyError("authoritative profile must be source_of_truth")
            if self.read_guarantee is not ReadGuarantee.AUTHORITATIVE_COMMITTED:
                raise ConsistencyError("authoritative profile requires committed reads")
            if self.write_guarantee is not WriteGuarantee.DURABLE_COMMIT_ACK:
                raise ConsistencyError("authoritative profile requires durable commit acknowledgement")
            if self.stale_policy != "reject":
                raise ConsistencyError("authoritative profile cannot serve stale reads")
        if self.authority in {"derived", "durable-projection"}:
            if self.source_of_truth:
                raise ConsistencyError("projection profile cannot be source_of_truth")
            if not self.source_refs:
                raise ConsistencyError("projection profile requires source domains")
            if self.read_guarantee is not ReadGuarantee.EVENTUAL_PROJECTION:
                raise ConsistencyError("projection profile requires eventual reads")
            if self.write_guarantee is not WriteGuarantee.SOURCE_FIRST_THEN_PROJECT:
                raise ConsistencyError("projection writes must be source-first")
        if self.authority == "scratch":
            if self.source_of_truth:
                raise ConsistencyError("scratch profile cannot be source_of_truth")
            if self.read_guarantee is not ReadGuarantee.BEST_EFFORT_SCRATCH:
                raise ConsistencyError("scratch profile requires best-effort reads")
            if self.write_guarantee is not WriteGuarantee.NON_AUTHORITATIVE_RECOMPUTABLE:
                raise ConsistencyError("scratch profile must be recomputable")
        if self.authority == "recovery-aid":
            if self.read_guarantee is not ReadGuarantee.RECOVERY_AID_ONLY:
                raise ConsistencyError("recovery aid must not expose normal reads")
            if self.write_guarantee is not WriteGuarantee.RECOVERY_AID_NO_AUTHORITY:
                raise ConsistencyError("recovery aid must not claim write authority")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "domain_id": self.domain_id,
            "physical_store": self.physical_store,
            "authority": self.authority,
            "source_of_truth": self.source_of_truth,
            "read_guarantee": self.read_guarantee.value,
            "write_guarantee": self.write_guarantee.value,
            "stale_policy": self.stale_policy,
            "unknown_policy": self.unknown_policy,
            "source_refs": list(self.source_refs),
            "max_staleness_ms": self.max_staleness_ms,
        }

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ConsistencyProfile":
        return cls(
            domain_id=value["domain_id"],
            physical_store=value["physical_store"],
            authority=value["authority"],
            source_of_truth=value["source_of_truth"],
            read_guarantee=value["read_guarantee"],
            write_guarantee=value["write_guarantee"],
            stale_policy=value["stale_policy"],
            unknown_policy=value["unknown_policy"],
            source_refs=tuple(value.get("source_refs", ())),
            max_staleness_ms=value.get("max_staleness_ms"),
            schema_version=value.get("schema_version", 1),
        )


@dataclass(frozen=True, slots=True)
class ReadObservation:
    domain_id: str
    freshness: FreshnessState
    observed_version: str | None = None
    authoritative_version: str | None = None
    lag_ms: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "domain_id", _id(self.domain_id, "domain_id"))
        try:
            object.__setattr__(self, "freshness", FreshnessState(self.freshness))
        except ValueError as exc:
            raise ConsistencyError("unsupported freshness state") from exc
        if self.observed_version is not None:
            object.__setattr__(
                self,
                "observed_version",
                _id(self.observed_version, "observed_version"),
            )
        if self.authoritative_version is not None:
            object.__setattr__(
                self,
                "authoritative_version",
                _id(self.authoritative_version, "authoritative_version"),
            )
        if self.lag_ms is not None:
            object.__setattr__(self, "lag_ms", _nonnegative(self.lag_ms, "lag_ms"))
        if (
            self.freshness is FreshnessState.STALE
            and self.observed_version is not None
            and self.authoritative_version is not None
            and self.observed_version == self.authoritative_version
        ):
            raise ConsistencyError(
                "stale observation cannot claim authoritative version equality"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain_id": self.domain_id,
            "freshness": self.freshness.value,
            "observed_version": self.observed_version,
            "authoritative_version": self.authoritative_version,
            "lag_ms": self.lag_ms,
        }

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


@dataclass(frozen=True, slots=True)
class ConsistencyDecision:
    allowed: bool
    disposition: ReadDisposition
    explicit_freshness: FreshnessState
    reason: str
    profile_digest: str
    observation_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "disposition": self.disposition.value,
            "explicit_freshness": self.explicit_freshness.value,
            "reason": self.reason,
            "profile_digest": self.profile_digest,
            "observation_digest": self.observation_digest,
        }

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


def evaluate_read(
    profile: ConsistencyProfile,
    observation: ReadObservation,
    *,
    allow_stale: bool = False,
) -> ConsistencyDecision:
    if not isinstance(profile, ConsistencyProfile):
        raise TypeError("profile must be ConsistencyProfile")
    if not isinstance(observation, ReadObservation):
        raise TypeError("observation must be ReadObservation")
    if not isinstance(allow_stale, bool):
        raise ConsistencyError("allow_stale must be boolean")
    if observation.domain_id != profile.domain_id:
        raise ConsistencyError("read observation domain does not match profile")

    if observation.freshness is FreshnessState.UNKNOWN:
        return ConsistencyDecision(
            allowed=False,
            disposition=ReadDisposition.BLOCK_UNKNOWN,
            explicit_freshness=observation.freshness,
            reason="state freshness is unknown; fail closed instead of presenting a projection as current",
            profile_digest=profile.digest,
            observation_digest=observation.digest,
        )

    if profile.read_guarantee is ReadGuarantee.RECOVERY_AID_ONLY:
        return ConsistencyDecision(
            allowed=False,
            disposition=ReadDisposition.BLOCK_RECOVERY_AID,
            explicit_freshness=observation.freshness,
            reason="recovery-aid state is not a normal application read authority",
            profile_digest=profile.digest,
            observation_digest=observation.digest,
        )

    if observation.freshness is FreshnessState.FRESH:
        return ConsistencyDecision(
            allowed=True,
            disposition=ReadDisposition.SERVE_FRESH,
            explicit_freshness=observation.freshness,
            reason="freshness is explicit and compatible with the domain profile",
            profile_digest=profile.digest,
            observation_digest=observation.digest,
        )

    if profile.stale_policy == "reject" or not allow_stale:
        return ConsistencyDecision(
            allowed=False,
            disposition=ReadDisposition.BLOCK_STALE,
            explicit_freshness=observation.freshness,
            reason="stale state requires an explicit projection policy and caller opt-in",
            profile_digest=profile.digest,
            observation_digest=observation.digest,
        )

    if (
        profile.max_staleness_ms is not None
        and (
            observation.lag_ms is None
            or observation.lag_ms > profile.max_staleness_ms
        )
    ):
        return ConsistencyDecision(
            allowed=False,
            disposition=ReadDisposition.BLOCK_STALE,
            explicit_freshness=observation.freshness,
            reason="stale projection exceeds the declared staleness bound",
            profile_digest=profile.digest,
            observation_digest=observation.digest,
        )

    return ConsistencyDecision(
        allowed=True,
        disposition=ReadDisposition.SERVE_EXPLICIT_STALE,
        explicit_freshness=observation.freshness,
        reason="caller explicitly accepted stale projection semantics",
        profile_digest=profile.digest,
        observation_digest=observation.digest,
    )


def require_readable(
    profile: ConsistencyProfile,
    observation: ReadObservation,
    *,
    allow_stale: bool = False,
) -> ConsistencyDecision:
    decision = evaluate_read(profile, observation, allow_stale=allow_stale)
    if not decision.allowed:
        raise ConsistencyError(
            f"read blocked: {decision.disposition.value}: {decision.reason}"
        )
    return decision


__all__ = [
    "ConsistencyDecision",
    "ConsistencyError",
    "ConsistencyProfile",
    "FreshnessState",
    "ReadDisposition",
    "ReadGuarantee",
    "ReadObservation",
    "WriteGuarantee",
    "evaluate_read",
    "require_readable",
]
