"""Deterministic scoped work leases for parallel creator agents (#807 B013).

This module is data-only. It never reads the wall clock, touches the filesystem,
starts work, or grants execution authority. Callers provide monotonic logical
time and persist returned immutable state through their existing authority
boundary.

Lease state is content-addressed and bound to the B001 batch-plan digest.
Batch claims conflict on identity. Path claims conflict on exact, ancestor, or
descendant overlap. Expired leases are swept before new claims are evaluated.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Final, NoReturn

from skeleton.kernel.errors import SkeletonError
from skeleton.repo_intelligence.batch_plan import BatchPlan, load_plan


WORK_LEASE_SCHEMA: Final = "creator.work_leases.v1"
WORK_LEASE_VERSION: Final = 1
MAX_LEASES: Final = 4_096
MAX_BATCHES_PER_LEASE: Final = 32
MAX_PATHS_PER_LEASE: Final = 256
MAX_OWNER_CHARS: Final = 96
MAX_LEASE_ID_CHARS: Final = 96
MAX_PATH_CHARS: Final = 512
MAX_TTL_SECONDS: Final = 7 * 24 * 60 * 60
MAX_STATE_BYTES: Final = 4 * 1024 * 1024

_TOKEN_RE: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,95}$")
_BATCH_RE: Final = re.compile(r"^B[0-9]{3}$")
_HEX64_RE: Final = re.compile(r"^[0-9a-f]{64}$")


class WorkLeaseError(SkeletonError):
    """Malformed state, unauthorized mutation, or overlapping work claim."""

    code = "CRE.WORK_LEASE"
    http_status = 409


class WorkLeaseVersionError(WorkLeaseError):
    """Unsupported persisted lease schema/version."""

    code = "CRE.WORK_LEASE_VERSION"
    http_status = 422


@dataclass(frozen=True, slots=True)
class LeaseScope:
    batch_ids: tuple[str, ...]
    paths: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {"batch_ids": list(self.batch_ids), "paths": list(self.paths)}


@dataclass(frozen=True, slots=True)
class WorkLease:
    lease_id: str
    owner_id: str
    scope: LeaseScope
    issued_at: int
    expires_at: int
    revision: int
    plan_digest: str
    digest: str

    def as_dict(self) -> dict[str, object]:
        return {
            "lease_id": self.lease_id,
            "owner_id": self.owner_id,
            "scope": self.scope.as_dict(),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "revision": self.revision,
            "plan_digest": self.plan_digest,
            "digest": self.digest,
        }


@dataclass(frozen=True, slots=True)
class LeaseConflict:
    lease_id: str
    owner_id: str
    batch_ids: tuple[str, ...]
    paths: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "lease_id": self.lease_id,
            "owner_id": self.owner_id,
            "batch_ids": list(self.batch_ids),
            "paths": list(self.paths),
        }


@dataclass(frozen=True, slots=True)
class LeaseState:
    schema: str
    schema_version: int
    plan_digest: str
    logical_time: int
    leases: tuple[WorkLease, ...]
    digest: str

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "plan_digest": self.plan_digest,
            "logical_time": self.logical_time,
            "leases": [lease.as_dict() for lease in self.leases],
            "digest": self.digest,
        }


@dataclass(frozen=True, slots=True)
class LeaseSweep:
    state: LeaseState
    expired_lease_ids: tuple[str, ...]


def _fail(message: str, *, reason: str, **context: object) -> NoReturn:
    raise WorkLeaseError(message, context={"reason": reason, **context})


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _strict_int(name: str, value: object, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{name} must be an integer", reason="malformed", field=name)
    if not minimum <= value <= maximum:
        _fail(
            f"{name} is outside the accepted range",
            reason="bound",
            field=name,
            minimum=minimum,
            maximum=maximum,
        )
    return value


def _token(name: str, value: object, *, maximum: int) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        _fail(f"{name} must be non-empty canonical text", reason="malformed", field=name)
    if len(value) > maximum or _TOKEN_RE.fullmatch(value) is None:
        _fail(f"{name} is not a canonical token", reason="malformed", field=name)
    return value


def _hex_digest(name: str, value: object) -> str:
    if not isinstance(value, str) or _HEX64_RE.fullmatch(value) is None:
        _fail(f"{name} must be a lowercase sha256 digest", reason="malformed", field=name)
    return value


def _plan(plan: BatchPlan | None) -> BatchPlan:
    resolved = load_plan() if plan is None else plan
    if not isinstance(resolved, BatchPlan):
        _fail("plan must be a BatchPlan", reason="malformed", field="plan")
    _hex_digest("plan.digest", resolved.digest)
    return resolved


def _batch_ids(plan: BatchPlan, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        _fail("batch_ids must be an iterable of ids", reason="malformed", field="batch_ids")
    result: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values, start=1):
        if index > MAX_BATCHES_PER_LEASE:
            _fail(
                "batch_ids exceeds per-lease bound",
                reason="bound",
                maximum=MAX_BATCHES_PER_LEASE,
            )
        if not isinstance(value, str) or _BATCH_RE.fullmatch(value) is None:
            _fail("batch_ids contains an invalid id", reason="malformed", field="batch_ids")
        if value not in plan.by_id:
            _fail("batch_ids contains an unknown batch", reason="unknown_batch", batch_id=value)
        if value in seen:
            _fail("batch_ids contains a duplicate", reason="duplicate", batch_id=value)
        seen.add(value)
        result.append(value)
    return tuple(sorted(result))


def _path(value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        _fail("path must be non-empty canonical text", reason="malformed", field="path")
    if len(value) > MAX_PATH_CHARS:
        _fail("path exceeds its character bound", reason="bound", field="path")
    if "\\" in value or "\x00" in value or any(ord(ch) < 32 for ch in value):
        _fail("path contains forbidden characters", reason="malformed", field="path")
    if value.startswith("/") or value.endswith("/") or "//" in value:
        _fail("path must be repository-relative POSIX form", reason="malformed", field="path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        _fail("path contains an unsafe segment", reason="malformed", field="path")
    if ":" in parts[0]:
        _fail("path must not contain a drive prefix", reason="malformed", field="path")
    return value


def _paths_overlap(left: str, right: str) -> bool:
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def _paths(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        _fail("paths must be an iterable of repository paths", reason="malformed", field="paths")
    result: list[str] = []
    seen: set[str] = set()
    for index, raw in enumerate(values, start=1):
        if index > MAX_PATHS_PER_LEASE:
            _fail(
                "paths exceeds per-lease bound",
                reason="bound",
                maximum=MAX_PATHS_PER_LEASE,
            )
        path = _path(raw)
        if path in seen:
            _fail("paths contains a duplicate", reason="duplicate", path=path)
        seen.add(path)
        result.append(path)
    result.sort()
    for index, left in enumerate(result):
        for right in result[index + 1 :]:
            if _paths_overlap(left, right):
                _fail(
                    "one lease scope contains redundant overlapping paths",
                    reason="self_overlap",
                    path_a=left,
                    path_b=right,
                )
    return tuple(result)


def _scope(plan: BatchPlan, batch_ids: Iterable[str], paths: Iterable[str]) -> LeaseScope:
    scope = LeaseScope(batch_ids=_batch_ids(plan, batch_ids), paths=_paths(paths))
    if not scope.batch_ids and not scope.paths:
        _fail("lease scope must claim at least one batch or path", reason="empty_scope")
    return scope


def _lease_payload(
    *,
    lease_id: str,
    owner_id: str,
    scope: LeaseScope,
    issued_at: int,
    expires_at: int,
    revision: int,
    plan_digest: str,
) -> dict[str, object]:
    return {
        "lease_id": lease_id,
        "owner_id": owner_id,
        "scope": scope.as_dict(),
        "issued_at": issued_at,
        "expires_at": expires_at,
        "revision": revision,
        "plan_digest": plan_digest,
    }


def _make_lease(
    *,
    lease_id: str,
    owner_id: str,
    scope: LeaseScope,
    issued_at: int,
    expires_at: int,
    revision: int,
    plan_digest: str,
) -> WorkLease:
    payload = _lease_payload(
        lease_id=lease_id,
        owner_id=owner_id,
        scope=scope,
        issued_at=issued_at,
        expires_at=expires_at,
        revision=revision,
        plan_digest=plan_digest,
    )
    return WorkLease(
        lease_id=lease_id,
        owner_id=owner_id,
        scope=scope,
        issued_at=issued_at,
        expires_at=expires_at,
        revision=revision,
        plan_digest=plan_digest,
        digest=_digest(payload),
    )


def _state_payload(
    *,
    plan_digest: str,
    logical_time: int,
    leases: tuple[WorkLease, ...],
) -> dict[str, object]:
    return {
        "schema": WORK_LEASE_SCHEMA,
        "schema_version": WORK_LEASE_VERSION,
        "plan_digest": plan_digest,
        "logical_time": logical_time,
        "leases": [lease.as_dict() for lease in leases],
    }


def _make_state(
    *,
    plan_digest: str,
    logical_time: int,
    leases: Iterable[WorkLease],
) -> LeaseState:
    ordered = tuple(sorted(leases, key=lambda item: item.lease_id))
    if len(ordered) > MAX_LEASES:
        _fail("lease state exceeds lease bound", reason="bound", maximum=MAX_LEASES)
    payload = _state_payload(
        plan_digest=plan_digest,
        logical_time=logical_time,
        leases=ordered,
    )
    return LeaseState(
        schema=WORK_LEASE_SCHEMA,
        schema_version=WORK_LEASE_VERSION,
        plan_digest=plan_digest,
        logical_time=logical_time,
        leases=ordered,
        digest=_digest(payload),
    )


def _verify_lease(lease: WorkLease, *, plan: BatchPlan) -> None:
    if not isinstance(lease, WorkLease):
        _fail("state contains a non-lease value", reason="malformed")
    lease_id = _token("lease_id", lease.lease_id, maximum=MAX_LEASE_ID_CHARS)
    owner_id = _token("owner_id", lease.owner_id, maximum=MAX_OWNER_CHARS)
    if lease.plan_digest != plan.digest:
        _fail("lease is bound to a different batch plan", reason="plan_drift", lease_id=lease_id)
    scope = _scope(plan, lease.scope.batch_ids, lease.scope.paths)
    if scope != lease.scope:
        _fail("lease scope is not canonical", reason="canonicalization", lease_id=lease_id)
    issued = _strict_int("issued_at", lease.issued_at, minimum=0, maximum=2**63 - 1)
    expires = _strict_int("expires_at", lease.expires_at, minimum=0, maximum=2**63 - 1)
    revision = _strict_int("revision", lease.revision, minimum=1, maximum=2**31 - 1)
    if expires <= issued:
        _fail("lease expiry must be after issuance", reason="malformed", lease_id=lease_id)
    expected = _make_lease(
        lease_id=lease_id,
        owner_id=owner_id,
        scope=scope,
        issued_at=issued,
        expires_at=expires,
        revision=revision,
        plan_digest=plan.digest,
    )
    if lease.digest != expected.digest:
        _fail("lease digest mismatch", reason="digest_mismatch", lease_id=lease_id)


def _verify_state(
    state: LeaseState,
    *,
    plan: BatchPlan,
    expected_state_digest: str | None = None,
) -> None:
    if not isinstance(state, LeaseState):
        _fail("state must be LeaseState", reason="malformed", field="state")
    if state.schema != WORK_LEASE_SCHEMA or state.schema_version != WORK_LEASE_VERSION:
        raise WorkLeaseVersionError(
            "unsupported work-lease state version",
            context={
                "expected_schema": WORK_LEASE_SCHEMA,
                "expected_version": WORK_LEASE_VERSION,
            },
        )
    if state.plan_digest != plan.digest:
        _fail("lease state is bound to a different batch plan", reason="plan_drift")
    logical_time = _strict_int(
        "logical_time", state.logical_time, minimum=0, maximum=2**63 - 1
    )
    if len(state.leases) > MAX_LEASES:
        _fail("lease state exceeds lease bound", reason="bound", maximum=MAX_LEASES)
    ids: set[str] = set()
    for lease in state.leases:
        _verify_lease(lease, plan=plan)
        if lease.lease_id in ids:
            _fail("lease state contains duplicate ids", reason="duplicate", lease_id=lease.lease_id)
        ids.add(lease.lease_id)
    if tuple(sorted(state.leases, key=lambda item: item.lease_id)) != state.leases:
        _fail("lease state ordering is not canonical", reason="canonicalization")
    expected = _make_state(
        plan_digest=plan.digest,
        logical_time=logical_time,
        leases=state.leases,
    )
    if state.digest != expected.digest:
        _fail("lease state digest mismatch", reason="digest_mismatch")
    if expected_state_digest is not None:
        expected_digest = _hex_digest("expected_state_digest", expected_state_digest)
        if state.digest != expected_digest:
            _fail(
                "lease state changed since caller snapshot",
                reason="concurrent_update",
                expected=expected_digest,
                actual=state.digest,
            )


def empty_lease_state(
    *,
    plan: BatchPlan | None = None,
    logical_time: int = 0,
) -> LeaseState:
    """Create empty digest-bound state for one batch-plan version."""
    resolved = _plan(plan)
    now = _strict_int("logical_time", logical_time, minimum=0, maximum=2**63 - 1)
    return _make_state(plan_digest=resolved.digest, logical_time=now, leases=())


def sweep_expired_leases(
    state: LeaseState,
    *,
    now: int,
    plan: BatchPlan | None = None,
    expected_state_digest: str | None = None,
) -> LeaseSweep:
    """Advance logical time and remove leases expired at or before now."""
    resolved = _plan(plan)
    _verify_state(state, plan=resolved, expected_state_digest=expected_state_digest)
    current = _strict_int("now", now, minimum=0, maximum=2**63 - 1)
    if current < state.logical_time:
        _fail(
            "logical time cannot move backwards",
            reason="time_regression",
            previous=state.logical_time,
            requested=current,
        )
    expired = tuple(
        lease.lease_id for lease in state.leases if lease.expires_at <= current
    )
    active = tuple(
        lease for lease in state.leases if lease.expires_at > current
    )
    return LeaseSweep(
        state=_make_state(
            plan_digest=resolved.digest,
            logical_time=current,
            leases=active,
        ),
        expired_lease_ids=expired,
    )


def conflicts_for_scope(
    state: LeaseState,
    *,
    batch_ids: Iterable[str] = (),
    paths: Iterable[str] = (),
    now: int,
    plan: BatchPlan | None = None,
) -> tuple[LeaseConflict, ...]:
    """Return active conflicts without mutating the supplied state."""
    resolved = _plan(plan)
    _verify_state(state, plan=resolved)
    scope = _scope(resolved, batch_ids, paths)
    sweep = sweep_expired_leases(state, now=now, plan=resolved)
    requested_batches = set(scope.batch_ids)
    conflicts: list[LeaseConflict] = []
    for lease in sweep.state.leases:
        batch_conflicts = tuple(
            sorted(requested_batches.intersection(lease.scope.batch_ids))
        )
        path_conflicts = tuple(
            sorted(
                {
                    requested
                    for requested in scope.paths
                    for claimed in lease.scope.paths
                    if _paths_overlap(requested, claimed)
                }
            )
        )
        if batch_conflicts or path_conflicts:
            conflicts.append(
                LeaseConflict(
                    lease_id=lease.lease_id,
                    owner_id=lease.owner_id,
                    batch_ids=batch_conflicts,
                    paths=path_conflicts,
                )
            )
    return tuple(conflicts)


def claim_work(
    state: LeaseState,
    *,
    lease_id: str,
    owner_id: str,
    batch_ids: Iterable[str] = (),
    paths: Iterable[str] = (),
    now: int,
    ttl_seconds: int,
    plan: BatchPlan | None = None,
    expected_state_digest: str | None = None,
) -> tuple[LeaseState, WorkLease]:
    """Claim a non-overlapping batch/file scope."""
    resolved = _plan(plan)
    _verify_state(state, plan=resolved, expected_state_digest=expected_state_digest)
    canonical_id = _token("lease_id", lease_id, maximum=MAX_LEASE_ID_CHARS)
    canonical_owner = _token("owner_id", owner_id, maximum=MAX_OWNER_CHARS)
    current = _strict_int("now", now, minimum=0, maximum=2**63 - 1)
    ttl = _strict_int("ttl_seconds", ttl_seconds, minimum=1, maximum=MAX_TTL_SECONDS)
    scope = _scope(resolved, batch_ids, paths)
    sweep = sweep_expired_leases(state, now=current, plan=resolved)
    if any(lease.lease_id == canonical_id for lease in sweep.state.leases):
        _fail("lease_id is already active", reason="duplicate_lease_id", lease_id=canonical_id)
    conflicts = conflicts_for_scope(
        sweep.state,
        batch_ids=scope.batch_ids,
        paths=scope.paths,
        now=current,
        plan=resolved,
    )
    if conflicts:
        _fail(
            "work scope overlaps active lease",
            reason="scope_conflict",
            lease_id=canonical_id,
            conflicts=[conflict.as_dict() for conflict in conflicts],
        )
    if len(sweep.state.leases) >= MAX_LEASES:
        _fail("lease state is full", reason="bound", maximum=MAX_LEASES)
    if current > 2**63 - 1 - ttl:
        _fail("lease expiry would overflow logical time", reason="bound")
    lease = _make_lease(
        lease_id=canonical_id,
        owner_id=canonical_owner,
        scope=scope,
        issued_at=current,
        expires_at=current + ttl,
        revision=1,
        plan_digest=resolved.digest,
    )
    return (
        _make_state(
            plan_digest=resolved.digest,
            logical_time=current,
            leases=(*sweep.state.leases, lease),
        ),
        lease,
    )


def renew_lease(
    state: LeaseState,
    *,
    lease_id: str,
    owner_id: str,
    now: int,
    ttl_seconds: int,
    expected_revision: int,
    plan: BatchPlan | None = None,
    expected_state_digest: str | None = None,
) -> tuple[LeaseState, WorkLease]:
    """Renew one live lease with owner/revision/state compare-and-swap guards."""
    resolved = _plan(plan)
    _verify_state(state, plan=resolved, expected_state_digest=expected_state_digest)
    canonical_id = _token("lease_id", lease_id, maximum=MAX_LEASE_ID_CHARS)
    canonical_owner = _token("owner_id", owner_id, maximum=MAX_OWNER_CHARS)
    current = _strict_int("now", now, minimum=0, maximum=2**63 - 1)
    ttl = _strict_int("ttl_seconds", ttl_seconds, minimum=1, maximum=MAX_TTL_SECONDS)
    revision = _strict_int(
        "expected_revision", expected_revision, minimum=1, maximum=2**31 - 1
    )
    sweep = sweep_expired_leases(state, now=current, plan=resolved)
    target = next(
        (lease for lease in sweep.state.leases if lease.lease_id == canonical_id),
        None,
    )
    if target is None:
        _fail("lease is missing or expired", reason="lease_unavailable", lease_id=canonical_id)
    if target.owner_id != canonical_owner:
        _fail("lease owner mismatch", reason="owner_mismatch", lease_id=canonical_id)
    if target.revision != revision:
        _fail(
            "lease revision changed",
            reason="revision_mismatch",
            lease_id=canonical_id,
            expected=revision,
            actual=target.revision,
        )
    if target.revision == 2**31 - 1 or current > 2**63 - 1 - ttl:
        _fail("lease renewal exceeds numeric bounds", reason="bound")
    renewed = _make_lease(
        lease_id=target.lease_id,
        owner_id=target.owner_id,
        scope=target.scope,
        issued_at=target.issued_at,
        expires_at=current + ttl,
        revision=target.revision + 1,
        plan_digest=resolved.digest,
    )
    leases = tuple(
        renewed if lease.lease_id == canonical_id else lease
        for lease in sweep.state.leases
    )
    return (
        _make_state(
            plan_digest=resolved.digest,
            logical_time=current,
            leases=leases,
        ),
        renewed,
    )


def release_lease(
    state: LeaseState,
    *,
    lease_id: str,
    owner_id: str,
    now: int,
    expected_revision: int,
    plan: BatchPlan | None = None,
    expected_state_digest: str | None = None,
) -> LeaseState:
    """Release one live lease with owner/revision/state guards."""
    resolved = _plan(plan)
    _verify_state(state, plan=resolved, expected_state_digest=expected_state_digest)
    canonical_id = _token("lease_id", lease_id, maximum=MAX_LEASE_ID_CHARS)
    canonical_owner = _token("owner_id", owner_id, maximum=MAX_OWNER_CHARS)
    current = _strict_int("now", now, minimum=0, maximum=2**63 - 1)
    revision = _strict_int(
        "expected_revision", expected_revision, minimum=1, maximum=2**31 - 1
    )
    sweep = sweep_expired_leases(state, now=current, plan=resolved)
    target = next(
        (lease for lease in sweep.state.leases if lease.lease_id == canonical_id),
        None,
    )
    if target is None:
        _fail("lease is missing or expired", reason="lease_unavailable", lease_id=canonical_id)
    if target.owner_id != canonical_owner:
        _fail("lease owner mismatch", reason="owner_mismatch", lease_id=canonical_id)
    if target.revision != revision:
        _fail(
            "lease revision changed",
            reason="revision_mismatch",
            lease_id=canonical_id,
            expected=revision,
            actual=target.revision,
        )
    return _make_state(
        plan_digest=resolved.digest,
        logical_time=current,
        leases=(
            lease for lease in sweep.state.leases if lease.lease_id != canonical_id
        ),
    )


def serialize_lease_state(
    state: LeaseState,
    *,
    plan: BatchPlan | None = None,
) -> bytes:
    """Serialize verified state as canonical JSON."""
    resolved = _plan(plan)
    _verify_state(state, plan=resolved)
    raw = _canonical_json(state.as_dict())
    if len(raw) > MAX_STATE_BYTES:
        _fail("serialized lease state exceeds byte bound", reason="bound")
    return raw


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate JSON field", reason="duplicate_field", field=key)
        result[key] = value
    return result


def parse_lease_state(
    raw: bytes | str,
    *,
    plan: BatchPlan | None = None,
) -> LeaseState:
    """Parse and digest-verify persisted lease state."""
    resolved = _plan(plan)
    if isinstance(raw, str):
        encoded = raw.encode("utf-8")
    elif isinstance(raw, bytes):
        encoded = raw
    else:
        _fail("lease state must be bytes or text", reason="malformed", field="raw")
    if not encoded or len(encoded) > MAX_STATE_BYTES:
        _fail("serialized lease state size is invalid", reason="bound")
    try:
        payload = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=_unique_object,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise WorkLeaseError(
            "lease state is not valid JSON",
            context={"reason": "malformed_json"},
            cause=exc,
        ) from exc
    if not isinstance(payload, Mapping):
        _fail("lease state root must be an object", reason="malformed")
    expected_root = {
        "schema",
        "schema_version",
        "plan_digest",
        "logical_time",
        "leases",
        "digest",
    }
    if set(payload) != expected_root:
        _fail("lease state root field set is invalid", reason="field_set")
    if (
        payload["schema"] != WORK_LEASE_SCHEMA
        or payload["schema_version"] != WORK_LEASE_VERSION
    ):
        raise WorkLeaseVersionError(
            "unsupported work-lease state version",
            context={
                "schema": payload.get("schema"),
                "schema_version": payload.get("schema_version"),
            },
        )
    plan_digest = _hex_digest("plan_digest", payload["plan_digest"])
    if plan_digest != resolved.digest:
        _fail("lease state is bound to a different batch plan", reason="plan_drift")
    logical_time = _strict_int(
        "logical_time", payload["logical_time"], minimum=0, maximum=2**63 - 1
    )
    raw_leases = payload["leases"]
    if (
        not isinstance(raw_leases, Sequence)
        or isinstance(raw_leases, (str, bytes, bytearray))
    ):
        _fail("leases must be a list", reason="malformed", field="leases")
    if len(raw_leases) > MAX_LEASES:
        _fail("lease state exceeds lease bound", reason="bound", maximum=MAX_LEASES)

    expected_lease_keys = {
        "lease_id",
        "owner_id",
        "scope",
        "issued_at",
        "expires_at",
        "revision",
        "plan_digest",
        "digest",
    }
    leases: list[WorkLease] = []
    for index, item in enumerate(raw_leases):
        if not isinstance(item, Mapping) or set(item) != expected_lease_keys:
            _fail("lease field set is invalid", reason="field_set", lease_index=index)
        scope_payload = item["scope"]
        if (
            not isinstance(scope_payload, Mapping)
            or set(scope_payload) != {"batch_ids", "paths"}
        ):
            _fail("lease scope field set is invalid", reason="field_set", lease_index=index)
        scope = _scope(
            resolved,
            scope_payload["batch_ids"],
            scope_payload["paths"],
        )
        leases.append(
            WorkLease(
                lease_id=_token(
                    "lease_id", item["lease_id"], maximum=MAX_LEASE_ID_CHARS
                ),
                owner_id=_token(
                    "owner_id", item["owner_id"], maximum=MAX_OWNER_CHARS
                ),
                scope=scope,
                issued_at=_strict_int(
                    "issued_at", item["issued_at"], minimum=0, maximum=2**63 - 1
                ),
                expires_at=_strict_int(
                    "expires_at", item["expires_at"], minimum=0, maximum=2**63 - 1
                ),
                revision=_strict_int(
                    "revision", item["revision"], minimum=1, maximum=2**31 - 1
                ),
                plan_digest=_hex_digest(
                    "lease.plan_digest", item["plan_digest"]
                ),
                digest=_hex_digest("lease.digest", item["digest"]),
            )
        )

    state = LeaseState(
        schema=WORK_LEASE_SCHEMA,
        schema_version=WORK_LEASE_VERSION,
        plan_digest=plan_digest,
        logical_time=logical_time,
        leases=tuple(leases),
        digest=_hex_digest("digest", payload["digest"]),
    )
    _verify_state(state, plan=resolved)
    return state


__all__ = [
    "LeaseConflict",
    "LeaseScope",
    "LeaseState",
    "LeaseSweep",
    "MAX_BATCHES_PER_LEASE",
    "MAX_LEASES",
    "MAX_PATHS_PER_LEASE",
    "MAX_TTL_SECONDS",
    "WORK_LEASE_SCHEMA",
    "WORK_LEASE_VERSION",
    "WorkLease",
    "WorkLeaseError",
    "WorkLeaseVersionError",
    "claim_work",
    "conflicts_for_scope",
    "empty_lease_state",
    "parse_lease_state",
    "release_lease",
    "renew_lease",
    "serialize_lease_state",
    "sweep_expired_leases",
]
