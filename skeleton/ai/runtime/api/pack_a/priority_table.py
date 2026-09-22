"""API compatibility facade for the Pack A priority catalog."""

from skeleton.kernel.pack_a.priority_table import (
    PRIORITY_TABLE,
    entries_for_class,
    priority_for_path,
    route_class_for_path,
    table_size,
)

__all__ = [
    "PRIORITY_TABLE",
    "entries_for_class",
    "priority_for_path",
    "route_class_for_path",
    "table_size",
]
