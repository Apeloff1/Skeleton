"""Candidate-only normalized training lines from TRAIN partition only."""
from __future__ import annotations
from dataclasses import dataclass

from .curriculum import interleave, curriculum_digest
from .splits import Partition
from .strict import digest
from .errors import deny


@dataclass(frozen=True, slots=True)
class TrainingWorkload:
    lines: tuple[str, ...]
    source_ids: tuple[str, ...]
    curriculum_sha256: str
    text_sha256: str

    def record(self) -> dict:
        return {
            "lines": len(self.lines),
            "source_sha256": digest(list(self.source_ids)),
            "curriculum_sha256": self.curriculum_sha256,
            "text_sha256": self.text_sha256,
            "uses_holdout": False, "uses_validation": False,
        }


def build(partition: Partition) -> TrainingWorkload:
    if type(partition) is not Partition or len(partition.train) != 432:
        deny("workload-partition")
    items = interleave(partition.train)
    lines = tuple(item.render() for item in items)
    if len(lines) != 432 or len(set(lines)) != len(lines):
        deny("workload-duplicate")
    return TrainingWorkload(lines, tuple(item.item_id for item in items),
                            curriculum_digest(partition.train), digest(lines))
