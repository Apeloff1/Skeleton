"""datetime.UTC compatibility for Python 3.10 and earlier.
Import UTC from here instead of datetime when targeting 3.10.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone

try:
    from datetime import UTC  # type: ignore[attr-defined]
except ImportError:
    UTC = timezone.utc  # type: ignore[assignment]

__all__ = ["UTC", "datetime", "timedelta", "timezone"]
