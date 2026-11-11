"""Bridge to main's existing percentile code.

We load ``skeleton/ai/runtime/observability/profiler.py`` directly from its
file so we reuse its ``Profiler.stats`` (p50/p95/p99/max) without importing the
heavy ``skeleton.ai`` / ``skeleton.ai.runtime.observability`` package
``__init__`` chains. If the file is missing we fall back to a normal import,
and fail loudly rather than silently computing our own numbers.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Iterable

_MODULE_NAME = "skeleton.ai.runtime.observability.profiler"
_REL = Path("ai") / "runtime" / "observability" / "profiler.py"


def _load() -> ModuleType:
    cached = sys.modules.get(_MODULE_NAME)
    if cached is not None:
        return cached
    path = Path(__file__).resolve().parent.parent / _REL
    if path.is_file():
        spec = importlib.util.spec_from_file_location("_perf_profiler_upstream_profiler", path)
        if spec is None or spec.loader is None:  # pragma: no cover - defensive
            raise ImportError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        # dataclasses resolves annotations via sys.modules[cls.__module__].
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(spec.name, None)
            raise
        return module
    from skeleton.ai.runtime.observability import profiler as upstream
    return upstream


_upstream = _load()
UpstreamProfiler = _upstream.Profiler


def percentile_summary(name: str, durations_ms: Iterable[float]) -> Dict[str, Any]:
    """Return main's ``Profiler.stats`` dict for ``durations_ms``."""
    values = list(durations_ms)
    profiler = UpstreamProfiler(max_samples_per_name=max(1, len(values)))
    for value in values:
        profiler.record(name, float(value))
    return profiler.stats(name)
