"""Compatibility aggregation surface for deterministic ECS domain primitives."""
from .archetype import Archetype, ArchetypeRegistry, ComponentTemplate
from .canonical import canonical_bytes, canonical_json, canonical_node, chained_digest, digest
from .codec import EncodedDocument, decode_document, encode_document
from .errors import *
from .identity import EntityAllocator, EntityId, validate_entity_id, validate_namespace
from .index import ComponentIndex, IndexSnapshot
from .invariants import FindingSeverity, InvariantFinding, InvariantInspector, InvariantReport
from .metrics import PlanMetrics, StoreMetrics, plan_metrics, store_metrics
from .query import CompareOp, FieldPredicate, QueryEngine, QueryRow, QuerySpec
from .schema import (ComponentSchema, FieldKind, FieldSpec, MigrationEvidence,
                     MigrationRegistry, MigrationStep, SchemaRegistry, make_schema,
                     validate_field)
from .store import ComponentValue, EntityRecord, EntityStore, ResourceValue, Tombstone
