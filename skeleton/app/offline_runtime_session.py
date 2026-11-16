"""Trusted local-process adapter for repeated resource admission.

The package exports an operator-pinned session API in addition to the CLI.
It owns its source selection, clock and probe invocation. No external
receipt, RPC, synthetic observation or provider can issue a live grant.
A consumed proposal is still only a cooperative scheduling budget.
"""
from __future__ import annotations

from pathlib import Path
import threading
import time
from typing import Self

from skeleton.ai.model_runtime.iteration_scheduler import IterationWork
from skeleton.app.offline_energy_hysteresis import HysteresisPolicy
from skeleton.app.offline_runtime_control import RuntimeAdmission
from skeleton.app.offline_runtime_preflight import (
    RuntimePolicy, digest, inspect_source, require, sample_hardware,
)


class OfflineRuntimeSession:
    """Explicit source inspection, live observations, release and reinspection.

    This object does not retain file descriptors or claim immutable custody
    after the source probe. A real model loader must independently verify
    the model while opening it and retain its own sealed source custody.
    """

    def __init__(self, store: Path, *, plan_digest: str, model_identity_digest: str,
                 policy: RuntimePolicy, hysteresis: HysteresisPolicy | None = None) -> None:
        require(isinstance(policy, RuntimePolicy), "runtime policy required")
        self._store = Path(store)
        self._plan_digest = plan_digest
        self._model_identity_digest = model_identity_digest
        self._policy = policy
        self._lock = threading.RLock()
        self._closed = False
        self._consumer: object | None = None
        self._source = inspect_source(self._store, plan_digest=self._plan_digest,
                                      model_identity_digest=self._model_identity_digest, policy=policy)
        self._source_digest = digest(self._source.snapshot())
        self._controller = RuntimeAdmission(self._source, policy, hysteresis_policy=(
            hysteresis or HysteresisPolicy(max_sample_age_ns=policy.sample_age_ns)))
        self._verified_ns = time.monotonic_ns()

    @property
    def policy(self) -> RuntimePolicy:
        """Immutable operator policy used by the local admission controller."""
        return self._policy

    def _open(self) -> None:
        require(not self._closed, "offline runtime session is closed")

    def claim_consumer(self) -> object:
        """Give one trusted execution owner exclusive use of this session.

        A scheduling proposal is not a physical reservation. Sharing this
        controller between independent consumers would let each consume a
        new grant while another consumer still owns active execution.
        A claimed session stays bound until closed; no transferable token
        or public receipt can restore ownership.
        """
        with self._lock:
            self._open()
            require(self._consumer is None, "offline session already has an execution owner")
            self._controller.revoke()
            self._consumer = object()
            return self._consumer

    def _authorize(self, consumer: object | None) -> None:
        require(consumer is self._consumer, "offline session execution owner mismatch")

    def revalidate_source(self, *, consumer: object | None = None) -> dict:
        """Reinspect all selected source bytes and revoke grants before the scan.

        Failure closes this session. A changed inventory cannot silently
        repin even when the selected model identity appears unchanged.
        """
        with self._lock:
            self._open()
            self._authorize(consumer)
            self._controller.revoke()
            try:
                observed = inspect_source(self._store, plan_digest=self._plan_digest,
                                          model_identity_digest=self._model_identity_digest,
                                          policy=self._policy)
                require(digest(observed.snapshot()) == self._source_digest,
                        "source evidence changed; reopen explicit pinned session")
                self._verified_ns = time.monotonic_ns()
            except BaseException:
                self._closed = True
                raise
            return {"source_digest": self._source_digest, "verified_ns": self._verified_ns,
                    "source_status": "reinspected", "native_qualified": False,
                    "release_qualified": False}

    def offer(self, work: tuple[IterationWork, ...], *, consumer: object | None = None) -> dict:
        with self._lock:
            self._open()
            self._authorize(consumer)
            try:
                observed = sample_hardware()
                require(observed.origin == "local_probe", "local probe required")
                result = self._controller.offer(observed, work, now_ns=time.monotonic_ns())
            except BaseException:
                self._controller.revoke()
                raise
            return result

    def consume(self, admission: dict, *, consumer: object | None = None) -> tuple[dict, ...]:
        """Return the exact pending sequence using the actual process clock."""
        with self._lock:
            self._open()
            self._authorize(consumer)
            return self._controller.consume(admission, now_ns=time.monotonic_ns())

    def status(self) -> dict:
        with self._lock:
            return {"closed": self._closed, "source_digest": self._source_digest,
                    "source_verified_ns": self._verified_ns,
                    "exclusive_consumer_bound": self._consumer is not None,
                    "admission": self._controller.status(),
                    "source_custody": "inspection_only_not_open_handle",
                    "native_qualified": False, "release_qualified": False}

    def close(self) -> None:
        with self._lock:
            self._controller.revoke()
            self._closed = True

    def __enter__(self) -> Self:
        with self._lock:
            self._open()
            return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
