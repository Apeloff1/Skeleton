"""Fail-closed URL admission for installed application health probes."""
import pytest
from skeleton.app.health import probe_http

@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "data:text/plain,ok", "ftp://localhost/x",
    "http://user:password@localhost:8010/health",
    "http://localhost:bad/health", "http://localhost:0/health",
    "http://localhost:8010/health#fragment", "http:///missing-host",
    "http://local\\host:8010/health", "http://local%68ost:8010/health",
    "http://localhost:8010/health\nX-Injected: yes",
    " http://localhost:8010/health", "http://localhost:8010/health\t",
])
def test_invalid_target_never_dispatches(monkeypatch, url):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid URL dispatched IO")
    monkeypatch.setattr("skeleton.app.health._open_direct_health", forbidden)
    result = probe_http("engine", url)
    assert not result.ok
    assert result.status is None
    assert result.url == ""
    assert result.detail == "health probe requires HTTP(S) without credentials"

def test_valid_http_still_uses_direct_transport(monkeypatch):
    class Response:
        status = 204
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def read(self, _size):
            return b""
        def geturl(self):
            return "http://127.0.0.1:8010/health"
    seen = []
    def direct(request, *, timeout):
        seen.append((request.full_url, timeout))
        return Response()
    monkeypatch.setattr("skeleton.app.health._open_direct_health", direct)
    result = probe_http("engine", "http://127.0.0.1:8010/health", timeout=1)
    assert result.ok
    assert seen == [("http://127.0.0.1:8010/health", 1)]

@pytest.mark.parametrize("budget", [True, False, None, "3", float("nan"), float("inf"), -1, 0, 31])
def test_invalid_timeout_fails_before_io(monkeypatch, budget):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid timeout dispatched IO")
    monkeypatch.setattr("skeleton.app.health._open_direct_health", forbidden)
    with pytest.raises((ValueError, TypeError), match="timeout"):
        probe_http("engine", "http://127.0.0.1:8010/health", timeout=budget)


@pytest.mark.parametrize("origin", [
    "http://127.0.0.1:8080\nX-Injected: yes",
    "http://127.0.0.1:8080\t",
    " http://127.0.0.1:8080",
    "http://127.0.0.1:8080 ",
    "http://127.0.0.1:8080\x7f",
])
def test_setup_probe_rejects_malformed_origin_without_io(monkeypatch, origin):
    from dataclasses import replace
    from skeleton.app.assembly import load_manifest
    from skeleton.app.health import probe_local_setup

    service = replace(load_manifest().service("frontend"), public_url=origin, health_path="/setup")
    def forbidden(*args, **kwargs):
        pytest.fail("malformed setup origin dispatched IO")
    monkeypatch.setattr("skeleton.app.health.build_opener", forbidden)
    result = probe_local_setup(service)
    assert not result.ok
    assert result.status is None
    assert result.url == ""


@pytest.mark.parametrize("budget", [True, False, None, "3", float("nan"), float("inf"), 0, -1, 11])
def test_setup_probe_rejects_invalid_timeout_before_io(monkeypatch, budget):
    from dataclasses import replace
    from skeleton.app.assembly import load_manifest
    from skeleton.app.health import probe_local_setup

    service = replace(load_manifest().service("frontend"), public_url="http://127.0.0.1:8080", health_path="/setup")
    def forbidden(*args, **kwargs):
        pytest.fail("invalid setup timeout dispatched IO")
    monkeypatch.setattr("skeleton.app.health.build_opener", forbidden)
    with pytest.raises(ValueError, match="timeout"):
        probe_local_setup(service, timeout=budget)


@pytest.mark.parametrize("field,value", [
    ("timeout", True), ("timeout", None), ("timeout", "3"),
    ("timeout", float("nan")), ("timeout", float("inf")),
    ("delay", False), ("delay", None), ("delay", "1"),
    ("delay", float("nan")), ("delay", float("-inf")),
])
def test_wait_budget_validation_precedes_probe(monkeypatch, field, value):
    from skeleton.app.health import wait_for_application
    def forbidden(*args, **kwargs):
        pytest.fail("invalid wait budget dispatched IO")
    monkeypatch.setattr("skeleton.app.health.probe_application", forbidden)
    with pytest.raises(ValueError, match=field):
        wait_for_application(**{field: value})


@pytest.mark.parametrize("status,final_url", [
    (None, "http://127.0.0.1:8010/health"),
    (True, "http://127.0.0.1:8010/health"),
    ("200", "http://127.0.0.1:8010/health"),
    (0, "http://127.0.0.1:8010/health"),
    (600, "http://127.0.0.1:8010/health"),
    (200, None),
    (200, 123),
])
def test_untrusted_transport_metadata_cannot_report_healthy(monkeypatch, status, final_url):
    url = "http://127.0.0.1:8010/health"
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def read(self, _size):
            return b""
        def geturl(self):
            return final_url
    response = Response()
    response.status = status
    monkeypatch.setattr("skeleton.app.health._open_direct_health", lambda *_args, **_kwargs: response)
    result = probe_http("engine", url)
    assert result.ok is False
    assert result.status is None
    assert result.detail == "health transport returned invalid response metadata"


def test_missing_transport_url_method_fails_closed(monkeypatch):
    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def read(self, _size):
            return b""
    monkeypatch.setattr("skeleton.app.health._open_direct_health", lambda *_args, **_kwargs: Response())
    result = probe_http("engine", "http://127.0.0.1:8010/health")
    assert not result.ok
    assert result.status is None
    assert result.detail == "health transport returned invalid response metadata"



@pytest.mark.parametrize("suffix", ["?token=private", "?", "#", "?x=1#",
                                    "/" + "x" * 4096])
def test_health_rejects_unreviewed_suffix_without_echoing_it(monkeypatch, suffix):
    def forbidden(*args, **kwargs):
        pytest.fail("unreviewed URL dispatched IO")
    monkeypatch.setattr("skeleton.app.health._open_direct_health", forbidden)
    result = probe_http("engine", "http://127.0.0.1:8010/health" + suffix)
    assert not result.ok and result.url == ""


@pytest.mark.parametrize("origin", [
    "http://localhost:8080?", "http://localhost:8080#",
    "http://localhost:8080?token=private", "http://local%68ost:8080",
    "http://localhost:8080\\", "http://localhost:8080/" + "x" * 4096,
])
def test_setup_rejects_ambiguous_origin_before_io(monkeypatch, origin):
    from types import SimpleNamespace
    from skeleton.app.health import probe_local_setup
    def forbidden(*args, **kwargs):
        pytest.fail("invalid setup origin dispatched IO")
    monkeypatch.setattr("skeleton.app.health._open_direct_health", forbidden)
    service = SimpleNamespace(name="frontend", public_url=origin, health_path="/setup")
    assert probe_local_setup(service).url == ""


_SETUP_URL = "http://127.0.0.1:8080/setup"


def _setup_response(status, final_url, content_types, sample):
    from email.message import Message

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def geturl(self):
            return final_url
        def read(self, size):
            assert size == 512
            return sample

    response = Response()
    if status != "missing":
        response.status = status
    response.headers = Message()
    for value in content_types:
        response.headers["Content-Type"] = value
    return response


@pytest.mark.parametrize("status", ["missing", None, True, "200", 0, 600, 302, 503])
def test_setup_requires_observed_success_status(monkeypatch, status):
    from types import SimpleNamespace
    from skeleton.app.health import probe_local_setup
    response = _setup_response(status, _SETUP_URL, ["text/html"], b"<!doctype html>")
    monkeypatch.setattr("skeleton.app.health._open_direct_health", lambda *_a, **_k: response)
    service = SimpleNamespace(name="frontend", public_url=_SETUP_URL[:-6], health_path="/setup")
    result = probe_local_setup(service)
    assert not result.ok


@pytest.mark.parametrize("url", [None, 123, "", "http://elsewhere.invalid/setup",
                                 "http://127.0.0.1:8080/login"])
def test_setup_requires_exact_observed_url_before_body(monkeypatch, url):
    from types import SimpleNamespace
    from skeleton.app.health import probe_local_setup
    response = _setup_response(200, url, ["text/html"], b"<!doctype html>")
    def forbidden(_size):
        pytest.fail("unadmitted response body was read")
    response.read = forbidden
    monkeypatch.setattr("skeleton.app.health._open_direct_health", lambda *_a, **_k: response)
    service = SimpleNamespace(name="frontend", public_url=_SETUP_URL[:-6], health_path="/setup")
    assert not probe_local_setup(service).ok


@pytest.mark.parametrize("headers,sample,expected", [
    (["text/html"], b"<!doctype html><html>", True),
    (["text/html; charset=utf-8"], b" \n<!DOCTYPE HTML>", True),
    ([], b"<!doctype html>", False),
    (["text/html", "application/json"], b"<!doctype html>", False),
    (["text/html", "text/html"], b"<!doctype html>", False),
    (["application/json"], b"<!doctype html>", False),
    (["text/html"], b"<!doctype html-not-a-document>", False),
    (["text/html"], b"<!doctype html", False),
    (["text/html"], "<!doctype html>", False),
    (["text/html"], b"<!doctype html>" + b"x" * 512, False),
])
def test_setup_requires_unambiguous_bounded_html(monkeypatch, headers, sample, expected):
    from types import SimpleNamespace
    from skeleton.app.health import probe_local_setup
    response = _setup_response(200, _SETUP_URL, headers, sample)
    monkeypatch.setattr("skeleton.app.health._open_direct_health", lambda *_a, **_k: response)
    service = SimpleNamespace(name="frontend", public_url=_SETUP_URL[:-6], health_path="/setup")
    assert probe_local_setup(service).ok is expected


def test_generic_liveness_does_not_wait_for_response_body(monkeypatch):
    response = _setup_response(200, _SETUP_URL, ["text/html"], b"")
    def forbidden(_size):
        pytest.fail("liveness unexpectedly waited for response body")
    response.read = forbidden
    monkeypatch.setattr("skeleton.app.health._open_direct_health", lambda *_a, **_k: response)
    assert probe_http("frontend", _SETUP_URL).ok


@pytest.mark.parametrize("code", [None, True, "302", 0, 600, 302, 503])
def test_http_error_response_is_closed_and_status_is_not_coerced(monkeypatch, code):
    from urllib.error import HTTPError
    class Error(HTTPError):
        closed_by_probe = False
        def close(self):
            self.closed_by_probe = True
    error = Error(_SETUP_URL, code, "private-message", {}, None)
    def fail(*_a, **_k):
        raise error
    monkeypatch.setattr("skeleton.app.health._open_direct_health", fail)
    result = probe_http("frontend", _SETUP_URL)
    assert not result.ok and error.closed_by_probe
    assert result.status == (code if type(code) is int and 100 <= code <= 599 else None)
    assert "private-message" not in repr(result.to_dict())


def test_setup_protocol_failure_is_redacted(monkeypatch):
    from http.client import IncompleteRead
    from types import SimpleNamespace
    from skeleton.app.health import probe_local_setup
    response = _setup_response(200, _SETUP_URL, ["text/html"], b"")
    def broken(_size):
        raise IncompleteRead(b"private-response-content", 100)
    response.read = broken
    monkeypatch.setattr("skeleton.app.health._open_direct_health", lambda *_a, **_k: response)
    service = SimpleNamespace(name="frontend", public_url=_SETUP_URL[:-6], health_path="/setup")
    result = probe_local_setup(service)
    assert not result.ok
    assert "private-response-content" not in repr(result.to_dict())



@pytest.mark.parametrize("boundary", ["before-first", "after-first", "before-aggregate"])
def test_admission_loss_drops_all_probe_evidence(monkeypatch,boundary):
    from skeleton.app import health
    calls=[]
    def admitted():
        if boundary=="before-first":
            return False
        if boundary=="after-first":
            return not calls
        return len(calls)<3
    def probe(service,*,timeout):
        calls.append(service.name)
        return health.ProbeResult(service.name,service.public_url,True,200,"fixture")
    def aggregate(*a,**k):
        pytest.fail("invalidated epoch reached aggregate health")
    monkeypatch.setattr(health,"probe_url",probe)
    monkeypatch.setattr(health,"probe_http",aggregate)
    result=health.probe_application(admit=admitted)
    assert result==()
    assert len(calls)=={"before-first":0,"after-first":1,"before-aggregate":3}[boundary]


def test_readiness_does_not_retry_after_epoch_rejection(monkeypatch):
    from skeleton.app import health
    calls=[]
    def probe(**kw):
        calls.append("round")
        assert kw["admit"]() is True
        calls.append("invalidated")
        assert kw["admit"]() is False
        calls.append("restored")
        assert kw["admit"]() is False
        return (health.ProbeResult("backend","http://localhost:8001",True,200,"fixture"),)
    monkeypatch.setattr(health,"probe_application",probe)
    monkeypatch.setattr(health.time,"sleep",lambda *a:pytest.fail("stale epoch retried"))
    assert health.wait_for_application(attempts=4,admit=lambda: "invalidated" not in calls or "restored" in calls)==()
    assert calls==["round","invalidated","restored"]


def test_admission_requires_exact_boolean_not_truthy_value(monkeypatch):
    from skeleton.app import health
    monkeypatch.setattr(health,"probe_url",lambda *a,**k:pytest.fail("truthy admission accepted"))
    assert health.probe_application(admit=lambda:1)==()



@pytest.mark.parametrize("fault",["none","missing","duplicate","extra","wrong_url","false","truthy","missing_status","redirect","bool_status","fake_row","wrong_full_profile"])
def test_readiness_requires_complete_exact_endpoint_evidence(fault):
    from dataclasses import replace
    from types import SimpleNamespace
    from skeleton.app.health import ProbeResult, probes_ok
    from skeleton.testing.app_health_fixtures import fixture_probes
    from skeleton.app.assembly import load_manifest
    manifest=load_manifest()
    rows=list(fixture_probes(manifest=manifest))
    assert {r.service:r.url for r in rows}=={
        "frontend":"http://localhost:3000/",
        "backend":"http://localhost:8001/api/health/ready",
        "skeleton":"http://localhost:8010/api/v1/health/live",
        "application":"http://localhost:8001/api/app/ready"}
    if fault=="missing":
        rows.pop()
    elif fault=="duplicate":
        rows[-1]=rows[0]
    elif fault=="extra":
        rows.append(ProbeResult("foreign","http://localhost:8099",True,200,"fixture"))
    elif fault=="wrong_url":
        rows[0]=replace(rows[0],url="http://localhost:9999/api/health/ready")
    elif fault=="false":
        rows[0]=replace(rows[0],ok=False)
    elif fault=="truthy":
        rows[0]=replace(rows[0],ok=1)
    elif fault=="missing_status":
        rows[0]=replace(rows[0],status=None)
    elif fault=="redirect":
        rows[0]=replace(rows[0],status=302)
    elif fault=="bool_status":
        rows[0]=replace(rows[0],status=True)
    elif fault=="fake_row":
        rows[0]=SimpleNamespace(**rows[0].to_dict())
    assert probes_ok(tuple(rows),manifest=manifest,full=fault=="wrong_full_profile") is (fault=="none")


def test_runtime_health_receipts_are_bound_to_custom_port_overrides():
    from skeleton.app.health import probes_ok
    from skeleton.testing.app_health_fixtures import fixture_probes
    ports={"frontend":"http://localhost:3400","backend":"http://localhost:8401"}
    rows=fixture_probes(public_url_overrides=ports)
    assert probes_ok(rows,public_url_overrides=ports)
    assert not probes_ok(rows)
    assert not probes_ok(rows,public_url_overrides={"frontend":"http://localhost:3500"})


@pytest.mark.parametrize("field",["timeout","delay"])
def test_large_integer_retry_budget_is_bounded_before_conversion(field):
    from skeleton.app.health import wait_for_application
    with pytest.raises(ValueError):
        wait_for_application(**{field:2**10000})


def test_partial_success_round_does_not_end_retry_campaign(monkeypatch):
    from skeleton.app import health
    from skeleton.testing.app_health_fixtures import fixture_probes
    calls=[]
    def probe(**kw):
        calls.append(1)
        rows=fixture_probes(**kw)
        return rows[:1] if len(calls)==1 else rows
    monkeypatch.setattr(health,"probe_application",probe)
    result=health.wait_for_application(attempts=2,delay=0)
    assert len(calls)==2 and health.probes_ok(result)
