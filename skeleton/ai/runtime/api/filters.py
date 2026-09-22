"""Filter parsing — turn `?filter=field:op:value` into structured terms."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

from skeleton.api.middleware import MiddlewareError


class FilterError(MiddlewareError):
    code = "API.FILTER"


class FilterOperation(str, Enum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    LT = "lt"
    GTE = "gte"
    LTE = "lte"
    CONTAINS = "contains"


@dataclass(frozen=True)
class Filter:
    field: str
    op: FilterOperation
    value: str


class FilterParser:
    """Parse comma-separated field:op:value query into filters."""

    OPERATIONS = set(op.value for op in FilterOperation)

    def parse(self, raw: Optional[str]) -> Tuple[Filter, ...]:
        if not raw:
            return tuple()
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        out: List[Filter] = []
        for part in parts:
            chunks = part.split(":", 2)
            if len(chunks) < 3:
                raise FilterError("filter must be field:op:value", context={"filter": part})
            field, op, value = chunks
            if op not in self.OPERATIONS:
                raise FilterError("unknown operator", context={"op": op})
            out.append(Filter(field=field, op=FilterOperation(op), value=value))
        return tuple(out)
