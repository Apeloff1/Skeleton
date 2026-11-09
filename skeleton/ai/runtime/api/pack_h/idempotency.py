"""``Idempotency-Key`` handling for Pack H write endpoints.

Usage inside a route::

    return run_idempotent(store, scope=f"{tenant}:records.create", key=key,
                          method="POST", path=path, body=payload,
                          handler=lambda: (201, record.as_dict()))

Semantics (aligned with the IETF httpapi idempotency-key draft):

* missing key on a route that requires one -> 400 ``idempotency_key_required``
* malformed key -> 400 ``idempotency_key_invalid``
* key reused with a different payload -> 422 ``idempotency_key_mismatch``
* same key still executing -> 409 ``idempotency_in_flight`` + ``Retry-After``
* completed key -> stored response replayed with ``Idempotent-Replayed: true``

Only 2xx and 4xx (except 409/429) responses are stored; 5xx and handler
exceptions release the key so the client can retry.
"""

from __future__ import annotations

import json
import math
from typing import Any, Callable, Optional, Tuple

from starlette.responses import Response

from skeleton.persistence.pack_h.idempotency_store import (
    IdempotencyStore,
    InvalidKey,
    Outcome,
    fingerprint,
    validate_key,
)

HEADER = "Idempotency-Key"
REPLAYED_HEADER = "Idempotent-Replayed"

HandlerResult = Tuple[int, Any]


def _json(status: int, body: Any, headers: Optional[dict] = None) -> Response:
    return Response(
        content=json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8"),
        status_code=status,
        media_type="application/json",
        headers=headers or {},
    )


def _storable(status: int) -> bool:
    return 200 <= status < 300 or (400 <= status < 500 and status not in (409, 429))


def run_idempotent(
    store: IdempotencyStore,
    *,
    scope: str,
    key: Optional[str],
    method: str,
    path: str,
    body: Any,
    handler: Callable[[], HandlerResult],
    required: bool = True,
) -> Response:
    if key is None:
        if required:
            return _json(400, {"error": "idempotency_key_required", "header": HEADER})
        status, payload = handler()
        return _json(status, payload)
    try:
        validate_key(key)
    except InvalidKey as exc:
        return _json(400, {"error": "idempotency_key_invalid", "detail": str(exc)})

    fp = fingerprint(method, path, body)
    begun = store.begin(scope, key, fp)
    if begun.outcome is Outcome.MISMATCH:
        return _json(422, {"error": "idempotency_key_mismatch"})
    if begun.outcome is Outcome.IN_FLIGHT:
        retry = max(1, math.ceil(begun.retry_after_s))
        return _json(409, {"error": "idempotency_in_flight", "retry_after_s": begun.retry_after_s},
                     {"Retry-After": str(retry)})
    if begun.outcome is Outcome.REPLAY:
        assert begun.response is not None
        headers = dict(begun.response.headers)
        headers[REPLAYED_HEADER] = "true"
        return Response(content=begun.response.body, status_code=begun.response.status_code,
                        media_type="application/json", headers=headers)

    assert begun.owner is not None
    try:
        status, payload = handler()
    except BaseException:
        store.abandon(scope, key, begun.owner)
        raise
    resp = _json(status, payload)
    if _storable(status):
        store.complete(scope, key, begun.owner, status_code=status, body=bytes(resp.body),
                       headers={"content-type": "application/json"})
    else:
        store.abandon(scope, key, begun.owner)
    return resp
