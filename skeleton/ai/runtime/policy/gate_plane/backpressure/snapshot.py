"""Pressure snapshot model shared by the Pack F gate plane and Backend's Pack H.

Contract (agreed with Backend for Pack H, ``schema_version`` 1)::

    {"schema_version": 1, "load": 0.0-1.0, "queue_depth": int,
     "max_queue_depth": int, "tenant_queue_depth": int | null,
     "retry_after_s": float, "state": "open" | "throttle" | "shed",
     "observed_at": ISO-8601}

* ``open``      load < 0.7
* ``throttle``  0.7 <= load < 0.95, or any non-zero ``retry_after_s``
* ``shed``      load >= 0.95, or the queue is full

``retry_after_s`` uses the same name and two-decimal rounding as
``RateLimitError`` in ``skeleton/api/middleware.py``; HTTP callers get it as
``Retry-After`` rounded *up* to whole seconds.

The gate plane never trusts a snapshot blindly: :func:`coerce_view` refuses
any schema other than 1 and :meth:`PressureView.effective_state` takes the
stricter of the reported state and the state derived from the numbers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Mapping, Optional

SCHEMA_VERSION = 1
THROTTLE_AT = 0.7
SHED_AT = 0.95

_FIELDS = (
    "schema_version",
    "load",
    "queue_depth",
    "max_queue_depth",
    "tenant_queue_depth",
    "retry_after_s",
    "state",
    "observed_at",
)


class PressureState(str, Enum):
    OPEN = "open"
    THROTTLE = "throttle"
    SHED = "shed"

    @property
    def severity(self) -> int:
        return {"open": 0, "throttle": 1, "shed": 2}[self.value]


class PressureUnavailable(Exception):
    """A pressure source could not produce a usable snapshot."""


class SchemaMismatch(PressureUnavailable):
    """Snapshot ``schema_version`` is not one this gate plane understands."""


def round_retry_after(value: float) -> float:
    return round(max(0.0, float(value)), 2)


def retry_after_header(seconds: float) -> str:
    """``Retry-After`` header value: whole seconds, rounded up, minimum 1."""
    return str(max(1, int(math.ceil(max(0.0, float(seconds))))))


def derive_state(
    load: float,
    queue_depth: int,
    max_queue_depth: int,
    retry_after_s: float,
    tenant_queue_depth: Optional[int] = None,
    max_tenant_queue_depth: Optional[int] = None,
) -> PressureState:
    full = max_queue_depth > 0 and queue_depth >= max_queue_depth
    tenant_full = (
        tenant_queue_depth is not None
        and max_tenant_queue_depth is not None
        and max_tenant_queue_depth > 0
        and tenant_queue_depth >= max_tenant_queue_depth
    )
    if load >= SHED_AT or full or tenant_full:
        return PressureState.SHED
    if load >= THROTTLE_AT or retry_after_s > 0:
        return PressureState.THROTTLE
    return PressureState.OPEN


def iso_now(epoch_s: float) -> str:
    return datetime.fromtimestamp(epoch_s, tz=timezone.utc).isoformat()


def parse_iso(value: str) -> float:
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


@dataclass(frozen=True)
class PressureView:
    schema_version: int
    load: float
    queue_depth: int
    max_queue_depth: int
    tenant_queue_depth: Optional[int]
    retry_after_s: float
    state: PressureState
    observed_at: str
    source: str = "unknown"

    @property
    def queue_full(self) -> bool:
        return self.max_queue_depth > 0 and self.queue_depth >= self.max_queue_depth

    @property
    def derived_state(self) -> PressureState:
        return derive_state(self.load, self.queue_depth, self.max_queue_depth, self.retry_after_s)

    @property
    def effective_state(self) -> PressureState:
        a, b = self.state, self.derived_state
        return a if a.severity >= b.severity else b

    def age_s(self, now_epoch_s: float) -> float:
        try:
            return max(0.0, now_epoch_s - parse_iso(self.observed_at))
        except (TypeError, ValueError):
            return float("inf")

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "load": self.load,
            "queue_depth": self.queue_depth,
            "max_queue_depth": self.max_queue_depth,
            "tenant_queue_depth": self.tenant_queue_depth,
            "retry_after_s": self.retry_after_s,
            "state": self.state.value,
            "observed_at": self.observed_at,
        }


def _get(obj: Any, name: str) -> Any:
    if isinstance(obj, Mapping):
        if name not in obj:
            raise PressureUnavailable(f"snapshot missing field {name!r}")
        return obj[name]
    if not hasattr(obj, name):
        raise PressureUnavailable(f"snapshot missing field {name!r}")
    return getattr(obj, name)


def coerce_view(raw: Any, *, source: str) -> PressureView:
    """Validate a Pack H snapshot (object, dataclass or mapping) into a view."""
    if raw is None:
        raise PressureUnavailable("empty snapshot")
    if not isinstance(raw, Mapping):
        for attr in ("as_dict", "to_dict", "model_dump", "dict"):
            fn = getattr(raw, attr, None)
            if callable(fn) and not all(hasattr(raw, f) for f in _FIELDS):
                try:
                    candidate = fn()
                except Exception:  # noqa: BLE001
                    continue
                if isinstance(candidate, Mapping):
                    raw = candidate
                    break
    version = _get(raw, "schema_version")
    if isinstance(version, bool) or version != SCHEMA_VERSION:
        raise SchemaMismatch(f"unsupported schema_version {version!r}")
    try:
        load = float(_get(raw, "load"))
        queue_depth = int(_get(raw, "queue_depth"))
        max_queue_depth = int(_get(raw, "max_queue_depth"))
        tqd_raw = _get(raw, "tenant_queue_depth")
        tenant_queue_depth = None if tqd_raw is None else int(tqd_raw)
        retry_after = float(_get(raw, "retry_after_s"))
        state_raw = _get(raw, "state")
        state = PressureState(getattr(state_raw, "value", state_raw))
        obs_raw = _get(raw, "observed_at")
        observed_at = obs_raw.isoformat() if isinstance(obs_raw, datetime) else str(obs_raw)
    except PressureUnavailable:
        raise
    except (TypeError, ValueError) as exc:
        raise PressureUnavailable(f"malformed snapshot: {exc}") from exc
    if math.isnan(load) or math.isnan(retry_after) or math.isinf(retry_after):
        raise PressureUnavailable("non-finite load/retry_after_s")
    if queue_depth < 0 or max_queue_depth < 0 or (tenant_queue_depth is not None and tenant_queue_depth < 0):
        raise PressureUnavailable("negative queue depth")
    return PressureView(
        schema_version=SCHEMA_VERSION,
        load=min(1.0, max(0.0, load)),
        queue_depth=queue_depth,
        max_queue_depth=max_queue_depth,
        tenant_queue_depth=tenant_queue_depth,
        retry_after_s=round_retry_after(retry_after),
        state=state,
        observed_at=observed_at,
        source=source,
    )


__all__ = [
    "PressureState",
    "PressureUnavailable",
    "PressureView",
    "SCHEMA_VERSION",
    "SHED_AT",
    "SchemaMismatch",
    "THROTTLE_AT",
    "coerce_view",
    "derive_state",
    "iso_now",
    "parse_iso",
    "retry_after_header",
    "round_retry_after",
]
