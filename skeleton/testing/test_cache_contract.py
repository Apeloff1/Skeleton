"""Regression tests for deterministic local/CI cache unification (#807 B003)."""

from __future__ import annotations

import json

import pytest

from skeleton.build.cache_contract import (
    CACHE_ALGORITHM,
    CACHE_KEY_PREFIX,
    CACHE_SCHEMA,
    CacheContractError,
    CacheEntry,
    EvictionPolicy,
    build_cache_key,
    plan_eviction,
)


def _key(**overrides: object):
    args = {
        "kind": "python",
        "namespace": "backend-tests",
        "materials": {
            "requirements.lock": "sha256:requirements-v1",
            "source-tree": "sha256:source-v1",
        },
        "toolchain": {
            "python": "3.11.16",
            "pip": "25.2",
            "platform": "linux-x86_64",
        },
        "config": {"mode": "test"},
    }
    args.update(overrides)
    return build_cache_key(**args)


def test_identical_material_is_order_independent_and_canonical() -> None:
    left = _key()
    right = build_cache_key(
        kind="python",
        namespace="backend-tests",
        materials={
            "source-tree": "sha256:source-v1",
            "requirements.lock": "sha256:requirements-v1",
        },
        toolchain={
            "platform": "linux-x86_64",
            "pip": "25.2",
            "python": "3.11.16",
        },
        config={"mode": "test"},
    )

    assert left == right
    assert left.schema == CACHE_SCHEMA
    assert left.algorithm == CACHE_ALGORITHM
    assert left.key.startswith(f"{CACHE_KEY_PREFIX}:python:backend-tests:")
    assert len(left.key.rsplit(":", 1)[-1]) == 64
    assert left.serialize() == json.dumps(
        json.loads(left.serialize()),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("materials", {"requirements.lock": "sha256:requirements-v2"}),
        ("toolchain", {"python": "3.12.12", "pip": "25.2", "platform": "linux-x86_64"}),
        ("config", {"mode": "release"}),
    ],
)
def test_semantic_input_changes_change_cache_identity(
    field: str,
    replacement: dict[str, str],
) -> None:
    baseline = _key()
    changed = _key(**{field: replacement})
    assert changed.key != baseline.key


def test_cache_kinds_share_contract_without_colliding() -> None:
    keys = {
        kind: build_cache_key(
            kind=kind,
            namespace="compile",
            materials={"input": "same"},
            toolchain={"tool": "same"},
        ).key
        for kind in ("python", "node", "assets", "generated")
    }
    assert len(set(keys.values())) == 4


def test_platform_is_explicit_not_implicitly_host_derived() -> None:
    linux = _key(toolchain={"python": "3.11.16", "platform": "linux-x86_64"})
    arm = _key(toolchain={"python": "3.11.16", "platform": "linux-arm64"})
    assert linux.key != arm.key


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": "unknown"},
        {"namespace": ""},
        {"namespace": "bad:value"},
        {"materials": {}},
        {"materials": {"x": 1}},
        {"toolchain": {}},
    ],
)
def test_malformed_cache_key_inputs_fail_closed(kwargs: dict[str, object]) -> None:
    with pytest.raises(CacheContractError):
        _key(**kwargs)


def test_eviction_is_deterministic_lru_with_stable_tie_breaking() -> None:
    entries = [
        CacheEntry("new", 4, last_access_generation=9, created_generation=8),
        CacheEntry("old-b", 4, last_access_generation=2, created_generation=1),
        CacheEntry("old-a", 4, last_access_generation=2, created_generation=1),
        CacheEntry("mid", 4, last_access_generation=5, created_generation=4),
    ]
    policy = EvictionPolicy(max_entries=2, max_bytes=8)

    plan = plan_eviction(entries, policy=policy, current_generation=10)

    assert plan.victims == ("old-a", "old-b")
    assert plan.retained == ("mid", "new")
    assert plan.bytes_before == 16
    assert plan.bytes_after == 8


def test_expiration_runs_before_budget_eviction_and_is_generation_based() -> None:
    entries = [
        CacheEntry("expired", 3, last_access_generation=2, created_generation=1),
        CacheEntry("warm", 3, last_access_generation=8, created_generation=4),
        CacheEntry("hot", 3, last_access_generation=10, created_generation=5),
    ]
    policy = EvictionPolicy(max_entries=2, max_bytes=6, ttl_generations=5)

    plan = plan_eviction(entries, policy=policy, current_generation=10)

    assert plan.expired == ("expired",)
    assert plan.victims == ("expired",)
    assert plan.retained == ("hot", "warm")


def test_pinned_entries_are_never_silently_discarded() -> None:
    entries = [
        CacheEntry("pinned", 8, 10, 1, pinned=True),
        CacheEntry("old", 4, 1, 1),
    ]
    plan = plan_eviction(
        entries,
        policy=EvictionPolicy(max_entries=1, max_bytes=8),
        current_generation=10,
    )
    assert plan.retained == ("pinned",)
    assert plan.victims == ("old",)

    with pytest.raises(CacheContractError, match="pinned entries exceed"):
        plan_eviction(
            [CacheEntry("too-large", 9, 10, 1, pinned=True)],
            policy=EvictionPolicy(max_entries=1, max_bytes=8),
            current_generation=10,
        )


def test_duplicate_future_and_temporally_invalid_entries_fail_closed() -> None:
    policy = EvictionPolicy(max_entries=10, max_bytes=100)

    with pytest.raises(CacheContractError, match="duplicate"):
        plan_eviction(
            [
                CacheEntry("same", 1, 1, 1),
                CacheEntry("same", 1, 1, 1),
            ],
            policy=policy,
            current_generation=2,
        )

    with pytest.raises(CacheContractError, match="future"):
        plan_eviction(
            [CacheEntry("future", 1, 3, 1)],
            policy=policy,
            current_generation=2,
        )

    with pytest.raises(CacheContractError, match="predates creation"):
        plan_eviction(
            [CacheEntry("invalid", 1, 1, 2)],
            policy=policy,
            current_generation=3,
        )


def test_mapping_entries_reject_unknown_fields() -> None:
    with pytest.raises(CacheContractError, match="unknown keys"):
        plan_eviction(
            [
                {
                    "key": "x",
                    "size_bytes": 1,
                    "last_access_generation": 1,
                    "created_generation": 1,
                    "shell": "rm -rf /",
                }
            ],
            policy=EvictionPolicy(max_entries=1, max_bytes=1),
            current_generation=1,
        )
