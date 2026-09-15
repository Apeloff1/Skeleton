"""
Route-ordering shadowing GUARD (2026-06) — countermeasure for the class of
bug fixed in iteration 4 (the dynamic `/pipeline/{build_id}` route was
registered BEFORE the static `/pipeline/catalog` route, so Starlette matched
"catalog" as a build_id and the catalog endpoint returned the wrong payload).

This is an AUTOMATIC, per-module regression guard: it enumerates EVERY route on
the galaxy-studio router (and every sub-router mounted under it) and asserts no
STATIC path is shadowed by an EARLIER-registered DYNAMIC sibling. Any future
extraction that re-introduces the ordering bug fails here — no per-endpoint
test needed.

It also keeps the live HTTP counter-checks: static catalogs resolve correctly
AND a bogus dynamic id does NOT return the catalog payload.
"""
import os
import re

import pytest
import requests


# ─────────────────────────────────────────────────────────────────────────
# Part 1 — In-process structural guard (no server needed)
# ─────────────────────────────────────────────────────────────────────────
def _galaxy_routes():
    """Return [(path, methods)] for the galaxy-studio router in registration order."""
    from routes.galaxy_studio import router as galaxy_router
    out = []
    for r in galaxy_router.routes:
        path = getattr(r, "path", None)
        if not path:
            continue
        methods = getattr(r, "methods", set()) or set()
        out.append((path, frozenset(methods)))
    return out


def _segments(path):
    return [s for s in path.strip("/").split("/")]


def _dynamic_matches_static(dyn_path, static_path):
    """True if `dyn_path` (with {param} segments) would match `static_path`.

    Same number of segments AND every dyn segment is either an exact literal
    match OR a `{param}` placeholder. A placeholder swallows the corresponding
    static literal segment — which is exactly the shadowing failure mode.
    """
    d, s = _segments(dyn_path), _segments(static_path)
    if len(d) != len(s):
        return False
    for ds, ss in zip(d, s):
        is_param = ds.startswith("{") and ds.endswith("}")
        if not is_param and ds != ss:
            return False
    return True


class TestRouteOrderingGuard:
    def test_no_static_route_is_shadowed_by_earlier_dynamic(self):
        routes = _galaxy_routes()
        dyn_re = re.compile(r"\{[^/}]+\}")
        violations = []
        for i, (path_i, methods_i) in enumerate(routes):
            if dyn_re.search(path_i):
                continue  # only audit STATIC targets
            # any EARLIER dynamic route that would swallow this static path?
            for j in range(i):
                path_j, methods_j = routes[j]
                if not dyn_re.search(path_j):
                    continue
                if methods_i and methods_j and methods_i.isdisjoint(methods_j):
                    continue  # different HTTP verbs can't collide
                if _dynamic_matches_static(path_j, path_i):
                    violations.append(
                        f"STATIC {sorted(methods_i)} {path_i} is shadowed by EARLIER "
                        f"DYNAMIC {sorted(methods_j)} {path_j} (index {j} < {i})"
                    )
        assert not violations, (
            "Route-ordering shadowing detected — a static path is registered "
            "AFTER a dynamic sibling that would match it first:\n  "
            + "\n  ".join(violations)
        )

    def test_known_catalog_paths_present_and_static(self):
        """The 3 catalog delegators must exist as STATIC routes."""
        paths = {p for p, _ in _galaxy_routes()}
        for cat in (
            "/api/galaxy-studio/pipeline/catalog",
            "/api/galaxy-studio/datasets/catalog",
            "/api/galaxy-studio/capabilities/catalog",
        ):
            assert cat in paths, f"missing static catalog route {cat}; have e.g. {sorted(paths)[:6]}"


# ─────────────────────────────────────────────────────────────────────────
# Part 2 — Live HTTP counter-checks (static wins / dynamic still works)
# ─────────────────────────────────────────────────────────────────────────
def _base_url() -> str:
    base = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
    if not base:
        with open("/app/frontend/.env") as fh:
            for line in fh:
                if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                    base = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                    break
    assert base, "EXPO_PUBLIC_BACKEND_URL must be set"
    return base


BASE_URL = _base_url()


class TestLiveCatalogResolution:
    def test_pipeline_catalog_resolves_static(self):
        r = requests.get(f"{BASE_URL}/api/galaxy-studio/pipeline/catalog", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # catalog payload — stage/task signal, NOT a build-lookup response
        assert isinstance(data, dict)
        assert any(k in data for k in ("total_stages", "stages", "total_tasks")), \
            f"pipeline/catalog returned non-catalog shape: {list(data.keys())[:8]}"

    def test_bogus_build_id_is_not_catalog(self):
        """A non-existent build id must NOT resolve to the catalog payload."""
        r = requests.get(f"{BASE_URL}/api/galaxy-studio/pipeline/__no_such_build__", timeout=15)
        # Either a 404/empty OR a build-shaped response — but never the catalog.
        if r.status_code == 200:
            data = r.json()
            assert not (isinstance(data, dict) and data.get("total_stages")), \
                "bogus /pipeline/{id} leaked the catalog payload — ordering bug regressed"
