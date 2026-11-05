"""Execution spine: durable, bounded, owner-scoped, model-neutral AI operations.

This package intentionally never loads remote providers or executes model-supplied
commands. The sole generation side effect happens through a caller-supplied,
model-pinned backend. Every durable transition lives in one SQLite transaction.
"""
from .contracts import Identity, InferenceRequest, GenerationReceipt, SpineLimits, SpineError
from .database import SpineDatabase
from .coordinator import ExecutionSpine
__all__ = ["Identity","InferenceRequest","GenerationReceipt","SpineLimits","SpineError","SpineDatabase","ExecutionSpine"]
