from fastapi import FastAPI

from core.routes_registry import KNOWN_ROUTES, register_routes


def test_mirror_room_router_is_in_canonical_registry() -> None:
    assert ("routes.mirror_room", "router") in KNOWN_ROUTES


def test_mirror_room_registry_mount_exposes_read_only_observatory_routes() -> None:
    app = FastAPI()
    report = register_routes(app, [("routes.mirror_room", "router")])

    assert report["ok"] == 1
    assert report["skipped"] == 0
    # Both flattened routes and FastAPI's preserved nested mounts must
    # report the same canonical API paths without depending on private layout.
    paths = set(report["mounted_paths"]["routes.mirror_room"])
    assert {
        "/api/mirror-room/status",
        "/api/mirror-room/file-tree",
        "/api/mirror-room/observatory",
    } <= paths
