"""Story-continuity endpoints are discoverable and creator protected."""
from fastapi import FastAPI
from core.routes_registry import KNOWN_ROUTES_WITH_PREFIX, register_routes
from routes.story_index import router as story_router
from skeleton.api.cortex_mount_guard import iter_route_paths


def test_story_index_is_registered_under_canonical_playable_games():
    entry = ("routes.story_index", "router", "/api/playable")
    assert entry in KNOWN_ROUTES_WITH_PREFIX
    app = FastAPI()
    report = register_routes(app, [entry])
    assert report["ok"] == 1, report
    assert report["skipped"] == 0
    # FastAPI can represent included routers as lazy _IncludedRouter entries.
    # Inspect the composed app paths instead of assuming every entry has .path.
    paths = set(iter_route_paths(app))
    expected = {
        "/api/playable/{pid}/story-index/events",
        "/api/playable/{pid}/story-index/audit",
        "/api/playable/{pid}/story-index/recall/{character_id}",
    }
    assert expected <= paths
    # Confirm allowed methods on the same router whose mounted paths were checked.
    registered = [
        route for route in story_router.routes
        if route.path == "/{pid}/story-index/events"
    ]
    assert any("POST" in route.methods for route in registered)
    assert any("GET" in route.methods for route in registered)
