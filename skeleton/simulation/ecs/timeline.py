"""Digest-chained deterministic state timeline.

``StateTimeline`` retains immutable store snapshots as evidence and provides
bounded seek/diff operations for editor undo, simulation inspection and replay
support.  It is not authoritative state: seeking always restores into an
explicit ``EntityStore`` supplied by the caller.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .canonical import chained_digest, digest
from .errors import BoundsError, SnapshotError, ValidationError
from .execution import StoreSnapshot, capture_snapshot, restore_snapshot
from .inspection import StateDiff, diff_state
from .store import EntityStore

MAX_TIMELINE_FRAMES = 4096
GENESIS_TIMELINE_DIGEST = "0" * 64


@dataclass(frozen=True)
class TimelinePolicy:
    capacity: int = 256
    allow_duplicate_state: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.capacity, bool) or not isinstance(self.capacity, int):
            raise ValidationError("timeline capacity must be integer")
        if not 1 <= self.capacity <= MAX_TIMELINE_FRAMES:
            raise ValidationError(
                "timeline capacity outside supported range",
                context={"capacity": self.capacity, "maximum": MAX_TIMELINE_FRAMES},
            )
        if not isinstance(self.allow_duplicate_state, bool):
            raise ValidationError("allow_duplicate_state must be boolean")

    @property
    def fingerprint(self) -> str:
        return digest(
            {
                "domain": "skeleton.simulation.ecs.timeline_policy.v1",
                "capacity": self.capacity,
                "allow_duplicate_state": self.allow_duplicate_state,
            }
        )


@dataclass(frozen=True)
class TimelineFrame:
    sequence: int
    label: str
    snapshot: StoreSnapshot
    metadata: Mapping[str, Any]
    previous_digest: str
    frame_digest: str

    @property
    def revision(self) -> int:
        return self.snapshot.revision

    @property
    def tick(self) -> int:
        return self.snapshot.tick

    @property
    def state_digest(self) -> str:
        return self.snapshot.state_digest

    def to_record(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "label": self.label,
            "revision": self.revision,
            "tick": self.tick,
            "state_digest": self.state_digest,
            "metadata": copy.deepcopy(dict(self.metadata)),
            "previous_digest": self.previous_digest,
            "frame_digest": self.frame_digest,
        }


@dataclass(frozen=True)
class TimelineVerification:
    frames: int
    retained_start_sequence: int
    head_digest: str
    valid: bool
    first_invalid_sequence: int | None = None
    reason: str | None = None


@dataclass(frozen=True)
class TimelineRange:
    start_sequence: int
    end_sequence: int
    frames: tuple[TimelineFrame, ...]
    range_digest: str


class StateTimeline:
    def __init__(self, *, policy: TimelinePolicy | None = None) -> None:
        self.policy = policy or TimelinePolicy()
        self._frames: list[TimelineFrame] = []
        self._next_sequence = 0
        self._head_digest = GENESIS_TIMELINE_DIGEST
        self._retained_previous_digest = GENESIS_TIMELINE_DIGEST

    def __len__(self) -> int:
        return len(self._frames)

    @property
    def next_sequence(self) -> int:
        return self._next_sequence

    @property
    def head_digest(self) -> str:
        return self._head_digest

    @property
    def retained_start_sequence(self) -> int:
        return self._frames[0].sequence if self._frames else self._next_sequence

    def frames(self) -> tuple[TimelineFrame, ...]:
        return tuple(self._frames)

    @staticmethod
    def _label(value: str) -> str:
        if not isinstance(value, str) or len(value) > 256:
            raise ValidationError("timeline label must be text up to 256 characters")
        return value

    def append(
        self,
        store: EntityStore,
        *,
        label: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> TimelineFrame:
        if not isinstance(store, EntityStore):
            raise ValidationError("timeline append requires EntityStore")
        label = self._label(label)
        frozen_metadata = copy.deepcopy(dict(metadata or {}))
        digest(frozen_metadata)
        snapshot = capture_snapshot(store)
        if (
            not self.policy.allow_duplicate_state
            and self._frames
            and self._frames[-1].state_digest == snapshot.state_digest
        ):
            raise SnapshotError(
                "timeline duplicate state is disabled",
                context={"state_digest": snapshot.state_digest},
            )
        material = {
            "domain": "skeleton.simulation.ecs.timeline_frame.v1",
            "sequence": self._next_sequence,
            "label": label,
            "revision": snapshot.revision,
            "tick": snapshot.tick,
            "state_digest": snapshot.state_digest,
            "metadata": frozen_metadata,
        }
        frame_digest = chained_digest(self._head_digest, material)
        frame = TimelineFrame(
            sequence=self._next_sequence,
            label=label,
            snapshot=snapshot,
            metadata=frozen_metadata,
            previous_digest=self._head_digest,
            frame_digest=frame_digest,
        )
        self._frames.append(frame)
        self._next_sequence += 1
        self._head_digest = frame_digest
        self._evict_if_needed()
        return frame

    def _evict_if_needed(self) -> None:
        while len(self._frames) > self.policy.capacity:
            evicted = self._frames.pop(0)
            self._retained_previous_digest = evicted.frame_digest

    def latest(self) -> TimelineFrame:
        if not self._frames:
            raise SnapshotError("timeline is empty")
        return self._frames[-1]

    def get(self, sequence: int) -> TimelineFrame:
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise ValidationError("timeline sequence must be non-negative integer")
        for frame in self._frames:
            if frame.sequence == sequence:
                return frame
        raise SnapshotError(
            "timeline sequence not retained",
            context={"sequence": sequence},
        )

    def by_label(self, label: str) -> tuple[TimelineFrame, ...]:
        label = self._label(label)
        return tuple(frame for frame in self._frames if frame.label == label)

    def at_revision(self, revision: int) -> tuple[TimelineFrame, ...]:
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise ValidationError("timeline revision must be non-negative integer")
        return tuple(frame for frame in self._frames if frame.revision == revision)

    def at_tick(self, tick: int) -> tuple[TimelineFrame, ...]:
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValidationError("timeline tick must be non-negative integer")
        return tuple(frame for frame in self._frames if frame.tick == tick)

    def seek(self, store: EntityStore, sequence: int) -> TimelineFrame:
        frame = self.get(sequence)
        if frame.snapshot.store.state_digest != frame.state_digest:
            raise SnapshotError("timeline frame snapshot digest mismatch")
        restore_snapshot(store, frame.snapshot)
        store.assert_invariants()
        return frame

    def diff(self, left_sequence: int, right_sequence: int) -> StateDiff:
        left = self.get(left_sequence)
        right = self.get(right_sequence)
        return diff_state(left.snapshot, right.snapshot)

    def range(self, start_sequence: int, end_sequence: int) -> TimelineRange:
        if (
            isinstance(start_sequence, bool)
            or isinstance(end_sequence, bool)
            or not isinstance(start_sequence, int)
            or not isinstance(end_sequence, int)
            or start_sequence < 0
            or end_sequence < start_sequence
        ):
            raise ValidationError("invalid timeline range")
        rows = tuple(
            frame
            for frame in self._frames
            if start_sequence <= frame.sequence <= end_sequence
        )
        if rows:
            actual_start = rows[0].sequence
            actual_end = rows[-1].sequence
        else:
            actual_start = start_sequence
            actual_end = end_sequence
        return TimelineRange(
            start_sequence=actual_start,
            end_sequence=actual_end,
            frames=rows,
            range_digest=digest(
                {
                    "domain": "skeleton.simulation.ecs.timeline_range.v1",
                    "requested_start": start_sequence,
                    "requested_end": end_sequence,
                    "frames": [row.frame_digest for row in rows],
                }
            ),
        )

    def verify(self) -> TimelineVerification:
        if not self._frames:
            return TimelineVerification(
                frames=0,
                retained_start_sequence=self._next_sequence,
                head_digest=self._head_digest,
                valid=self._head_digest == GENESIS_TIMELINE_DIGEST,
            )

        previous = self._retained_previous_digest
        expected_sequence = self._frames[0].sequence
        for frame in self._frames:
            if frame.sequence != expected_sequence:
                return TimelineVerification(
                    len(self._frames),
                    self._frames[0].sequence,
                    previous,
                    False,
                    frame.sequence,
                    "sequence_gap",
                )
            if frame.previous_digest != previous:
                return TimelineVerification(
                    len(self._frames),
                    self._frames[0].sequence,
                    previous,
                    False,
                    frame.sequence,
                    "previous_digest_mismatch",
                )
            if frame.snapshot.store.state_digest != frame.state_digest:
                return TimelineVerification(
                    len(self._frames),
                    self._frames[0].sequence,
                    previous,
                    False,
                    frame.sequence,
                    "snapshot_digest_mismatch",
                )
            material = {
                "domain": "skeleton.simulation.ecs.timeline_frame.v1",
                "sequence": frame.sequence,
                "label": frame.label,
                "revision": frame.revision,
                "tick": frame.tick,
                "state_digest": frame.state_digest,
                "metadata": dict(frame.metadata),
            }
            expected_digest = chained_digest(previous, material)
            if expected_digest != frame.frame_digest:
                return TimelineVerification(
                    len(self._frames),
                    self._frames[0].sequence,
                    previous,
                    False,
                    frame.sequence,
                    "frame_digest_mismatch",
                )
            previous = frame.frame_digest
            expected_sequence += 1

        return TimelineVerification(
            frames=len(self._frames),
            retained_start_sequence=self._frames[0].sequence,
            head_digest=previous,
            valid=previous == self._head_digest,
            reason=None if previous == self._head_digest else "head_digest_mismatch",
        )

    def summary(self) -> dict[str, Any]:
        return {
            "frames": len(self._frames),
            "next_sequence": self._next_sequence,
            "retained_start_sequence": self.retained_start_sequence,
            "head_digest": self._head_digest,
            "policy_fingerprint": self.policy.fingerprint,
            "labels": tuple(sorted({frame.label for frame in self._frames if frame.label})),
            "revisions": tuple(frame.revision for frame in self._frames),
            "ticks": tuple(frame.tick for frame in self._frames),
        }


def record_states(
    stores: Iterable[EntityStore],
    *,
    policy: TimelinePolicy | None = None,
    label_prefix: str = "state",
) -> StateTimeline:
    timeline = StateTimeline(policy=policy or TimelinePolicy(allow_duplicate_state=True))
    for index, store in enumerate(stores):
        timeline.append(store, label=f"{label_prefix}:{index}")
    return timeline
