"""Security regressions for API-gateway failure sanitization."""
from __future__ import annotations

from skeleton.api.gateway import APIGateway, GatewayRequest


_PRIVATE_DETAIL = "private-detail-must-not-leak-7f31"


class _RecordingLogger:
    def __init__(self) -> None:
        self.events: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def info(self, *args: object, **kwargs: object) -> None:
        self.events.append((args, kwargs))


def test_handler_exception_detail_is_redacted_from_response_and_logs() -> None:
    logger = _RecordingLogger()
    gateway = APIGateway(logger=logger)

    def explode(_payload):
        raise RuntimeError(_PRIVATE_DETAIL)

    gateway.route("/explode", explode)
    response = gateway.handle(GatewayRequest("/explode", actor="test-actor"))

    assert response.status == 500
    assert response.body == {"error": "internal server error"}
    assert _PRIVATE_DETAIL not in repr(response.body)
    assert _PRIVATE_DETAIL not in repr(logger.events)
    assert gateway.card()["routes"]["/explode"]["errors"] == 1


def test_transform_exception_detail_is_redacted() -> None:
    gateway = APIGateway()
    gateway.route("/transform", lambda _payload: {"ok": True})

    def explode_transform(_body):
        raise ValueError(_PRIVATE_DETAIL)

    gateway.add_transform(explode_transform)
    response = gateway.handle(GatewayRequest("/transform"))

    assert response.status == 500
    assert response.body == {"error": "internal server error"}
    assert _PRIVATE_DETAIL not in repr(response.body)
    assert gateway.card()["routes"]["/transform"]["errors"] == 1
