"""Platform adapters that map engine-neutral contracts onto engine surfaces.

Core game/world/creator semantics stay in their owning packages. This package
only hosts fail-closed, versioned adapter boundaries.
"""

from skeleton.platform.godot_adapter import (
    ADAPTER_INPUT_SCHEMA,
    ADAPTER_SCHEMA,
    ADAPTER_VERSION,
    FOOTPRINT_POLICY,
    GodotAdapter,
    GodotAdapterError,
    GodotAdapterView,
    GodotUnsupportedFeatureError,
    GodotVersionError,
    adapt_document,
    inventory_godot_footprint,
    materialise_pack,
    project_document,
)

__all__ = [
    "ADAPTER_INPUT_SCHEMA",
    "ADAPTER_SCHEMA",
    "ADAPTER_VERSION",
    "FOOTPRINT_POLICY",
    "GodotAdapter",
    "GodotAdapterError",
    "GodotAdapterView",
    "GodotUnsupportedFeatureError",
    "GodotVersionError",
    "adapt_document",
    "inventory_godot_footprint",
    "materialise_pack",
    "project_document",
]
