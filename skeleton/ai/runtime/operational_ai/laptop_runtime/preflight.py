"""Canonical finite native request shape before GGUF activation or private I/O.

A syntactically admissible resource reservation is not actual CPU, RAM,
WSL2, GPU, model-rights or device qualification. The source-bound installer
and isolated native backend retain the final admission authority.
"""
from __future__ import annotations

from .contracts import refuse, nonnegative


def validate_native_shape(
    *,
    n_ctx: int,
    max_new_tokens: int,
    n_threads: int,
    gpu_layers: int,
    capacity_budget_bytes: int,
    capacity_slots: int = 1,
    inference_ms: int = 90000,
) -> None:
    """Reject impossible model limits without starting or opening anything."""
    for label, value, low, high in (
        ("context", n_ctx, 128, 131072),
        ("output tokens", max_new_tokens, 1, 8192),
        ("CPU threads", n_threads, 1, 64),
        ("GPU offload layers", gpu_layers, 0, 128),
        ("capacity bytes", capacity_budget_bytes, 1, 20000000000),
        ("capacity slots", capacity_slots, 1, 64),
        ("native inference timeout", inference_ms, 100, 600000),
    ):
        nonnegative(value, maximum=high)
        if value < low:
            refuse("invalid finite native " + label)
    if max_new_tokens >= n_ctx:
        refuse("native output tokens must fit the context reservation")


__all__ = ["validate_native_shape"]
