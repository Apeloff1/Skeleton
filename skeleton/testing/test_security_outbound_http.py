from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import socket
from typing import AsyncIterator

import pytest

from skeleton.security.outbound_http import (
    OutboundHttpEvidenceError,
    OutboundHttpLimitError,
    OutboundHttpPolicy,
    OutboundHttpPolicyError,
    SafeAsyncHttpClient,
    TimeoutBudget,
    TransportRequest,
    TransportResponse,
)


def answer(address: str, port: int = 443):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sockaddr = (address, port, 0, 0) if family == socket.AF_INET6 else (address, port)
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)


def resolver_for(*addresses: str):
    def resolve(host: str, port: int, family: int, socktype: int, proto: int):
        assert host
        assert port > 0
        assert family == socket.AF_UNSPEC
        assert socktype == socket.SOCK_STREAM
        assert proto == socket.IPPROTO_TCP
        return [answer(address, port) for address in addresses]
    return resolve


async def chunks(*values: bytes) -> AsyncIterator[bytes]:
    for value in values:
        yield value


@dataclass
class Step:
    status: int = 200
    headers: tuple[tuple[str, str], ...] = ()
    body: tuple[bytes, ...] = (b"ok",)
    peer: str = "8.8.8.8"


class FakeTransport:
    def __init__(self, *steps: Step):
        self.steps = list(steps)
        self.requests: list[TransportRequest] = []

    async def request(self, request: TransportRequest) -> TransportResponse:
        self.requests.append(request)
        if not self.steps:
            raise AssertionError("unexpected request")
        step = self.steps.pop(0)
        return TransportResponse(
            status_code=step.status,
            headers=step.headers,
            body=chunks(*step.body),
            peer_address=step.peer,
        )


def run(coro):
    return asyncio.run(coro)


def client(
    transport: FakeTransport,
    *,
    policy: OutboundHttpPolicy | None = None,
    addresses: tuple[str, ...] = ("8.8.8.8",),
) -> SafeAsyncHttpClient:
    return SafeAsyncHttpClient(
        transport,
        policy=policy,
        resolver=resolver_for(*addresses),
    )


def test_get_requires_connected_peer_to_match_dns_snapshot() -> None:
    transport = FakeTransport(Step(peer="8.8.8.8"))
    response = run(client(transport).get("https://api.example.com/data"))
    assert response.status_code == 200
    assert response.body == b"ok"
    assert response.peer_address == "8.8.8.8"
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    "peer",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "::1",
        "fe80::1",
        "9.9.9.9",
    ],
)
def test_peer_mismatch_or_private_peer_fails_before_body(peer: str) -> None:
    transport = FakeTransport(Step(peer=peer, body=(b"SECRET_BODY",)))
    with pytest.raises(OutboundHttpEvidenceError, match="peer"):
        run(client(transport).get("https://api.example.com/data"))


def test_mixed_public_private_dns_evidence_is_rejected_before_transport() -> None:
    transport = FakeTransport(Step())
    unsafe = client(
        transport,
        addresses=("8.8.8.8", "10.0.0.1"),
    )
    with pytest.raises(OutboundHttpPolicyError, match="destination"):
        run(unsafe.get("https://api.example.com/data"))
    assert transport.requests == []


@pytest.mark.parametrize(
    "url",
    [
        "http://api.example.com/",
        "https://localhost/",
        "https://metadata.google.internal/latest",
        "https://169.254.169.254/latest",
        "https://10.0.0.1/",
        "https://127.0.0.1/",
        "https://[::1]/",
        "https://user:password@api.example.com/",
        " https://api.example.com/",
        "https://api.example.com/ ",
    ],
)
def test_unsafe_url_is_rejected_before_transport(url: str) -> None:
    transport = FakeTransport(Step())
    with pytest.raises(OutboundHttpPolicyError):
        run(client(transport).get(url))
    assert transport.requests == []


def test_safe_relative_redirect_is_revalidated_and_followed() -> None:
    transport = FakeTransport(
        Step(
            status=302,
            headers=(("Location", "/next?cursor=1"),),
            body=(b"ignored",),
        ),
        Step(status=200, body=(b"final",)),
    )
    response = run(client(transport).get("https://api.example.com/start"))
    assert response.body == b"final"
    assert response.redirects == 1
    assert len(transport.requests) == 2
    assert transport.requests[1].destination.url == "https://api.example.com/next?cursor=1"


def test_same_origin_absolute_redirect_is_allowed() -> None:
    transport = FakeTransport(
        Step(status=301, headers=(("location", "https://api.example.com/next"),)),
        Step(body=(b"final",)),
    )
    response = run(client(transport).get("https://api.example.com/start"))
    assert response.url == "https://api.example.com/next"


@pytest.mark.parametrize(
    "target",
    [
        "http://api.example.com/next",
        "https://other.example.com/next",
        "https://api.example.com:444/next",
        "https://127.0.0.1/next",
        "https://169.254.169.254/latest",
        "https://user:pass@api.example.com/next",
    ],
)
def test_redirect_cannot_change_security_boundary_by_default(target: str) -> None:
    transport = FakeTransport(
        Step(status=302, headers=(("location", target),)),
    )
    with pytest.raises((OutboundHttpPolicyError, OutboundHttpEvidenceError, ValueError)):
        run(client(transport).get("https://api.example.com/start"))
    assert len(transport.requests) == 1


def test_cross_origin_redirect_can_be_explicitly_enabled_but_is_reresolved() -> None:
    transport = FakeTransport(
        Step(status=302, headers=(("location", "https://cdn.example.com/next"),)),
        Step(status=200, body=(b"cdn",)),
    )
    policy = OutboundHttpPolicy(allow_cross_origin_redirects=True)
    response = run(client(transport, policy=policy).get("https://api.example.com/start"))
    assert response.body == b"cdn"
    assert len(transport.requests) == 2
    assert transport.requests[1].destination.host == "cdn.example.com"


def test_same_origin_redirect_preserves_caller_headers() -> None:
    transport = FakeTransport(
        Step(status=302, headers=(("location", "/next"),)),
        Step(status=200),
    )
    run(
        client(transport).get(
            "https://api.example.com/start",
            headers=(("Authorization", "Bearer secret"), ("X-Api-Key", "opaque")),
        )
    )
    assert transport.requests[1].headers == (
        ("authorization", "Bearer secret"),
        ("x-api-key", "opaque"),
    )


def test_cross_origin_redirect_drops_all_caller_headers() -> None:
    transport = FakeTransport(
        Step(status=302, headers=(("location", "https://cdn.example.com/next"),)),
        Step(status=200),
    )
    policy = OutboundHttpPolicy(allow_cross_origin_redirects=True)
    run(
        client(transport, policy=policy).get(
            "https://api.example.com/start",
            headers=(
                ("Authorization", "Bearer secret"),
                ("Cookie", "session=secret"),
                ("X-Api-Key", "opaque"),
            ),
        )
    )
    assert transport.requests[0].headers
    assert transport.requests[1].headers == ()


def test_redirect_without_location_fails_closed() -> None:
    transport = FakeTransport(Step(status=302))
    with pytest.raises(OutboundHttpEvidenceError, match="Location"):
        run(client(transport).get("https://api.example.com/start"))


def test_redirect_bound_is_enforced() -> None:
    transport = FakeTransport(
        Step(status=302, headers=(("location", "/1"),)),
        Step(status=302, headers=(("location", "/2"),)),
    )
    policy = OutboundHttpPolicy(max_redirects=1)
    with pytest.raises(OutboundHttpLimitError, match="redirect"):
        run(client(transport, policy=policy).get("https://api.example.com/start"))


def test_zero_redirect_policy_rejects_first_redirect() -> None:
    transport = FakeTransport(Step(status=302, headers=(("location", "/1"),)))
    with pytest.raises(OutboundHttpLimitError):
        run(
            client(
                transport,
                policy=OutboundHttpPolicy(max_redirects=0),
            ).get("https://api.example.com/start")
        )


def test_declared_body_size_is_bounded_before_streaming() -> None:
    transport = FakeTransport(
        Step(
            headers=(("content-length", "5"),),
            body=(b"12345",),
        )
    )
    policy = OutboundHttpPolicy(max_response_bytes=4)
    with pytest.raises(OutboundHttpLimitError, match="declared"):
        run(client(transport, policy=policy).get("https://api.example.com/data"))


def test_streamed_body_size_is_bounded_without_content_length() -> None:
    transport = FakeTransport(Step(body=(b"12", b"34", b"5")))
    policy = OutboundHttpPolicy(max_response_bytes=4)
    with pytest.raises(OutboundHttpLimitError, match="streamed"):
        run(client(transport, policy=policy).get("https://api.example.com/data"))


def test_content_length_must_match_streamed_body() -> None:
    transport = FakeTransport(
        Step(headers=(("content-length", "4"),), body=(b"abc",))
    )
    with pytest.raises(OutboundHttpEvidenceError, match="differs"):
        run(client(transport).get("https://api.example.com/data"))


@pytest.mark.parametrize("value", ["-1", "+1", "1.5", "NaN", "1 2", ""])
def test_malformed_content_length_fails_closed(value: str) -> None:
    transport = FakeTransport(
        Step(headers=(("content-length", value),), body=(b"x",))
    )
    with pytest.raises(OutboundHttpEvidenceError, match="Content-Length"):
        run(client(transport).get("https://api.example.com/data"))


def test_response_chunk_count_is_bounded() -> None:
    transport = FakeTransport(Step(body=(b"a", b"b", b"c")))
    policy = OutboundHttpPolicy(max_response_chunks=2)
    with pytest.raises(OutboundHttpLimitError, match="chunk-count"):
        run(client(transport, policy=policy).get("https://api.example.com/data"))


def test_non_bytes_body_chunk_is_rejected() -> None:
    async def malformed():
        yield "not-bytes"

    class BadTransport:
        async def request(self, request: TransportRequest):
            return TransportResponse(200, (), malformed(), "8.8.8.8")

    unsafe = SafeAsyncHttpClient(
        BadTransport(),
        resolver=resolver_for("8.8.8.8"),
    )
    with pytest.raises(OutboundHttpEvidenceError, match="non-bytes"):
        run(unsafe.get("https://api.example.com/data"))


def test_body_iterator_exception_is_redacted() -> None:
    secret = "SIGNED_URL_SECRET"

    async def broken():
        yield b"ok"
        raise RuntimeError(secret)

    class BadTransport:
        async def request(self, request: TransportRequest):
            return TransportResponse(200, (), broken(), "8.8.8.8")

    unsafe = SafeAsyncHttpClient(
        BadTransport(),
        resolver=resolver_for("8.8.8.8"),
    )
    with pytest.raises(OutboundHttpEvidenceError) as caught:
        run(unsafe.get("https://api.example.com/data"))
    assert secret not in str(caught.value)


def test_transport_exception_is_redacted() -> None:
    secret = "TOKEN_IN_EXCEPTION"

    class BadTransport:
        async def request(self, request: TransportRequest):
            raise RuntimeError(secret)

    unsafe = SafeAsyncHttpClient(
        BadTransport(),
        resolver=resolver_for("8.8.8.8"),
    )
    with pytest.raises(OutboundHttpEvidenceError) as caught:
        run(unsafe.get("https://api.example.com/data"))
    assert secret not in str(caught.value)


@pytest.mark.parametrize("status", [0, 99, 600, 999, True, "200"])
def test_status_code_evidence_is_validated(status: object) -> None:
    class BadTransport:
        async def request(self, request: TransportRequest):
            return TransportResponse(
                status,  # type: ignore[arg-type]
                (),
                chunks(b"ok"),
                "8.8.8.8",
            )

    unsafe = SafeAsyncHttpClient(BadTransport(), resolver=resolver_for("8.8.8.8"))
    with pytest.raises(OutboundHttpEvidenceError, match="status"):
        run(unsafe.get("https://api.example.com/data"))


def test_request_method_is_allowlisted() -> None:
    transport = FakeTransport(Step())
    with pytest.raises(OutboundHttpPolicyError, match="method"):
        run(client(transport).request("POST", "https://api.example.com/data"))
    assert transport.requests == []


def test_custom_method_allowlist_is_respected() -> None:
    transport = FakeTransport(Step())
    policy = OutboundHttpPolicy(allowed_methods=("POST",))
    response = run(
        client(transport, policy=policy).request(
            "POST",
            "https://api.example.com/data",
        )
    )
    assert response.status_code == 200


@pytest.mark.parametrize("method", ["", "G ET", "G\nET", "1", "get "])
def test_invalid_method_syntax_is_rejected(method: str) -> None:
    transport = FakeTransport(Step())
    with pytest.raises(ValueError):
        run(client(transport).request(method, "https://api.example.com/data"))
    assert transport.requests == []


@pytest.mark.parametrize(
    "name",
    ["host", "Host", "content-length", "transfer-encoding", "connection"],
)
def test_transport_owned_request_headers_are_forbidden(name: str) -> None:
    transport = FakeTransport(Step())
    with pytest.raises(OutboundHttpPolicyError, match="transport-owned"):
        run(
            client(transport).get(
                "https://api.example.com/data",
                headers=((name, "value"),),
            )
        )


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("bad header", "x"),
        ("x\nname", "x"),
        ("x-name", "line\nbreak"),
        ("x-name", "nul\x00value"),
    ],
)
def test_request_header_injection_is_rejected(name: str, value: str) -> None:
    transport = FakeTransport(Step())
    with pytest.raises((OutboundHttpEvidenceError, OutboundHttpPolicyError)):
        run(
            client(transport).get(
                "https://api.example.com/data",
                headers=((name, value),),
            )
        )


def test_request_headers_are_normalized_for_transport() -> None:
    transport = FakeTransport(Step())
    run(
        client(transport).get(
            "https://api.example.com/data",
            headers=(("X-Trace-ID", "abc"),),
        )
    )
    assert transport.requests[0].headers == (("x-trace-id", "abc"),)


def test_response_header_count_is_bounded() -> None:
    transport = FakeTransport(
        Step(headers=(("x-a", "1"), ("x-b", "2"), ("x-c", "3")))
    )
    policy = OutboundHttpPolicy(max_header_count=2)
    with pytest.raises(OutboundHttpLimitError, match="count"):
        run(client(transport, policy=policy).get("https://api.example.com/data"))


def test_response_header_name_size_is_bounded() -> None:
    transport = FakeTransport(Step(headers=(("x-long-name", "1"),)))
    policy = OutboundHttpPolicy(max_header_name_bytes=5)
    with pytest.raises(OutboundHttpLimitError, match="name"):
        run(client(transport, policy=policy).get("https://api.example.com/data"))


def test_response_header_value_size_is_bounded() -> None:
    transport = FakeTransport(Step(headers=(("x", "12345"),)))
    policy = OutboundHttpPolicy(max_header_value_bytes=4)
    with pytest.raises(OutboundHttpLimitError, match="value"):
        run(client(transport, policy=policy).get("https://api.example.com/data"))


def test_total_header_bytes_are_bounded() -> None:
    transport = FakeTransport(Step(headers=(("x-a", "1234"), ("x-b", "5678"))))
    policy = OutboundHttpPolicy(max_total_header_bytes=12)
    with pytest.raises(OutboundHttpLimitError, match="total"):
        run(client(transport, policy=policy).get("https://api.example.com/data"))


def test_duplicate_content_length_is_rejected() -> None:
    transport = FakeTransport(
        Step(
            headers=(("content-length", "2"), ("Content-Length", "2")),
            body=(b"ok",),
        )
    )
    with pytest.raises(OutboundHttpEvidenceError, match="duplicate"):
        run(client(transport).get("https://api.example.com/data"))


def test_duplicate_location_is_rejected() -> None:
    transport = FakeTransport(
        Step(
            status=302,
            headers=(("location", "/a"), ("Location", "/b")),
        )
    )
    with pytest.raises(OutboundHttpEvidenceError, match="duplicate"):
        run(client(transport).get("https://api.example.com/data"))


def test_content_type_allowlist_accepts_parameters() -> None:
    transport = FakeTransport(
        Step(
            headers=(("content-type", "application/json; charset=utf-8"),),
            body=(b"{}",),
        )
    )
    policy = OutboundHttpPolicy(accepted_content_types=("application/json",))
    response = run(client(transport, policy=policy).get("https://api.example.com/data"))
    assert response.json() == {}


def test_content_type_allowlist_rejects_missing_type() -> None:
    transport = FakeTransport(Step(body=(b"{}",)))
    policy = OutboundHttpPolicy(accepted_content_types=("application/json",))
    with pytest.raises(OutboundHttpPolicyError, match="Content-Type"):
        run(client(transport, policy=policy).get("https://api.example.com/data"))


def test_content_type_allowlist_rejects_wrong_type() -> None:
    transport = FakeTransport(
        Step(headers=(("content-type", "text/html"),), body=(b"<html>",))
    )
    policy = OutboundHttpPolicy(accepted_content_types=("application/json",))
    with pytest.raises(OutboundHttpPolicyError, match="not permitted"):
        run(client(transport, policy=policy).get("https://api.example.com/data"))


def test_response_text_decodes_explicit_encoding() -> None:
    transport = FakeTransport(Step(body=("café".encode("utf-8"),)))
    response = run(client(transport).get("https://api.example.com/data"))
    assert response.text() == "café"


def test_response_text_decode_failure_is_generic() -> None:
    transport = FakeTransport(Step(body=(b"\xff",)))
    response = run(client(transport).get("https://api.example.com/data"))
    with pytest.raises(OutboundHttpEvidenceError, match="decoding"):
        response.text()


def test_response_json_parses_bounded_body() -> None:
    payload = json.dumps({"ok": True, "n": 3}).encode()
    transport = FakeTransport(Step(body=(payload,)))
    response = run(client(transport).get("https://api.example.com/data"))
    assert response.json() == {"ok": True, "n": 3}


def test_response_json_failure_does_not_echo_body() -> None:
    secret = "SECRET_RESPONSE_BODY"
    transport = FakeTransport(Step(body=(secret.encode(),)))
    response = run(client(transport).get("https://api.example.com/data"))
    with pytest.raises(OutboundHttpEvidenceError) as caught:
        response.json()
    assert secret not in str(caught.value)


def test_response_header_helper_is_case_insensitive() -> None:
    transport = FakeTransport(Step(headers=(("X-Trace", "abc"),)))
    response = run(client(transport).get("https://api.example.com/data"))
    assert response.header("x-trace") == "abc"
    assert response.header("missing") is None


def test_head_request_is_supported_by_default() -> None:
    transport = FakeTransport(Step(body=()))
    response = run(client(transport).head("https://api.example.com/data"))
    assert response.body == b""
    assert transport.requests[0].method == "HEAD"


def test_timeout_budget_is_forwarded_immutably() -> None:
    transport = FakeTransport(Step())
    timeout = TimeoutBudget(connect_seconds=1, read_seconds=2, total_seconds=3)
    policy = OutboundHttpPolicy(timeout=timeout)
    run(client(transport, policy=policy).get("https://api.example.com/data"))
    assert transport.requests[0].timeout == timeout


@pytest.mark.parametrize(
    "kwargs",
    [
        {"connect_seconds": 0},
        {"connect_seconds": -1},
        {"connect_seconds": float("inf")},
        {"connect_seconds": True},
        {"read_seconds": 0},
        {"total_seconds": 0},
    ],
)
def test_timeout_budget_rejects_invalid_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        TimeoutBudget(**kwargs)  # type: ignore[arg-type]


def test_timeout_components_cannot_exceed_total() -> None:
    with pytest.raises(ValueError):
        TimeoutBudget(connect_seconds=5, read_seconds=1, total_seconds=4)
    with pytest.raises(ValueError):
        TimeoutBudget(connect_seconds=1, read_seconds=5, total_seconds=4)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_response_bytes": 0},
        {"max_response_chunks": 0},
        {"max_header_count": 0},
        {"max_header_name_bytes": 0},
        {"max_header_value_bytes": 0},
        {"max_total_header_bytes": 0},
        {"max_redirects": -1},
        {"max_redirects": 17},
        {"max_redirects": True},
        {"allow_cross_origin_redirects": "false"},
        {"allow_cross_origin_redirects": 1},
        {"allowed_methods": ()},
        {"allowed_methods": ("GET", "GET")},
        {"accepted_content_types": ("application/json", "application/json")},
    ],
)
def test_http_policy_rejects_invalid_limits(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        OutboundHttpPolicy(**kwargs)  # type: ignore[arg-type]


def test_client_requires_transport() -> None:
    with pytest.raises(TypeError):
        SafeAsyncHttpClient(None, resolver=resolver_for("8.8.8.8"))  # type: ignore[arg-type]


def test_client_requires_resolver() -> None:
    with pytest.raises(TypeError):
        SafeAsyncHttpClient(FakeTransport(Step()), resolver=None)  # type: ignore[arg-type]


def test_dns_resolution_exception_is_redacted() -> None:
    secret = "SECRET_RESOLVER_DETAIL"

    def broken(*_args):
        raise OSError(secret)

    transport = FakeTransport(Step())
    unsafe = SafeAsyncHttpClient(transport, resolver=broken)
    with pytest.raises(OutboundHttpPolicyError) as caught:
        run(unsafe.get("https://api.example.com/data"))
    assert secret not in str(caught.value)
    assert transport.requests == []


def test_connected_peer_error_does_not_echo_peer_payload() -> None:
    secret = "SECRET_PEER"
    transport = FakeTransport(Step(peer=secret))
    with pytest.raises(OutboundHttpEvidenceError) as caught:
        run(client(transport).get("https://api.example.com/data"))
    assert secret not in str(caught.value)


def test_malformed_response_header_evidence_is_rejected() -> None:
    class BadTransport:
        async def request(self, request: TransportRequest):
            return TransportResponse(
                200,
                [("good", "x"), ("bad",)],  # type: ignore[list-item]
                chunks(b"ok"),
                "8.8.8.8",
            )

    unsafe = SafeAsyncHttpClient(BadTransport(), resolver=resolver_for("8.8.8.8"))
    with pytest.raises(OutboundHttpEvidenceError, match="malformed"):
        run(unsafe.get("https://api.example.com/data"))


def test_body_is_not_consumed_when_peer_evidence_fails() -> None:
    consumed = False

    async def guarded():
        nonlocal consumed
        consumed = True
        yield b"secret"

    class BadTransport:
        async def request(self, request: TransportRequest):
            return TransportResponse(200, (), guarded(), "127.0.0.1")

    unsafe = SafeAsyncHttpClient(BadTransport(), resolver=resolver_for("8.8.8.8"))
    with pytest.raises(OutboundHttpEvidenceError):
        run(unsafe.get("https://api.example.com/data"))
    assert consumed is False


def test_redirect_body_is_not_consumed() -> None:
    consumed = False

    async def guarded_redirect_body():
        nonlocal consumed
        consumed = True
        yield b"redirect body"

    class RedirectTransport:
        def __init__(self):
            self.count = 0

        async def request(self, request: TransportRequest):
            self.count += 1
            if self.count == 1:
                return TransportResponse(
                    302,
                    (("location", "/next"),),
                    guarded_redirect_body(),
                    "8.8.8.8",
                )
            return TransportResponse(200, (), chunks(b"ok"), "8.8.8.8")

    transport = RedirectTransport()
    unsafe = SafeAsyncHttpClient(transport, resolver=resolver_for("8.8.8.8"))
    response = run(unsafe.get("https://api.example.com/start"))
    assert response.body == b"ok"
    assert consumed is False


def test_request_preserves_query_without_logging_or_rewriting() -> None:
    transport = FakeTransport(Step())
    url = "https://api.example.com/data?token=signed-value&cursor=1"
    response = run(client(transport).get(url))
    assert response.url == url
    assert transport.requests[0].destination.url == url


def test_multiple_approved_addresses_accept_either_actual_peer() -> None:
    transport = FakeTransport(Step(peer="1.1.1.1"))
    response = run(
        client(
            transport,
            addresses=("8.8.8.8", "1.1.1.1"),
        ).get("https://api.example.com/data")
    )
    assert response.peer_address == "1.1.1.1"


def test_transport_request_carries_resolution_snapshot() -> None:
    transport = FakeTransport(Step(peer="1.1.1.1"))
    run(
        client(
            transport,
            addresses=("8.8.8.8", "1.1.1.1"),
        ).get("https://api.example.com/data")
    )
    snapshot = transport.requests[0].destination
    assert snapshot.addresses == ("1.1.1.1", "8.8.8.8")
    assert snapshot.host == "api.example.com"
    assert snapshot.port == 443
