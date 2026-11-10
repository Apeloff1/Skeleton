import pytest
from skeleton.api.v1_edge.registry import RouteRegistry, RouteSpec


def test_match_params_and_specificity():
    r = RouteRegistry()
    r.register(RouteSpec("GET", "/p/{id}"))
    r.register(RouteSpec("GET", "/p/special"))
    spec, params, _ = r.match("GET", "/api/v1/p/special")
    assert spec.path == "/p/special" and params == {}
    spec, params, _ = r.match("get", "/api/v1/p/42")
    assert params == {"id": "42"}


def test_405_vs_404_and_head():
    r = RouteRegistry()
    r.register(RouteSpec("GET", "/x"))
    assert r.match("POST", "/api/v1/x")[2] is True
    assert r.match("POST", "/api/v1/y")[2] is False
    assert r.match("HEAD", "/api/v1/x")[0] is not None
    assert r.allowed_methods("/api/v1/x") == ["GET"]


def test_rejects_bad_specs_and_duplicates():
    with pytest.raises(ValueError):
        RouteSpec("GET", "x")
    with pytest.raises(ValueError):
        RouteSpec("GET", "/x", auth="magic")
    r = RouteRegistry()
    r.register(RouteSpec("GET", "/x"))
    with pytest.raises(ValueError):
        r.register(RouteSpec("get", "/x"))
    assert r.card()["routes"] == 1


def test_param_does_not_cross_segments_or_regex_inject():
    r = RouteRegistry()
    r.register(RouteSpec("GET", "/a.b/{id}"))
    assert r.match("GET", "/api/v1/a.b/1/2")[0] is None
    assert r.match("GET", "/api/v1/aXb/1")[0] is None
