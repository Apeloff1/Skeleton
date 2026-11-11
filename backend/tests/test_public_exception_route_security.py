"""Behavioral and source-contract regression for server-error redaction."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.public_exception_route import PublicExceptionRoute


def _app() -> FastAPI:
    app = FastAPI()
    router = APIRouter(route_class=PublicExceptionRoute)

    @router.get("/failure")
    async def failure():
        raise RuntimeError("SECRET_ACCESS_TOKEN=do-not-expose /var/private/files")

    @router.get("/known/{code}")
    async def known(code: int):
        if code == 404:
            raise HTTPException(404, "known public error")
        return {"ok": True}

    @router.get("/declared-server-error/{status}")
    async def declared_server_error(status: int):
        if status < 500:
            raise HTTPException(
                status_code=status, detail={"reason": "ordinary public error"},
                headers={"Retry-After": "30"},
            )
        raise HTTPException(
            status_code=status,
            detail={"database_password": "private-db-password-do-not-leak"},
            headers={"X-Debug-Token": "private-debug-secret-do-not-leak"},
        )

    @router.get("/returned-server-error/{status}")
    async def returned_server_error(status: int):
        return JSONResponse(
            status_code=status,
            content={"detail": "private-response-body-must-not-leak"},
            headers={"X-Private-Debug": "private-response-header-must-not-leak"},
        )

    class Payload(BaseModel):
        count: int

    @router.post("/validated")
    async def validated(payload: Payload):
        return {"value": payload.count}

    app.include_router(router)
    return app


def test_unexpected_error_never_leaks_internal_message():
    with TestClient(_app(), raise_server_exceptions=False) as client:
        response = client.get("/failure")
    assert response.status_code == 500
    assert response.json() == {"detail": "internal server error"}
    assert "SECRET_ACCESS_TOKEN" not in response.text
    assert "/var/private" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_explicit_public_http_errors_are_preserved():
    with TestClient(_app(), raise_server_exceptions=False) as client:
        response = client.get("/known/404")
    assert response.status_code == 404
    assert response.json() == {"detail": "known public error"}


def test_explicit_server_http_errors_do_not_leak_details_or_headers():
    for status in (500, 502, 503):
        with TestClient(_app(), raise_server_exceptions=False) as client:
            response = client.get(f"/declared-server-error/{status}")
        assert response.status_code == status
        assert response.json() == {"detail": "internal server error"}
        assert "private-db-password" not in response.text
        assert "x-debug-token" not in response.headers
        assert response.headers["cache-control"] == "no-store"


def test_returned_server_responses_are_replaced_before_wire_serialization():
    for status in (500, 502, 503):
        with TestClient(_app(), raise_server_exceptions=False) as client:
            response = client.get(f"/returned-server-error/{status}")
        assert response.status_code == status
        assert response.json() == {"detail": "internal server error"}
        assert "private-response-body-must-not-leak" not in response.text
        assert "x-private-debug" not in response.headers
        assert response.headers["cache-control"] == "no-store"


def test_returned_client_responses_are_not_rewritten():
    with TestClient(_app(), raise_server_exceptions=False) as client:
        response = client.get("/returned-server-error/409")
    assert response.status_code == 409
    assert response.json() == {"detail": "private-response-body-must-not-leak"}
    assert response.headers["x-private-debug"] == "private-response-header-must-not-leak"


def test_explicit_public_client_errors_remain_unchanged():
    with TestClient(_app(), raise_server_exceptions=False) as client:
        response = client.get("/declared-server-error/429")
    assert response.status_code == 429
    assert response.json() == {"detail": {"reason": "ordinary public error"}}
    assert response.headers["retry-after"] == "30"


def test_request_validation_remains_http_422():
    with TestClient(_app(), raise_server_exceptions=False) as client:
        response = client.post("/validated", json={"count": "not-a-number"})
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"]


def _assert_private_build_route_inherits_public_error_custody(
    playable_source: str, build_source: str
) -> None:
    """Keep both project admission and inherited public 5xx redaction."""
    import ast

    playable_tree = ast.parse(playable_source)
    public_import = [
        node for node in playable_tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "core.public_exception_route"
        and any(alias.name == "PublicExceptionRoute" for alias in node.names)
    ]
    assert len(public_import) == 1
    private_classes = [
        node for node in playable_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "_PrivateProjectRoute"
    ]
    assert len(private_classes) == 1
    assert len(private_classes[0].bases) == 1
    assert isinstance(private_classes[0].bases[0], ast.Name)
    assert private_classes[0].bases[0].id == "PublicExceptionRoute"

    build_tree = ast.parse(build_source)
    private_import = [
        node for node in build_tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "routes.playable_access"
        and any(alias.name == "_PrivateProjectRoute" for alias in node.names)
    ]
    assert len(private_import) == 1
    routers = [
        node.value for node in build_tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "router"
                for target in node.targets)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "APIRouter"
    ]
    assert len(routers) == 1
    route_classes = [keyword.value for keyword in routers[0].keywords
                     if keyword.arg == "route_class"]
    assert len(route_classes) == 1
    assert isinstance(route_classes[0], ast.Name)
    assert route_classes[0].id == "_PrivateProjectRoute"


def test_legacy_routes_use_fail_closed_error_boundary():
    backend = Path(__file__).resolve().parents[1]
    for filename in (
        "nexus.py", "swarm_planner.py", "swarm_cold_legion.py",
        "storage.py", "text_gamefile.py", "sota_2026.py",
        "build_pipeline.py",
    ):
        source = (backend / "routes" / filename).read_text(encoding="utf-8")
        assert "PublicExceptionRoute" in source, filename
        assert "route_class=PublicExceptionRoute" in source, filename

    _assert_private_build_route_inherits_public_error_custody(
        (backend / "routes/playable_access.py").read_text(encoding="utf-8"),
        (backend / "routes/gameforge_build.py").read_text(encoding="utf-8"),
    )


def test_private_build_route_contract_rejects_security_regressions():
    backend = Path(__file__).resolve().parents[1]
    playable = (backend / "routes/playable_access.py").read_text(encoding="utf-8")
    build = (backend / "routes/gameforge_build.py").read_text(encoding="utf-8")
    mutations = (
        (playable.replace(
            "class _PrivateProjectRoute(PublicExceptionRoute):",
            "class _PrivateProjectRoute(APIRoute):", 1), build),
        (playable.replace(
            "from core.public_exception_route import PublicExceptionRoute",
            "from fastapi.routing import PublicExceptionRoute", 1), build),
        (playable, build.replace(
            "route_class=_PrivateProjectRoute", "route_class=APIRoute", 1)),
        (playable, build.replace(
            "from routes.playable_access import _PrivateProjectRoute",
            "from routes.other_access import _PrivateProjectRoute", 1)),
    )
    for mutated_playable, mutated_build in mutations:
        assert (mutated_playable, mutated_build) != (playable, build)
        try:
            _assert_private_build_route_inherits_public_error_custody(
                mutated_playable, mutated_build
            )
        except AssertionError:
            continue
        raise AssertionError("unprotected private build route passed contract")
