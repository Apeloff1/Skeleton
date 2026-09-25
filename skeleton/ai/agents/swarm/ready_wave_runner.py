"""Sync ready_wave runner — drains SwarmDag waves with attested completion.

Extend-only sibling to ``SwarmDag``: holds a DAG, claims each ready task,
invokes a capability handler, then ``complete`` (non-None attested result)
or ``fail`` on exception / missing handler / None result.

No asyncio — matches SwarmDag / Skeleton scheduler style.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from skeleton.swarm.dag import SwarmDag, TaskNode


Handler = Callable[[TaskNode], Any]


@dataclass
class ReadyWaveReport:
    """Outcome of one ``run_available`` or a multi-wave ``drain``."""

    waves: int = 0
    completed: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    stopped: str = "idle"
    stats: Dict[str, Any] = field(default_factory=dict)

    def merge(self, other: "ReadyWaveReport") -> "ReadyWaveReport":
        self.waves += other.waves
        self.completed.extend(other.completed)
        self.failed.extend(other.failed)
        self.errors.extend(other.errors)
        self.stopped = other.stopped or self.stopped
        self.stats = other.stats or self.stats
        return self


class ReadyWaveRunner:
    """Thin sync runner: ready_wave → claim → handler → complete|fail."""

    def __init__(self, dag: Optional[SwarmDag] = None) -> None:
        self.dag = dag if dag is not None else SwarmDag()

    def run_available(
        self,
        executor_id: str,
        handlers: Dict[str, Handler],
    ) -> ReadyWaveReport:
        """Process one ready wave.

        For each task in ``ready_wave()``: claim → invoke ``handlers[capability]``
        → complete with non-None result, or fail on missing handler / exception /
        None return (attestation required).
        """
        report = ReadyWaveReport()
        if not isinstance(executor_id, str) or not executor_id.strip():
            raise ValueError("executor_id is required")
        wave = self.dag.ready_wave()
        if not wave:
            report.stats = self.dag.stats()
            return report

        report.waves = 1
        for task in wave:
            claimed = self.dag.claim(task.id, executor_id)
            if claimed is None:
                # Race / already claimed — skip without counting as fail
                continue
            handler = handlers.get(claimed.capability)
            if handler is None:
                self.dag.fail(claimed.id)
                report.failed.append(claimed.id)
                continue
            try:
                result = handler(claimed)
            except Exception as exc:
                self.dag.fail(claimed.id)
                report.failed.append(claimed.id)
                report.errors.append(type(exc).__name__)
                continue
            if result is None or not self.dag.complete(claimed.id, result):
                self.dag.fail(claimed.id)
                report.failed.append(claimed.id)
            else:
                report.completed.append(claimed.id)

        report.stats = self.dag.stats()
        return report

    def drain(
        self,
        executor_id: str,
        handlers: Dict[str, Handler],
        *,
        max_waves: int = 64,
    ) -> ReadyWaveReport:
        """Loop ``run_available`` until a wave is empty or ``max_waves`` hit."""
        if isinstance(max_waves, bool) or not isinstance(max_waves, int) or max_waves < 1:
            raise ValueError("max_waves must be a positive integer")
        aggregate = ReadyWaveReport()
        for _ in range(max_waves):
            wave_report = self.run_available(executor_id, handlers)
            if wave_report.waves == 0:
                aggregate.stats = wave_report.stats or self.dag.stats()
                aggregate.stopped = "idle"
                break
            aggregate.merge(wave_report)
        else:
            aggregate.stats = self.dag.stats()
            aggregate.stopped = "budget"
        return aggregate
