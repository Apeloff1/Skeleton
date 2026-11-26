"""Bounded observation, action, and camera history.

Live observations stay within a caller-supplied capacity. Eviction removes the
oldest observation from that window and keeps a content-addressed summary so a
later revisit can still be compared. The same append sequence always yields the
same summary digest.

This package does not render frames, load weights, call a model, or open a
second memory owner. Observation identity is a digest already stored on an
existing field (frame receipt, chunk, cursor, pixel capture, world-model
evidence, or memory reconciliation payload).
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Any

# Digest fields that already exist on frame and memory records. Values are
# copied from those fields; this module does not mint a parallel receipt.
EXISTING_DIGEST_FIELDS = frozenset({
    "receipt_digest",          # FrameReceipt.receipt_digest
    "content_digest",          # FrameChunk.content_digest
    "cursor_digest",           # FrameContextCursor.cursor_digest
    "pixel_sha256",            # viewport capture row pixel_sha256
    "source_digest",           # FrameObject / VisualFrame / WorldModelEvidence
    "reconstruction_digest",   # WorldModelEvidence.reconstruction_digest
    "payload_digest",          # memory reconciliation candidate payload_digest
})

GENESIS = "0" * 64
SCHEMA = "skeleton.frontier_temporal.world_memory.v1"
_MAX_CAPACITY = 4096
_MAX_FRAME = 10_000_000
_MAX_ABS = 1e8


class TemporalMemoryError(ValueError):
    """A temporal record, evaluator input, or frame decision violated its contract."""


def _digest(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, OverflowError) as exc:
        raise TemporalMemoryError("temporal content must be canonical finite JSON") from exc
    return sha256(encoded).hexdigest()


def _sha256_hex(value: object, label: str) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise TemporalMemoryError(f"{label} must be lowercase sha256")
    return value


def _finite(value: object, label: str, *, limit: float = _MAX_ABS) -> float:
    if isinstance(value, bool) or type(value) not in (int, float):
        raise TemporalMemoryError(f"{label} must be a finite number")
    number = float(value)
    if not math.isfinite(number) or abs(number) > limit:
        raise TemporalMemoryError(f"{label} is non-finite or out of bounds")
    return number


def _wrap_pi(delta: float) -> float:
    return (delta + math.pi) % (2.0 * math.pi) - math.pi


def read_existing_digest(source: object, field: str) -> str:
    """Return a digest already stored on ``source``.

    The field must be one of the existing receipt, chunk, cursor, pixel,
    world-model, or memory payload digests. Nothing is rendered and no new
    receipt is hashed from pixels or geometry.
    """
    if field not in EXISTING_DIGEST_FIELDS:
        known = ", ".join(sorted(EXISTING_DIGEST_FIELDS))
        raise TemporalMemoryError(f"observation digest must reference an existing field: {known}")
    if isinstance(source, Mapping):
        if field not in source:
            raise TemporalMemoryError(f"source has no {field}")
        value = source[field]
    else:
        if not hasattr(source, field):
            raise TemporalMemoryError(f"source has no {field}")
        value = getattr(source, field)
    return _sha256_hex(value, field)


def _freeze_action(value: object, depth: int = 0) -> tuple:
    if depth > 4:
        raise TemporalMemoryError("action nesting exceeds 4")
    if isinstance(value, (list, tuple)):
        if len(value) > 32:
            raise TemporalMemoryError("action width exceeds 32")
        return tuple(_freeze_action(item, depth + 1) for item in value)
    if value is None:
        return None  # type: ignore[return-value]
    if type(value) is bool or type(value) is int:
        if type(value) is int and not -10**12 <= value <= 10**12:
            raise TemporalMemoryError("action integer out of bounds")
        return value  # type: ignore[return-value]
    if type(value) is float:
        return _finite(value, "action float")  # type: ignore[return-value]
    if type(value) is str:
        if not 1 <= len(value) <= 128:
            raise TemporalMemoryError("action string must be 1..128 characters")
        return value  # type: ignore[return-value]
    raise TemporalMemoryError("action must be a bounded JSON-compatible tuple")


def _action_json(value: object) -> object:
    if isinstance(value, tuple):
        return [_action_json(item) for item in value]
    return value


@dataclass(frozen=True)
class CameraPose:
    """Camera position and orientation supplied by the caller.

    Angles are radians. This is the pose stored beside an observation digest;
    it is not a rendered camera and it does not sample a framebuffer.
    """

    x: float
    y: float
    z: float
    yaw_rad: float
    pitch_rad: float
    roll_rad: float = 0.0

    def __post_init__(self) -> None:
        for name in ("x", "y", "z", "yaw_rad", "pitch_rad", "roll_rad"):
            object.__setattr__(self, name, _finite(getattr(self, name), name, limit=1e6))

    def components(self) -> list[float]:
        return [self.x, self.y, self.z, self.yaw_rad, self.pitch_rad, self.roll_rad]


def pose_distance(left: CameraPose, right: CameraPose) -> float:
    """Euclidean distance of position and wrapped yaw, pitch, and roll."""
    return math.sqrt(
        (left.x - right.x) ** 2
        + (left.y - right.y) ** 2
        + (left.z - right.z) ** 2
        + _wrap_pi(left.yaw_rad - right.yaw_rad) ** 2
        + _wrap_pi(left.pitch_rad - right.pitch_rad) ** 2
        + _wrap_pi(left.roll_rad - right.roll_rad) ** 2
    )


@dataclass(frozen=True)
class TemporalRecord:
    """One captured observation digest, the action that led there, and the camera pose."""

    frame_index: int
    observation_digest: str
    observation_digest_field: str
    action: tuple
    pose: CameraPose
    kind: str = "captured"

    def __post_init__(self) -> None:
        if type(self.frame_index) is not int or isinstance(self.frame_index, bool):
            raise TemporalMemoryError("frame index must be an int")
        if not 0 <= self.frame_index <= _MAX_FRAME:
            raise TemporalMemoryError("frame index out of bounds")
        if self.kind != "captured":
            raise TemporalMemoryError("interpolated frames cannot be stored as captured observations")
        if self.observation_digest_field not in EXISTING_DIGEST_FIELDS:
            raise TemporalMemoryError("observation digest field is not an existing digest field")
        object.__setattr__(
            self, "observation_digest", _sha256_hex(self.observation_digest, "observation_digest")
        )
        if not isinstance(self.pose, CameraPose):
            raise TemporalMemoryError("camera pose required")
        frozen = _freeze_action(self.action)
        if not isinstance(frozen, tuple):
            raise TemporalMemoryError("action must be a tuple")
        object.__setattr__(self, "action", frozen)

    def payload(self) -> dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "observation_digest": self.observation_digest,
            "observation_digest_field": self.observation_digest_field,
            "action": _action_json(self.action),
            "pose": self.pose.components(),
            "kind": self.kind,
        }

    @property
    def record_digest(self) -> str:
        return _digest(self.payload())

    @property
    def action_digest(self) -> str:
        return _digest(_action_json(self.action))

    @property
    def pose_digest(self) -> str:
        return _digest(self.pose.components())


@dataclass(frozen=True)
class EvictionSummary:
    """Content-addressed residue of one observation removed from the live window."""

    frame_index: int
    observation_digest: str
    observation_digest_field: str
    action_digest: str
    pose: CameraPose
    pose_digest: str
    prior_digest: str
    summary_digest: str

    def __post_init__(self) -> None:
        if type(self.frame_index) is not int or not 0 <= self.frame_index <= _MAX_FRAME:
            raise TemporalMemoryError("summary frame index out of bounds")
        object.__setattr__(
            self, "observation_digest", _sha256_hex(self.observation_digest, "observation_digest")
        )
        object.__setattr__(self, "action_digest", _sha256_hex(self.action_digest, "action_digest"))
        object.__setattr__(self, "pose_digest", _sha256_hex(self.pose_digest, "pose_digest"))
        object.__setattr__(self, "prior_digest", _sha256_hex(self.prior_digest, "prior_digest"))
        object.__setattr__(self, "summary_digest", _sha256_hex(self.summary_digest, "summary_digest"))
        if self.observation_digest_field not in EXISTING_DIGEST_FIELDS:
            raise TemporalMemoryError("summary digest field is not an existing digest field")
        if not isinstance(self.pose, CameraPose):
            raise TemporalMemoryError("summary camera pose required")
        if self.pose_digest != self.pose_digest_of(self.pose):
            raise TemporalMemoryError("summary pose digest does not match the stored pose")
        if self.summary_digest != self._expected_digest():
            raise TemporalMemoryError("summary digest does not match its content")

    @staticmethod
    def pose_digest_of(pose: CameraPose) -> str:
        return _digest(pose.components())

    def _body(self) -> dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "observation_digest": self.observation_digest,
            "observation_digest_field": self.observation_digest_field,
            "action_digest": self.action_digest,
            "pose": self.pose.components(),
            "pose_digest": self.pose_digest,
            "prior": self.prior_digest,
        }

    def _expected_digest(self) -> str:
        return _digest(self._body())

    @classmethod
    def from_record(cls, record: TemporalRecord, *, prior: str) -> "EvictionSummary":
        pose_digest = record.pose_digest
        prior_digest = _sha256_hex(prior, "prior_digest")
        body = {
            "frame_index": record.frame_index,
            "observation_digest": record.observation_digest,
            "observation_digest_field": record.observation_digest_field,
            "action_digest": record.action_digest,
            "pose": record.pose.components(),
            "pose_digest": pose_digest,
            "prior": prior_digest,
        }
        return cls(
            frame_index=record.frame_index,
            observation_digest=record.observation_digest,
            observation_digest_field=record.observation_digest_field,
            action_digest=record.action_digest,
            pose=record.pose,
            pose_digest=pose_digest,
            prior_digest=prior_digest,
            summary_digest=_digest(body),
        )

    def as_dict(self) -> dict[str, Any]:
        return self._body() | {"summary_digest": self.summary_digest}


@dataclass(frozen=True)
class RevisitComparison:
    """Comparison of a candidate observation against a live record or eviction summary."""

    observation_digest: str
    matched: bool
    source: str
    frame_index: int | None
    distance: float | None
    pose_digest: str | None
    summary_digest: str | None


class TemporalWorldMemory:
    """Gap-free monotonic history with a bounded live window and a summary chain.

    Append accepts frame indexes 0, 1, 2, ... with no gaps and no rewinds.
    When the live window is full, the oldest observation is dropped and folded
    into a content-addressed summary. Summary entries themselves are bounded
    by the same capacity; older summaries fold into a single archive digest.
    A revisit whose observation digest is still in the live window or the
    retained summaries can be compared by digest and camera-pose distance.
    """

    def __init__(self, capacity: int) -> None:
        if type(capacity) is not int or isinstance(capacity, bool) or not 1 <= capacity <= _MAX_CAPACITY:
            raise TemporalMemoryError(f"capacity must be an int in 1..{_MAX_CAPACITY}")
        self.capacity = capacity
        self._records: list[TemporalRecord] = []
        self._summaries: list[EvictionSummary] = []
        self._archive_digest: str | None = None
        self._chain_tail: str = GENESIS
        self._next_frame_index = 0

    @property
    def live_records(self) -> tuple[TemporalRecord, ...]:
        return tuple(self._records)

    @property
    def summaries(self) -> tuple[EvictionSummary, ...]:
        return tuple(self._summaries)

    @property
    def archive_digest(self) -> str | None:
        return self._archive_digest

    @property
    def next_frame_index(self) -> int:
        return self._next_frame_index

    @property
    def summary_digest(self) -> str:
        """Digest of the archive, retained summaries, and live records.

        Replaying the same append sequence produces this same digest.
        """
        return _digest({
            "schema": SCHEMA,
            "capacity": self.capacity,
            "archive_digest": self._archive_digest,
            "chain_tail": self._chain_tail,
            "summaries": [item.summary_digest for item in self._summaries],
            "live": [item.record_digest for item in self._records],
            "next_frame_index": self._next_frame_index,
        })

    def status(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "capacity": self.capacity,
            "live_observations": len(self._records),
            "retained_summaries": len(self._summaries),
            "archive_digest": self._archive_digest,
            "summary_digest": self.summary_digest,
            "next_frame_index": self._next_frame_index,
            "model_calls": 0,
            "renders_frames": False,
            "loads_weights": False,
            "uses_wall_clock": False,
        }

    def append(self, record: TemporalRecord) -> str:
        """Append one captured observation. Returns the memory summary digest."""
        if not isinstance(record, TemporalRecord):
            raise TemporalMemoryError("captured temporal record required")
        if record.frame_index != self._next_frame_index:
            raise TemporalMemoryError(
                f"frame index must be gap-free and monotonic, expected {self._next_frame_index}"
            )
        if len(self._records) == self.capacity:
            self._evict_oldest()
        self._records.append(record)
        self._next_frame_index += 1
        return self.summary_digest

    def _evict_oldest(self) -> None:
        oldest = self._records.pop(0)
        if len(self._summaries) == self.capacity:
            folded = self._summaries.pop(0)
            self._archive_digest = _digest({
                "prior": self._archive_digest,
                "folded_summary": folded.summary_digest,
            })
        summary = EvictionSummary.from_record(oldest, prior=self._chain_tail)
        self._chain_tail = summary.summary_digest
        self._summaries.append(summary)

    def compare_revisit(self, observation_digest: str, pose: CameraPose) -> RevisitComparison:
        """Compare ``pose`` to a stored pose that carries this observation digest.

        Live records are preferred over older summaries. A digest that has been
        folded into the archive is not individually comparable; the archive
        digest remains part of ``summary_digest`` for replay equality.
        """
        digest = _sha256_hex(observation_digest, "observation_digest")
        if not isinstance(pose, CameraPose):
            raise TemporalMemoryError("camera pose required")
        found_pose: CameraPose | None = None
        found_frame: int | None = None
        found_pose_digest: str | None = None
        found_summary: str | None = None
        source = "absent"
        for record in reversed(self._records):
            if record.observation_digest == digest:
                found_pose = record.pose
                found_frame = record.frame_index
                found_pose_digest = record.pose_digest
                source = "live"
                break
        if found_pose is None:
            for summary in reversed(self._summaries):
                if summary.observation_digest == digest:
                    found_pose = summary.pose
                    found_frame = summary.frame_index
                    found_pose_digest = summary.pose_digest
                    found_summary = summary.summary_digest
                    source = "summary"
                    break
        if found_pose is None:
            return RevisitComparison(digest, False, "absent", None, None, None, None)
        return RevisitComparison(
            digest,
            True,
            source,
            found_frame,
            pose_distance(pose, found_pose),
            found_pose_digest,
            found_summary,
        )

    def stored_pose(self, frame_index: int) -> CameraPose:
        if type(frame_index) is not int or isinstance(frame_index, bool):
            raise TemporalMemoryError("frame index must be an int")
        for record in self._records:
            if record.frame_index == frame_index:
                return record.pose
        for summary in self._summaries:
            if summary.frame_index == frame_index:
                return summary.pose
        raise TemporalMemoryError(f"frame {frame_index} is not in the live window or retained summaries")

    def export_state(self) -> dict[str, Any]:
        """Serializable checkpoint. The caller persists it; this method does not touch a clock or a file."""
        return {
            "schema": SCHEMA,
            "capacity": self.capacity,
            "next_frame_index": self._next_frame_index,
            "archive_digest": self._archive_digest,
            "chain_tail": self._chain_tail,
            "summaries": [item.as_dict() for item in self._summaries],
            "live": [item.payload() for item in self._records],
        }

    @classmethod
    def from_state(cls, state: Mapping[str, Any]) -> "TemporalWorldMemory":
        """Rebuild a memory from a checkpoint and reject a digest that does not recompute."""
        if not isinstance(state, Mapping):
            raise TemporalMemoryError("checkpoint must be a mapping")
        if state.get("schema") != SCHEMA:
            raise TemporalMemoryError("checkpoint schema mismatch")
        memory = cls(state.get("capacity"))  # type: ignore[arg-type]
        archive = state.get("archive_digest")
        if archive is not None:
            archive = _sha256_hex(archive, "archive_digest")
        chain_tail = _sha256_hex(state.get("chain_tail"), "chain_tail")
        raw_summaries = state.get("summaries")
        raw_live = state.get("live")
        next_index = state.get("next_frame_index")
        if type(next_index) is not int or isinstance(next_index, bool):
            raise TemporalMemoryError("checkpoint next_frame_index must be an int")
        if not isinstance(raw_summaries, list) or not isinstance(raw_live, list):
            raise TemporalMemoryError("checkpoint records must be lists")
        if len(raw_summaries) > memory.capacity or len(raw_live) > memory.capacity:
            raise TemporalMemoryError("checkpoint exceeds capacity")
        summaries: list[EvictionSummary] = []
        for item in raw_summaries:
            if not isinstance(item, Mapping):
                raise TemporalMemoryError("summary checkpoint must be a mapping")
            pose_values = item.get("pose")
            if not isinstance(pose_values, list) or len(pose_values) != 6:
                raise TemporalMemoryError("summary pose must be six numbers")
            summary = EvictionSummary(
                frame_index=item.get("frame_index"),  # type: ignore[arg-type]
                observation_digest=item.get("observation_digest"),  # type: ignore[arg-type]
                observation_digest_field=item.get("observation_digest_field"),  # type: ignore[arg-type]
                action_digest=item.get("action_digest"),  # type: ignore[arg-type]
                pose=CameraPose(*pose_values),
                pose_digest=item.get("pose_digest"),  # type: ignore[arg-type]
                prior_digest=item.get("prior"),  # type: ignore[arg-type]
                summary_digest=item.get("summary_digest"),  # type: ignore[arg-type]
            )
            summaries.append(summary)
        if summaries:
            if archive is None and summaries[0].prior_digest != GENESIS:
                raise TemporalMemoryError("first summary must chain from genesis when nothing is archived")
            for earlier, later in zip(summaries, summaries[1:]):
                if later.prior_digest != earlier.summary_digest:
                    raise TemporalMemoryError("summary chain prior does not match the previous summary")
                if later.frame_index <= earlier.frame_index:
                    raise TemporalMemoryError("summary frame indexes must increase")
            if chain_tail != summaries[-1].summary_digest:
                raise TemporalMemoryError("chain tail does not match the newest summary")
        elif chain_tail != GENESIS or archive is not None:
            raise TemporalMemoryError("empty summary chain must stay at genesis with no archive")
        records: list[TemporalRecord] = []
        for item in raw_live:
            if not isinstance(item, Mapping):
                raise TemporalMemoryError("live checkpoint must be a mapping")
            pose_values = item.get("pose")
            if not isinstance(pose_values, list) or len(pose_values) != 6:
                raise TemporalMemoryError("live pose must be six numbers")
            action = item.get("action")
            if not isinstance(action, list):
                raise TemporalMemoryError("live action must be a list")
            records.append(TemporalRecord(
                frame_index=item.get("frame_index"),  # type: ignore[arg-type]
                observation_digest=item.get("observation_digest"),  # type: ignore[arg-type]
                observation_digest_field=item.get("observation_digest_field"),  # type: ignore[arg-type]
                action=tuple(action),
                pose=CameraPose(*pose_values),
                kind=item.get("kind", ""),
            ))
        for earlier, later in zip(records, records[1:]):
            if later.frame_index != earlier.frame_index + 1:
                raise TemporalMemoryError("live frame indexes must be gap-free")
        if summaries and records and records[0].frame_index != summaries[-1].frame_index + 1:
            raise TemporalMemoryError("live window must continue the newest summary")
        if records:
            if records[0].frame_index < 0 or next_index != records[-1].frame_index + 1:
                raise TemporalMemoryError("checkpoint next index must follow the live tail")
        elif summaries:
            if next_index != summaries[-1].frame_index + 1:
                raise TemporalMemoryError("checkpoint next index must follow the summary tail")
        elif next_index != 0:
            raise TemporalMemoryError("empty memory must resume at frame 0")
        memory._archive_digest = archive
        memory._chain_tail = chain_tail
        memory._summaries = summaries
        memory._records = records
        memory._next_frame_index = next_index
        return memory

    def restore(self, state: Mapping[str, Any]) -> str:
        """Replace this memory with a validated checkpoint. A bad checkpoint leaves it unchanged."""
        rebuilt = self.from_state(state)
        self.capacity = rebuilt.capacity
        self._records = rebuilt._records
        self._summaries = rebuilt._summaries
        self._archive_digest = rebuilt._archive_digest
        self._chain_tail = rebuilt._chain_tail
        self._next_frame_index = rebuilt._next_frame_index
        return self.summary_digest
