"""Authenticated redundant snapshots for the native admission scheduler.

A majority of three or more distinct configured replicas must agree on the
same scheduler snapshot, term and parent revision. This code is deliberately
not a distributed consensus protocol: writers need an independent leader
lease, authoritative term floor and durable monotonic sequence high-watermark.

Recovery never guesses between split votes and never applies read-repair
automatically. An HMAC detects unauthenticated corruption only while the key
remains secret; it does not prove that a quorum's data is timely.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import hmac
import json
from typing import Mapping

from .admission_checkpoint import restore_admission_scheduler
from .admission_scheduler import AdmissionLimits, RuntimeAdmissionScheduler
from .flgb_model_runtime import ModelRuntimeError
from .runtime_policy import RuntimePolicy


SCHEMA = "skeleton.ai.admission-replica.v1"
MAX_REPLICA_BYTES = 16 * 1024 * 1024
MAX_REPLICA_COUNT = 7
_FIELDS = frozenset({
    "schema", "member_id", "leader_term", "sequence", "parent_digest",
    "snapshot_digest", "snapshot", "hmac_sha256",
})


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, OverflowError) as exc:
        raise ModelRuntimeError("invalid replica checkpoint encoding") from exc


def _key(value: bytes) -> bytes:
    if type(value) is not bytes or not 32 <= len(value) <= 4096:
        raise ModelRuntimeError("replica HMAC key must be 32-4096 bytes")
    return value


def _member(value: str) -> str:
    if (type(value) is not str or not 1 <= len(value) <= 64 or
            any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for ch in value)):
        raise ModelRuntimeError("invalid replica member identity")
    return value


def _integer(value: int, name: str) -> int:
    if type(value) is not int or not 0 <= value <= 2**63 - 1:
        raise ModelRuntimeError(f"invalid replica {name}")
    return value


def _hex(value: str, label: str) -> str:
    if (type(value) is not str or len(value) != 64 or
            any(ch not in "0123456789abcdef" for ch in value)):
        raise ModelRuntimeError(f"invalid replica {label}")
    return value


def _parent(value: str | None) -> str | None:
    return None if value is None else _hex(value, "parent digest")


def _digest(body: dict[str, object], key: bytes) -> str:
    return hmac.new(key, _canonical(body), hashlib.sha256).hexdigest()


def _parse_no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ModelRuntimeError("duplicate JSON key in replica checkpoint")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ModelRuntimeError("nonfinite JSON number in replica checkpoint")


def _seal(
    snapshot: dict[str, object], *, member_id: str, leader_term: int,
    parent_digest: str | None, secret_key: bytes,
) -> bytes:
    body = {
        "schema": SCHEMA,
        "member_id": _member(member_id),
        "leader_term": _integer(leader_term, "leadership term"),
        "sequence": _integer(snapshot["sequence"], "sequence"),
        "parent_digest": _parent(parent_digest),
        "snapshot_digest": _hex(snapshot["digest"], "snapshot digest"),
        "snapshot": snapshot,
    }
    result = _canonical({**body, "hmac_sha256": _digest(body, _key(secret_key))})
    if len(result) > MAX_REPLICA_BYTES:
        raise ModelRuntimeError("replica checkpoint exceeds byte limit")
    return result


def create_admission_replica(
    scheduler: RuntimeAdmissionScheduler, *, member_id: str,
    leader_term: int, secret_key: bytes, parent_digest: str | None = None,
) -> bytes:
    """Seal one live snapshot for a specific independent replica member.

    The caller must hold write authority for the supplied leadership term;
    generating an HMAC does not acquire a distributed lease.
    """
    if not isinstance(scheduler, RuntimeAdmissionScheduler):
        raise ModelRuntimeError("RuntimeAdmissionScheduler required")
    snapshot = scheduler.snapshot()
    restore_admission_scheduler(
        snapshot, expected_policy=scheduler.policy,
        expected_limits=scheduler.limits,
        minimum_sequence=snapshot["sequence"],
        expected_digest=snapshot["digest"],
    )
    return _seal(
        snapshot, member_id=member_id, leader_term=leader_term,
        parent_digest=parent_digest, secret_key=secret_key,
    )


@dataclass(frozen=True, slots=True)
class ValidatedAdmissionReplica:
    member_id: str
    leader_term: int
    sequence: int
    parent_digest: str | None
    snapshot_digest: str
    canonical_snapshot: bytes
    scheduler: RuntimeAdmissionScheduler

    @property
    def vote(self) -> tuple[int, int, str | None, str]:
        return (
            self.leader_term, self.sequence, self.parent_digest,
            self.snapshot_digest,
        )


def decode_admission_replica(
    blob: bytes, *, member_id: str, secret_key: bytes,
    minimum_term: int = 0, minimum_sequence: int = 0,
    expected_policy: RuntimePolicy | None = None,
    expected_limits: AdmissionLimits | None = None,
    expected_digest: str | None = None,
) -> ValidatedAdmissionReplica:
    """Verify the exact member binding, authenticated envelope and snapshot."""
    member_id = _member(member_id)
    secret_key = _key(secret_key)
    _integer(minimum_term, "minimum term")
    _integer(minimum_sequence, "minimum sequence")
    if type(blob) is not bytes or not 0 < len(blob) <= MAX_REPLICA_BYTES:
        raise ModelRuntimeError("invalid replica checkpoint byte size")
    try:
        raw = json.loads(
            blob.decode("utf-8", errors="strict"),
            object_pairs_hook=_parse_no_duplicates,
            parse_constant=_reject_constant,
        )
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise ModelRuntimeError("invalid replica checkpoint JSON") from exc
    if type(raw) is not dict or set(raw) != _FIELDS:
        raise ModelRuntimeError("invalid replica checkpoint schema fields")
    if raw["schema"] != SCHEMA or raw["member_id"] != member_id:
        raise ModelRuntimeError("wrong replica identity or schema")
    if blob != _canonical(raw):
        raise ModelRuntimeError("noncanonical replica checkpoint encoding")
    received_mac = _hex(raw["hmac_sha256"], "HMAC")
    unsigned = {key: val for key, val in raw.items() if key != "hmac_sha256"}
    if not hmac.compare_digest(received_mac, _digest(unsigned, secret_key)):
        raise ModelRuntimeError("replica authentication failed")
    term = _integer(raw["leader_term"], "leadership term")
    sequence = _integer(raw["sequence"], "sequence")
    parent_digest = _parent(raw["parent_digest"])
    digest = _hex(raw["snapshot_digest"], "snapshot digest")
    if term < minimum_term or sequence < minimum_sequence:
        raise ModelRuntimeError("replica below trusted monotonic recovery floor")
    if expected_digest is not None:
        pinned = _hex(expected_digest, "expected digest")
        if not hmac.compare_digest(pinned, digest):
            raise ModelRuntimeError("replica differs from trusted checkpoint digest")
    snapshot = raw["snapshot"]
    if type(snapshot) is not dict:
        raise ModelRuntimeError("replica snapshot must be a JSON object")
    if type(snapshot.get("sequence")) is not int or snapshot["sequence"] != sequence:
        raise ModelRuntimeError("replica envelope/snapshot sequence mismatch")
    if type(snapshot.get("digest")) is not str or snapshot["digest"] != digest:
        raise ModelRuntimeError("replica envelope/snapshot digest mismatch")
    scheduler = restore_admission_scheduler(
        snapshot,
        expected_policy=expected_policy,
        expected_limits=expected_limits,
        minimum_sequence=minimum_sequence,
        expected_digest=digest,
    )
    return ValidatedAdmissionReplica(
        member_id, term, sequence, parent_digest, digest,
        _canonical(snapshot), scheduler,
    )


@dataclass(frozen=True, slots=True)
class QuorumAdmissionRecovery:
    scheduler: RuntimeAdmissionScheduler
    leader_term: int
    sequence: int
    parent_digest: str | None
    snapshot_digest: str
    supporters: tuple[str, ...]
    repair_targets: tuple[str, ...]
    invalid_members: tuple[str, ...]
    missing_members: tuple[str, ...]
    canonical_snapshot: bytes

    def rebuild_replica(self, member_id: str, *, secret_key: bytes) -> bytes:
        """Construct a proposal for repair; persistence needs leader fencing."""
        if member_id not in self.repair_targets:
            raise ModelRuntimeError("replica is not eligible for read repair")
        # Use the immutable snapshot captured at recovery, not a possibly
        # mutated scheduler reference, when constructing repair evidence.
        snapshot = json.loads(self.canonical_snapshot)
        return _seal(
            snapshot, member_id=member_id, leader_term=self.leader_term,
            parent_digest=self.parent_digest, secret_key=secret_key,
        )


def recover_admission_quorum(
    replicas: Mapping[str, bytes | None], *, members: tuple[str, ...],
    secret_key: bytes, minimum_term: int, minimum_sequence: int,
    expected_policy: RuntimePolicy | None = None,
    expected_limits: AdmissionLimits | None = None,
    expected_digest: str | None = None,
) -> QuorumAdmissionRecovery:
    """Recover only the highest authenticated checkpoint with member quorum.

    'members' is an independently configured physical member set, never taken
    from envelopes supplied by replicas. A compromised/stale minority has no
    vote. A stale majority still needs externally enforced term/sequence floors.
    """
    secret_key = _key(secret_key)
    _integer(minimum_term, "minimum term")
    _integer(minimum_sequence, "minimum sequence")
    if (type(members) is not tuple or len(members) not in (3, 5, 7) or
            len(set(members)) != len(members)):
        raise ModelRuntimeError("replica membership must be three, five or seven unique members")
    for member_id in members:
        _member(member_id)
    if not isinstance(replicas, Mapping) or not set(replicas).issubset(members):
        raise ModelRuntimeError("unknown or invalid replica input member")
    if expected_digest is not None:
        _hex(expected_digest, "expected digest")
    by_vote: dict[tuple[int, int, str | None, str], list[ValidatedAdmissionReplica]] = defaultdict(list)
    invalid: list[str] = []
    missing: list[str] = []
    for member_id in members:
        payload = replicas.get(member_id)
        if payload is None:
            missing.append(member_id)
            continue
        try:
            validated = decode_admission_replica(
                payload, member_id=member_id, secret_key=secret_key,
                minimum_term=minimum_term, minimum_sequence=minimum_sequence,
                expected_policy=expected_policy,
                expected_limits=expected_limits, expected_digest=expected_digest,
            )
        except (ModelRuntimeError, ValueError, TypeError, OverflowError):
            invalid.append(member_id)
            continue
        by_vote[validated.vote].append(validated)
    quorum = len(members) // 2 + 1
    eligible = [v for v in by_vote.values() if len(v) >= quorum]
    if not eligible:
        raise ModelRuntimeError("replica quorum unavailable or split-brain checkpoint")
    eligible.sort(key=lambda row: (row[0].leader_term, row[0].sequence), reverse=True)
    cohort = eligible[0]
    first = cohort[0]
    supporters = tuple(sorted(replica.member_id for replica in cohort))
    targets = tuple(member_id for member_id in members if member_id not in supporters)
    return QuorumAdmissionRecovery(
        first.scheduler, first.leader_term, first.sequence,
        first.parent_digest, first.snapshot_digest, supporters,
        targets, tuple(sorted(invalid)), tuple(sorted(missing)),
        first.canonical_snapshot,
    )


__all__ = [
    "SCHEMA", "MAX_REPLICA_BYTES", "MAX_REPLICA_COUNT",
    "ValidatedAdmissionReplica", "QuorumAdmissionRecovery",
    "create_admission_replica", "decode_admission_replica",
    "recover_admission_quorum",
]
