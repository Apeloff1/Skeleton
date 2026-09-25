"""Meta-Learning — split from the intelligence monolith (v16.2)."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus

from ._tensor import Tensor

# =============================================================================
# 3. META-LEARNING
# =============================================================================

@dataclass
class TaskEmbedding:
    """Embedding vector representing a task."""
    task_id: str
    embedding: Tensor
    support_set: List[Dict[str, Any]] = field(default_factory=list)
    query_set: List[Dict[str, Any]] = field(default_factory=list)


class MetaLearner:
    """
    Model-Agnostic Meta-Learning (MAML) style adaptation.
    Features:
      - Task embedding generation
      - Few-shot gradient updates
      - Rapid domain transfer
      - Meta-parameter management
    """

    def __init__(self, parameter_dim: int = 128, bus: Optional[EventBus] = None) -> None:
        if isinstance(parameter_dim, bool) or not isinstance(parameter_dim, int) or parameter_dim < 1:
            raise ValueError("parameter_dim must be a positive integer")
        self.parameter_dim = parameter_dim
        self.meta_parameters = Tensor.random(parameter_dim)
        self.task_embeddings: Dict[str, TaskEmbedding] = {}
        self.learning_rate = 0.01
        self.inner_steps = 5
        self._bus = bus

    def embed_task(self, support_set: List[Dict[str, Any]], task_id: str) -> TaskEmbedding:
        """
        Generate task embedding from support set.
        Uses simple feature statistics as embedding.
        """
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task id is required")
        if not isinstance(support_set, list) or not support_set:
            raise ValueError("support set is required")
        flat: List[float] = []
        for example in support_set:
            if not isinstance(example, dict):
                raise ValueError("support example must be an object")
            numeric: List[float] = []
            for value in example.values():
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                if value != value or value in (float("inf"), float("-inf")):
                    raise ValueError("support features must be finite")
                numeric.append(float(value))
            if not numeric:
                raise ValueError("support example needs a finite number")
            flat.extend(numeric)
        if len(flat) != self.parameter_dim:
            raise ValueError("support features must match the parameter dimension")
        embedding = Tensor(flat, (self.parameter_dim,))

        task_emb = TaskEmbedding(
            task_id=task_id,
            embedding=embedding,
            support_set=support_set,
        )
        self.task_embeddings[task_id] = task_emb
        return task_emb

    def adapt(
        self,
        task_id: str,
        loss_fn: Callable[[Tensor, Dict[str, Any]], float],
    ) -> Tensor:
        """
        Adapt meta-parameters to a specific task using gradient descent.
        Returns adapted parameters.
        """
        if task_id not in self.task_embeddings:
            raise ValueError(f"Task {task_id} not embedded")

        task = self.task_embeddings[task_id]
        params = Tensor(self.meta_parameters.data.copy(), self.meta_parameters.shape)

        if not task.support_set:
            raise ValueError("support set is required")
        # Inner loop: gradient steps on support set
        for _ in range(self.inner_steps):
            # Compute gradient on random support example
            example = random.choice(task.support_set)
            loss = loss_fn(params, example)
            # Numerical gradient (simplified)
            grad = self._numerical_gradient(params, lambda p: loss_fn(p, example))
            # Update
            params = Tensor(
                [p - self.learning_rate * g for p, g in zip(params.data, grad.data)],
                params.shape,
            )

        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="meta.adaptation.complete",
                    payload={
                        "task_id": task_id,
                        "inner_steps": self.inner_steps,
                        "final_loss": loss_fn(params, task.support_set[-1]),
                    },
                    correlation_id=f"meta_{task_id}",
                )
            )

        return params

    def _numerical_gradient(
        self,
        params: Tensor,
        loss_fn: Callable[[Tensor], float],
        epsilon: float = 1e-5,
    ) -> Tensor:
        """Compute numerical gradient."""
        if isinstance(epsilon, bool) or not isinstance(epsilon, (int, float)) or float(epsilon) == 0.0:
            raise ValueError("epsilon must be a non-zero number")
        grad = []
        for i in range(len(params.data)):
            params_plus = Tensor(params.data.copy(), params.shape)
            params_plus.data[i] += epsilon
            params_minus = Tensor(params.data.copy(), params.shape)
            params_minus.data[i] -= epsilon
            grad.append((loss_fn(params_plus) - loss_fn(params_minus)) / (2 * epsilon))
        return Tensor(grad, params.shape)

    def transfer(
        self,
        source_task_id: str,
        target_task_id: str,
        target_support: List[Dict[str, Any]],
    ) -> Tensor:
        """
        Transfer knowledge from source task to target task.
        Uses source adapted parameters as initialization.
        """
        # Embed target task
        self.embed_task(target_support, target_task_id)

        # Get source adapted parameters
        source_params = self.adapt(source_task_id, lambda p, e: self._default_loss(p, e))

        # Use as initialization for target
        self.meta_parameters = source_params
        return self.adapt(target_task_id, lambda p, e: self._default_loss(p, e))

    def _default_loss(self, params: Tensor, example: Dict[str, Any]) -> float:
        """Default loss: MSE between parameter dot product and target."""
        target = example.get("target", 0.0)
        features = [v for v in example.values() if isinstance(v, (int, float)) and v != target]
        if not features:
            return 0.0
        # Pad/truncate features
        if len(features) < len(params.data):
            features.extend([0.0] * (len(params.data) - len(features)))
        else:
            features = features[:len(params.data)]
        prediction = sum(p * f for p, f in zip(params.data, features))
        return (prediction - target) ** 2
