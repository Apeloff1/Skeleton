"""Pack F authZ policies and pipeline routes derived from the systems catalog.

The edge enforces system-level scopes itself (see :mod:`.edge`); these
builders additionally publish the same rules as a
:class:`~skeleton.gate_plane.s2s.authz.PolicyTable` and a
:class:`~skeleton.gate_plane.pipeline.routes.RouteTable`, so an app that
already runs ``S2SAuthMiddleware`` / ``PipelineRouter`` sees identical
decisions for the recovered systems. Merging into an existing table only
adds rows; it never replaces or reorders a policy the base already owns.
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from skeleton.gate_plane.pipeline.breaker import BreakerConfig
from skeleton.gate_plane.pipeline.retry import RetrySpec
from skeleton.gate_plane.pipeline.routes import RouteConfig, RouteTable
from skeleton.gate_plane.s2s.authz import MUTATING_METHODS, PolicyError, PolicyTable, RoutePolicy
from skeleton.gate_plane.systems.catalog import SAFE_METHODS, SystemCatalog, SystemProfile, default_catalog

READ_METHODS = sorted(SAFE_METHODS)
WRITE_METHODS = sorted(MUTATING_METHODS)


def _allow_kwargs(profile: SystemProfile) -> dict:
    out: dict = {"deny_services": sorted(profile.deny_services)}
    if profile.allow_services is not None:
        out["allow_services"] = sorted(profile.allow_services)
    return out


def system_policies(profile: SystemProfile) -> List[RoutePolicy]:
    """Policies for one system: anonymous probes, admin, read and write rows."""
    rows: List[RoutePolicy] = []
    read_m = [m for m in READ_METHODS if m in profile.methods]
    write_m = [m for m in WRITE_METHODS if m in profile.methods]
    for i, pat in enumerate(profile.anonymous_read_patterns):
        rows.append(
            RoutePolicy.build(
                f"{profile.name}-probe-{i}", pat, methods=[m for m in ("GET", "HEAD") if m in profile.methods] or ["GET"],
                allow_anonymous=True, priority=0,
            )
        )
    for i, pat in enumerate(profile.admin_patterns):
        rows.append(
            RoutePolicy.build(
                f"{profile.name}-admin-{i}", pat, scopes_any=sorted(profile.admin_scopes),
                allow_overlap_keys=False, priority=min(profile.priority, 1), **_allow_kwargs(profile),
            )
        )
    for i, pat in enumerate(profile.patterns):
        if read_m:
            rows.append(
                RoutePolicy.build(
                    f"{profile.name}-read-{i}", pat, methods=read_m,
                    scopes_any=sorted(profile.read_scopes | profile.write_scopes),
                    priority=profile.priority, **_allow_kwargs(profile),
                )
            )
        if write_m:
            rows.append(
                RoutePolicy.build(
                    f"{profile.name}-write-{i}", pat, methods=write_m,
                    scopes_any=sorted(profile.write_scopes),
                    priority=profile.priority, **_allow_kwargs(profile),
                )
            )
    return rows


def catalog_policies(catalog: Optional[SystemCatalog] = None) -> PolicyTable:
    """Default-deny table covering only the catalog's systems."""
    cat = catalog if catalog is not None else default_catalog()
    rows: List[RoutePolicy] = []
    for prof in cat.profiles():
        rows.extend(system_policies(prof))
    return PolicyTable(rows)


def merge_into(base: PolicyTable, catalog: Optional[SystemCatalog] = None) -> PolicyTable:
    """New table = ``base`` rows + catalog rows. Conflicts raise instead of overriding."""
    merged = PolicyTable(base.policies())
    cat = catalog if catalog is not None else default_catalog()
    for prof in cat.profiles():
        for row in system_policies(prof):
            try:
                merged.add(row)
            except PolicyError as exc:
                raise PolicyError(f"system {prof.name!r} conflicts with base policy table: {exc}") from exc
    return merged


def system_routes(profile: SystemProfile) -> List[RouteConfig]:
    """Pipeline routes (deadline, retry, breaker) for one system's upstream."""
    lim = profile.limits
    breaker = BreakerConfig(
        consecutive_failures=lim.breaker_failures,
        min_calls=max(lim.breaker_failures, 2),
        window_size=max(lim.breaker_failures * 2, 4),
        cooldown_s=lim.breaker_cooldown_s,
    )
    read_m = frozenset(m for m in SAFE_METHODS if m in profile.methods)
    write_m = frozenset(m for m in MUTATING_METHODS if m in profile.methods)
    out: List[RouteConfig] = []
    for i, pat in enumerate(profile.patterns):
        if read_m:
            out.append(
                RouteConfig(
                    name=f"{profile.name}-read-{i}", pattern=pat, upstream=profile.upstream, methods=read_m,
                    timeout_s=lim.deadline_for("GET"),
                    retry=RetrySpec(max_attempts=lim.retry_attempts), breaker=breaker,
                )
            )
        if write_m:
            out.append(
                RouteConfig(
                    name=f"{profile.name}-write-{i}", pattern=pat, upstream=profile.upstream, methods=write_m,
                    timeout_s=lim.deadline_for("POST"),
                    # Writes retry only with an Idempotency-Key (RetrySpec default); never more than reads.
                    retry=RetrySpec(max_attempts=min(lim.retry_attempts, 2)), breaker=breaker,
                )
            )
    return out


def catalog_routes(catalog: Optional[SystemCatalog] = None, *, extra: Iterable[RouteConfig] = ()) -> RouteTable:
    cat = catalog if catalog is not None else default_catalog()
    table = RouteTable(list(extra))
    for prof in cat.profiles():
        for r in system_routes(prof):
            table.add(r)
    return table


__all__ = [
    "catalog_policies",
    "catalog_routes",
    "merge_into",
    "system_policies",
    "system_routes",
]
