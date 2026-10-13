"""Revisioned AI autonomy policy store with compare-and-swap semantics."""

from __future__ import annotations

from dataclasses import dataclass
import threading

from skeleton.shells.ai.policy import AIShellPolicy


@dataclass(frozen=True)
class AIPolicyRevision:
    revision: int
    fingerprint: str
    policy: AIShellPolicy

    def to_dict(self) -> dict[str, object]:
        return {"revision": self.revision, "fingerprint": self.fingerprint}


class AIPolicyConflict(RuntimeError):
    pass


class AIPolicyStore:
    def __init__(self, initial: AIShellPolicy | None = None) -> None:
        policy = initial or AIShellPolicy()
        self._current = AIPolicyRevision(1, policy.fingerprint, policy)
        self._history = [self._current]
        self._lock = threading.RLock()

    def current(self) -> AIPolicyRevision:
        with self._lock:
            return self._current

    def compare_and_swap(
        self,
        expected_revision: int,
        policy: AIShellPolicy,
    ) -> AIPolicyRevision:
        with self._lock:
            if self._current.revision != expected_revision:
                raise AIPolicyConflict("AI shell policy revision conflict")
            updated = AIPolicyRevision(
                self._current.revision + 1,
                policy.fingerprint,
                policy,
            )
            self._current = updated
            self._history.append(updated)
            return updated

    def replace(self, policy: AIShellPolicy) -> AIPolicyRevision:
        with self._lock:
            return self.compare_and_swap(self._current.revision, policy)

    def at(self, revision: int) -> AIPolicyRevision:
        with self._lock:
            if revision <= 0 or revision > len(self._history):
                raise KeyError(revision)
            return self._history[revision - 1]

    def history(self) -> tuple[AIPolicyRevision, ...]:
        with self._lock:
            return tuple(self._history)
