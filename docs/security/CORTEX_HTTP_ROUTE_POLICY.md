# Cortex HTTP route custody

**Decision (2026-10-16): keep legacy cortex routes unmounted.**

The historical `skeleton/api/cortex_routes.py` defines 52 endpoints using
`register_routes(app, deck)`, including read/write/rotation of secrets under
`/api/v1/secrets`. These endpoints were not designed for the canonical route
charter and HMAC/seal enforcement. A passing route inventory does **not**
authorize exposing them over HTTP.

The canonical `skeleton.api.server.create_app` uses its separately registered
routers and must **not** invoke `cortex_routes.register_routes`. The factory
now calls `reject_cortex_secret_routes(app)` after registering all declared
routes; registration of `/api/v1/secrets` or descendants fails app creation
rather than silently leaking stored secrets. Percent-encoded and case aliases
are included in the guard. The existing `/cortex/status` read-only route
remains available under its separate policy.

```bash
python -m pytest -q skeleton/testing/test_cortex_secret_route_guard.py \
  skeleton/testing/test_cortex_route_audit_snapshot.py
python -m skeleton capabilities --cortex-audit
```

**Promotion requirements:** a future read-only cortex API needs a separate
charter review, authenticated and audited handlers, explicit least-privilege
response schemas, and regression tests for unauthorized access. Secret values
and mutations are **never** authorized through these historical HTTP routes.
A new chartered endpoint must not reuse the forbidden `/api/v1/secrets`
namespace without deliberate policy revision. This guard is defense in depth:
other authorization, secret redaction and deployed ingress boundaries remain
mandatory.

This document does not claim deployed or end-to-end qualification; required
source-head CI and a real installed product audit must still pass.
