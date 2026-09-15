"""
Skeleton Intelligence — Orchestrator and adaptive learning

Provides:
- IntelligenceOrchestrator: Coordinate reasoning tasks across subsystems
- AdaptiveLearner: Meta-learning grid for capability improvement
- default_meta_grid: Default learning hyperparameters
"""

from __future__ import annotations

import time
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


class IntelligenceOrchestrator:
    """Coordinate reasoning tasks across memory, swarm, and cortex."""

    def __init__(self, bus: Optional[EventBus] = None):
        self._bus = bus
        self._tasks: Dict[str, ReasoningTask] = {}
        self._results: Dict[str, ReasoningResult] = {}
        self._handlers: Dict[str, Callable[[ReasoningTask], ReasoningResult]] = {}
        self._stats = {"submitted": 0, "completed": 0, "failed": 0}

    def register_handler(self, capability: str, handler: Callable[[ReasoningTask], ReasoningResult]) -> None:
        """Register a handler for a specific capability."""
        self._handlers[capability] = handler

    def reason(self, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Submit a reasoning query and return the result."""
        import uuid
        task = ReasoningTask(
            task_id=str(uuid.uuid4())[:8],
            query=query,
            context=context or {},
        )
        self._tasks[task.task_id] = task
        self._stats["submitted"] += 1
        
        start = time.time()
        
        # Try each handler until one succeeds
        for capability, handler in self._handlers.items():
            try:
                result = handler(task)
                result.latency_ms = (time.time() - start) * 1000
                self._results[task.task_id] = result
                self._stats["completed"] += 1
                
                if self._bus:
                    self._bus.emit("intelligence.reasoning.completed", {
                        "task_id": task.task_id,
                        "capability": capability,
                        "confidence": result.confidence,
                        "latency_ms": result.latency_ms,
                    })
                
                return {
                    "answer": result.answer,
                    "confidence": result.confidence,
                    "sources": result.sources,
                    "latency_ms": result.latency_ms,
                    "handler": capability,
                }
            except Exception as e:
                continue
        
        self._stats["failed"] += 1
        return {"error": "No handler could process the query", "task_id": task.task_id}

    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)


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

    def record_experience(self, capability: str, input_data: Any, outcome: float, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Record a learning experience."""
        self._experience.append({
            "capability": capability,
            "input": input_data,
            "outcome": outcome,
            "metadata": metadata or {},
            "timestamp": time.time(),
        })
        self._stats["experiences"] += 1
        
        # Update running score for capability
        alpha = self.grid.learning_rate
        current = self._capability_scores.get(capability, 0.5)
        self._capability_scores[capability] = current + alpha * (outcome - current)
        
        if self._bus:
            self._bus.emit("intelligence.learning.experience", {
                "capability": capability,
                "outcome": outcome,
                "score": self._capability_scores[capability],
            })

    def adapt(self, capability: str) -> Dict[str, Any]:
        """Adapt learning parameters based on recent performance."""
        recent = [e for e in self._experience[-self.grid.memory_window:] if e["capability"] == capability]
        if not recent:
            return {"status": "no_data", "capability": capability}
        
        outcomes = [e["outcome"] for e in recent]
        avg_outcome = sum(outcomes) / len(outcomes)
        
        # Adjust exploration based on performance variance
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
