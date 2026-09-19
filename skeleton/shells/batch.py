"""Bounded parallel shell execution."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import threading
from typing import Iterable, Mapping

from skeleton.shells.capabilities import ShellCapability
from skeleton.shells.executor import ExecutionOutcome, ShellExecutor
from skeleton.shells.retry import RetryPolicy
from skeleton.shells.runner import ShellCommand
from skeleton.shells.session import ShellSession


@dataclass(frozen=True)
class BatchItem:
    item_id: str
    command: ShellCommand
    retry: RetryPolicy | None = None

    def __post_init__(self) -> None:
        if not self.item_id or len(self.item_id) > 128:
            raise ValueError("batch item_id must be non-empty and bounded")


@dataclass(frozen=True)
class BatchResult:
    outcomes: Mapping[str, ExecutionOutcome]
    errors: Mapping[str, str]
    skipped: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors and not self.skipped and all(outcome.ok for outcome in self.outcomes.values())


class BatchExecutor:
    def __init__(self, executor: ShellExecutor, *, max_workers: int = 4, max_items: int = 256) -> None:
        if max_workers <= 0 or max_items <= 0:
            raise ValueError("batch bounds must be positive")
        self.executor = executor
        self.max_workers = max_workers
        self.max_items = max_items

    def execute(
        self,
        items: Iterable[BatchItem],
        *,
        session: ShellSession | None = None,
        fail_fast: bool = False,
    ) -> BatchResult:
        self.executor.grant.require(ShellCapability.PARALLEL, detail="parallel batch execution requires capability")
        batch = tuple(items)
        if len(batch) > self.max_items:
            raise ValueError("batch item count exceeds bound")
        ids = [item.item_id for item in batch]
        if len(ids) != len(set(ids)):
            raise ValueError("batch item IDs must be unique")

        outcomes: dict[str, ExecutionOutcome] = {}
        errors: dict[str, str] = {}
        skipped: set[str] = set()
        stop = threading.Event()

        def run(item: BatchItem) -> ExecutionOutcome:
            if stop.is_set():
                raise RuntimeError("batch fail-fast stop")
            return self.executor.execute(item.command, retry=item.retry, session=session)

        with ThreadPoolExecutor(max_workers=min(self.max_workers, max(1, len(batch)))) as pool:
            futures: dict[Future[ExecutionOutcome], BatchItem] = {pool.submit(run, item): item for item in batch}
            for future in as_completed(futures):
                item = futures[future]
                try:
                    outcome = future.result()
                except Exception as exc:
                    errors[item.item_id] = type(exc).__name__
                    if fail_fast:
                        stop.set()
                    continue
                outcomes[item.item_id] = outcome
                if fail_fast and not outcome.ok:
                    stop.set()

            if stop.is_set():
                for future, item in futures.items():
                    if item.item_id in outcomes or item.item_id in errors:
                        continue
                    if future.cancel():
                        skipped.add(item.item_id)
                    else:
                        try:
                            outcome = future.result()
                        except Exception as exc:
                            errors[item.item_id] = type(exc).__name__
                        else:
                            outcomes[item.item_id] = outcome

        return BatchResult(dict(outcomes), dict(errors), tuple(sorted(skipped)))
