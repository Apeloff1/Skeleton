"""Canonical snapshot of AI shell planning and evidence state."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import time
from typing import Callable

from skeleton.shells.ai.budget import AIBudget
from skeleton.shells.ai.calibration import AICalibration
from skeleton.shells.ai.diagnostics import AIShellDiagnostics
from skeleton.shells.ai.journal import AIDecisionJournal
from skeleton.shells.ai.memory import AIOutcomeMemory
from skeleton.shells.ai.policy_store import AIPolicyStore


@dataclass(frozen=True)
class AIShellSnapshot:
    schema_version: int
    created_at: float
    policy: dict[str, object]
    diagnostics: dict[str, object]
    budget: dict[str, int]
    calibration: tuple[dict[str, object], ...]
    memory_items: int
    journal_root: str
    journal_valid: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "policy": dict(self.policy),
            "diagnostics": dict(self.diagnostics),
            "budget": dict(self.budget),
            "calibration": list(self.calibration),
            "memory_items": self.memory_items,
            "journal_root": self.journal_root,
            "journal_valid": self.journal_valid,
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
        return hashlib.sha256(raw).hexdigest()


class AIShellSnapshotter:
    def __init__(
        self,
        *,
        policy_store: AIPolicyStore,
        diagnostics: AIShellDiagnostics,
        budget: AIBudget,
        calibration: AICalibration,
        memory: AIOutcomeMemory,
        journal: AIDecisionJournal,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.policy_store = policy_store
        self.diagnostics = diagnostics
        self.budget = budget
        self.calibration = calibration
        self.memory = memory
        self.journal = journal
        self._clock = clock

    def capture(self) -> AIShellSnapshot:
        policy = self.policy_store.current()
        return AIShellSnapshot(
            1,
            self._clock(),
            {
                "revision": policy.revision,
                "fingerprint": policy.fingerprint,
                "policy": policy.policy.to_dict(),
            },
            self.diagnostics.inspect().to_dict(),
            self.budget.snapshot().to_dict(),
            tuple(item.to_dict() for item in self.calibration.snapshot()),
            len(self.memory.snapshot()),
            self.journal.root_hash(),
            self.journal.verify(),
        )
