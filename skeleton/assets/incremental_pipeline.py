"""Deterministic incremental asset invalidation and package planning (#807 B007).

The planner is pure: callers provide SHA-256 identities for source bytes,
normalized configuration, and the tool/transcoder/model version. Only recipe
identity changes cause regeneration. Packages are repacked only when membership
changes or one of their member assets is regenerated.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

from skeleton.kernel.errors import KernelError


PIPELINE_SCHEMA = 1
MAX_ASSETS = 4096
MAX_PACKAGES = 1024
MAX_PACKAGES_PER_ASSET = 32
MAX_TOKEN_LENGTH = 128
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$")


class IncrementalAssetError(KernelError):
    code = "ASSET.INCREMENTAL_PIPELINE"
    http_status = 400


@dataclass(frozen=True, slots=True)
class AssetRecipe:
    asset_id: str
    source_digest: str
    config_digest: str
    tool_digest: str
    package_ids: tuple[str, ...] = ()

    @property
    def recipe_digest(self) -> str:
        return _digest(
            {
                "asset_id": self.asset_id,
                "source_digest": self.source_digest,
                "config_digest": self.config_digest,
                "tool_digest": self.tool_digest,
            }
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "source_digest": self.source_digest,
            "config_digest": self.config_digest,
            "tool_digest": self.tool_digest,
            "package_ids": list(self.package_ids),
            "recipe_digest": self.recipe_digest,
        }


@dataclass(frozen=True, slots=True)
class AssetSnapshot:
    asset_id: str
    recipe_digest: str
    output_digest: str

    def to_payload(self) -> dict[str, str]:
        return {
            "asset_id": self.asset_id,
            "recipe_digest": self.recipe_digest,
            "output_digest": self.output_digest,
        }


@dataclass(frozen=True, slots=True)
class PackageSnapshot:
    package_id: str
    members: tuple[tuple[str, str], ...]

    @property
    def package_digest(self) -> str:
        return _digest(
            {
                "package_id": self.package_id,
                "members": [
                    [asset_id, output_digest]
                    for asset_id, output_digest in self.members
                ],
            }
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "members": [
                {"asset_id": asset_id, "output_digest": output_digest}
                for asset_id, output_digest in self.members
            ],
            "package_digest": self.package_digest,
        }


@dataclass(frozen=True, slots=True)
class AssetPipelineState:
    assets: tuple[AssetSnapshot, ...]
    packages: tuple[PackageSnapshot, ...]
    schema: int = PIPELINE_SCHEMA

    @property
    def state_digest(self) -> str:
        return _digest(self.to_payload(include_digest=False))

    def to_payload(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": self.schema,
            "assets": [asset.to_payload() for asset in self.assets],
            "packages": [package.to_payload() for package in self.packages],
        }
        if include_digest:
            payload["state_digest"] = self.state_digest
        return payload

    def serialize(self) -> str:
        return _canonical_json(self.to_payload())


@dataclass(frozen=True, slots=True)
class AssetPipelinePlan:
    recipes: tuple[AssetRecipe, ...]
    rebuild_assets: tuple[str, ...]
    reuse_assets: tuple[str, ...]
    remove_assets: tuple[str, ...]
    repack_packages: tuple[str, ...]
    remove_packages: tuple[str, ...]
    previous_state_digest: str | None
    schema: int = PIPELINE_SCHEMA

    @property
    def plan_digest(self) -> str:
        return _digest(self.to_payload(include_digest=False))

    def to_payload(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": self.schema,
            "recipes": [recipe.to_payload() for recipe in self.recipes],
            "rebuild_assets": list(self.rebuild_assets),
            "reuse_assets": list(self.reuse_assets),
            "remove_assets": list(self.remove_assets),
            "repack_packages": list(self.repack_packages),
            "remove_packages": list(self.remove_packages),
            "previous_state_digest": self.previous_state_digest,
        }
        if include_digest:
            payload["plan_digest"] = self.plan_digest
        return payload

    def serialize(self) -> str:
        return _canonical_json(self.to_payload())


def plan_asset_pipeline(
    recipes: Iterable[AssetRecipe | Mapping[str, Any]],
    *,
    previous: AssetPipelineState | Mapping[str, Any] | None = None,
) -> AssetPipelinePlan:
    normalized = _normalize_recipes(recipes)
    old = _coerce_state(previous) if previous is not None else None
    old_assets = {} if old is None else {row.asset_id: row for row in old.assets}
    old_packages = {} if old is None else {row.package_id: row for row in old.packages}

    rebuild: list[str] = []
    reuse: list[str] = []
    for recipe in normalized:
        prior = old_assets.get(recipe.asset_id)
        if prior is None or prior.recipe_digest != recipe.recipe_digest:
            rebuild.append(recipe.asset_id)
        else:
            reuse.append(recipe.asset_id)

    current_ids = {recipe.asset_id for recipe in normalized}
    removed_assets = tuple(sorted(set(old_assets) - current_ids))

    new_membership = _membership(normalized)
    old_membership = {
        package_id: tuple(asset_id for asset_id, _ in package.members)
        for package_id, package in old_packages.items()
    }
    rebuild_set = set(rebuild)
    repack: list[str] = []
    for package_id, members in new_membership.items():
        if package_id not in old_packages:
            repack.append(package_id)
        elif old_membership.get(package_id) != members:
            repack.append(package_id)
        elif any(asset_id in rebuild_set for asset_id in members):
            repack.append(package_id)

    return AssetPipelinePlan(
        recipes=normalized,
        rebuild_assets=tuple(sorted(rebuild)),
        reuse_assets=tuple(sorted(reuse)),
        remove_assets=removed_assets,
        repack_packages=tuple(sorted(repack)),
        remove_packages=tuple(sorted(set(old_packages) - set(new_membership))),
        previous_state_digest=None if old is None else old.state_digest,
    )


def finalize_asset_pipeline(
    plan: AssetPipelinePlan,
    *,
    rebuilt_output_digests: Mapping[str, str],
    previous: AssetPipelineState | Mapping[str, Any] | None = None,
) -> AssetPipelineState:
    if not isinstance(plan, AssetPipelinePlan):
        raise IncrementalAssetError("plan must be an AssetPipelinePlan")
    old = _coerce_state(previous) if previous is not None else None
    expected_previous = None if old is None else old.state_digest
    if plan.previous_state_digest != expected_previous:
        raise IncrementalAssetError(
            "plan previous-state digest does not match supplied previous state"
        )
    expected_plan = plan_asset_pipeline(plan.recipes, previous=old)
    if plan != expected_plan:
        raise IncrementalAssetError(
            "plan decisions do not match deterministic invalidation result"
        )
    if not isinstance(rebuilt_output_digests, Mapping):
        raise IncrementalAssetError("rebuilt_output_digests must be a mapping")

    expected_rebuild = set(plan.rebuild_assets)
    supplied = set(rebuilt_output_digests)
    if supplied != expected_rebuild:
        raise IncrementalAssetError(
            "rebuilt output set does not exactly match rebuild plan",
            context={
                "missing": sorted(expected_rebuild - supplied),
                "extra": sorted(supplied - expected_rebuild),
            },
        )

    old_assets = {} if old is None else {row.asset_id: row for row in old.assets}
    output_by_id: dict[str, str] = {}
    snapshots: list[AssetSnapshot] = []
    for recipe in plan.recipes:
        if recipe.asset_id in expected_rebuild:
            output_digest = _sha256(
                rebuilt_output_digests[recipe.asset_id],
                field=f"rebuilt_output_digests[{recipe.asset_id}]",
            )
        else:
            prior = old_assets.get(recipe.asset_id)
            if prior is None or prior.recipe_digest != recipe.recipe_digest:
                raise IncrementalAssetError(
                    "reuse plan does not bind matching previous asset",
                    context={"asset_id": recipe.asset_id},
                )
            output_digest = prior.output_digest
        output_by_id[recipe.asset_id] = output_digest
        snapshots.append(
            AssetSnapshot(
                asset_id=recipe.asset_id,
                recipe_digest=recipe.recipe_digest,
                output_digest=output_digest,
            )
        )

    packages = tuple(
        PackageSnapshot(
            package_id=package_id,
            members=tuple(
                (asset_id, output_by_id[asset_id]) for asset_id in member_ids
            ),
        )
        for package_id, member_ids in _membership(plan.recipes).items()
    )
    return AssetPipelineState(
        assets=tuple(sorted(snapshots, key=lambda row: row.asset_id)),
        packages=tuple(sorted(packages, key=lambda row: row.package_id)),
    )


def parse_asset_pipeline_state(
    raw: str | bytes | Mapping[str, Any],
) -> AssetPipelineState:
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise IncrementalAssetError("state must be UTF-8") from exc
    if isinstance(raw, str):
        try:
            payload = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
        except json.JSONDecodeError as exc:
            raise IncrementalAssetError("state is not valid JSON") from exc
    elif isinstance(raw, Mapping):
        payload = dict(raw)
    else:
        raise IncrementalAssetError("state must be JSON text/bytes or a mapping")
    return _coerce_state(payload)


def _normalize_recipes(
    recipes: Iterable[AssetRecipe | Mapping[str, Any]],
) -> tuple[AssetRecipe, ...]:
    if isinstance(recipes, (str, bytes, bytearray, Mapping)):
        raise IncrementalAssetError("recipes must be an iterable of recipe records")
    rows: list[AssetRecipe] = []
    seen: set[str] = set()
    for raw in recipes:
        if len(rows) >= MAX_ASSETS:
            raise IncrementalAssetError("recipe count exceeds asset bound")
        recipe = _coerce_recipe(raw)
        if recipe.asset_id in seen:
            raise IncrementalAssetError(
                "duplicate asset recipe",
                context={"asset_id": recipe.asset_id},
            )
        seen.add(recipe.asset_id)
        rows.append(recipe)
    return tuple(sorted(rows, key=lambda row: row.asset_id))


def _coerce_recipe(raw: AssetRecipe | Mapping[str, Any]) -> AssetRecipe:
    if isinstance(raw, AssetRecipe):
        asset_id = _token(raw.asset_id, field="asset_id")
        source = _sha256(raw.source_digest, field="source_digest")
        config = _sha256(raw.config_digest, field="config_digest")
        tool = _sha256(raw.tool_digest, field="tool_digest")
        packages = _package_ids(raw.package_ids)
    elif isinstance(raw, Mapping):
        expected = {
            "asset_id",
            "source_digest",
            "config_digest",
            "tool_digest",
            "package_ids",
        }
        extra = sorted(str(key) for key in raw if key not in expected)
        missing = sorted(key for key in expected if key not in raw)
        if extra or missing:
            raise IncrementalAssetError(
                "asset recipe keys mismatch",
                context={"missing": missing, "extra": extra},
            )
        asset_id = _token(raw["asset_id"], field="asset_id")
        source = _sha256(raw["source_digest"], field="source_digest")
        config = _sha256(raw["config_digest"], field="config_digest")
        tool = _sha256(raw["tool_digest"], field="tool_digest")
        packages = _package_ids(raw["package_ids"])
    else:
        raise IncrementalAssetError("asset recipe must be AssetRecipe or mapping")
    return AssetRecipe(
        asset_id=asset_id,
        source_digest=source,
        config_digest=config,
        tool_digest=tool,
        package_ids=packages,
    )


def _coerce_state(
    raw: AssetPipelineState | Mapping[str, Any],
) -> AssetPipelineState:
    if isinstance(raw, AssetPipelineState):
        if raw.schema != PIPELINE_SCHEMA:
            raise IncrementalAssetError("unsupported asset pipeline state schema")
        if len(raw.assets) > MAX_ASSETS or len(raw.packages) > MAX_PACKAGES:
            raise IncrementalAssetError("asset state exceeds configured bounds")
        state = AssetPipelineState(
            assets=tuple(_coerce_asset_snapshot(row) for row in raw.assets),
            packages=tuple(_coerce_package_snapshot(row) for row in raw.packages),
        )
        declared_digest: str | None = None
    elif isinstance(raw, Mapping):
        expected = {"schema", "assets", "packages", "state_digest"}
        extra = sorted(str(key) for key in raw if key not in expected)
        missing = sorted(key for key in expected if key not in raw)
        if extra or missing:
            raise IncrementalAssetError(
                "asset state keys mismatch",
                context={"missing": missing, "extra": extra},
            )
        if raw["schema"] != PIPELINE_SCHEMA:
            raise IncrementalAssetError("unsupported asset pipeline state schema")
        assets_raw = raw["assets"]
        packages_raw = raw["packages"]
        if not isinstance(assets_raw, list) or not isinstance(packages_raw, list):
            raise IncrementalAssetError("asset state assets/packages must be lists")
        if len(assets_raw) > MAX_ASSETS or len(packages_raw) > MAX_PACKAGES:
            raise IncrementalAssetError("asset state exceeds configured bounds")
        state = AssetPipelineState(
            assets=tuple(_coerce_asset_snapshot(row) for row in assets_raw),
            packages=tuple(_coerce_package_snapshot(row) for row in packages_raw),
        )
        declared_digest = _sha256(raw["state_digest"], field="state_digest")
    else:
        raise IncrementalAssetError(
            "previous state must be AssetPipelineState or mapping"
        )

    asset_ids = [row.asset_id for row in state.assets]
    package_ids = [row.package_id for row in state.packages]
    if len(asset_ids) != len(set(asset_ids)):
        raise IncrementalAssetError("asset state contains duplicate asset ids")
    if len(package_ids) != len(set(package_ids)):
        raise IncrementalAssetError("asset state contains duplicate package ids")
    asset_id_set = set(asset_ids)
    unknown_members = sorted(
        {
            asset_id
            for package in state.packages
            for asset_id, _ in package.members
            if asset_id not in asset_id_set
        }
    )
    if unknown_members:
        raise IncrementalAssetError(
            "package snapshot references unknown asset id",
            context={"asset_ids": unknown_members[:16]},
        )
    canonical = AssetPipelineState(
        assets=tuple(sorted(state.assets, key=lambda row: row.asset_id)),
        packages=tuple(sorted(state.packages, key=lambda row: row.package_id)),
    )
    if declared_digest is not None and declared_digest != canonical.state_digest:
        raise IncrementalAssetError("asset state digest mismatch")
    return canonical


def _coerce_asset_snapshot(raw: Any) -> AssetSnapshot:
    if isinstance(raw, AssetSnapshot):
        return AssetSnapshot(
            asset_id=_token(raw.asset_id, field="asset_id"),
            recipe_digest=_sha256(raw.recipe_digest, field="recipe_digest"),
            output_digest=_sha256(raw.output_digest, field="output_digest"),
        )
    if not isinstance(raw, Mapping):
        raise IncrementalAssetError("asset snapshot must be an object")
    if set(raw) != {"asset_id", "recipe_digest", "output_digest"}:
        raise IncrementalAssetError("asset snapshot keys mismatch")
    return AssetSnapshot(
        asset_id=_token(raw["asset_id"], field="asset_id"),
        recipe_digest=_sha256(raw["recipe_digest"], field="recipe_digest"),
        output_digest=_sha256(raw["output_digest"], field="output_digest"),
    )


def _coerce_package_snapshot(raw: Any) -> PackageSnapshot:
    if isinstance(raw, PackageSnapshot):
        package_id = _token(raw.package_id, field="package_id")
        members: list[tuple[str, str]] = []
        seen: set[str] = set()
        for asset_id_raw, digest_raw in raw.members:
            asset_id = _token(asset_id_raw, field="asset_id")
            if asset_id in seen:
                raise IncrementalAssetError("package contains duplicate asset id")
            seen.add(asset_id)
            members.append(
                (asset_id, _sha256(digest_raw, field="output_digest"))
            )
        return PackageSnapshot(
            package_id=package_id,
            members=tuple(sorted(members)),
        )
    if not isinstance(raw, Mapping):
        raise IncrementalAssetError("package snapshot must be an object")
    if set(raw) != {"package_id", "members", "package_digest"}:
        raise IncrementalAssetError("package snapshot keys mismatch")
    package_id = _token(raw["package_id"], field="package_id")
    members_raw = raw["members"]
    if not isinstance(members_raw, list) or len(members_raw) > MAX_ASSETS:
        raise IncrementalAssetError("package members must be a bounded list")
    members: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in members_raw:
        if (
            not isinstance(item, Mapping)
            or set(item) != {"asset_id", "output_digest"}
        ):
            raise IncrementalAssetError("package member keys mismatch")
        asset_id = _token(item["asset_id"], field="asset_id")
        if asset_id in seen:
            raise IncrementalAssetError("package contains duplicate asset id")
        seen.add(asset_id)
        members.append(
            (asset_id, _sha256(item["output_digest"], field="output_digest"))
        )
    snapshot = PackageSnapshot(
        package_id=package_id,
        members=tuple(sorted(members)),
    )
    declared = _sha256(raw["package_digest"], field="package_digest")
    if declared != snapshot.package_digest:
        raise IncrementalAssetError("package snapshot digest mismatch")
    return snapshot


def _package_ids(raw: Any) -> tuple[str, ...]:
    if isinstance(raw, (str, bytes, bytearray)) or not isinstance(raw, Sequence):
        raise IncrementalAssetError("package_ids must be a sequence")
    if len(raw) > MAX_PACKAGES_PER_ASSET:
        raise IncrementalAssetError(
            "asset package membership exceeds configured bound"
        )
    values = tuple(_token(value, field="package_id") for value in raw)
    if len(values) != len(set(values)):
        raise IncrementalAssetError(
            "asset recipe contains duplicate package id"
        )
    return tuple(sorted(values))


def _membership(
    recipes: Sequence[AssetRecipe],
) -> dict[str, tuple[str, ...]]:
    members: dict[str, list[str]] = {}
    for recipe in recipes:
        for package_id in recipe.package_ids:
            members.setdefault(package_id, []).append(recipe.asset_id)
    if len(members) > MAX_PACKAGES:
        raise IncrementalAssetError("package count exceeds configured bound")
    return {
        package_id: tuple(sorted(asset_ids))
        for package_id, asset_ids in sorted(members.items())
    }


def _token(value: Any, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_TOKEN_LENGTH
        or _TOKEN_RE.fullmatch(value) is None
    ):
        raise IncrementalAssetError(f"{field} must be a canonical token")
    return value


def _sha256(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise IncrementalAssetError(
            f"{field} must be a lowercase SHA-256 digest"
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
        raise IncrementalAssetError(
            "value is not canonically serializable"
        ) from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _reject_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise IncrementalAssetError(f"duplicate JSON key: {key}")
        payload[key] = value
    return payload


__all__ = [
    "PIPELINE_SCHEMA",
    "AssetPipelinePlan",
    "AssetPipelineState",
    "AssetRecipe",
    "AssetSnapshot",
    "IncrementalAssetError",
    "PackageSnapshot",
    "finalize_asset_pipeline",
    "parse_asset_pipeline_state",
    "plan_asset_pipeline",
]
