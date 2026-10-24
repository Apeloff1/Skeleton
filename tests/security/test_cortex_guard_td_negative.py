"""TD (Jenkins) negative tests for cortex_mount_guard -- blockers from the #4129 review.

Each test asserts the guard REFUSES a bypass. They are xfail(strict=True) while the
blocker is open on main, so they flip to XPASS (and fail CI) the moment a fix lands,
forcing removal of the marker. See PR description for the blocker map.
"""
import pytest
from fastapi import APIRouter, FastAPI
from starlette.routing import Mount

from skeleton.api import cortex_routes
from skeleton.api.cortex_mount_guard import reject_cortex_secret_routes

OPEN = pytest.mark.xfail(strict=True, reason="TD blocker open on main (#4129 review)")


def _cortex_router():
    r = APIRouter()
    reg = getattr(cortex_routes, "register_routes", None)
    if reg is None:
        pytest.skip("cortex_routes.register_routes unavailable")
    from unittest.mock import MagicMock
    reg(r, MagicMock())  # deck is only captured by handlers, never called at registration
    return r


def _refuses(app):
    with pytest.raises(RuntimeError):
        reject_cortex_secret_routes(app)


def test_baseline_plain_secrets_route_refused():
    app = FastAPI()

    @app.get("/api/v1/secrets/x")
    def _h():
        return {}

    _refuses(app)


@OPEN
def test_b1_fake_route_object_with_text_path_needs_type_allowlist():
    class Fake:  # not a Starlette route type; serves anything
        path = "/healthz"
        routes = []

        async def __call__(self, scope, receive, send):
            pass

    app = FastAPI()
    app.router.routes.append(Fake())
    _refuses(app)


@OPEN
def test_b2_opaque_mount_at_parameter_path():
    async def opaque(scope, receive, send):
        pass

    app = FastAPI()
    app.router.routes.append(Mount("/{tenant}", app=opaque))
    _refuses(app)


@OPEN
def test_b3_cortex_handlers_under_other_prefix_refused_by_module():
    app = FastAPI()
    app.include_router(_cortex_router(), prefix="/internal")
    _refuses(app)


@OPEN
@pytest.mark.parametrize("p", ["/api/v1/x/../secrets/k", "/api/v1/./secrets/k",
                               "/api/v1/%2e%2e/v1/secrets/k", "/api/v1/\uff53ecrets/k"])
def test_b4_dot_segments_and_unicode(p):
    app = FastAPI()
    app.add_api_route(p, lambda: {})
    _refuses(app)


@OPEN
def test_b5_route_added_after_create_app_rechecked_by_default():
    from fastapi.testclient import TestClient
    from skeleton.api.server import create_app

    app = create_app()
    app.add_api_route("/api/v1/secrets/late", lambda: {})
    with pytest.raises(Exception):
        with TestClient(app):
            pass


@OPEN
def test_b6_low_priority_routes_walked():
    app = FastAPI()
    holder = getattr(app.router, "_low_priority_routes", None)
    if holder is None:
        pytest.skip("router has no _low_priority_routes on this FastAPI")
    r = APIRouter()
    r.add_api_route("/api/v1/secrets/lp", lambda: {})
    holder.extend(r.routes)
    _refuses(app)


@OPEN
def test_cycle_raises():
    a, b = Mount("/a", routes=[]), Mount("/b", routes=[])
    a.routes.append(b)
    b.routes.append(a)
    app = FastAPI()
    app.router.routes.append(a)
    _refuses(app)
