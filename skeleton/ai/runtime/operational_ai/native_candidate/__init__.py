"""Candidate-only, source-bound native AI training. Never mutates serving weights."""
from .records import TrainingExample
from .catalog import iter_examples, inventory
from .plan import TrainingPlan
__all__ = ["TrainingExample", "iter_examples", "inventory", "TrainingPlan"]
