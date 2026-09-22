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
        if not support_set:
            embedding = Tensor.zeros(self.parameter_dim)
        else:
            # Extract numeric features and compute statistics
            features: List[List[float]] = []
            for example in support_set:
                numeric = [v for v in example.values() if isinstance(v, (int, float))]
                if numeric:
                    features.append(numeric)

            if not features:
                embedding = Tensor.zeros(self.parameter_dim)
            else:
                # Flatten and pad/truncate to parameter_dim
                flat = [f for feat in features for f in feat]
                if len(flat) < self.parameter_dim:
                    flat.extend([0.0] * (self.parameter_dim - len(flat)))
                else:
                    flat = flat[:self.parameter_dim]
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

        # Inner loop: gradient steps on support set
        for _ in range(self.inner_steps):
            if not task.support_set:
                break
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
                        "final_loss": loss_fn(params, random.choice(task.support_set)) if task.support_set else 0,
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
