"""Versioned component schemas for the deterministic ECS core."""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Iterable, Mapping

from .canonical import digest
from .errors import SchemaConflictError, SchemaError, SchemaNotFoundError, SchemaVersionError, ValidationError

_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
MAX_FIELDS = 256
MAX_SCHEMA_VERSIONS = 64
MAX_TEXT = 1_000_000


class FieldKind(str, Enum):
    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    TEXT = "text"
    BYTES = "bytes"
    JSON = "json"


@dataclass(frozen=True)
class FieldSpec:
    name: str
    kind: FieldKind
    required: bool = True
    default: Any = None
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[Any, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _TOKEN_RE.fullmatch(self.name):
            raise SchemaError("invalid field name", context={"name": self.name})
        if not isinstance(self.kind, FieldKind):
            try:
                object.__setattr__(self, "kind", FieldKind(self.kind))
            except Exception as exc:
                raise SchemaError("unknown field kind") from exc
        if not isinstance(self.required, bool):
            raise SchemaError("required must be boolean")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise SchemaError("minimum exceeds maximum", context={"field": self.name})
        if self.choices and len(self.choices) > 1024:
            raise SchemaError("too many field choices", context={"field": self.name})
        if self.default is not None:
            validate_field(self, self.default)

    def to_record(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "required": self.required,
            "default": copy.deepcopy(self.default),
            "minimum": self.minimum,
            "maximum": self.maximum,
            "choices": list(copy.deepcopy(self.choices)),
        }


@dataclass(frozen=True)
class ComponentSchema:
    schema_id: str
    version: int
    fields: tuple[FieldSpec, ...]
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.schema_id, str) or not _TOKEN_RE.fullmatch(self.schema_id):
            raise SchemaError("invalid schema id", context={"schema_id": self.schema_id})
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise SchemaVersionError("schema version must be positive integer")
        fields = tuple(self.fields)
        if len(fields) > MAX_FIELDS:
            raise SchemaError("schema field bound exceeded", context={"maximum": MAX_FIELDS})
        names = [f.name for f in fields]
        if len(names) != len(set(names)):
            raise SchemaError("duplicate field names", context={"schema_id": self.schema_id})
        object.__setattr__(self, "fields", tuple(sorted(fields, key=lambda f: f.name)))
        if not isinstance(self.description, str) or len(self.description) > 4096:
            raise SchemaError("invalid schema description")

    @property
    def key(self) -> tuple[str, int]:
        return self.schema_id, self.version

    @property
    def fingerprint(self) -> str:
        return digest(self.to_record())

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "version": self.version,
            "fields": [f.to_record() for f in self.fields],
            "description": self.description,
        }

    def validate(self, value: Mapping[str, Any], *, allow_extra: bool = False) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise SchemaError("component value must be mapping", context={"schema_id": self.schema_id})
        specs = {f.name: f for f in self.fields}
        extras = sorted(set(value) - set(specs))
        if extras and not allow_extra:
            raise SchemaError("component has unknown fields", context={"schema_id": self.schema_id, "fields": extras})
        out: dict[str, Any] = {}
        for name in sorted(specs):
            spec = specs[name]
            if name in value:
                out[name] = validate_field(spec, value[name])
            elif spec.default is not None:
                out[name] = copy.deepcopy(spec.default)
            elif spec.required:
                raise SchemaError("component missing required field", context={"schema_id": self.schema_id, "field": name})
        if allow_extra:
            for name in extras:
                out[name] = copy.deepcopy(value[name])
        return out


def validate_field(spec: FieldSpec, value: Any) -> Any:
    kind = spec.kind
    if kind is FieldKind.BOOL:
        if not isinstance(value, bool):
            raise SchemaError("field must be bool", context={"field": spec.name})
    elif kind is FieldKind.INT:
        if isinstance(value, bool) or not isinstance(value, int):
            raise SchemaError("field must be int", context={"field": spec.name})
    elif kind is FieldKind.FLOAT:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SchemaError("field must be numeric", context={"field": spec.name})
        value = float(value)
        if value != value or value in (float("inf"), float("-inf")):
            raise SchemaError("field must be finite", context={"field": spec.name})
    elif kind is FieldKind.TEXT:
        if not isinstance(value, str):
            raise SchemaError("field must be text", context={"field": spec.name})
        if len(value) > MAX_TEXT:
            raise SchemaError("text field too large", context={"field": spec.name})
    elif kind is FieldKind.BYTES:
        if not isinstance(value, (bytes, bytearray, memoryview)):
            raise SchemaError("field must be bytes", context={"field": spec.name})
        value = bytes(value)
    elif kind is FieldKind.JSON:
        try:
            digest(value)
        except ValidationError as exc:
            raise SchemaError("field is not canonical-json compatible", context={"field": spec.name}) from exc
    if spec.minimum is not None and isinstance(value, (int, float)) and value < spec.minimum:
        raise SchemaError("field below minimum", context={"field": spec.name, "minimum": spec.minimum})
    if spec.maximum is not None and isinstance(value, (int, float)) and value > spec.maximum:
        raise SchemaError("field above maximum", context={"field": spec.name, "maximum": spec.maximum})
    if spec.choices and value not in spec.choices:
        raise SchemaError("field not in choices", context={"field": spec.name})
    return copy.deepcopy(value)


class SchemaRegistry:
    def __init__(self) -> None:
        self._schemas: dict[tuple[str, int], ComponentSchema] = {}
        self._latest: dict[str, int] = {}

    def register(self, schema: ComponentSchema) -> ComponentSchema:
        if not isinstance(schema, ComponentSchema):
            raise SchemaError("register requires ComponentSchema")
        key = schema.key
        previous = self._schemas.get(key)
        if previous is not None:
            if previous.fingerprint != schema.fingerprint:
                raise SchemaConflictError("schema key already registered with different definition", context={"schema_id": schema.schema_id, "version": schema.version})
            return previous
        versions = [version for (sid, version) in self._schemas if sid == schema.schema_id]
        if len(versions) >= MAX_SCHEMA_VERSIONS:
            raise SchemaVersionError("too many schema versions", context={"schema_id": schema.schema_id})
        self._schemas[key] = schema
        self._latest[schema.schema_id] = max(schema.version, self._latest.get(schema.schema_id, 0))
        return schema

    def get(self, schema_id: str, version: int | None = None) -> ComponentSchema:
        if version is None:
            version = self._latest.get(schema_id)
        if version is None or (schema_id, version) not in self._schemas:
            raise SchemaNotFoundError("schema not found", context={"schema_id": schema_id, "version": version})
        return self._schemas[(schema_id, version)]

    def has(self, schema_id: str, version: int | None = None) -> bool:
        try:
            self.get(schema_id, version)
            return True
        except SchemaNotFoundError:
            return False

    def versions(self, schema_id: str) -> tuple[int, ...]:
        return tuple(sorted(version for sid, version in self._schemas if sid == schema_id))

    def catalog(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._schemas[key].to_record() for key in sorted(self._schemas))

    @property
    def fingerprint(self) -> str:
        return digest({"domain": "skeleton.simulation.ecs.schema_registry.v1", "catalog": self.catalog()})


def make_schema(schema_id: str, version: int, fields: Iterable[FieldSpec | Mapping[str, Any]], *, description: str = "") -> ComponentSchema:
    normalized: list[FieldSpec] = []
    for field in fields:
        if isinstance(field, FieldSpec):
            normalized.append(field)
        elif isinstance(field, Mapping):
            normalized.append(FieldSpec(**dict(field)))
        else:
            raise SchemaError("invalid field specification")
    return ComponentSchema(schema_id=schema_id, version=version, fields=tuple(normalized), description=description)


@dataclass(frozen=True)
class MigrationStep:
    schema_id: str
    from_version: int
    to_version: int
    name: str

    def __post_init__(self) -> None:
        if self.to_version != self.from_version + 1:
            raise SchemaVersionError("migration steps must advance one version")
        if not _TOKEN_RE.fullmatch(self.schema_id) or not _TOKEN_RE.fullmatch(self.name):
            raise SchemaError("invalid migration step identifier")


@dataclass(frozen=True)
class MigrationEvidence:
    schema_id: str
    from_version: int
    to_version: int
    steps: tuple[str, ...]
    before_digest: str
    after_digest: str


class MigrationRegistry:
    def __init__(self, schemas: SchemaRegistry) -> None:
        self.schemas = schemas
        self._steps: dict[tuple[str, int], tuple[MigrationStep, Callable[[dict[str, Any]], Mapping[str, Any]]]] = {}

    def register(self, step: MigrationStep, transform: Callable[[dict[str, Any]], Mapping[str, Any]]) -> None:
        key = (step.schema_id, step.from_version)
        if key in self._steps:
            raise SchemaConflictError("migration step already registered", context={"schema_id": step.schema_id, "from": step.from_version})
        if not callable(transform):
            raise SchemaError("migration transform must be callable")
        self.schemas.get(step.schema_id, step.from_version)
        self.schemas.get(step.schema_id, step.to_version)
        self._steps[key] = (step, transform)

    def migrate(self, schema_id: str, from_version: int, to_version: int, value: Mapping[str, Any]) -> tuple[dict[str, Any], MigrationEvidence]:
        if to_version < from_version:
            raise SchemaVersionError("downgrade migrations are not supported")
        current = self.schemas.get(schema_id, from_version).validate(value)
        before = digest(current)
        names: list[str] = []
        version = from_version
        while version < to_version:
            key = (schema_id, version)
            if key not in self._steps:
                raise SchemaVersionError("migration path is incomplete", context={"schema_id": schema_id, "from": version, "to": to_version})
            step, transform = self._steps[key]
            produced = transform(copy.deepcopy(current))
            current = self.schemas.get(schema_id, step.to_version).validate(produced)
            names.append(step.name)
            version = step.to_version
        evidence = MigrationEvidence(schema_id, from_version, to_version, tuple(names), before, digest(current))
        return current, evidence
