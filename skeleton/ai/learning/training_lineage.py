"""Deterministic training-data lineage and mixture reconstruction.

A training run must be able to prove exactly which immutable source/shard set,
mixture weights and sampling cursor produced a checkpoint.  This module keeps
that identity provider-independent and executable without requiring a specific
training framework.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
import hashlib
import json
from typing import Mapping, Sequence


class TrainingLineageError(RuntimeError):
    """Training data lineage is incomplete, ambiguous, or non-reproducible."""


def _stable_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise TrainingLineageError("lineage value is not deterministic JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _text(name: str, value: object, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrainingLineageError(f"{name} must be non-empty text")
    result = value.strip()
    if len(result) > maximum:
        raise TrainingLineageError(f"{name} exceeds {maximum} characters")
    return result


def _sha(name: str, value: object) -> str:
    result = _text(name, value, maximum=64).lower()
    if len(result) != 64 or any(ch not in "0123456789abcdef" for ch in result):
        raise TrainingLineageError(f"{name} must be lowercase sha256")
    return result


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TrainingLineageError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class SourceRecord:
    source_id: str
    content_digest: str
    rights_refs: tuple[str, ...]
    policy_refs: tuple[str, ...] = ()
    synthetic_parent_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        object.__setattr__(
            self, "content_digest", _sha("content_digest", self.content_digest)
        )
        for field_name in ("rights_refs", "policy_refs", "synthetic_parent_refs"):
            raw = getattr(self, field_name)
            values = tuple(_text(field_name, item) for item in raw)
            if len(values) != len(set(values)):
                raise TrainingLineageError(f"{field_name} must be unique")
            if field_name == "rights_refs" and not values:
                raise TrainingLineageError("rights_refs must not be empty")
            object.__setattr__(self, field_name, values)

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "content_digest": self.content_digest,
            "rights_refs": list(self.rights_refs),
            "policy_refs": list(self.policy_refs),
            "synthetic_parent_refs": list(self.synthetic_parent_refs),
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class DatasetShardManifest:
    dataset_id: str
    shard_id: str
    content_digest: str
    sample_count: int
    source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_id", _text("dataset_id", self.dataset_id))
        object.__setattr__(self, "shard_id", _text("shard_id", self.shard_id))
        object.__setattr__(
            self, "content_digest", _sha("content_digest", self.content_digest)
        )
        object.__setattr__(
            self, "sample_count", _positive_int("sample_count", self.sample_count)
        )
        sources = tuple(_text("source_id", item) for item in self.source_ids)
        if not sources:
            raise TrainingLineageError("source_ids must not be empty")
        if len(sources) != len(set(sources)):
            raise TrainingLineageError("source_ids must be unique")
        object.__setattr__(self, "source_ids", sources)

    def as_dict(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "shard_id": self.shard_id,
            "content_digest": self.content_digest,
            "sample_count": self.sample_count,
            "source_ids": list(self.source_ids),
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class MixtureComponent:
    dataset_id: str
    weight_numerator: int
    weight_denominator: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_id", _text("dataset_id", self.dataset_id))
        numerator = _positive_int("weight_numerator", self.weight_numerator)
        denominator = _positive_int("weight_denominator", self.weight_denominator)
        ratio = Fraction(numerator, denominator)
        object.__setattr__(self, "weight_numerator", ratio.numerator)
        object.__setattr__(self, "weight_denominator", ratio.denominator)

    @property
    def weight(self) -> Fraction:
        return Fraction(self.weight_numerator, self.weight_denominator)

    def as_dict(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "weight_numerator": self.weight_numerator,
            "weight_denominator": self.weight_denominator,
        }


@dataclass(frozen=True, slots=True)
class MixtureManifest:
    mixture_id: str
    components: tuple[MixtureComponent, ...]
    seed: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "mixture_id", _text("mixture_id", self.mixture_id))
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise TrainingLineageError("seed must be an integer")
        if not self.components:
            raise TrainingLineageError("mixture requires at least one component")
        if any(not isinstance(item, MixtureComponent) for item in self.components):
            raise TypeError("components must contain MixtureComponent values")
        ids = [item.dataset_id for item in self.components]
        if len(ids) != len(set(ids)):
            raise TrainingLineageError("mixture dataset_ids must be unique")
        if sum((item.weight for item in self.components), Fraction()) <= 0:
            raise TrainingLineageError("mixture total weight must be positive")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.training_mixture.v1",
            "mixture_id": self.mixture_id,
            "components": [item.as_dict() for item in self.components],
            "seed": self.seed,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())

    def _ticket_state(self) -> tuple[tuple[int, ...], int, tuple[int, ...]]:
        denominators = [item.weight.denominator for item in self.components]
        common = 1
        for denominator in denominators:
            a, b = common, denominator
            while b:
                a, b = b, a % b
            common = common * denominator // a

        tickets = tuple(
            item.weight.numerator * (common // item.weight.denominator)
            for item in self.components
        )
        total = sum(tickets)
        if total <= 0:
            raise TrainingLineageError("mixture ticket total must be positive")

        offset = self.seed % len(self.components)
        order = tuple(range(offset, len(self.components))) + tuple(range(0, offset))
        return tickets, total, order

    @staticmethod
    def _validate_draws(draws: object) -> int:
        if isinstance(draws, bool) or not isinstance(draws, int) or draws < 0:
            raise TrainingLineageError("draws must be a non-negative integer")
        return draws

    def dataset_schedule(self, *, draws: int) -> tuple[str, ...]:
        """Return an exact deterministic weighted round-robin schedule."""

        draws = self._validate_draws(draws)
        if draws == 0:
            return ()

        tickets, total, order = self._ticket_state()
        deficits = [0] * len(self.components)
        schedule: list[str] = []
        for _ in range(draws):
            for index, ticket in enumerate(tickets):
                deficits[index] += ticket
            winner = max(order, key=lambda index: deficits[index])
            deficits[winner] -= total
            schedule.append(self.components[winner].dataset_id)
        return tuple(schedule)

    def dataset_draw_counts(self, *, draws: int) -> dict[str, int]:
        """Return exact per-dataset draw counts without replaying full epochs."""

        draws = self._validate_draws(draws)
        tickets, total, order = self._ticket_state()
        cycles, remainder = divmod(draws, total)
        counts = [cycles * ticket for ticket in tickets]
        if remainder:
            deficits = [0] * len(self.components)
            for _ in range(remainder):
                for index, ticket in enumerate(tickets):
                    deficits[index] += ticket
                winner = max(order, key=lambda index: deficits[index])
                deficits[winner] -= total
                counts[winner] += 1
        return {
            component.dataset_id: counts[index]
            for index, component in enumerate(self.components)
        }


@dataclass(frozen=True, slots=True)
class TrainingDataManifest:
    manifest_id: str
    sources: tuple[SourceRecord, ...]
    shards: tuple[DatasetShardManifest, ...]
    mixture: MixtureManifest
    transform_refs: tuple[str, ...] = ()
    holdout_refs: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "manifest_id", _text("manifest_id", self.manifest_id))
        if not self.sources:
            raise TrainingLineageError("training manifest requires sources")
        if not self.shards:
            raise TrainingLineageError("training manifest requires shards")
        if any(not isinstance(item, SourceRecord) for item in self.sources):
            raise TypeError("sources must contain SourceRecord values")
        if any(not isinstance(item, DatasetShardManifest) for item in self.shards):
            raise TypeError("shards must contain DatasetShardManifest values")
        if not isinstance(self.mixture, MixtureManifest):
            raise TypeError("mixture must be MixtureManifest")

        source_ids = [item.source_id for item in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise TrainingLineageError("source ids must be unique")
        source_set = set(source_ids)

        shard_keys = [(item.dataset_id, item.shard_id) for item in self.shards]
        if len(shard_keys) != len(set(shard_keys)):
            raise TrainingLineageError("dataset/shard identities must be unique")
        for shard in self.shards:
            unknown = set(shard.source_ids) - source_set
            if unknown:
                raise TrainingLineageError(
                    f"shard {shard.shard_id} references unknown source ids"
                )

        dataset_ids = {item.dataset_id for item in self.shards}
        mixture_ids = {item.dataset_id for item in self.mixture.components}
        if dataset_ids != mixture_ids:
            missing = sorted(dataset_ids - mixture_ids)
            extra = sorted(mixture_ids - dataset_ids)
            raise TrainingLineageError(
                f"mixture dataset coverage mismatch missing={missing} extra={extra}"
            )

        for field_name in ("transform_refs", "holdout_refs"):
            raw = getattr(self, field_name)
            values = tuple(_text(field_name, item) for item in raw)
            if len(values) != len(set(values)):
                raise TrainingLineageError(f"{field_name} must be unique")
            object.__setattr__(self, field_name, values)

        frozen = dict(self.metadata)
        _stable_json(frozen)
        object.__setattr__(self, "metadata", frozen)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.training_data_manifest.v1",
            "manifest_id": self.manifest_id,
            "sources": [
                item.as_dict()
                for item in sorted(self.sources, key=lambda item: item.source_id)
            ],
            "shards": [
                item.as_dict()
                for item in sorted(
                    self.shards, key=lambda item: (item.dataset_id, item.shard_id)
                )
            ],
            "mixture": self.mixture.as_dict(),
            "transform_refs": list(self.transform_refs),
            "holdout_refs": list(self.holdout_refs),
            "metadata": dict(self.metadata),
        }

    @property
    def root_digest(self) -> str:
        return _digest(self.as_dict())

    def expected_dataset_offsets(self, *, draw_index: int) -> dict[str, int]:
        return dict(self.mixture.dataset_draw_counts(draws=draw_index))

    def checkpoint_cursor(
        self,
        *,
        draw_index: int,
        dataset_offsets: Mapping[str, int],
    ) -> "TrainingCursor":
        cursor = TrainingCursor(
            manifest_root=self.root_digest,
            mixture_digest=self.mixture.digest,
            draw_index=draw_index,
            dataset_offsets=dict(dataset_offsets),
        )
        cursor.assert_compatible(self)
        return cursor

    def derived_checkpoint_cursor(self, *, draw_index: int) -> "TrainingCursor":
        return TrainingCursor(
            manifest_root=self.root_digest,
            mixture_digest=self.mixture.digest,
            draw_index=draw_index,
            dataset_offsets=self.expected_dataset_offsets(draw_index=draw_index),
        )


@dataclass(frozen=True, slots=True)
class TrainingCursor:
    manifest_root: str
    mixture_digest: str
    draw_index: int
    dataset_offsets: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "manifest_root", _sha("manifest_root", self.manifest_root)
        )
        object.__setattr__(
            self, "mixture_digest", _sha("mixture_digest", self.mixture_digest)
        )
        if isinstance(self.draw_index, bool) or not isinstance(self.draw_index, int):
            raise TrainingLineageError("draw_index must be an integer")
        if self.draw_index < 0:
            raise TrainingLineageError("draw_index must be non-negative")
        offsets: dict[str, int] = {}
        for dataset_id, raw in self.dataset_offsets.items():
            key = _text("dataset_id", dataset_id)
            if key in offsets:
                raise TrainingLineageError(
                    "dataset offset identities collide after normalization"
                )
            if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
                raise TrainingLineageError("dataset offsets must be non-negative integers")
            offsets[key] = raw
        object.__setattr__(self, "dataset_offsets", dict(sorted(offsets.items())))

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.training_cursor.v1",
            "manifest_root": self.manifest_root,
            "mixture_digest": self.mixture_digest,
            "draw_index": self.draw_index,
            "dataset_offsets": dict(self.dataset_offsets),
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())

    def assert_compatible(self, manifest: TrainingDataManifest) -> None:
        if not isinstance(manifest, TrainingDataManifest):
            raise TypeError("manifest must be TrainingDataManifest")
        if self.manifest_root != manifest.root_digest:
            raise TrainingLineageError("checkpoint data manifest root mismatch")
        if self.mixture_digest != manifest.mixture.digest:
            raise TrainingLineageError("checkpoint mixture identity mismatch")
        expected = manifest.expected_dataset_offsets(draw_index=self.draw_index)
        if dict(self.dataset_offsets) != expected:
            raise TrainingLineageError(
                "checkpoint dataset offsets do not match deterministic mixture schedule"
            )


__all__ = [
    "DatasetShardManifest",
    "MixtureComponent",
    "MixtureManifest",
    "SourceRecord",
    "TrainingCursor",
    "TrainingDataManifest",
    "TrainingLineageError",
]
