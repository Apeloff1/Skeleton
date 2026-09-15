"""
Skeleton Intelligence — quality-aware orchestration and adaptive learning.

The orchestrator is intentionally provider-agnostic. It coordinates synchronous
reasoning handlers, ranks them by configured priority plus observed quality,
tracks failures, applies circuit breaking, enforces confidence/deadline gates,
and can cache stable results. Existing two-argument ``register_handler`` and
``reason(query, context)`` calls remain valid.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from skeleton.kernel.events import EventBus


@dataclass
class ReasoningTask:
    """A single reasoning task for the orchestrator."""

    task_id: str
    query: str
    context: Dict[str, Any] = field(default_factory=dict)
    priority: int = 1
    deadline: Optional[float] = None


@dataclass
class ReasoningResult:
    """Result of a reasoning task."""

    task_id: str
    answer: Any
    confidence: float
    sources: List[str] = field(default_factory=list)
    latency_ms: float = 0.0


@dataclass
class HandlerPolicy:
    """Routing and resilience controls for one reasoning capability."""

    priority: float = 0.0
    min_confidence: Optional[float] = None
    enabled: bool = True
    failure_threshold: int = 3
    cooldown_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.min_confidence is not None and not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1")
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if self.cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must be >= 0")


@dataclass
class HandlerTelemetry:
    """Online routing telemetry used for quality-aware handler selection."""

    attempts: int = 0
    successes: int = 0
    failures: int = 0
    rejected: int = 0
    consecutive_failures: int = 0
    avg_latency_ms: float = 0.0
    avg_confidence: float = 0.0
    last_error: Optional[str] = None
    circuit_open_until: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.successes / self.attempts if self.attempts else 0.5

    def snapshot(self, now: Optional[float] = None) -> Dict[str, Any]:
        current = time.time() if now is None else now
        return {
            "attempts": self.attempts,
            "successes": self.successes,
            "failures": self.failures,
            "rejected": self.rejected,
            "consecutive_failures": self.consecutive_failures,
            "success_rate": self.success_rate,
            "avg_latency_ms": self.avg_latency_ms,
            "avg_confidence": self.avg_confidence,
            "last_error": self.last_error,
            "circuit_open": self.circuit_open_until > current,
            "circuit_open_until": self.circuit_open_until,
        }


@dataclass
class _CacheEntry:
    payload: Dict[str, Any]
    expires_at: float


class IntelligenceOrchestrator:
    """Coordinate reasoning with quality routing, fallbacks, and resilience."""

    def __init__(
        self,
        bus: Optional[EventBus] = None,
        *,
        min_confidence: float = 0.0,
        max_attempts: Optional[int] = None,
        selection_mode: str = "first_acceptable",
        result_cache_ttl_seconds: float = 0.0,
        max_cache_entries: int = 256,
    ):
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1")
        if max_attempts is not None and max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if selection_mode not in {"first_acceptable", "best_confidence"}:
            raise ValueError("selection_mode must be 'first_acceptable' or 'best_confidence'")
        if result_cache_ttl_seconds < 0:
            raise ValueError("result_cache_ttl_seconds must be >= 0")
        if max_cache_entries < 1:
            raise ValueError("max_cache_entries must be >= 1")

        self._bus = bus
        self._tasks: Dict[str, ReasoningTask] = {}
        self._results: Dict[str, ReasoningResult] = {}
        self._handlers: Dict[str, Callable[[ReasoningTask], ReasoningResult]] = {}
        self._policies: Dict[str, HandlerPolicy] = {}
        self._telemetry: Dict[str, HandlerTelemetry] = {}
        self._registration_order: Dict[str, int] = {}
        self._next_registration_order = 0
        self._min_confidence = min_confidence
        self._max_attempts = max_attempts
        self._selection_mode = selection_mode
        self._result_cache_ttl_seconds = result_cache_ttl_seconds
        self._max_cache_entries = max_cache_entries
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._stats = {
            "submitted": 0,
            "completed": 0,
            "failed": 0,
            "fallbacks": 0,
            "rejected": 0,
            "deadline_exceeded": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }

    def register_handler(
        self,
        capability: str,
        handler: Callable[[ReasoningTask], ReasoningResult],
        *,
        priority: float = 0.0,
        min_confidence: Optional[float] = None,
        enabled: bool = True,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
    ) -> None:
        """Register or replace a reasoning handler."""
        if not capability or not capability.strip():
            raise ValueError("capability must be non-empty")
        if not callable(handler):
            raise TypeError("handler must be callable")

        policy = HandlerPolicy(
            priority=priority,
            min_confidence=min_confidence,
            enabled=enabled,
            failure_threshold=failure_threshold,
            cooldown_seconds=cooldown_seconds,
        )
        with self._lock:
            if capability not in self._registration_order:
                self._registration_order[capability] = self._next_registration_order
                self._next_registration_order += 1
            self._handlers[capability] = handler
            self._policies[capability] = policy
            self._telemetry[capability] = HandlerTelemetry()

    def unregister_handler(self, capability: str) -> bool:
        """Remove a capability and its routing state."""
        with self._lock:
            existed = capability in self._handlers
            self._handlers.pop(capability, None)
            self._policies.pop(capability, None)
            self._telemetry.pop(capability, None)
            self._registration_order.pop(capability, None)
            return existed

    def set_handler_enabled(self, capability: str, enabled: bool) -> None:
        """Enable or disable a registered capability without losing telemetry."""
        with self._lock:
            if capability not in self._policies:
                raise KeyError(capability)
            self._policies[capability].enabled = enabled

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    def explain_route(self) -> List[Dict[str, Any]]:
        """Return the current deterministic routing order and health signals."""
        now = time.time()
        with self._lock:
            candidates = []
            for capability in self._handlers:
                policy = self._policies[capability]
                telemetry = self._telemetry[capability]
                candidates.append(
                    {
                        "capability": capability,
                        "score": self._route_score(capability),
                        "priority": policy.priority,
                        "enabled": policy.enabled,
                        "min_confidence": policy.min_confidence,
                        **telemetry.snapshot(now),
                    }
                )
            order = dict(self._registration_order)
        candidates.sort(key=lambda item: (-item["score"], order[item["capability"]]))
        return candidates

    def reason(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        *,
        min_confidence: Optional[float] = None,
        max_attempts: Optional[int] = None,
        deadline: Optional[float] = None,
        selection_mode: Optional[str] = None,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """Submit a reasoning query and return the best acceptable result."""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        if min_confidence is not None and not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1")
        if max_attempts is not None and max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        mode = selection_mode or self._selection_mode
        if mode not in {"first_acceptable", "best_confidence"}:
            raise ValueError("selection_mode must be 'first_acceptable' or 'best_confidence'")

        normalized_context = dict(context or {})
        task = ReasoningTask(
            task_id=str(uuid.uuid4())[:8],
            query=query,
            context=normalized_context,
            deadline=deadline,
        )
        with self._lock:
            self._tasks[task.task_id] = task
            self._stats["submitted"] += 1

        effective_min_confidence = self._min_confidence if min_confidence is None else min_confidence
        cache_key = self._cache_key(query, normalized_context, effective_min_confidence, mode)
        if use_cache and self._result_cache_ttl_seconds > 0:
            cached = self._cache_get(cache_key)
            if cached is not None:
                cached["task_id"] = task.task_id
                cached["cached"] = True
                cached["latency_ms"] = 0.0
                with self._lock:
                    self._stats["completed"] += 1
                return cached

        route = self._eligible_route()
        attempt_limit = max_attempts if max_attempts is not None else self._max_attempts
        if attempt_limit is not None:
            route = route[:attempt_limit]

        started = time.perf_counter()
        attempts: List[Dict[str, Any]] = []
        accepted: List[Tuple[str, ReasoningResult]] = []

        for capability in route:
            if deadline is not None and time.time() >= deadline:
                with self._lock:
                    self._stats["deadline_exceeded"] += 1
                attempts.append({"handler": capability, "status": "deadline_exceeded"})
                self._emit(
                    "intelligence.reasoning.deadline_exceeded",
                    {"task_id": task.task_id, "capability": capability, "attempts": len(attempts) - 1},
                )
                break

            handler = self._handlers[capability]
            handler_started = time.perf_counter()
            try:
                result = handler(task)
                handler_latency_ms = (time.perf_counter() - handler_started) * 1000.0
                self._validate_result(result)
                result.latency_ms = handler_latency_ms
                threshold = self._handler_threshold(capability, effective_min_confidence)

                if result.confidence < threshold:
                    self._record_rejection(capability, result, handler_latency_ms)
                    attempts.append(
                        {
                            "handler": capability,
                            "status": "rejected",
                            "confidence": result.confidence,
                            "required_confidence": threshold,
                        }
                    )
                    with self._lock:
                        self._stats["rejected"] += 1
                    self._emit(
                        "intelligence.reasoning.rejected",
                        {
                            "task_id": task.task_id,
                            "capability": capability,
                            "confidence": result.confidence,
                            "required_confidence": threshold,
                        },
                    )
                    continue

                self._record_success(capability, result, handler_latency_ms)
                attempts.append(
                    {"handler": capability, "status": "accepted", "confidence": result.confidence}
                )
                accepted.append((capability, result))
                if mode == "first_acceptable":
                    break
            except Exception as exc:
                handler_latency_ms = (time.perf_counter() - handler_started) * 1000.0
                self._record_failure(capability, exc, handler_latency_ms)
                attempts.append(
                    {
                        "handler": capability,
                        "status": "failed",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
                self._emit(
                    "intelligence.reasoning.handler_failed",
                    {
                        "task_id": task.task_id,
                        "capability": capability,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )

        if accepted:
            capability, result = (
                max(accepted, key=lambda item: item[1].confidence)
                if mode == "best_confidence"
                else accepted[0]
            )
            total_latency_ms = (time.perf_counter() - started) * 1000.0
            result.latency_ms = total_latency_ms
            with self._lock:
                self._results[task.task_id] = result
                self._stats["completed"] += 1
                chosen_index = next(
                    (
                        index
                        for index, attempt in enumerate(attempts)
                        if attempt.get("handler") == capability and attempt.get("status") == "accepted"
                    ),
                    0,
                )
                if any(
                    attempt.get("status") in {"failed", "rejected"}
                    for attempt in attempts[:chosen_index]
                ):
                    self._stats["fallbacks"] += 1
            payload = {
                "answer": result.answer,
                "confidence": result.confidence,
                "sources": list(result.sources),
                "latency_ms": total_latency_ms,
                "handler": capability,
                "task_id": task.task_id,
                "attempts": attempts,
                "cached": False,
            }
            self._emit(
                "intelligence.reasoning.completed",
                {
                    "task_id": task.task_id,
                    "capability": capability,
                    "confidence": result.confidence,
                    "latency_ms": total_latency_ms,
                    "attempt_count": len(attempts),
                },
            )
            if use_cache and self._result_cache_ttl_seconds > 0:
                self._cache_put(cache_key, payload)
            return payload

        with self._lock:
            self._stats["failed"] += 1
        error = "No handler produced an acceptable result"
        if not route:
            error = "No eligible reasoning handlers are available"
        return {
            "error": error,
            "task_id": task.task_id,
            "attempts": attempts,
            "cached": False,
        }

    def stats(self) -> Dict[str, Any]:
        """Return aggregate and per-handler orchestration telemetry."""
        now = time.time()
        with self._lock:
            return {
                **self._stats,
                "handlers": {
                    capability: telemetry.snapshot(now)
                    for capability, telemetry in self._telemetry.items()
                },
                "cache_entries": len(self._cache),
            }

    def _eligible_route(self) -> List[str]:
        now = time.time()
        with self._lock:
            candidates = [
                capability
                for capability, policy in self._policies.items()
                if policy.enabled and self._telemetry[capability].circuit_open_until <= now
            ]
            candidates.sort(
                key=lambda capability: (
                    -self._route_score(capability),
                    self._registration_order[capability],
                )
            )
            return candidates

    def _route_score(self, capability: str) -> float:
        policy = self._policies[capability]
        telemetry = self._telemetry[capability]
        if telemetry.attempts == 0:
            quality = 0.5
        else:
            quality = 0.65 * telemetry.success_rate + 0.35 * telemetry.avg_confidence
        latency_penalty = min(0.25, telemetry.avg_latency_ms / 20_000.0) if telemetry.attempts else 0.0
        return policy.priority + quality - latency_penalty

    def _handler_threshold(self, capability: str, global_threshold: float) -> float:
        handler_threshold = self._policies[capability].min_confidence
        return max(global_threshold, handler_threshold if handler_threshold is not None else 0.0)

    @staticmethod
    def _validate_result(result: ReasoningResult) -> None:
        if not isinstance(result, ReasoningResult):
            raise TypeError("reasoning handler must return ReasoningResult")
        if not isinstance(result.confidence, (int, float)):
            raise TypeError("result confidence must be numeric")
        if not 0.0 <= float(result.confidence) <= 1.0:
            raise ValueError("result confidence must be between 0 and 1")
        if result.sources is None:
            result.sources = []

    def _record_success(self, capability: str, result: ReasoningResult, latency_ms: float) -> None:
        with self._lock:
            telemetry = self._telemetry[capability]
            telemetry.attempts += 1
            telemetry.successes += 1
            telemetry.consecutive_failures = 0
            telemetry.last_error = None
            telemetry.circuit_open_until = 0.0
            telemetry.avg_latency_ms = self._running_average(
                telemetry.avg_latency_ms, latency_ms, telemetry.attempts
            )
            telemetry.avg_confidence = self._running_average(
                telemetry.avg_confidence, float(result.confidence), telemetry.successes
            )

    def _record_rejection(self, capability: str, result: ReasoningResult, latency_ms: float) -> None:
        with self._lock:
            telemetry = self._telemetry[capability]
            telemetry.attempts += 1
            telemetry.rejected += 1
            telemetry.consecutive_failures = 0
            telemetry.avg_latency_ms = self._running_average(
                telemetry.avg_latency_ms, latency_ms, telemetry.attempts
            )
            observed = telemetry.successes + telemetry.rejected
            telemetry.avg_confidence = self._running_average(
                telemetry.avg_confidence, float(result.confidence), observed
            )

    def _record_failure(self, capability: str, exc: Exception, latency_ms: float) -> None:
        circuit_opened = False
        cooldown_seconds = 0.0
        failures = 0
        with self._lock:
            telemetry = self._telemetry[capability]
            policy = self._policies[capability]
            telemetry.attempts += 1
            telemetry.failures += 1
            telemetry.consecutive_failures += 1
            telemetry.last_error = f"{type(exc).__name__}: {exc}"
            telemetry.avg_latency_ms = self._running_average(
                telemetry.avg_latency_ms, latency_ms, telemetry.attempts
            )
            if telemetry.consecutive_failures >= policy.failure_threshold:
                telemetry.circuit_open_until = time.time() + policy.cooldown_seconds
                circuit_opened = True
                cooldown_seconds = policy.cooldown_seconds
                failures = telemetry.consecutive_failures
        if circuit_opened:
            self._emit(
                "intelligence.reasoning.circuit_opened",
                {
                    "capability": capability,
                    "failures": failures,
                    "cooldown_seconds": cooldown_seconds,
                },
            )

    @staticmethod
    def _running_average(current: float, new_value: float, count: int) -> float:
        return new_value if count <= 1 else current + (new_value - current) / count

    def _cache_key(
        self,
        query: str,
        context: Dict[str, Any],
        min_confidence: float,
        selection_mode: str,
    ) -> str:
        try:
            context_blob = json.dumps(context, sort_keys=True, separators=(",", ":"), default=repr)
        except (TypeError, ValueError):
            context_blob = repr(sorted(context.items(), key=lambda item: str(item[0])))
        payload = f"v2\0{query}\0{context_blob}\0{min_confidence:.6f}\0{selection_mode}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _cache_get(self, key: str) -> Optional[Dict[str, Any]]:
        now = time.time()
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._stats["cache_misses"] += 1
                return None
            if entry.expires_at <= now:
                self._cache.pop(key, None)
                self._stats["cache_misses"] += 1
                return None
            self._cache.move_to_end(key)
            self._stats["cache_hits"] += 1
            return dict(entry.payload)

    def _cache_put(self, key: str, payload: Dict[str, Any]) -> None:
        with self._lock:
            cached_payload = dict(payload)
            cached_payload.pop("attempts", None)
            self._cache[key] = _CacheEntry(
                payload=cached_payload,
                expires_at=time.time() + self._result_cache_ttl_seconds,
            )
            self._cache.move_to_end(key)
            while len(self._cache) > self._max_cache_entries:
                self._cache.popitem(last=False)

    def _emit(self, topic: str, payload: Dict[str, Any]) -> None:
        if self._bus is None:
            return
        try:
            self._bus.emit(topic, payload)
        except Exception:
            return


@dataclass
class MetaGrid:
    """Hyperparameter grid for adaptive learning."""

    learning_rate: float = 0.01
    exploration_rate: float = 0.1
    discount_factor: float = 0.95
    batch_size: int = 32
    memory_window: int = 1000

    def to_dict(self) -> Dict[str, Any]:
        return {
            "learning_rate": self.learning_rate,
            "exploration_rate": self.exploration_rate,
            "discount_factor": self.discount_factor,
            "batch_size": self.batch_size,
            "memory_window": self.memory_window,
        }


def default_meta_grid() -> MetaGrid:
    return MetaGrid()


class AdaptiveLearner:
    """Meta-learning system that improves capabilities over time."""

    def __init__(self, grid: MetaGrid, bus: Optional[EventBus] = None):
        self.grid = grid
        self._bus = bus
        self._experience: List[Dict[str, Any]] = []
        self._capability_scores: Dict[str, float] = {}
        self._stats = {"updates": 0, "experiences": 0}

    def record_experience(
        self,
        capability: str,
        input_data: Any,
        outcome: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a learning experience."""
        self._experience.append(
            {
                "capability": capability,
                "input": input_data,
                "outcome": outcome,
                "metadata": metadata or {},
                "timestamp": time.time(),
            }
        )
        self._stats["experiences"] += 1

        alpha = self.grid.learning_rate
        current = self._capability_scores.get(capability, 0.5)
        self._capability_scores[capability] = current + alpha * (outcome - current)

        if self._bus:
            self._bus.emit(
                "intelligence.learning.experience",
                {
                    "capability": capability,
                    "outcome": outcome,
                    "score": self._capability_scores[capability],
                },
            )

    def adapt(self, capability: str) -> Dict[str, Any]:
        """Adapt learning parameters based on recent performance."""
        recent = [
            e
            for e in self._experience[-self.grid.memory_window :]
            if e["capability"] == capability
        ]
        if not recent:
            return {"status": "no_data", "capability": capability}

        outcomes = [e["outcome"] for e in recent]
        avg_outcome = sum(outcomes) / len(outcomes)

        if len(outcomes) > 10:
            import statistics

            try:
                variance = statistics.variance(outcomes)
                if variance > 0.1:
                    self.grid.exploration_rate = min(0.5, self.grid.exploration_rate * 1.1)
                else:
                    self.grid.exploration_rate = max(0.01, self.grid.exploration_rate * 0.95)
            except statistics.StatisticsError:
                pass

        self._stats["updates"] += 1

        return {
            "capability": capability,
            "avg_outcome": avg_outcome,
            "exploration_rate": self.grid.exploration_rate,
            "score": self._capability_scores.get(capability, 0.5),
            "experiences": len(recent),
        }

    def best_capability(self) -> Optional[str]:
        """Return the highest-scoring capability."""
        if not self._capability_scores:
            return None
        return max(self._capability_scores.items(), key=lambda x: x[1])[0]

    def stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "capabilities": len(self._capability_scores),
            "scores": dict(self._capability_scores),
        }
