"""Deterministic incremental asset rebuild planning.

Issue #807 batch B007 reuses the content-addressed incremental graph rather
than creating a second invalidation engine. Asset declarations bind exact
source/config/tool identities to build nodes. A change plan then:

* seeds only assets that reference changed source/config/tool keys;
* uses IncrementalBuildGraph.invalidate for transitive dependents;
* emits rebuild targets in canonical graph order;
* repackages only packages containing affected assets;
* reports unrelated changes without forcing a global rebuild;
* fails closed on malformed declarations, digests, dependencies, and bounds.

This module is planning-only. It does not inspect the filesystem, execute asset
tools, write packages, open the network, or infer content digests.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

from skeleton.build.incremental_graph import (
    IncrementalBuildGraph,
    IncrementalGraphError,
    MAX_INPUT_KEYS,
    NodeSpec,
    build_incremental_graph,
)
from skeleton.kernel.errors import SkeletonError


ASSET_PIPELINE_SCHEMA = 1
ASSET_PIPELINE_ALGORITHM = "sha256"
MAX_ASSETS = 4096
MAX_INPUTS_PER_CLASS = MAX_INPUT_KEYS
MAX_PACKAGES_PER_ASSET = 64
MAX_CHANGE_KEYS = 16384
MAX_ID_LENGTH = 256
MAX_KEY_LENGTH = 512
MAX_PACKAGE_LENGTH = 256
MAX_COST = 1_000_000
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SPEC_KEYS = frozenset(
    {
        "id",
        "asset_id",
        "sources",
        "config",
        "tools",
        "dependencies",
        "packages",
        "cost",
    }
)


class AssetPipelineError(SkeletonError):
    """Refuse an asset plan whose identity or dependency model is untrusted."""

    code = "BUILD.ASSET_PIPELINE"
    http_status = 400


@dataclass(frozen=True, slots=True)
class AssetSpec:
    """Declared incremental asset unit."""

    asset_id: str
    sources: Mapping[str, str] | None = None
    config: Mapping[str, str] | None = None
    tools: Mapping[str, str] | None = None
    dependencies: Sequence[str] = ()
    packages: Sequence[str] = ()
    cost: int = 1


@dataclass(frozen=True, slots=True)
class AssetDescriptor:
    asset_id: str
    sources: tuple[tuple[str, str], ...]
    config: tuple[tuple[str, str], ...]
    tools: tuple[tuple[str, str], ...]
    dependencies: tuple[str, ...]
    packages: tuple[str, ...]
    cost: int
    fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "sources": [[name, digest] for name, digest in self.sources],
            "config": [[name, digest] for name, digest in self.config],
            "tools": [[name, digest] for name, digest in self.tools],
            "dependencies": list(self.dependencies),
            "packages": list(self.packages),
            "cost": self.cost,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class AssetPipeline:
    schema: int
    algorithm: str
    fingerprint: str
    graph: IncrementalBuildGraph
    assets: tuple[AssetDescriptor, ...]

    def asset_map(self) -> dict[str, AssetDescriptor]:
        return {asset.asset_id: asset for asset in self.assets}

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "algorithm": self.algorithm,
            "fingerprint": self.fingerprint,
            "graph_fingerprint": self.graph.fingerprint,
            "assets": [asset.to_dict() for asset in self.assets],
        }

    def serialize(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class AssetRebuildPlan:
    schema: int
    algorithm: str
    pipeline_fingerprint: str
    plan_fingerprint: str
    changed_sources: tuple[str, ...]
    changed_config: tuple[str, ...]
    changed_tools: tuple[str, ...]
    ignored_sources: tuple[str, ...]
    ignored_config: tuple[str, ...]
    ignored_tools: tuple[str, ...]
    seed_assets: tuple[str, ...]
    rebuild_assets: tuple[str, ...]
    repackage: tuple[str, ...]

    @property
    def is_noop(self) -> bool:
        return not self.rebuild_assets

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "algorithm": self.algorithm,
            "pipeline_fingerprint": self.pipeline_fingerprint,
            "plan_fingerprint": self.plan_fingerprint,
            "changed_sources": list(self.changed_sources),
            "changed_config": list(self.changed_config),
            "changed_tools": list(self.changed_tools),
            "ignored_sources": list(self.ignored_sources),
            "ignored_config": list(self.ignored_config),
            "ignored_tools": list(self.ignored_tools),
            "seed_assets": list(self.seed_assets),
            "rebuild_assets": list(self.rebuild_assets),
            "repackage": list(self.repackage),
        }

    def serialize(self) -> str:
        return _canonical_json(self.to_dict())


def build_asset_pipeline(
    specs: Iterable[AssetSpec | Mapping[str, Any]],
) -> AssetPipeline:
    """Compile normalized asset declarations into the canonical build graph."""

    raw_specs = _bounded_iterable(specs, field="specs", maximum=MAX_ASSETS)
    normalized: list[AssetSpec] = []
    seen: set[str] = set()
    for raw in raw_specs:
        spec = _coerce_spec(raw)
        if spec.asset_id in seen:
            raise AssetPipelineError(
                "duplicate asset id",
                context={"asset_id": spec.asset_id},
            )
        seen.add(spec.asset_id)
        normalized.append(spec)

    if not normalized:
        raise AssetPipelineError("asset pipeline requires at least one asset")

    graph_specs: list[NodeSpec] = []
    normalized_payload: dict[str, dict[str, Any]] = {}
    for spec in normalized:
        sources = _normalize_digest_map(spec.sources or {}, field="sources")
        config = _normalize_digest_map(spec.config or {}, field="config")
        tools = _normalize_digest_map(spec.tools or {}, field="tools")
        total_inputs = len(sources) + len(config) + len(tools)
        if total_inputs > MAX_INPUT_KEYS:
            raise AssetPipelineError(
                "asset input count exceeds incremental graph limit",
                context={
                    "asset_id": spec.asset_id,
                    "inputs": total_inputs,
                    "max_inputs": MAX_INPUT_KEYS,
                },
            )
        dependencies = _normalize_ids(
            spec.dependencies,
            field="dependencies",
            maximum=MAX_ASSETS,
        )
        packages = _normalize_packages(spec.packages)
        cost = _bounded_int(
            spec.cost,
            field="cost",
            minimum=1,
            maximum=MAX_COST,
        )
        if not sources and not config and not tools and not dependencies:
            raise AssetPipelineError(
                "asset must declare an input or dependency",
                context={"asset_id": spec.asset_id},
            )

        inputs: dict[str, str] = {}
        for prefix, pairs in (
            ("source", sources),
            ("config", config),
            ("tool", tools),
        ):
            for name, digest in pairs:
                inputs[f"{prefix}:{name}"] = digest

        graph_specs.append(
            NodeSpec(
                node_id=spec.asset_id,
                kind="asset",
                inputs=inputs,
                dependencies=dependencies,
                cost=cost,
            )
        )
        normalized_payload[spec.asset_id] = {
            "sources": sources,
            "config": config,
            "tools": tools,
            "dependencies": dependencies,
            "packages": packages,
            "cost": cost,
        }

    try:
        graph = build_incremental_graph(graph_specs)
    except IncrementalGraphError as exc:
        raise AssetPipelineError("asset dependency graph is invalid") from exc

    graph_nodes = graph.node_map()
    descriptors = tuple(
        AssetDescriptor(
            asset_id=asset_id,
            sources=normalized_payload[asset_id]["sources"],
            config=normalized_payload[asset_id]["config"],
            tools=normalized_payload[asset_id]["tools"],
            dependencies=normalized_payload[asset_id]["dependencies"],
            packages=normalized_payload[asset_id]["packages"],
            cost=normalized_payload[asset_id]["cost"],
            fingerprint=graph_nodes[asset_id].fingerprint,
        )
        for asset_id in sorted(normalized_payload)
    )
    fingerprint = _sha256(
        {
            "schema": ASSET_PIPELINE_SCHEMA,
            "algorithm": ASSET_PIPELINE_ALGORITHM,
            "graph_fingerprint": graph.fingerprint,
            "assets": [asset.to_dict() for asset in descriptors],
        }
    )
    return AssetPipeline(
        schema=ASSET_PIPELINE_SCHEMA,
        algorithm=ASSET_PIPELINE_ALGORITHM,
        fingerprint=fingerprint,
        graph=graph,
        assets=descriptors,
    )


def plan_asset_rebuild(
    pipeline: AssetPipeline,
    *,
    changed_sources: Iterable[str] = (),
    changed_config: Iterable[str] = (),
    changed_tools: Iterable[str] = (),
) -> AssetRebuildPlan:
    """Return the minimal deterministic asset/package rebuild plan."""

    if not isinstance(pipeline, AssetPipeline):
        raise AssetPipelineError("pipeline must be an AssetPipeline")
    _validate_pipeline(pipeline)

    sources = _normalize_changes(changed_sources, field="changed_sources")
    config = _normalize_changes(changed_config, field="changed_config")
    tools = _normalize_changes(changed_tools, field="changed_tools")

    source_index = _reverse_index(pipeline.assets, "sources")
    config_index = _reverse_index(pipeline.assets, "config")
    tool_index = _reverse_index(pipeline.assets, "tools")

    seed_set: set[str] = set()
    for name in sources:
        seed_set.update(source_index.get(name, ()))
    for name in config:
        seed_set.update(config_index.get(name, ()))
    for name in tools:
        seed_set.update(tool_index.get(name, ()))

    ignored_sources = tuple(name for name in sources if name not in source_index)
    ignored_config = tuple(name for name in config if name not in config_index)
    ignored_tools = tuple(name for name in tools if name not in tool_index)

    if seed_set:
        try:
            affected = pipeline.graph.invalidate(sorted(seed_set))
        except IncrementalGraphError as exc:
            raise AssetPipelineError("asset invalidation failed") from exc
    else:
        affected = frozenset()

    rebuild_assets = tuple(
        asset_id
        for asset_id in pipeline.graph.topological_order
        if asset_id in affected
    )
    asset_map = pipeline.asset_map()
    packages = tuple(
        sorted(
            {
                package
                for asset_id in rebuild_assets
                for package in asset_map[asset_id].packages
            }
        )
    )
    seed_assets = tuple(sorted(seed_set))

    payload = {
        "schema": ASSET_PIPELINE_SCHEMA,
        "algorithm": ASSET_PIPELINE_ALGORITHM,
        "pipeline_fingerprint": pipeline.fingerprint,
        "changed_sources": list(sources),
        "changed_config": list(config),
        "changed_tools": list(tools),
        "ignored_sources": list(ignored_sources),
        "ignored_config": list(ignored_config),
        "ignored_tools": list(ignored_tools),
        "seed_assets": list(seed_assets),
        "rebuild_assets": list(rebuild_assets),
        "repackage": list(packages),
    }
    return AssetRebuildPlan(
        schema=ASSET_PIPELINE_SCHEMA,
        algorithm=ASSET_PIPELINE_ALGORITHM,
        pipeline_fingerprint=pipeline.fingerprint,
        plan_fingerprint=_sha256(payload),
        changed_sources=sources,
        changed_config=config,
        changed_tools=tools,
        ignored_sources=ignored_sources,
        ignored_config=ignored_config,
        ignored_tools=ignored_tools,
        seed_assets=seed_assets,
        rebuild_assets=rebuild_assets,
        repackage=packages,
    )


def _validate_pipeline(pipeline: AssetPipeline) -> None:
    """Rebind a supplied pipeline object to canonical declarations.

    Planning accepts a materialized pipeline rather than raw declarations, so
    it must not trust a caller-constructed dataclass merely because its fields
    look plausible. Canonical reconstruction validates every descriptor,
    dependency edge, graph fingerprint, and derived pipeline identity before
    invalidation is allowed to proceed.
    """

    if (
        pipeline.schema != ASSET_PIPELINE_SCHEMA
        or pipeline.algorithm != ASSET_PIPELINE_ALGORITHM
    ):
        raise AssetPipelineError("pipeline schema or algorithm is unsupported")
    if not isinstance(pipeline.graph, IncrementalBuildGraph):
        raise AssetPipelineError("pipeline graph must be an IncrementalBuildGraph")
    if not pipeline.assets or len(pipeline.assets) > MAX_ASSETS:
        raise AssetPipelineError("pipeline asset count is invalid")

    specs: list[AssetSpec] = []
    for asset in pipeline.assets:
        if not isinstance(asset, AssetDescriptor):
            raise AssetPipelineError(
                "pipeline assets must contain AssetDescriptor values"
            )
        try:
            sources = dict(asset.sources)
            config = dict(asset.config)
            tools = dict(asset.tools)
        except (TypeError, ValueError) as exc:
            raise AssetPipelineError(
                "pipeline descriptor mappings are malformed"
            ) from exc
        specs.append(
            AssetSpec(
                asset_id=asset.asset_id,
                sources=sources,
                config=config,
                tools=tools,
                dependencies=asset.dependencies,
                packages=asset.packages,
                cost=asset.cost,
            )
        )

    expected = build_asset_pipeline(specs)
    if pipeline != expected:
        raise AssetPipelineError(
            "pipeline derived fields drifted from canonical declarations"
        )


def _reverse_index(
    assets: Sequence[AssetDescriptor],
    field: str,
) -> dict[str, tuple[str, ...]]:
    pending: dict[str, set[str]] = {}
    for asset in assets:
        pairs = getattr(asset, field)
        for name, _digest in pairs:
            pending.setdefault(name, set()).add(asset.asset_id)
    return {
        name: tuple(sorted(asset_ids))
        for name, asset_ids in pending.items()
    }


def _coerce_spec(raw: AssetSpec | Mapping[str, Any]) -> AssetSpec:
    if isinstance(raw, AssetSpec):
        asset_id = _required_identifier(raw.asset_id, field="asset_id")
        return AssetSpec(
            asset_id=asset_id,
            sources=raw.sources,
            config=raw.config,
            tools=raw.tools,
            dependencies=raw.dependencies,
            packages=raw.packages,
            cost=raw.cost,
        )
    if not isinstance(raw, Mapping):
        raise AssetPipelineError("asset spec must be an AssetSpec or mapping")

    extra = sorted(str(key) for key in raw if key not in _SPEC_KEYS)
    if extra:
        raise AssetPipelineError(
            "asset spec contains unknown keys",
            context={"keys": extra},
        )

    raw_id = raw.get("asset_id", raw.get("id"))
    if "asset_id" in raw and "id" in raw and raw["asset_id"] != raw["id"]:
        raise AssetPipelineError("asset_id and id aliases disagree")
    return AssetSpec(
        asset_id=_required_identifier(raw_id, field="asset_id"),
        sources=raw.get("sources"),
        config=raw.get("config"),
        tools=raw.get("tools"),
        dependencies=raw.get("dependencies", ()),
        packages=raw.get("packages", ()),
        cost=raw.get("cost", 1),
    )


def _normalize_digest_map(
    value: Any,
    *,
    field: str,
) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, Mapping):
        raise AssetPipelineError(f"{field} must be a mapping")
    if len(value) > MAX_INPUTS_PER_CLASS:
        raise AssetPipelineError(
            f"{field} exceeds configured limit",
            context={"count": len(value), "max": MAX_INPUTS_PER_CLASS},
        )

    normalized: list[tuple[str, str]] = []
    for raw_name, raw_digest in value.items():
        name = _required_key(raw_name, field=f"{field} key")
        if not isinstance(raw_digest, str) or SHA256_RE.fullmatch(raw_digest) is None:
            raise AssetPipelineError(
                f"{field} values must be lowercase SHA-256 digests",
                context={"name": name},
            )
        normalized.append((name, raw_digest))
    return tuple(sorted(normalized))


def _normalize_ids(
    value: Any,
    *,
    field: str,
    maximum: int,
) -> tuple[str, ...]:
    raw_items = _bounded_iterable(value, field=field, maximum=maximum)
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        item = _required_identifier(raw, field=field)
        if item in seen:
            raise AssetPipelineError(
                f"{field} contains duplicate entry",
                context={"value": item},
            )
        seen.add(item)
        normalized.append(item)
    return tuple(sorted(normalized))


def _normalize_packages(value: Any) -> tuple[str, ...]:
    raw_items = _bounded_iterable(
        value,
        field="packages",
        maximum=MAX_PACKAGES_PER_ASSET,
    )
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        package = _required_text(
            raw,
            field="package",
            maximum=MAX_PACKAGE_LENGTH,
        )
        if package in {".", "/", "*", "**"}:
            raise AssetPipelineError("package identifier is over-broad")
        if package in seen:
            raise AssetPipelineError(
                "packages contains duplicate entry",
                context={"package": package},
            )
        seen.add(package)
        normalized.append(package)
    return tuple(sorted(normalized))


def _normalize_changes(value: Any, *, field: str) -> tuple[str, ...]:
    raw_items = _bounded_iterable(
        value,
        field=field,
        maximum=MAX_CHANGE_KEYS,
    )
    normalized: set[str] = set()
    for raw in raw_items:
        normalized.add(_required_key(raw, field=field))
    return tuple(sorted(normalized))


def _bounded_iterable(
    value: Any,
    *,
    field: str,
    maximum: int,
) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes, bytearray, Mapping)):
        raise AssetPipelineError(f"{field} must be an iterable sequence")
    try:
        iterator = iter(value)
    except TypeError as exc:
        raise AssetPipelineError(f"{field} must be iterable") from exc

    items: list[Any] = []
    for item in iterator:
        if len(items) >= maximum:
            raise AssetPipelineError(
                f"{field} exceeds configured limit",
                context={"max": maximum},
            )
        items.append(item)
    return tuple(items)


def _required_identifier(value: Any, *, field: str) -> str:
    text = _required_text(value, field=field, maximum=MAX_ID_LENGTH)
    if any(ch in text for ch in ("/", "\\", ":", "\t")):
        raise AssetPipelineError(
            f"{field} contains unsafe identifier characters",
            context={"value": text},
        )
    return text


def _required_key(value: Any, *, field: str) -> str:
    text = _required_text(value, field=field, maximum=MAX_KEY_LENGTH)
    if "\t" in text:
        raise AssetPipelineError(f"{field} contains unsafe characters")
    return text


def _required_text(value: Any, *, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise AssetPipelineError(f"{field} must be a non-empty trimmed string")
    if len(value) > maximum:
        raise AssetPipelineError(
            f"{field} exceeds max length",
            context={"length": len(value), "max": maximum},
        )
    if any(ch in value for ch in ("\x00", "\n", "\r")):
        raise AssetPipelineError(f"{field} contains unsafe characters")
    return value


def _bounded_int(
    value: Any,
    *,
    field: str,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AssetPipelineError(f"{field} must be an integer")
    if value < minimum or value > maximum:
        raise AssetPipelineError(
            f"{field} is out of range",
            context={"minimum": minimum, "maximum": maximum, "value": value},
        )
    return value


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise AssetPipelineError("value is not canonically serializable") from exc


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
