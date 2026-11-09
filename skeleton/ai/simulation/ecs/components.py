"""Component type registry for the live world.

A component type is a name bound to

* a dense integer id (registration order; ids are part of snapshot state),
* a storage strategy: ``table`` (archetype columns — fast iteration, moves on
  add/remove) or ``sparse`` (sparse set — O(1) add/remove, for components that
  churn such as status effects or short-lived markers), and
* a value contract: a versioned :class:`~.schema.ComponentSchema` (reusing the
  authoritative store's schema machinery rather than a parallel one), a
  *tag* (zero-sized marker) or free-form plain data.

The registry can emit a :class:`~.schema.SchemaRegistry` so a live world can
be exported into the authoritative :class:`~.store.EntityStore`.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .canonical import digest
from .errors import ComponentTypeError, SchemaError, ValidationError
from .schema import ComponentSchema, FieldKind, FieldSpec, SchemaRegistry, make_schema
from .values import canonical_copy, check_value, copy_value

MAX_COMPONENT_TYPES = 4096
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
FREEFORM_FIELD = "value"


class StorageKind(str, Enum):
    TABLE = "table"
    SPARSE = "sparse"


class ValueKind(str, Enum):
    SCHEMA = "schema"
    TAG = "tag"
    FREEFORM = "freeform"


@dataclass(frozen=True)
class ComponentInfo:
    component_id: int
    name: str
    storage: StorageKind
    value_kind: ValueKind
    schema: ComponentSchema | None = None
    description: str = ""

    @property
    def is_tag(self) -> bool:
        return self.value_kind is ValueKind.TAG

    def to_record(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "name": self.name,
            "storage": self.storage.value,
            "value_kind": self.value_kind.value,
            "schema": self.schema.to_record() if self.schema is not None else None,
            "description": self.description,
        }


def schema_from_record(record: Mapping[str, Any]) -> ComponentSchema:
    """Rebuild a :class:`ComponentSchema` from :meth:`ComponentSchema.to_record`."""
    if not isinstance(record, Mapping):
        raise SchemaError("schema record must be a mapping")
    try:
        fields = []
        for row in record["fields"]:
            row = dict(row)
            row["choices"] = tuple(row.get("choices") or ())
            fields.append(FieldSpec(**row))
        return make_schema(record["schema_id"], record["version"], fields, description=record.get("description", ""))
    except (KeyError, TypeError) as exc:
        raise SchemaError("malformed schema record") from exc


class ComponentRegistry:
    """Deterministic name → :class:`ComponentInfo` registry."""

    def __init__(self) -> None:
        self._by_name: dict[str, ComponentInfo] = {}
        self._by_id: list[ComponentInfo] = []

    def __len__(self) -> int:
        return len(self._by_id)

    def __contains__(self, name: object) -> bool:
        return name in self._by_name

    def register(
        self,
        name: str,
        *,
        schema: ComponentSchema | None = None,
        fields: Iterable[FieldSpec | Mapping[str, Any]] | None = None,
        tag: bool = False,
        storage: StorageKind | str = StorageKind.TABLE,
        description: str = "",
    ) -> ComponentInfo:
        """Register a component type (idempotent for identical definitions)."""
        if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
            raise ComponentTypeError("invalid component name", context={"name": name})
        try:
            storage = StorageKind(storage)
        except ValueError as exc:
            raise ComponentTypeError("unknown storage kind", context={"storage": storage}) from exc
        if sum(1 for flag in (schema is not None, fields is not None, tag) if flag) > 1:
            raise ComponentTypeError("choose one of schema=, fields= or tag=", context={"name": name})
        if fields is not None:
            schema = make_schema(name, 1, fields, description=description)
        if schema is not None:
            if not isinstance(schema, ComponentSchema):
                raise ComponentTypeError("schema must be a ComponentSchema")
            if schema.schema_id != name:
                raise ComponentTypeError("schema id must equal component name", context={"name": name, "schema_id": schema.schema_id})
            kind = ValueKind.SCHEMA
        else:
            kind = ValueKind.TAG if tag else ValueKind.FREEFORM
        if not isinstance(description, str) or len(description) > 4096:
            raise ComponentTypeError("invalid component description")
        prior = self._by_name.get(name)
        if prior is not None:
            same = (
                prior.storage is storage
                and prior.value_kind is kind
                and (prior.schema.fingerprint if prior.schema else None) == (schema.fingerprint if schema else None)
            )
            if not same:
                raise ComponentTypeError("component already registered with a different definition", context={"name": name})
            return prior
        if len(self._by_id) >= MAX_COMPONENT_TYPES:
            raise ComponentTypeError("component type bound exceeded", context={"maximum": MAX_COMPONENT_TYPES})
        info = ComponentInfo(len(self._by_id), name, storage, kind, schema, description)
        self._by_name[name] = info
        self._by_id.append(info)
        return info

    def get(self, name: str) -> ComponentInfo:
        try:
            return self._by_name[name]
        except (KeyError, TypeError):
            raise ComponentTypeError("unknown component type", context={"name": name}) from None

    def by_id(self, component_id: int) -> ComponentInfo:
        if not isinstance(component_id, int) or not 0 <= component_id < len(self._by_id):
            raise ComponentTypeError("unknown component id", context={"component_id": component_id})
        return self._by_id[component_id]

    def id_of(self, name: str) -> int:
        return self.get(name).component_id

    def names(self) -> tuple[str, ...]:
        return tuple(info.name for info in self._by_id)

    def infos(self) -> tuple[ComponentInfo, ...]:
        return tuple(self._by_id)

    # -- values ----------------------------------------------------------
    def normalise(self, name: str, value: Any, *, info: ComponentInfo | None = None) -> Any:
        """Validate ``value`` for component ``name`` and return an owned copy."""
        info = info or self.get(name)
        if info.value_kind is ValueKind.SCHEMA:
            assert info.schema is not None
            if not isinstance(value, Mapping):
                raise ValidationError("schema component value must be a mapping", context={"component": name})
            try:
                out = info.schema.validate(value)
            except SchemaError as exc:
                raise ValidationError(
                    "component value failed schema validation",
                    context={"component": name, "error": str(exc), **dict(getattr(exc, "context", {}) or {})},
                ) from exc
            check_value(out, label=f"component {name}")
            return canonical_copy(out)
        if info.value_kind is ValueKind.TAG:
            if value not in (None, True, {}):
                raise ValidationError("tag components carry no data", context={"component": name})
            return None
        check_value(value, label=f"component {name}")
        return canonical_copy(value)

    # -- persistence -----------------------------------------------------
    def catalog(self) -> list[dict[str, Any]]:
        return [info.to_record() for info in self._by_id]

    @property
    def fingerprint(self) -> str:
        return digest({"domain": "skeleton.simulation.ecs.live_components.v1", "catalog": self.catalog()})

    @classmethod
    def from_catalog(cls, catalog: Iterable[Mapping[str, Any]]) -> ComponentRegistry:
        registry = cls()
        for expected_id, row in enumerate(catalog):
            if not isinstance(row, Mapping) or row.get("component_id") != expected_id:
                raise ComponentTypeError("component catalog ids must be dense and ordered")
            kind = ValueKind(row["value_kind"])
            schema = schema_from_record(row["schema"]) if row.get("schema") is not None else None
            registry.register(
                row["name"],
                schema=schema,
                tag=kind is ValueKind.TAG,
                storage=row["storage"],
                description=row.get("description", ""),
            )
        return registry

    def schema_for_store(self, info: ComponentInfo) -> ComponentSchema:
        """Schema used when exporting ``info`` into an ``EntityStore``."""
        if info.value_kind is ValueKind.SCHEMA:
            assert info.schema is not None
            return info.schema
        if info.value_kind is ValueKind.TAG:
            return make_schema(info.name, 1, [], description=info.description or "live tag component")
        return make_schema(
            info.name,
            1,
            [FieldSpec(FREEFORM_FIELD, FieldKind.JSON, required=False)],
            description=info.description or "live free-form component",
        )

    def to_schema_registry(self) -> SchemaRegistry:
        registry = SchemaRegistry()
        for info in self._by_id:
            registry.register(self.schema_for_store(info))
        return registry

    def store_value(self, info: ComponentInfo, value: Any) -> dict[str, Any]:
        if info.value_kind is ValueKind.SCHEMA:
            return copy_value(value)
        if info.value_kind is ValueKind.TAG:
            return {}
        return {FREEFORM_FIELD: copy_value(value)}

    def value_from_store(self, info: ComponentInfo, data: Mapping[str, Any]) -> Any:
        if info.value_kind is ValueKind.SCHEMA:
            return copy_value(dict(data))
        if info.value_kind is ValueKind.TAG:
            return None
        return copy_value(data.get(FREEFORM_FIELD))


__all__ = [
    "FREEFORM_FIELD",
    "MAX_COMPONENT_TYPES",
    "ComponentInfo",
    "ComponentRegistry",
    "StorageKind",
    "ValueKind",
    "schema_from_record",
]
