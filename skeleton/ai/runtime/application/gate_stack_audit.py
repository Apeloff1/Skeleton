"""Import-free audit of ``install_gate`` middleware registration order.

Starlette ``add_middleware`` is LIFO: the last registered class is outermost.
This snapshot reports inner-first registration and the derived outer-first
runtime stack without importing the API package.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import install_gate_middleware_order
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


GATE_STACK_AUDIT_KIND: Final = "gate_stack_audit"


def gate_stack_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable install_gate middleware-order audit."""

    inner_first = install_gate_middleware_order()
    rows: list[dict[str, object]] = []
    total = len(inner_first)
    for index, name in enumerate(inner_first):
        rows.append(
            {
                "layer": name,
                "register_index": index,
                "outer_index": total - 1 - index,
                "outermost": index == total - 1,
                "innermost": index == 0,
            }
        )
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": GATE_STACK_AUDIT_KIND,
        "layers": rows,
        "inner_first": inner_first,
        "outer_first": list(reversed(inner_first)),
    }


def get_gate_stack_audit_row(layer_id: str) -> dict[str, object]:
    """Return one gate-stack audit row by middleware class name."""

    if not isinstance(layer_id, str):
        raise TypeError("layer_id must be a string")
    normalized = layer_id.strip()
    if not normalized:
        raise ValueError("layer_id must not be empty")
    for row in gate_stack_audit_snapshot()["layers"]:
        if row["layer"] == normalized:
            return dict(row)
    raise KeyError(f"unknown layer: {normalized}")
