"""Bounded optimizer batch receipts; time and steps must monotonically increase."""
from __future__ import annotations
from dataclasses import dataclass
from .strict import number, digest
from .errors import deny


@dataclass(frozen=True, slots=True)
class BatchReceipt:
    index: int
    first_line: int
    line_count: int
    steps: int
    cumulative_steps: int
    elapsed_ms: int
    source_sha256: str

    def __post_init__(self) -> None:
        from .strict import sha
        for name, lo, hi in (
            ("index", 0, 100000), ("first_line", 0, 576),
            ("line_count", 1, 128), ("steps", 0, 1000000),
            ("cumulative_steps", 0, 1000000), ("elapsed_ms", 0, 36000000),
        ):
            number(getattr(self, name), name, lo, hi)
        sha(self.source_sha256, "batch-source")

    def record(self) -> dict:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}

    @property
    def digest(self) -> str:
        return digest(self.record())


def verify_sequence(receipts: tuple[BatchReceipt, ...], expected_lines: int,
                    expected_steps: int) -> dict:
    number(expected_lines, "lines", 1, 576)
    number(expected_steps, "steps", 1, 1000000)
    total_lines = total_steps = 0
    prev_time = -1
    for index, item in enumerate(receipts):
        if type(item) is not BatchReceipt or item.index != index:
            deny("batch-order")
        if item.first_line != total_lines or item.elapsed_ms < prev_time:
            deny("batch-sequence")
        total_lines += item.line_count
        total_steps += item.steps
        if item.cumulative_steps != total_steps:
            deny("batch-cumulative")
        prev_time = item.elapsed_ms
    if (total_lines, total_steps) != (expected_lines, expected_steps):
        deny("batch-total")
    return {"batches": len(receipts), "lines": total_lines,
            "steps": total_steps, "digest": digest([r.record() for r in receipts])}
