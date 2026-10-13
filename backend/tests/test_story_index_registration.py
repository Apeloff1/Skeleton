"""Story-continuity endpoints are discoverable and creator protected."""
from fastapi import FastAPI
from core.routes_registry import KNOWN_ROUTES_WITH_PREFIX, register_routes


def test_story_index_is_registered_under_canonical_playable_games():
    entry = ("routes.story_index", "router", "/api/playable")
    assert entry in KNOWN_ROUTES_WITH_PREFIX
    app = FastAPI()
    report = register_routes(app, [entry])
    assert report["ok"] == 1, report
    assert report["skipped"] == 0
    paths = {route.path for route in app.routes}
    expected = {
        "/api/playable/{pid}/story-index/events",
        "/api/playable/{pid}/story-index/audit",
        "/api/playable/{pid}/story-index/recall/{character_id}",
    }
    assert expected <= paths
    registered = [
        route for route in app.routes
        if route.path == "/api/playable/{pid}/story-index/events"
    ]
    assert any("POST" in route.methods for route in registered)
    assert any("GET" in route.methods for route in registered)
