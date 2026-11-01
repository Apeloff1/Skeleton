"""Bridge to main's existing percentile code.

We load ``skeleton/ai/runtime/observability/profiler.py`` directly from its
file so we reuse its ``Profiler.stats`` (p50/p95/p99/max) without importing the
heavy ``skeleton.ai`` / ``skeleton.ai.runtime.observability`` package
``__init__`` chains. If the file is missing we fall back to a normal import,
and fail loudly rather than silently computing our own numbers.
"""
from __future__ import annotations

import importlib
import importlib.util
import math
import sys
import unicodedata
from itertools import islice
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Iterable

MAX_SUMMARY_SAMPLES = 100_000
MAX_DURATION_MS = 1_000_000_000_000  # 31,000 years; bounds upstream sums
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
    return importlib.import_module(_MODULE_NAME)


_upstream = _load()
UpstreamProfiler = _upstream.Profiler


def percentile_summary(name: str, durations_ms: Iterable[float]) -> Dict[str, Any]:
    """Return main's ``Profiler.stats`` dict for ``durations_ms``."""
    if (type(name) is not str or not 1 <= len(name) <= 128
            or any(unicodedata.category(ch) in {"Cc", "Cf", "Zl", "Zp"} for ch in name)):
        raise ValueError("percentile name must be bounded and printable")
    values = list(islice(durations_ms, MAX_SUMMARY_SAMPLES + 1))
    if len(values) > MAX_SUMMARY_SAMPLES:
        raise ValueError("percentile sample count exceeds bound")
    normalized: list[float] = []
    for value in values:
        if type(value) not in (int, float) or value < 0:
            raise ValueError("percentile samples must be nonnegative finite numbers")
        try:
            duration = float(value)
        except (OverflowError, ValueError):
            raise ValueError("percentile samples must be nonnegative finite numbers") from None
        if not math.isfinite(duration) or duration > MAX_DURATION_MS:
            raise ValueError("percentile samples must be nonnegative finite numbers within bound")
        normalized.append(duration)
    profiler = UpstreamProfiler(max_samples_per_name=max(1, len(normalized)))
    for duration in normalized:
        profiler.record(name, duration)
    return profiler.stats(name)
