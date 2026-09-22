"""Data accessors — uniform read helpers used across blueprints.

Materialised blueprints often need typed dict traversals; accessors
return nested values from the blueprint-registry object type
without adhoc getitem calls per caller.

- :class:`Accessor` — dict-backed key/chain helpers
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


class Accessor:
    """Nested dict helper: get via key path with default."""

    def __init__(self, data: Dict[str, Any]) -> None:
        self._data = data

    def chain(self, *keys: str, default: Any = None) -> Any:
        node = self._data
        for key in keys:
            if not isinstance(node, dict):
                return default
            node = node.get(key)
            if node is None:
                return default
        return node

    def present(self, *keys: str) -> bool:
        return self.chain(*keys) is not None

    def key(self, name: str, default: Any = None) -> Any:
        return self._data.get(name, default)

    def nested_items(self, prefix: str) -> List[str]:
        node = self._data.get(prefix, {})
        return list(node) if isinstance(node, dict) else []
