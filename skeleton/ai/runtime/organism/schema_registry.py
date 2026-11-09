"""Schema registry — versioned data schemas with validation and migration.

Provides a central schema registry for all subsystem data models.
Supports JSON Schema-style validation, versioned schemas, and
automatic migration paths between versions.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


class SchemaRegistry:
    """Versioned schema registry with validation and migration."""

    def __init__(self):
        self._schemas: Dict[str, Dict[int, Dict[str, Any]]] = {}
        self._migrations: Dict[str, Dict[int, Callable[[Any], Any]]] = {}
        self._validators: Dict[str, Callable[[Any], List[str]]] = {}

    def register(self, name: str, version: int, schema: Dict[str, Any], validator: Optional[Callable[[Any], List[str]]] = None) -> None:
        self._schemas.setdefault(name, {})[version] = schema
        if validator:
            self._validators[name] = validator

    def register_migration(self, name: str, from_version: int, to_version: int, fn: Callable[[Any], Any]) -> None:
        self._migrations.setdefault(name, {})[from_version] = fn

    def validate(self, name: str, data: Any, version: Optional[int] = None) -> List[str]:
        versions = self._schemas.get(name, {})
        if not versions:
            return [f"unknown schema: {name}"]
        target = version or max(versions.keys())
        validator = self._validators.get(name)
        if validator:
            return validator(data)
        return self._default_validate(data, versions.get(target, {}))

    def _default_validate(self, data: Any, schema: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        if not isinstance(data, dict):
            return ["data must be a dict"]
        required = schema.get("required", [])
        for key in required:
            if key not in data:
                errors.append(f"missing required field: {key}")
        properties = schema.get("properties", {})
        for key, value in data.items():
            prop = properties.get(key)
            if prop and "type" in prop:
                expected = prop["type"]
                actual = self._python_type_name(value)
                if expected != actual and not (expected == "number" and actual in ("int", "float")):
                    errors.append(f"field {key}: expected {expected}, got {actual}")
        return errors

    def _python_type_name(self, value: Any) -> str:
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "int"
        if isinstance(value, float):
            return "float"
        if isinstance(value, str):
            return "string"
        if isinstance(value, list):
            return "array"
        if isinstance(value, dict):
            return "object"
        return "unknown"

    def migrate(self, name: str, data: Any, from_version: int, to_version: int) -> Any:
        current = from_version
        while current < to_version:
            migrations = self._migrations.get(name, {})
            fn = migrations.get(current)
            if not fn:
                raise ValueError(f"no migration path from {current} for {name}")
            data = fn(data)
            current += 1
        return data

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "schema-registry-card",
            "schemas": {name: list(versions.keys()) for name, versions in self._schemas.items()},
            "total_migrations": sum(len(m) for m in self._migrations.values()),
        }
