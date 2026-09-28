"""Deterministic cache identity/eviction regressions for #807 B003."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.build.cache_contract import (
    CacheContractError,
    CacheDomainPolicy,
    CacheEntry,
    CachePolicy,
    REQUIRED_DOMAINS,
    SECONDS_PER_DAY,
    cli_main,
    compile_cache_key,
    load_policy,
    plan_evictions,
)


def _policy() -> CachePolicy:
    return load_policy()


def _entry(
    key: str,
    *,
    domain: str = "python",
    size: int = 10,
    created: int = 100,
    used: int = 200,
) -> CacheEntry:
    return CacheEntry(
        key=key,
        domain=domain,
        size_bytes=size,
        created_epoch=created,
        last_used_epoch=used,
    )


def _with_python_budget(
    policy: CachePolicy,
    *,
    max_entries: int,
    max_bytes: int,
    max_age_days: int | None = None,
) -> CachePolicy:
    domains = dict(policy.domains)
    domains["python"] = CacheDomainPolicy(
        max_entries=max_entries,
        max_bytes=max_bytes,
    )
    return replace(
        policy,
        max_age_days=policy.max_age_days if max_age_days is None else max_age_days,
        domains=tuple(sorted(domains.items())),
    )


def test_repository_policy_covers_all_canonical_domains() -> None:
    policy = _policy()
    assert tuple(name for name, _ in policy.domains) == REQUIRED_DOMAINS
    assert REQUIRED_DOMAINS == ("assets", "generated", "node", "python")
    assert policy.algorithm == "sha256"
    assert policy.max_age_days == 30


def test_material_order_does_not_change_cache_identity() -> None:
    policy = _policy()
    left = compile_cache_key(
        policy,
        domain="python",
        materials={
            "lockfile": "sha256:aaa",
            "toolchain": "python-3.11",
            "platform": "linux-arm64",
        },
    )
    right = compile_cache_key(
        policy,
        domain="python",
        materials={
            "platform": "linux-arm64",
            "toolchain": "python-3.11",
            "lockfile": "sha256:aaa",
        },
    )
    assert left == right
    assert left.key.startswith("skeleton-cache-v1-python-")
    assert len(left.digest) == 64


def test_local_and_ci_share_identity_by_construction() -> None:
    policy = _policy()
    materials = {
        "lockfile": "requirements.lock:abc",
        "toolchain": "python-3.11.16",
        "platform": "linux-arm64",
    }
    local_key = compile_cache_key(policy, domain="python", materials=materials)
    ci_key = compile_cache_key(policy, domain="python", materials=dict(materials))
    assert local_key == ci_key


@pytest.mark.parametrize("domain", REQUIRED_DOMAINS)
def test_all_domains_use_same_key_contract(domain: str) -> None:
    key = compile_cache_key(
        _policy(),
        domain=domain,
        materials={"content": "same-material"},
    )
    assert key.domain == domain
    assert key.key.startswith(f"skeleton-cache-v1-{domain}-")


def test_domains_are_separated_even_for_identical_materials() -> None:
    policy = _policy()
    materials = {"content": "same-material"}
    keys = {
        compile_cache_key(policy, domain=domain, materials=materials).key
        for domain in REQUIRED_DOMAINS
    }
    assert len(keys) == len(REQUIRED_DOMAINS)


def test_build_graph_fingerprint_participates_in_key() -> None:
    policy = _policy()
    materials = {"inputs": "same"}
    one = compile_cache_key(
        policy,
        domain="generated",
        materials=materials,
        build_graph_fingerprint="a" * 64,
    )
    two = compile_cache_key(
        policy,
        domain="generated",
        materials=materials,
        build_graph_fingerprint="b" * 64,
    )
    assert one.key != two.key


def test_policy_change_invalidates_cache_identity() -> None:
    policy = _policy()
    changed = _with_python_budget(
        policy,
        max_entries=31,
        max_bytes=policy.domain_map()["python"].max_bytes,
    )
    materials = {"lock": "same"}
    assert compile_cache_key(
        policy,
        domain="python",
        materials=materials,
    ).key != compile_cache_key(
        changed,
        domain="python",
        materials=materials,
    ).key


def test_eviction_is_deterministic_and_order_independent() -> None:
    policy = _with_python_budget(
        _policy(),
        max_entries=2,
        max_bytes=1000,
        max_age_days=365,
    )
    entries = [
        _entry("new", created=30, used=300),
        _entry("old", created=10, used=100),
        _entry("middle", created=20, used=200),
    ]
    left = plan_evictions(
        policy,
        domain="python",
        entries=entries,
        now_epoch=400,
    )
    right = plan_evictions(
        policy,
        domain="python",
        entries=reversed(entries),
        now_epoch=400,
    )
    assert left == right == ("old",)


def test_byte_budget_evicts_lru_until_satisfied() -> None:
    policy = _with_python_budget(
        _policy(),
        max_entries=10,
        max_bytes=15,
        max_age_days=365,
    )
    entries = [
        _entry("a", size=10, created=10, used=100),
        _entry("b", size=10, created=20, used=200),
        _entry("c", size=5, created=30, used=300),
    ]
    assert plan_evictions(
        policy,
        domain="python",
        entries=entries,
        now_epoch=400,
    ) == ("a",)


def test_expired_entries_are_removed_before_budget_selection() -> None:
    policy = _with_python_budget(
        _policy(),
        max_entries=10,
        max_bytes=1000,
        max_age_days=30,
    )
    now = 40 * SECONDS_PER_DAY
    entries = [
        _entry("expired", created=0, used=10 * SECONDS_PER_DAY),
        _entry("fresh", created=30 * SECONDS_PER_DAY, used=39 * SECONDS_PER_DAY),
    ]
    assert plan_evictions(
        policy,
        domain="python",
        entries=entries,
        now_epoch=now,
    ) == ("expired",)


def test_eviction_ties_break_by_creation_then_key() -> None:
    policy = _with_python_budget(
        _policy(),
        max_entries=1,
        max_bytes=1000,
        max_age_days=365,
    )
    entries = [
        _entry("b", created=10, used=100),
        _entry("a", created=10, used=100),
    ]
    assert plan_evictions(
        policy,
        domain="python",
        entries=entries,
        now_epoch=200,
    ) == ("a",)


def test_invalid_materials_and_domains_fail_closed() -> None:
    policy = _policy()
    with pytest.raises(CacheContractError, match="unknown cache domain"):
        compile_cache_key(policy, domain="other", materials={"x": "y"})
    with pytest.raises(CacheContractError, match="at least one material"):
        compile_cache_key(policy, domain="python", materials={})
    with pytest.raises(CacheContractError, match="invalid material name"):
        compile_cache_key(policy, domain="python", materials={"bad name": "x"})
    with pytest.raises(CacheContractError, match="lowercase SHA-256"):
        compile_cache_key(
            policy,
            domain="python",
            materials={"x": "y"},
            build_graph_fingerprint="A" * 64,
        )


def test_invalid_entries_fail_closed() -> None:
    policy = _policy()
    with pytest.raises(CacheContractError, match="domain mismatch"):
        plan_evictions(
            policy,
            domain="python",
            entries=[_entry("x", domain="node")],
            now_epoch=300,
        )
    with pytest.raises(CacheContractError, match="duplicate cache entry key"):
        plan_evictions(
            policy,
            domain="python",
            entries=[_entry("x"), _entry("x")],
            now_epoch=300,
        )
    with pytest.raises(CacheContractError, match="future"):
        plan_evictions(
            policy,
            domain="python",
            entries=[_entry("x", used=400)],
            now_epoch=300,
        )


def test_duplicate_policy_json_keys_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "cache-policy.json"
    path.write_text(
        '{"schema_version":1,"schema_version":1}',
        encoding="utf-8",
    )
    with pytest.raises(CacheContractError, match="duplicate JSON key"):
        load_policy(path)


def test_policy_rejects_missing_canonical_domain(tmp_path: Path) -> None:
    payload = _policy().to_dict()
    payload["domains"].pop("assets")
    path = tmp_path / "cache-policy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CacheContractError, match="canonical domain set"):
        load_policy(path)


def test_cli_emits_same_key_as_library(capsys: pytest.CaptureFixture[str]) -> None:
    policy = _policy()
    expected = compile_cache_key(
        policy,
        domain="node",
        materials={"lockfile": "yarn.lock:abc", "toolchain": "node-22"},
    )
    assert cli_main(
        [
            "key",
            "--domain",
            "node",
            "--material",
            "lockfile=yarn.lock:abc",
            "--material",
            "toolchain=node-22",
        ]
    ) == 0
    assert capsys.readouterr().out.strip() == expected.key


def test_cli_rejects_duplicate_material_name(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main(
        [
            "key",
            "--domain",
            "python",
            "--material",
            "lock=a",
            "--material",
            "lock=b",
        ]
    ) == 1
    assert "duplicate CLI material name" in capsys.readouterr().out


def test_repository_cli_wrapper_runs_without_installed_package() -> None:
    root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/cache_contract.py",
            "key",
            "--domain",
            "assets",
            "--material",
            "content=asset-digest",
        ],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert completed.stderr == ""
    assert completed.stdout.strip().startswith("skeleton-cache-v1-assets-")
